"""Source selection before common parsing. Approved community-v2-2 adaptation."""

import hashlib
from dataclasses import dataclass

from ghostfolio_boursedirect_sync import folder, paperless
from ghostfolio_boursedirect_sync.models import Settings

DocumentReference = int | str


@dataclass(frozen=True)
class SourceDocument:
    reference: DocumentReference
    pdf: bytes | None
    digest: str
    code: str = ""
    copies: int = 1


@dataclass(frozen=True)
class Source:
    documents: tuple[SourceDocument, ...]
    snapshot: folder.FolderSnapshot | None = None


def acquire(settings: Settings) -> Source:
    if settings.notice_dir:
        snapshot = folder.acquire(settings.notice_dir)
        return Source(tuple(SourceDocument(d.reference, d.pdf,
                            d.reference.removeprefix("sha256:") if d.pdf is not None else "", d.code,
                            sum(digest == d.reference.removeprefix("sha256:") for _, _, digest in snapshot.evidence)
                            if d.pdf is not None else 1)
                            for d in sorted(snapshot.documents, key=lambda d: d.reference)), snapshot)
    documents = []
    for reference in paperless.document_ids(settings):
        pdf = paperless.original_pdf(settings, reference)
        documents.append(SourceDocument(reference, pdf, hashlib.sha256(pdf).hexdigest()))
    return Source(tuple(documents))


def verify(settings: Settings, source: Source) -> None:
    if source.snapshot is not None:
        folder.verify(settings.notice_dir, source.snapshot)
