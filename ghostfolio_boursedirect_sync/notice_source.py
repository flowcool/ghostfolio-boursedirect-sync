"""Source selection before common parsing. Approved community-v2-2 adaptation."""

import hashlib

from ghostfolio_boursedirect_sync import folder, paperless
from ghostfolio_boursedirect_sync.models import Settings, Source, SourceDocument


def acquire(settings: Settings) -> Source:
    if settings.notice_dir:
        snapshot = folder.acquire(settings.notice_dir)
        return Source(tuple(sorted(snapshot.documents, key=lambda d: str(d.reference))), snapshot)
    documents = []
    for reference in paperless.document_ids(settings):
        pdf = paperless.original_pdf(settings, reference)
        documents.append(SourceDocument(reference, pdf, hashlib.sha256(pdf).hexdigest()))
    return Source(tuple(documents))


def verify(settings: Settings, source: Source) -> None:
    if source.snapshot is not None:
        folder.verify(settings.notice_dir, source.snapshot)
