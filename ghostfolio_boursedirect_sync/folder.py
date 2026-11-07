"""Read-only folder acquisition. Approved community-v2-2 BD adaptation."""

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

MAX_PDF_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class FolderDocument:
    reference: str
    pdf: bytes | None
    code: str = ""


@dataclass(frozen=True)
class FolderSnapshot:
    documents: tuple[FolderDocument, ...]
    files: int
    ignored: int
    evidence: tuple[tuple[str, tuple[int, ...], str], ...]
    root: tuple[int, ...]


def signature(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def open_directory(path: Path) -> int:
    """Open every component with NOFOLLOW; never traverse a directory link."""
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            info = os.stat(part, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError("notice_unreadable")
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def acquire(path: str) -> FolderSnapshot:
    """Read a bounded snapshot before dispatch; keep readable previews on bad PDFs."""
    documents: dict[str, FolderDocument] = {}
    evidence: list[tuple[str, tuple[int, ...], str]] = []
    files = ignored = 0
    try:
        root = open_directory(Path(path))
        try:
            before = os.fstat(root)
            if not before.st_mode & 0o444 or not before.st_mode & 0o111:
                raise OSError
            names = sorted(os.listdir(root))
            for name in names:
                if not name.lower().endswith(".pdf"):
                    ignored += 1
                    continue
                files += 1
                info = os.stat(name, dir_fd=root, follow_symlinks=False)
                data = None
                digest = ""
                if (stat.S_ISREG(info.st_mode) and info.st_mode & 0o444
                        and 1 <= info.st_size <= MAX_PDF_BYTES):
                    try:
                        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=root)
                        with os.fdopen(fd, "rb") as stream:
                            opened = os.fstat(stream.fileno())
                            if signature(opened) != signature(info):
                                raise RuntimeError("notice_source_unavailable")
                            data = stream.read(MAX_PDF_BYTES + 1)
                            if signature(os.fstat(stream.fileno())) != signature(info) or len(data) != info.st_size:
                                raise RuntimeError("notice_source_unavailable")
                        digest = hashlib.sha256(data).hexdigest()
                    except OSError:
                        data = None
                after = os.stat(name, dir_fd=root, follow_symlinks=False)
                if signature(after) != signature(info):
                    raise RuntimeError("notice_source_unavailable")
                reference = "sha256:" + digest if data is not None else "unreadable:" + str(files)
                documents.setdefault(reference, FolderDocument(reference, data, "" if data is not None else "notice_unreadable"))
                evidence.append((name, signature(info), digest))
            if names != sorted(os.listdir(root)) or signature(before) != signature(os.fstat(root)):
                raise RuntimeError("notice_source_unavailable")
            return FolderSnapshot(tuple(documents.values()), files, ignored, tuple(evidence), signature(before))
        finally:
            os.close(root)
    except OSError:
        raise RuntimeError("notice_source_unavailable") from None


def verify(path: str, snapshot: FolderSnapshot) -> None:
    """Refuse changed source bytes or membership before financial dispatch."""
    current = acquire(path)
    if current.evidence != snapshot.evidence or current.root != snapshot.root:
        raise RuntimeError("notice_source_unavailable")


def load_waivers(filename: str, notice_dir: str, review_file: str) -> tuple[tuple[str, str], ...]:
    """Validate exact digest/code consent once, before any service access."""
    if not filename:
        return ()
    try:
        path = Path(filename)
        source = Path(notice_dir)
        if not path.is_absolute() or path.resolve().is_relative_to(source.resolve()):
            raise ValueError
        parent = open_directory(path.parent)
        try:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o444 or info.st_size > 65536:
                raise ValueError
            if review_file:
                review = Path(review_file).absolute()
                for suffix in ("", ".state.yaml", ".journal.yaml", ".lock", ".notifications.yaml"):
                    target = Path(str(review) + suffix)
                    if path.resolve() == target.resolve() or (target.exists() and os.path.samefile(path, target)):
                        raise ValueError
            # A hard-linked input must not serve as a waiver, even outside the source tree.
            if not any(p.is_symlink() for p in (source, *source.parents)) and source.is_dir():
                for entry in source.iterdir():
                    if not entry.is_symlink() and entry.is_file() and os.path.samefile(path, entry):
                        raise ValueError
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            with os.fdopen(fd, "rb") as stream:
                if signature(os.fstat(stream.fileno())) != signature(info):
                    raise ValueError
                data = stream.read(65537)
                if len(data) != info.st_size or signature(os.fstat(stream.fileno())) != signature(info):
                    raise ValueError
        finally:
            os.close(parent)
        pairs: set[tuple[str, str]] = set()
        for line in data.decode("utf-8").split("\n"):
            if not line:
                continue
            if re.fullmatch(r"sha256:[0-9a-f]{64} (share_count_change|unknown_operation)", line) is None:
                raise ValueError
            digest, code = line.split(" ")
            if (digest, code) in pairs:
                raise ValueError
            pairs.add((digest, code))
        return tuple(sorted(pairs))
    except (OSError, ValueError, RuntimeError):
        raise RuntimeError("invalid_configuration NOTICE_WAIVER_FILE") from None
