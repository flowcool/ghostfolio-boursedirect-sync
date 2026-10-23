"""Parse the observed BUY PDF layout, using legacy parse_contract_note labels.

The source-specific PDF extractor is the approved pdftotext -layout mechanism.
No holder data or raw text crosses the logging boundary.
"""

import re
import subprocess
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext

from ghostfolio_boursedirect_sync.models import Buy, Notice

NUMBER = r"[+-]?[0-9][0-9 ]*(?:[,.][0-9]+)?"
HEADER = re.compile(
    rf"^\s*(\d{{2}}/\d{{2}}/\d{{4}})\s+ACHAT (?:ETRANGER|COMPTANT)\s+"
    rf"([A-Z]{{2}}[A-Z0-9]{{9}}[0-9])\s+.+?\s{{2,}}({NUMBER})\s*$"
)
ACCOUNT = re.compile(
    r"\bCOMPTE\s+N[°º]\s*:?\s*([A-Z0-9 ]+?)EUR\s*(?:PEA-PME|PEA)\b", re.I
)


def extract_text(pdf: bytes) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", "-", "-"],
            input=pdf,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=True,
        )
        return result.stdout.decode("utf-8")
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise RuntimeError("notice_unreadable") from None


def decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value.replace(" ", "").replace(",", "."))
    except DecimalException:
        raise RuntimeError("notice_unreadable") from None
    if not parsed.is_finite():
        raise RuntimeError("notice_unreadable")
    return parsed


def amount(block: str, label: str) -> Decimal:
    matches = re.findall(rf"\b{label}\s*:\s*({NUMBER})", block)
    if len(matches) != 1:
        raise RuntimeError("notice_unreadable")
    return decimal(matches[0])


def parse_text(text: str) -> Notice:
    """Read the labelled identifier; EUR and account type are separate metadata."""
    account_lines = [line for line in text.splitlines() if re.search(r"\bCOMPTE\b", line, re.I)]
    labels = re.findall(r"\bCOMPTE\s+N[°º]", text, re.I)
    if len(labels) != 1 or len(account_lines) != 1:
        raise RuntimeError("notice_unreadable")
    match = ACCOUNT.search(account_lines[0])
    if match is None:
        raise RuntimeError("notice_unreadable")
    account_ref = match[1].replace(" ", "")
    lines = text.splitlines()
    headers = [(index, HEADER.fullmatch(line)) for index, line in enumerate(lines)]
    starts = [(index, header) for index, header in headers if header is not None]
    # Other operation layouts need their own real evidence in later tasks.
    operation_lines = [line for line in lines if re.match(r"\s*\d{2}/\d{2}/\d{4}\s+", line)]
    if not starts or len(starts) != len(operation_lines):
        raise RuntimeError("notice_unreadable")
    buys = []
    for rank, (index, header) in enumerate(starts):
        end = starts[rank + 1][0] if rank + 1 < len(starts) else len(lines)
        block = "\n".join(lines[index + 1:end])
        try:
            day = datetime.strptime(header[1], "%d/%m/%Y").date()
        except ValueError:
            raise RuntimeError("notice_unreadable") from None
        quantity = amount(block, "QUANTITE")
        price = amount(block, "COURS")
        gross = amount(block, "BRUT")
        fee = amount(block, "COURTAGE")
        vat = amount(block, "TVA")
        debit = decimal(header[3])
        with localcontext() as context:
            context.prec = max(28, sum(len(v.as_tuple().digits) for v in (quantity, price, gross, fee)) + 8)
            if (
                min(quantity, price, gross, debit) <= 0
                or fee < 0
                or vat != 0
                or quantity * price != gross
                or gross + fee + vat != debit
            ):
                raise RuntimeError("amount_check_failed")
        buys.append(Buy(day, header[2], quantity, price, fee))
    return Notice(account_ref, tuple(buys))
