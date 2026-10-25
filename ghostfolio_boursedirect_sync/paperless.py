"""Read originals only; paperless-ngx 2b00cf6 filters.py and DownloadView.

Pagination reuses the configured URL. Response URLs never receive tokens.
"""

import json

import requests

from ghostfolio_boursedirect_sync.models import Settings


def get(settings: Settings, path: str, params: dict[str, str | int]) -> requests.Response:
    try:
        response = requests.get(
            f"{settings.paperless_url}{path}", params=params,
            headers={"Authorization": f"Token {settings.paperless_token}"},
            timeout=(10, 120), allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError("paperless_unreachable") from None
    if response.status_code in (401, 403):
        raise RuntimeError(f"paperless_auth_failed HTTP {response.status_code}")
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"paperless_unreachable HTTP {response.status_code}")
    return response


def document_ids(settings: Settings) -> list[int]:
    """Return labelled documents and reject unlabelled BourseDirect files.

    The second query is a read-only safety check. It catches a file that keeps
    the BillCollector filename but lost the Paperless Source field.
    """
    source_ids = _document_ids(settings, {
        "custom_field_query": json.dumps(["Source", "exact", "Bourse Direct"]),
    })
    filename_ids = _document_ids(settings, {
        "original_file_name__istartswith": "BourseDirect_",
    })
    if set(filename_ids).difference(source_ids):
        raise RuntimeError("source_field_missing")
    return source_ids


def _document_ids(settings: Settings, filters: dict[str, str]) -> list[int]:
    """Read every page for one Paperless filter with stable count evidence."""
    ids: list[int] = []
    page = 1
    expected_count: int | None = None
    while True:
        response = get(settings, "/api/documents/", {**filters, "page": page})
        try:
            body: object = response.json()
        except ValueError:
            raise RuntimeError("paperless_unreachable") from None
        if not isinstance(body, dict):
            raise RuntimeError("paperless_unreachable")
        count, rows, next_page = body.get("count"), body.get("results"), body.get("next")
        if (type(count) is not int or count < 0 or not isinstance(rows, list)
                or "next" not in body or (next_page is not None and not isinstance(next_page, str))):
            raise RuntimeError("paperless_unreachable")
        if expected_count is None:
            expected_count = count
        if count != expected_count:
            raise RuntimeError("paperless_unreachable")
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int:
                raise RuntimeError("paperless_unreachable")
            document_id = row["id"]
            if document_id <= 0 or document_id in ids:
                raise RuntimeError("paperless_unreachable")
            ids.append(document_id)
        if len(ids) > count:
            raise RuntimeError("paperless_unreachable")
        if next_page is None:
            if len(ids) != count:
                raise RuntimeError("paperless_unreachable")
            return ids
        if not rows or len(ids) >= count:
            raise RuntimeError("paperless_unreachable")
        page += 1


def original_pdf(settings: Settings, document_id: int) -> bytes:
    if document_id <= 0:
        raise RuntimeError("paperless_unreachable")
    return get(settings, f"/api/documents/{document_id}/download/", {"original": "true"}).content
