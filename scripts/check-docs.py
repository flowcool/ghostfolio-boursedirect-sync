#!/usr/bin/env python3
"""Check local links in the entry documents."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ENTRY_DOCUMENTS = ["AGENTS.md", "CLAUDE.md", "README.md", "CONTRIBUTING.md", "CHANGELOG.md", "docs/README.md"]


def check_docs(root):
    errors = []
    documents = [root / name for name in ENTRY_DOCUMENTS if (root / name).exists()]
    documents.extend(sorted((root / "docs/agents").glob("*.md")))
    for document in documents:
        for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", document.read_text()):
            link = urlsplit(target)
            if link.scheme or link.netloc or not link.path:
                continue
            if not (document.parent / unquote(link.path)).exists():
                errors.append("broken local link in " + str(document.relative_to(root)) + ": " + target)
    return errors


if __name__ == "__main__":
    try:
        failures = check_docs(Path(__file__).resolve().parents[1])
    except (OSError, UnicodeError) as error:
        print("Documentation check failed: " + str(error), file=sys.stderr)
        sys.exit(1)
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        sys.exit(1)
    print("Documentation local links passed")
