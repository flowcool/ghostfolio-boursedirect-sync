#!/usr/bin/env python3
"""Bounded current-file scan. This is not a history or secret certification."""

import argparse
import re
import subprocess
import tarfile
from pathlib import Path

MAX_TEXT_BYTES = 1024 * 1024
RULES = {
    "private_workspace": re.compile(r"/home/[^/\s]+/(?:claude_project|\.claude|\.codex)|~/claude_project/"),
    "private_tracker": re.compile(r"\binfra-[a-z0-9]+(?:\.[0-9]+)*\b"),
    "personal_host": re.compile(r"\b(?:agentvm|ugreen)\b", re.I),
    "holder_field": re.compile(r"^\s*(?:titulaire|nom du titulaire|adresse du titulaire)\s*:\s*\S", re.I | re.M),
    "credential_signature": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def scan(entries):
    findings = []
    for name, data in entries:
        # This file defines the signatures, not operational values.
        if name == "scripts/check_public_privacy.py" or len(data) > MAX_TEXT_BYTES or b"\0" in data:
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            continue
        if name.startswith("tests/fixtures/"):
            for line in text.splitlines():
                if re.search(r"COMPTE\s+N[°º]", line, re.I) and "TEST ACCOUNT" not in line:
                    findings.append(f"{name}: source_account_label")
        for code, pattern in RULES.items():
            if pattern.search(text):
                findings.append(f"{name}: {code}")
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.archive:
        with tarfile.open(args.archive, "r:gz") as archive:
            entries = []
            for member in archive.getmembers():
                if member.isfile() and member.size <= MAX_TEXT_BYTES:
                    with archive.extractfile(member) as stream:
                        entries.append((member.name.split("/", 1)[-1], stream.read(MAX_TEXT_BYTES + 1)))
    else:
        names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
        entries = [(name, (root / name).read_bytes()) for name in names
                   if name and (root / name).is_file() and (root / name).stat().st_size <= MAX_TEXT_BYTES]
    findings = scan(entries)
    for finding in findings:
        print(finding)
    print(f"Current public privacy scan: {len(findings)} findings; bounded text only; history not certified")
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
