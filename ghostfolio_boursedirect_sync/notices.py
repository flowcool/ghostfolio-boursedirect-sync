"""Parse the observed BUY PDF layout, using legacy parse_contract_note labels.

The source-specific PDF extractor is the approved pdftotext -layout mechanism.
No holder data or raw text crosses the logging boundary.
"""

import re
import subprocess
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext
from typing import Literal

from ghostfolio_boursedirect_sync.models import Buy, Notice

NUMBER = r"[+-]?(?:[1-9][0-9]{0,2}(?: [0-9]{3})+|[0-9]+)(?:[,.][0-9]+)?"
HEADER = re.compile(
    rf"^\s*(\d{{2}}/\d{{2}}/\d{{4}})\s+ACHAT (?:ETRANGER|COMPTANT)\s+"
    rf"([A-Z]{{2}}[A-Z0-9]{{9}}[0-9])\s+.+?\s{{2,}}({NUMBER})\s*$"
)
ACCOUNT = re.compile(
    r"\bCOMPTE\s+N[°º]\s*:?\s*([A-Z0-9 ]+?)EUR\s*(?:PEA-PME|PEA)\b", re.I
)
FIELD = rf"([A-Z][A-Z .]*?)\s*:\s*({NUMBER})"
FOOTER = re.compile(
    r"\s*(?:Sous réserve de bonne fin / Ce relevé ne constitue pas une facture|"
    r"Les montants des colonnes Débit et Crédit sont stipulés TVA Comprise|"
    r"Bourse Direct\s*,\s*SA au capital de .+)\s*"
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


def checked_fields(block: str, required: set[str], optional: set[str] | None = None) -> dict[str, Decimal]:
    """Reject unknown labels and partial numbers instead of guessing source fields."""
    values: dict[str, Decimal] = {}
    for line in block.splitlines():
        if not line.strip() or FOOTER.fullmatch(line):
            continue
        if re.fullmatch(
            r"\s*Heure Execution:\s*\d{2}:\d{2}:\d{2}\s+Lieu:\s*.+", line
        ):
            continue
        if re.fullmatch(rf"\s*(?:{FIELD}\s*)+", line) is None:
            raise RuntimeError("notice_unreadable")
        for match in re.finditer(FIELD, line):
            label = match[1].strip()
            if label not in required | (optional or set()) or label in values:
                raise RuntimeError("notice_unreadable")
            values[label] = decimal(match[2])
    if not required <= values.keys():
        raise RuntimeError("notice_unreadable")
    return values


def checked_amounts(kind: Literal["BUY", "SELL", "DIVIDEND"], block: str, net: Decimal,
                    currency: str) -> dict[str, Decimal]:
    """BD adapter of DEGIRO sync.py:282: corroborate cash with source fields.

    Unlike DEGIRO, BD requires exact gross and cash equality, without tolerance.
    Coupon cash is authoritative; its gross price is not a net-price formula.
    SELL/coupon dispatch is added separately in tasks 4.2/4.3.
    """
    if kind == "DIVIDEND":
        fields = checked_fields(block, {"QUANTITE", "PX UN.BRUT", "BRUT", "COMMISSION"},
                                {"CRED. IMPOT", "TVA"})
    else:
        fields = checked_fields(block, {"QUANTITE", "COURS", "BRUT", "COURTAGE", "TVA"})
    if currency != "EUR" or not net.is_finite() or net <= 0 or fields.get("TVA", Decimal(0)) != 0:
        raise RuntimeError("amount_check_failed")
    if kind == "DIVIDEND":
        return fields
    quantity, price, gross, fee, vat = (fields[key] for key in
                                       ("QUANTITE", "COURS", "BRUT", "COURTAGE", "TVA"))
    with localcontext() as context:
        context.prec = max(28, sum(len(format(v, "f")) for v in (*fields.values(), net)) + 8)
        if (
            (quantity <= 0 if kind == "BUY" else quantity >= 0)
            or min(price, gross) <= 0 or fee < 0
            or quantity.copy_abs() * price != gross
            or (gross + fee + vat if kind == "BUY" else gross - fee - vat) != net
        ):
            raise RuntimeError("amount_check_failed")
    return fields


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
        fields = checked_amounts("BUY", block, decimal(header[3]), "EUR")
        buys.append(Buy(day, header[2], fields["QUANTITE"].copy_abs(), fields["COURS"], fields["COURTAGE"]))
    return Notice(account_ref, tuple(buys))
