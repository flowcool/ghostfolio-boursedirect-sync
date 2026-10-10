#!/usr/bin/env python3
"""Check the design catalogue and local links in agent entry documents."""

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def check_docs(root):
    design = root / "docs/design"
    index = design / "index.md"
    errors = []
    entries = []
    expected = {p.name for p in design.glob("*.md") if p != index}
    for line in index.read_text().splitlines():
        match = re.fullmatch(r"\| \[([^]]+)\]\(([^)]+)\) \| (.*) \|", line)
        if not match:
            if line.startswith("| ["):
                errors.append("malformed catalogue row")
            continue
        title, target, summary = match.groups()
        entries.append(target)
        path = design / target
        if target not in expected:
            errors.append("unknown catalogue target: " + target)
            continue
        lines = path.read_text().splitlines()
        heading = next((line[2:] for line in lines if line.startswith("# ")), "")
        first = next((line for line in lines if line.strip() and not line.startswith("#")), "")
        if title != heading or summary != first:
            errors.append("stale catalogue entry: " + target)
    if set(entries) != expected or len(entries) != len(set(entries)):
        errors.append("catalogue must list every Markdown contract exactly once")
    documents = [root / "AGENTS.md", root / "CLAUDE.md", index]
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
    print("Documentation catalogue and local links passed")
