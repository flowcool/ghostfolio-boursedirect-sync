"""Run the installed candidate on captured originals and an isolated real lab.

Only Paperless reads use saved responses. Ghostfolio authentication, selection,
imports and confirmation use the real lab API. No host package is mounted.
Run from the candidate container on a reserved lab network, with lab credentials.
"""

import argparse
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import requests

from ghostfolio_boursedirect_sync import app, config, ghostfolio


def same_fields(actual, expected):
    for key, value in expected.items():
        if key == "accountId":
            continue
        if key in ("quantity", "unitPrice", "fee"):
            if Decimal(str(actual[key])) != Decimal(str(value)):
                return False
        elif key == "date":
            if ghostfolio.activity_instant(actual[key]) != ghostfolio.activity_instant(value):
                return False
        elif actual.get(key) != value:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--phase", choices=("preview", "apply", "repeat"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if (os.environ.get("GHOST_HOST") != "http://ghostfolio:3333"
            or os.environ.get("PAPERLESS_URL") != "http://paperless.invalid"
            or os.environ.get("IMPORT_CREATE_FROM") != "2026-10-01"
            or os.environ.get("DRY_RUN") != ("1" if args.phase == "preview" else "0")
            or os.environ.get("ACTIVITY_REVIEW_FILE") or os.environ.get("CRON")
            or os.environ.get("NOTICE_COVERAGE", "0") != "0"
            or os.environ.get("APPRISE_URLS") != "[]"):
        raise RuntimeError("Use isolated cut-off lab settings")
    manifest = json.loads((args.capture / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if Path(name).name != name or hashlib.sha256((args.capture / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("Captured input changed")
    paper = json.loads((args.capture / "paperless.json").read_text())
    expected = json.loads(args.expected.read_text())
    allowed = expected["preview"]
    if len(allowed) != 2 or len(paper["source_ids"]) != 75:
        raise RuntimeError("Use the reviewed two-BUY, 75-original proof")
    writes = []
    native = requests.sessions.Session.request

    def request(session, method, url, **kwargs):
        parsed = urlsplit(url)
        method = method.upper()
        if parsed.scheme != "http" or parsed.query or parsed.fragment or parsed.username:
            raise RuntimeError("Non-lab request refused")
        if parsed.netloc == "paperless.invalid" and method == "GET":
            parts = parsed.path.strip("/").split("/")
            if parts == ["api", "documents"]:
                params = kwargs.get("params", {})
                if params.get("page") != 1 or "tags__id__all" in params:
                    raise RuntimeError("Unexpected source page or tag query")
                data = {"count": 75, "next": None, "results": [{"id": i} for i in paper["source_ids"]]}
                content = json.dumps(data).encode()
            elif len(parts) in (3, 4) and parts[:2] == ["api", "documents"]:
                document = paper["documents"][parts[2]]
                if len(parts) == 4 and parts[3] == "download":
                    content = (args.capture / f"original-{document['id']}.pdf").read_bytes()
                    if hashlib.sha256(content).hexdigest() != document["sha256"]:
                        raise RuntimeError("Original changed")
                elif len(parts) == 3:
                    content = json.dumps(document["metadata"]).encode()
                else:
                    raise RuntimeError("Unexpected source route")
            elif parts == ["api", "tags"]:
                # This captured source has no done tags.
                data = {"count": 0, "next": None, "results": []}
                content = json.dumps(data).encode()
            else:
                raise RuntimeError("Unexpected source route")
            response = requests.Response()
            response.status_code = 200
            response._content = content
            return response
        if parsed.netloc != "ghostfolio:3333":
            raise RuntimeError("Non-lab request refused")
        if method == "POST" and parsed.path == "/api/v1/import":
            if args.phase != "apply":
                raise RuntimeError("Financial write outside apply phase")
            rows = json.loads(kwargs["data"], parse_float=Decimal)["activities"]
            if len(rows) != 1:
                raise RuntimeError("Require native one-row writes")
            row = rows[0]
            matches = [a for a in allowed if same_fields(row, a)]
            if len(matches) != 1 or row["comment"] in writes or row["accountId"] != account:
                raise RuntimeError("Unexpected or repeated financial request")
            writes.append(row["comment"])
        elif method != "GET" and not (method == "POST" and parsed.path == "/api/v1/auth/anonymous"):
            raise RuntimeError("Unreviewed lab mutation refused")
        return native(session, method, url, **kwargs)

    requests.sessions.Session.request = request
    settings = config.load()
    token = ghostfolio.exchange_token(settings)
    account = ghostfolio.find_account(settings, token)
    before = ghostfolio.read_activities(settings, token)
    code = app.main()
    after = ghostfolio.read_activities(settings, token)
    before_rows = {row["id"]: row for row in before.raw_rows}
    after_rows = {row["id"]: row for row in after.raw_rows}
    if code or any(after_rows.get(key) != row for key, row in before_rows.items()):
        raise RuntimeError("Cycle failed or existing activities changed")
    additions = [row for key, row in after_rows.items() if key not in before_rows]
    if len(additions) != (2 if args.phase == "apply" else 0):
        raise RuntimeError("Unexpected addition count")
    for item in allowed:
        matches = [row for row in after.rows if row.account_id == account and row.comment == item["comment"]]
        if args.phase in ("apply", "repeat"):
            if len(matches) != 1:
                raise RuntimeError("Missing exact readback")
            row = matches[0]
            actual = {"date": row.date.isoformat(), "type": row.type, "symbol": row.symbol,
                      "quantity": row.quantity, "unitPrice": row.unit_price, "fee": row.fee,
                      "comment": row.comment, "currency": row.currency, "dataSource": row.data_source}
            if not same_fields(actual, item):
                raise RuntimeError("Financial readback differs")
    result = {"status": "PASS", "phase": args.phase, "exit": code, "added": len(additions),
              "import_posts": len(writes), "baseline_preserved": True,
              "before_count": len(before_rows), "after_count": len(after_rows)}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
