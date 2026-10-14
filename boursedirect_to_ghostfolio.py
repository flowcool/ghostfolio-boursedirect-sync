"""Offline source-characterization probe; does not import Ghostfolio activities."""

import argparse
import calendar
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import fcntl
import hashlib
import http.client
import json
import logging
import os
from pathlib import Path
import re
import stat
import ssl
import signal
import subprocess
import sys
import uuid
from urllib.parse import parse_qs, urljoin, urlsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Comment
import yaml


log = logging.getLogger(__name__)
HEADERS = ("Date", "Désignation", "Débit (€)", "Crédit (€)")
VERIFICATION_REFERENCE_LIMIT = 10000
VERIFICATION_DECIMAL_CHAR_LIMIT = 4096
FROZEN_REVIEW_PRECISION_LIMIT = 10000


def fail(code):
    # Codes only: source text, paths and account data must not leak to logs.
    raise RuntimeError(code)


def text(node):
    return " ".join(node.get_text(" ", strip=True).split())


def parse_decimal(value, cash=False):
    value = " ".join(value.split())
    if not re.fullmatch(r"[+-]?(?:[0-9]+|[0-9]{1,3}(?: [0-9]{3})+)(?:,[0-9]+)?", value):
        fail("INVALID_DECIMAL")
    try:
        result = Decimal(value.replace(" ", "").replace(",", "."))
    except InvalidOperation:
        fail("INVALID_DECIMAL")
    fraction = value.split(",", 1)[1] if "," in value else ""
    if cash and len(fraction.rstrip("0")) > 2:
        fail("INVALID_CASH_PRECISION")
    return result


def parse_date(value):
    if not re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", value):
        fail("INVALID_DATE")
    try:
        return datetime.strptime(value, "%d/%m/%Y").date()
    except ValueError:
        fail("INVALID_DATE")


def direct_rows(table):
    rows = []
    for child in table.children:
        if getattr(child, "name", None) == "tr":
            rows.append(child)
        elif getattr(child, "name", None) == "tbody":
            if any(getattr(c, "name", None) not in (None, "tr") for c in child.children):
                fail("UNSUPPORTED_TABLE_STRUCTURE")
            reject_direct_text(child, "UNSUPPORTED_TABLE_STRUCTURE")
            rows.extend(child.find_all("tr", recursive=False))
        elif getattr(child, "name", None) is not None:
            fail("UNSUPPORTED_TABLE_STRUCTURE")
    reject_direct_text(table, "UNSUPPORTED_TABLE_STRUCTURE")
    return rows


def reject_direct_text(node, code):
    if any(getattr(c, "name", None) is None and not isinstance(c, Comment)
           and str(c).strip() for c in node.children):
        fail(code)


def cells(row):
    return row.find_all(["td", "th"], recursive=False)


def decode_document(raw):
    # Only explicitly characterized encodings. No guessed or replacement decoding.
    if b"\x00" in raw:
        fail("INVALID_DOCUMENT_BYTES")
    declarations = re.findall(
        rb"<meta\b[^>]*\bcharset\s*=\s*[\"']?\s*([a-zA-Z0-9_-]+)", raw, re.I
    )
    aliases = {"windows-1252": "cp1252", "cp1252": "cp1252", "utf-8": "utf-8"}
    encodings = {aliases.get(v.decode("ascii").lower()) for v in declarations}
    if not encodings or None in encodings or len(encodings) != 1:
        fail("UNSUPPORTED_OR_AMBIGUOUS_ENCODING")
    encoding = encodings.pop()
    if raw.startswith(b"\xef\xbb\xbf"):
        if encoding != "utf-8":
            fail("ENCODING_BOM_CONFLICT")
        raw = raw[3:]
    try:
        html = raw.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        fail("INVALID_DOCUMENT_ENCODING")
    if "\ufffd" in html:
        fail("REPLACEMENT_CHARACTER")
    return html


def read_local_bytes(path, input_root, max_bytes):
    if max_bytes <= 0:
        fail("INVALID_SIZE_LIMIT")
    root = Path(input_root).resolve(strict=True)
    source = Path(path)
    if source.is_symlink():
        fail("SYMLINK_INPUT")
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(root):
        fail("INPUT_OUTSIDE_ROOT")
    descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            fail("INPUT_NOT_REGULAR")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(max_bytes + 1)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > max_bytes:
        fail("INPUT_TOO_LARGE")
    return raw


def read_document(path, input_root, max_bytes):
    raw = read_local_bytes(path, input_root, max_bytes)
    return decode_document(raw), hashlib.sha256(raw).hexdigest()


def parse_statement(html, max_depth):
    if max_depth <= 0:
        fail("INVALID_DEPTH_LIMIT")
    soup = BeautifulSoup(html, "html.parser")
    # Iterative traversal bounds depth without recursion on hostile nesting.
    pending = [(soup, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > max_depth:
            fail("INPUT_TOO_DEEP")
        pending.extend((child, depth + 1) for child in node.children if getattr(child, "name", None))
    titles = [n for n in soup.find_all("strong") if text(n) == "RELEVE DE COMPTE"]
    if len(titles) != 1:
        fail("STATEMENT_TITLE_MISSING_OR_AMBIGUOUS")
    account_refs = []
    for row in soup.find_all("tr"):
        values = cells(row)
        if len(values) == 2 and text(values[0]) == "COMPTE N°":
            account_refs.append(text(values[1]))
    if len(account_refs) != 1 or not account_refs[0]:
        fail("ACCOUNT_HEADER_MISSING_OR_AMBIGUOUS")

    candidates = []
    for table in soup.find_all("table"):
        # Avoid traversing descendants when choosing the ledger by headers.
        first = table.find("tr", recursive=False)
        if first is None:
            body = table.find("tbody", recursive=False)
            first = body.find("tr", recursive=False) if body else None
        if first and tuple(text(c) for c in cells(first)) == HEADERS:
            candidates.append(table)
    if len(candidates) != 1:
        fail("LEDGER_MISSING_OR_AMBIGUOUS")
    outer_rows = direct_rows(candidates[0])
    if len(outer_rows) != 2 or len(cells(outer_rows[1])) != 4:
        fail("UNSUPPORTED_LEDGER_STRUCTURE")
    vectors = []
    for column in cells(outer_rows[1]):
        tables = column.find_all("table", recursive=False)
        if len(tables) != 1:
            fail("UNSUPPORTED_COLUMN_STRUCTURE")
        if any(getattr(c, "name", None) not in (None, "table") for c in column.children):
            fail("UNSUPPORTED_COLUMN_STRUCTURE")
        reject_direct_text(column, "UNSUPPORTED_COLUMN_STRUCTURE")
        vectors.append(direct_rows(tables[0]))
    if len({len(v) for v in vectors}) != 1:
        fail("UNEQUAL_COLUMN_LENGTHS")
    controls = []
    events = []
    for slot, rows in enumerate(zip(*vectors)):
        parts = [cells(row) for row in rows]
        if any(len(parts[i]) != 1 for i in (0, 2, 3)) or len(parts[1]) not in (1, 3):
            fail("UNSUPPORTED_SLOT_STRUCTURE")
        if any(c.find("table") for part in parts for c in part):
            fail("NESTED_SLOT_TABLE")
        date_text = text(parts[0][0])
        descriptions = [text(c) for c in parts[1]]
        label = descriptions[0]
        debit_text, credit_text = text(parts[2][0]), text(parts[3][0])
        if not any([date_text, *descriptions, debit_text, credit_text]):
            continue
        debit = parse_decimal(debit_text, cash=True) if debit_text else Decimal(0)
        credit = parse_decimal(credit_text, cash=True) if credit_text else Decimal(0)
        if min(debit, credit) < 0:
            fail("NEGATIVE_CASH_COLUMN")
        balance = re.fullmatch(r"Solde au : ([0-9]{2}/[0-9]{2}/[0-9]{4})", label)
        if balance or label == "Cumul mouvements :":
            if date_text or any(descriptions[1:]):
                fail("CONTROL_ALIGNMENT_ERROR")
            if balance and debit_text and credit_text:
                fail("AMBIGUOUS_BALANCE_DIRECTION")
            controls.append({"slot": slot, "kind": "balance" if balance else "cumulative",
                             "date": parse_date(balance[1]) if balance else None,
                             "debit": debit, "credit": credit})
            continue
        if not label or not date_text:
            fail("ORPHAN_LEDGER_SLOT")
        date = parse_date(date_text)
        if debit_text and credit_text:
            fail("AMBIGUOUS_OPERATION_DIRECTION")
        kind = "SELL" if label.startswith(("VTE CPT ", "VENTE ETRANGER ")) else "BUY" if label.startswith("ACH CPT ") else "UNKNOWN"
        event = {"slot": slot, "date": date, "label": label, "kind": kind,
                 "debit": debit, "credit": credit}
        if kind in ("BUY", "SELL"):
            if len(descriptions) != 3:
                fail("TRADE_FIELDS_MISSING")
            quantity = re.fullmatch(r"Qté : (.+)", descriptions[1])
            price = re.fullmatch(r"Cours : (.+)", descriptions[2])
            if not quantity or not price:
                fail("TRADE_FIELDS_MISSING")
            event["quantity"] = parse_decimal(quantity[1])
            event["unit_price"] = parse_decimal(price[1])
            if event["unit_price"] <= 0:
                fail("INVALID_TRADE_PRICE")
            if kind == "BUY" and (event["quantity"] <= 0 or not debit_text or credit_text):
                fail("BUY_DIRECTION_CONFLICT")
            if kind == "SELL" and (event["quantity"] >= 0 or not credit_text or debit_text):
                fail("SELL_DIRECTION_CONFLICT")
            if debit + credit <= 0:
                fail("TRADE_NET_NOT_POSITIVE")
        events.append(event)
    if [c["kind"] for c in controls] != ["balance", "cumulative", "balance"]:
        fail("CONTROL_ROWS_MISSING_OR_REORDERED")
    opening, cumulative, closing = controls
    expected_opening = closing["date"].replace(day=1) - timedelta(days=1)
    if opening["date"] != expected_opening or closing["date"].day != calendar.monthrange(closing["date"].year, closing["date"].month)[1]:
        fail("INVALID_STATEMENT_PERIOD")
    if any(not opening["slot"] < e["slot"] < cumulative["slot"] for e in events):
        fail("OPERATIONS_OUTSIDE_CONTROL_ROWS")
    validate_ledger(controls, events)
    blockers = {"CONTRACT_NOTE_ENRICHMENT_UNVERIFIED", "REAL_SOURCE_ACCEPTANCE_PENDING"}
    if any(e["kind"] == "UNKNOWN" for e in events):
        blockers.add("UNKNOWN_OPERATIONS")
    if any(e["date"].strftime("%Y-%m") != closing["date"].strftime("%Y-%m") for e in events):
        blockers.add("OPERATION_OUTSIDE_STATEMENT_MONTH")
    return {"account_ref": account_refs[0], "period": closing["date"].strftime("%Y-%m"),
            "events": events, "controls": controls, "slot_count": len(vectors[0]),
            "blockers": sorted(blockers)}


def validate_ledger(controls, events):
    opening, cumulative, closing = controls
    values = [row[column] for row in [*controls, *events] for column in ("debit", "credit")]
    # Do not allow the process-wide Decimal precision to silently round controls.
    precision = max(len(v.as_tuple().digits) for v in values) + len(str(len(events) + 1)) + 4
    with localcontext() as context:
        context.prec = max(28, precision)
        debits = sum((e["debit"] for e in events), Decimal(0))
        credits = sum((e["credit"] for e in events), Decimal(0))
        if opening["credit"] - opening["debit"] + credits - debits != closing["credit"] - closing["debit"]:
            fail("BALANCE_MISMATCH")
        if (opening["debit"] + debits, opening["credit"] + credits) != (cumulative["debit"], cumulative["credit"]):
            fail("CUMULATIVE_MISMATCH")


def inspection_summary(statement):
    return {"document": "document-1", "slots": statement["slot_count"],
            "operation_counts": {kind: sum(e["kind"] == kind for e in statement["events"])
                                 for kind in ("BUY", "SELL", "UNKNOWN")},
            "ledger_reconciled": True, "import_ready": False,
            "blockers": statement["blockers"]}


def valid_isin(value):
    if not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    total = 0
    for index, digit in enumerate(reversed(digits)):
        number = int(digit) * (2 if index % 2 else 1)
        total += number // 10 + number % 10
    return total % 10 == 0


def contract_note_ledger(soup, notice_sync=False):
    candidates = []
    for table in soup.find_all("table"):
        first = table.find("tr", recursive=False)
        if first is None:
            body = table.find("tbody", recursive=False)
            first = body.find("tr", recursive=False) if body else None
        headers = tuple(text(c) for c in cells(first)) if first else ()
        if headers == HEADERS or (notice_sync and len(headers) == 4 and headers[:2] == HEADERS[:2]
                and re.fullmatch(r"Débit(?: \(.*\))?", headers[2])
                and re.fullmatch(r"Crédit(?: \(.*\))?", headers[3])):
            candidates.append(table)
    if len(candidates) != 1:
        fail("LEDGER_MISSING_OR_AMBIGUOUS")
    return candidates[0]


def parse_contract_note(html, max_depth, include_coupons=False, skip_missing_isin=False, notice_sync=False):
    if type(include_coupons) is not bool:
        fail("INVALID_NOTE_INSPECTION_MODE")
    if type(skip_missing_isin) is not bool or type(notice_sync) is not bool:
        fail("INVALID_NOTE_INSPECTION_MODE")
    if max_depth <= 0:
        fail("INVALID_DEPTH_LIMIT")
    soup = BeautifulSoup(html, "html.parser")
    pending = [(soup, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > max_depth:
            fail("INPUT_TOO_DEEP")
        pending.extend((c, depth + 1) for c in node.children if getattr(c, "name", None))
    if sum(text(n) == "Avis d'Opération" for n in soup.find_all("strong")) != 1:
        fail("NOTE_TITLE_MISSING_OR_AMBIGUOUS")
    accounts = [text(cells(r)[1]) for r in soup.find_all("tr")
                if len(cells(r)) == 2 and text(cells(r)[0]) == "COMPTE N°"]
    if len(accounts) != 1 or not accounts[0]:
        fail("ACCOUNT_HEADER_MISSING_OR_AMBIGUOUS")
    ledger = contract_note_ledger(soup, notice_sync)
    rows = direct_rows(ledger)
    headers = tuple(text(c) for c in cells(rows[0]))
    net_currency = "EUR" if headers == HEADERS else None
    if len(rows) != 2 or len(cells(rows[1])) != 4:
        fail("UNSUPPORTED_NOTE_STRUCTURE")
    vectors = []
    for column in cells(rows[1]):
        tables = column.find_all("table", recursive=False)
        if len(tables) != 1 or any(getattr(c, "name", None) not in (None, "table") for c in column.children):
            fail("UNSUPPORTED_COLUMN_STRUCTURE")
        reject_direct_text(column, "UNSUPPORTED_COLUMN_STRUCTURE")
        vectors.append(direct_rows(tables[0]))
    lengths = {len(v) for v in vectors}
    if len(lengths) != 1:
        fail("UNEQUAL_COLUMN_LENGTHS")
    count = len(vectors[0])
    if not count or not (include_coupons or skip_missing_isin) and count % 9:
        fail("UNSUPPORTED_NOTE_GROUP_LENGTH")
    groups = []
    labels = {"ACHAT COMPTANT": "BUY", "ACHAT ETRANGER": "BUY", "VENTE COMPTANT": "SELL", "VENTE ETRANGER": "SELL"}
    start = 0
    while start < count:
        if count - start < 2:
            fail("UNSUPPORTED_NOTE_GROUP_LENGTH")
        initial = cells(vectors[1][start + 1])
        if len(initial) != 1:
            fail("UNSUPPORTED_NOTE_SLOT")
        coupon = include_coupons and text(initial[0]).startswith("COUPONS ")
        unknown = (include_coupons or skip_missing_isin) and not coupon and not any(
            text(initial[0]).startswith(label + " ") for label in labels)
        size = 6 if coupon else 9
        if unknown:
            next_headers = []
            for index in range(start + 2, count):
                date_cells = cells(vectors[0][index])
                if len(date_cells) != 1:
                    fail("UNSUPPORTED_NOTE_SLOT")
                if text(date_cells[0]):
                    next_headers.append(index)
            size = (next_headers[0] - 1 if next_headers else count) - start
            if size < 3:
                fail("UNSUPPORTED_NOTE_GROUP_LENGTH")
        if count - start < size:
            fail("UNSUPPORTED_NOTE_GROUP_LENGTH")
        slots = []
        for offset in range(size):
            parts = [cells(v[start + offset]) for v in vectors]
            if any(len(c) != 1 for c in parts):
                fail("UNSUPPORTED_NOTE_SLOT")
            if any(c[0].find("table") for i, c in enumerate(parts) if i != 1):
                fail("UNSUPPORTED_NOTE_SLOT")
            if offset in ({0, 2} if unknown else {0, 2, 6, 8}):
                if any(text(c[0]) or c[0].find("table") for c in parts):
                    fail("NOTE_BLANK_SLOT_CONFLICT")
            elif offset != 1 and any(text(parts[i][0]) for i in (0, 2, 3)):
                fail("NOTE_FIELD_ALIGNMENT_ERROR")
            slots.append(parts)

        def fields(offset):
            cell = slots[offset][1][0]
            nested = cell.find_all("table", recursive=False)
            if len(nested) != 1 or any(getattr(c, "name", None) not in (None, "table") for c in cell.children):
                fail("UNSUPPORTED_NOTE_FIELD_TABLE")
            reject_direct_text(cell, "UNSUPPORTED_NOTE_FIELD_TABLE")
            field_rows = direct_rows(nested[0])
            if len(field_rows) != 1 or len(cells(field_rows[0])) != 3:
                fail("UNSUPPORTED_NOTE_FIELD_TABLE")
            field_cells = cells(field_rows[0])
            if any(c.find("table") for c in field_cells):
                fail("UNSUPPORTED_NOTE_FIELD_TABLE")
            return [text(c) for c in field_cells]

        header = fields(1)
        if header[0] not in labels and not (coupon and header[0] == "COUPONS") and not unknown:
            fail("UNSUPPORTED_NOTE_OPERATION")
        missing_isin = skip_missing_isin and not header[1]
        skipped = missing_isin and not notice_sync
        if not missing_isin and (not valid_isin(header[1]) or not header[2]):
            fail("INVALID_NOTE_SECURITY")
        kind = "SKIPPED_NO_ISIN" if skipped else "UNKNOWN" if unknown else "COUPON" if coupon else labels[header[0]]
        note = {"slot": start + 1, "kind": kind, "isin": header[1] or None, "name": header[2],
                "date": parse_date(text(slots[1][0][0])), "net_currency": net_currency,
                "price_currency": None}
        if notice_sync:
            note['source_kind'] = header[0]
        if unknown or skipped:
            note.update(source_kind=header[0], source_fields=[], gross_semantics_verified=False)
            if skipped:
                note.update(skip_reason="SOURCE_ISIN_ABSENT", financial_conversion=False)
            for offset in range(3, size):
                cell = slots[offset][1][0]
                if text(cell) or cell.find("table"):
                    note["source_fields"].append(fields(offset))
            for key, column in (("debit", 2), ("credit", 3)):
                value = text(slots[1][column][0])
                note[key] = parse_decimal(value, cash=True) if value else Decimal(0)
            if min(note["debit"], note["credit"]) < 0 or note["debit"] and note["credit"]:
                fail("NOTE_DIRECTION_CONFLICT")
            groups.append(note)
            start += size
            continue
        if coupon:
            layout = {3: (("QUANTITE", "quantity", False),),
                      4: (("PX UN.BRUT", "unit_gross", False), ("BRUT", "gross", True)),
                      5: (("COMMISSION", "commission", True),)}
            for offset, definitions in layout.items():
                values = fields(offset)
                extra = values[len(definitions):]
                if offset == 5 and extra[0]:
                    match = re.fullmatch(r"CRED\. IMPOT\s*:\s*(.+)", extra[0])
                    if not match:
                        fail("UNSUPPORTED_NOTE_EXTRA_FIELD")
                    note["tax_credit"] = parse_decimal(match[1], cash=True)
                    extra = extra[1:]
                if any(extra):
                    fail("UNSUPPORTED_NOTE_EXTRA_FIELD")
                for value, (label, key, cash) in zip(values, definitions):
                    match = re.fullmatch(re.escape(label) + r"\s*:\s*(.+)", value)
                    if not match:
                        fail("NOTE_FIELD_MISSING_OR_REORDERED")
                    note[key] = parse_decimal(match[1], cash=cash)
            for key, column in (("debit", 2), ("credit", 3)):
                value = text(slots[1][column][0])
                note[key] = parse_decimal(value, cash=True) if value else Decimal(0)
            if min(note[k] for k in ("gross", "commission", "debit", "credit")) < 0 or note.get("tax_credit", Decimal(0)) < 0:
                fail("NEGATIVE_NOTE_AMOUNT")
            if note["quantity"] >= 0 or note["credit"] <= 0 or note["debit"]:
                fail("NOTE_DIRECTION_CONFLICT")
            if note["unit_gross"] <= 0 or note["gross"] <= 0:
                fail("INVALID_NOTE_PRICE_OR_GROSS")
            # These are observed source fields, not a dividend conversion. In
            # particular gross minus credit is not an inferred withholding tax.
            note.update(withholding=None, gross_semantics_verified=False)
            groups.append(note)
            start += size
            continue
        layout = {3: (("QUANTITE", "quantity", False),),
                  4: (("COURS", "unit_price", False), ("BRUT", "gross", True)),
                  5: (("COURTAGE", "brokerage", True), ("TVA", "vat", True))}
        for offset, definitions in layout.items():
            values = fields(offset)
            if any(values[len(definitions):]):
                fail("UNSUPPORTED_NOTE_EXTRA_FIELD")
            for value, (label, key, cash) in zip(values, definitions):
                match = re.fullmatch(re.escape(label) + r"\s*:\s*(.+)", value)
                if not match:
                    fail("NOTE_FIELD_MISSING_OR_REORDERED")
                note[key] = parse_decimal(match[1], cash=cash)
        execution = fields(7)
        time = re.fullmatch(r"Heure Execution:\s*([0-9]{2}:[0-9]{2}:[0-9]{2})", execution[0])
        venue = re.fullmatch(r"Lieu:\s*(.+)", execution[1])
        if not time or not venue or execution[2]:
            fail("UNSUPPORTED_NOTE_EXECUTION_FIELDS")
        try:
            datetime.strptime(time[1], "%H:%M:%S")
        except ValueError:
            fail("INVALID_NOTE_EXECUTION_TIME")
        note.update(execution_time=time[1], venue=venue[1])
        for key, column in (("debit", 2), ("credit", 3)):
            value = text(slots[1][column][0])
            note[key] = parse_decimal(value, cash=True) if value else Decimal(0)
        nonnegative = ("gross", "brokerage", "debit", "credit") if notice_sync else (
            "gross", "brokerage", "vat", "debit", "credit")
        if min(note[k] for k in nonnegative) < 0:
            fail("NEGATIVE_NOTE_AMOUNT")
        if note["unit_price"] <= 0 or note["gross"] <= 0:
            fail("INVALID_NOTE_PRICE_OR_GROSS")
        if (kind == "BUY" and (note["quantity"] <= 0 or note["debit"] <= 0 or note["credit"])
                or kind == "SELL" and (note["quantity"] >= 0 or note["credit"] <= 0 or note["debit"])):
            fail("NOTE_DIRECTION_CONFLICT")
        precision = sum(len(note[k].as_tuple().digits) for k in ("quantity", "unit_price", "gross", "brokerage", "vat")) + 8
        with localcontext() as context:
            context.prec = max(28, precision)
            if note["gross"] != note["quantity"].copy_abs() * note["unit_price"]:
                fail("NOTE_GROSS_MISMATCH")
            costs = note["brokerage"] + note["vat"]
            expected = note["gross"] + costs if kind == "BUY" else note["gross"] - costs
            if note["debit"] + note["credit"] != expected:
                fail("NOTE_NET_MISMATCH")
        groups.append(note)
        start += size
    if not notice_sync and len({n["date"] for n in groups}) != 1:
        fail("NOTE_MULTIPLE_DATES")
    return {"account_ref": accounts[0], "notes": groups, "slot_count": count}


def match_missing_isin_skips(statement, documents):
    """Bind exclusions to the original cash ledger without removing its rows."""
    validate_ledger(statement["controls"], statement["events"])
    if any(doc["account_ref"] != statement["account_ref"] for doc in documents):
        fail("NOTE_ACCOUNT_MISMATCH")
    skipped = [n for doc in documents for n in doc["notes"] if n["kind"] == "SKIPPED_NO_ISIN"]
    aliases = {"ACHAT COMPTANT": "ACH CPT", "ACHAT ETRANGER": "ACH CPT", "VENTE COMPTANT": "VTE CPT"}
    candidates = []
    for note in skipped:
        if note["isin"] is not None or note["date"].strftime("%Y-%m") != statement["period"]:
            fail("SKIPPED_NOTE_CONTEXT_CONFLICT")
        label = (aliases.get(note["source_kind"], note["source_kind"]) + " " + note["name"]).strip()
        candidates.append([i for i, event in enumerate(statement["events"])
                           if event["label"] == label and all(event[k] == note[k] for k in ("date", "debit", "credit"))])
    uses = {i: sum(i in group for group in candidates) for i in range(len(statement["events"]))}
    if any(len(group) != 1 or uses[group[0]] != 1 for group in candidates):
        fail("SKIPPED_NOTE_MATCHING_NOT_COMPLETE")
    excluded = {group[0] for group in candidates}
    return {**statement, "events": [{**event, "skip_reason": "SOURCE_ISIN_ABSENT"} if i in excluded else dict(event)
                                   for i, event in enumerate(statement["events"])]}


def match_trade_notes(statement, documents):
    if any(d["account_ref"] != statement["account_ref"] for d in documents):
        fail("NOTE_ACCOUNT_MISMATCH")
    notes = [n for d in documents for n in d["notes"] if n["kind"] != "SKIPPED_NO_ISIN"]
    if any(n["kind"] not in ("BUY", "SELL") for n in notes):
        fail("NON_TRADE_NOTES_REQUIRE_SEPARATE_REVIEW")
    trades = [e for e in statement["events"] if e["kind"] in ("BUY", "SELL") and not e.get("skip_reason")]
    keys = ("date", "kind", "unit_price", "debit", "credit")
    candidates = [[i for i, n in enumerate(notes)
                   if all(e[k] == n[k] for k in keys)
                   and e["quantity"].copy_abs() == n["quantity"].copy_abs()]
                  for e in trades]
    uses = {i: sum(i in group for group in candidates) for i in range(len(notes))}
    matches = [(e, notes[c[0]]) for e, c in zip(trades, candidates)
               if len(c) == 1 and uses[c[0]] == 1]
    blockers = set()
    if any(not c for c in candidates):
        blockers.add("TRADE_NOTE_MISSING")
    if any(len(c) > 1 or any(uses[i] > 1 for i in c) for c in candidates):
        blockers.add("TRADE_NOTE_AMBIGUOUS")
    if any(uses[i] == 0 for i in range(len(notes))):
        blockers.add("UNMATCHED_CONTRACT_NOTE")
    # Mapping and explicit currency evidence are later gates, never guessed here.
    blockers.add("EXPLICIT_PRICE_CURRENCY_REQUIRED")
    return {"matches": matches, "blockers": sorted(blockers), "note_count": len(notes),
            "missing_trades": sum(not c for c in candidates),
            "ambiguous_trades": sum(len(c) > 1 or any(uses[i] > 1 for i in c) for c in candidates),
            "unmatched_notes": sum(uses[i] == 0 for i in range(len(notes)))}


def convert_matched_trades(statement, documents, account, mappings, include_dividends=False):
    """Return private internal records only; identity and API contracts are separate."""
    if type(include_dividends) is not bool or not isinstance(account, dict) or not isinstance(mappings, dict):
        fail("INVALID_CONVERSION_CONFIGURATION")
    for key in ("source_account_ref", "account_key", "target_account_id"):
        if not isinstance(account.get(key), str) or not account[key].strip():
            fail("ACCOUNT_CONFIGURATION_MISSING")
    if statement["account_ref"] != account["source_account_ref"]:
        fail("SOURCE_ACCOUNT_MISMATCH")
    statement = match_missing_isin_skips(statement, documents)
    coupons = None
    if include_dividends and any(n["kind"] == "UNKNOWN" for doc in documents for n in doc["notes"]):
        fail("UNSUPPORTED_OPERATION_PERIOD")
    if include_dividends and (any(e["label"].startswith("COUPONS ") and not e.get("skip_reason") for e in statement["events"])
                              or any(n["kind"] == "COUPON" for doc in documents for n in doc["notes"])):
        coupons = review_coupon_cash(statement, documents)
        if "UNSUPPORTED_OPERATION_PERIOD" in coupons["blockers"]:
            fail("UNSUPPORTED_OPERATION_PERIOD")
    if any(e["kind"] not in ("BUY", "SELL") and not e.get("skip_reason")
           and not (coupons and str(e["slot"]) in coupons["coupons"]) for e in statement["events"]):
        fail("UNSUPPORTED_OPERATION_PERIOD")
    if any(e["date"].strftime("%Y-%m") != statement["period"] for e in statement["events"]):
        fail("OPERATION_OUTSIDE_STATEMENT_MONTH")
    validate_ledger(statement["controls"], statement["events"])
    trade_documents = ([{**doc, "notes": [n for n in doc["notes"] if n["kind"] != "COUPON"]} for doc in documents]
                       if include_dividends else documents)
    result = match_trade_notes(statement, trade_documents)
    if set(result["blockers"]) - {"EXPLICIT_PRICE_CURRENCY_REQUIRED"}:
        fail("NOTE_MATCHING_NOT_COMPLETE")
    records = []
    for event, note in result["matches"]:
        mapping = mappings.get(note["isin"])
        if not isinstance(mapping, dict):
            fail("SECURITY_MAPPING_MISSING")
        for key in ("symbol", "currency_evidence", "target_security_evidence"):
            if not isinstance(mapping.get(key), str) or not mapping[key].strip():
                fail("SECURITY_MAPPING_UNVERIFIED")
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,63}", mapping["symbol"]):
            fail("INVALID_TARGET_SYMBOL")
        if mapping.get("data_source") != "YAHOO":
            fail("UNSUPPORTED_TARGET_DATA_SOURCE")
        price_currency = mapping.get("execution_price_currency")
        if not price_currency or mapping.get("target_currency") != price_currency:
            fail("SECURITY_CURRENCY_CONFLICT")
        if price_currency != "EUR" or note["net_currency"] != "EUR":
            fail("UNVERIFIED_FX_SEMANTICS")
        if note["price_currency"] not in (None, price_currency):
            fail("SOURCE_PRICE_CURRENCY_CONFLICT")
        if note["vat"] != 0:
            fail("UNVERIFIED_VAT_TREATMENT")
        if note["brokerage"] < 0 or event["unit_price"] <= 0:
            fail("INVALID_TRADE_PRICE_OR_COST")
        if (event["kind"] == "BUY" and (event["quantity"] <= 0 or event["debit"] <= 0 or event["credit"])
                or event["kind"] == "SELL" and (event["quantity"] >= 0 or event["credit"] <= 0 or event["debit"])):
            fail("TRADE_DIRECTION_CONFLICT")
        if note["quantity"] != event["quantity"]:
            fail("NOTE_QUANTITY_SIGN_CONFLICT")
        if not valid_isin(note["isin"]):
            fail("INVALID_NOTE_SECURITY")
        monetary = [note[k] for k in ("gross", "brokerage", "vat")]
        monetary.extend(event[k] for k in ("quantity", "unit_price", "debit", "credit"))
        with localcontext() as context:
            context.prec = max(28, sum(len(v.as_tuple().digits) for v in monetary) + 8)
            if note["gross"] != event["quantity"].copy_abs() * event["unit_price"]:
                fail("NOTE_GROSS_MISMATCH")
            net = event["debit"] + event["credit"]
            expected = note["gross"] + note["brokerage"] if event["kind"] == "BUY" else note["gross"] - note["brokerage"]
            if expected != net:
                fail("NOTE_NET_MISMATCH")
        records.append({"account_key": account["account_key"], "target_account_id": account["target_account_id"],
                        "statement_period": statement["period"], "operation_date": event["date"],
                        "execution_time": note["execution_time"], "kind": event["kind"],
                        "source_label": event["label"], "isin": note["isin"], "symbol": mapping["symbol"],
                        "data_source": "YAHOO", "quantity": event["quantity"].copy_abs(),
                        "unit_price": event["unit_price"], "price_currency": price_currency,
                        "gross": note["gross"], "net": net, "net_currency": "EUR",
                        "brokerage": note["brokerage"], "vat": note["vat"], "fee": note["brokerage"],
                        "source_slot": event["slot"], "import_ready": False})
    mapped_symbols = {}
    for record in records:
        if record["symbol"] in mapped_symbols and mapped_symbols[record["symbol"]] != record["isin"]:
            fail("SECURITY_MAPPING_AMBIGUOUS")
        mapped_symbols[record["symbol"]] = record["isin"]
    for coupon in coupons["coupons"].values() if coupons else []:
        mapping = mappings.get(coupon["isin"])
        if mapping is None:
            fail("SECURITY_MAPPING_MISSING")
        if (not isinstance(mapping, dict) or mapping.get("data_source") != "YAHOO"
                or mapping.get("target_currency") != "EUR"
                or type(mapping.get("target_security_evidence")) is not str or not mapping["target_security_evidence"].strip()
                or type(mapping.get("symbol")) is not str
                or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,63}", mapping["symbol"])):
            fail("SECURITY_MAPPING_UNVERIFIED")
        if mapping["symbol"] in mapped_symbols and mapped_symbols[mapping["symbol"]] != coupon["isin"]:
            fail("SECURITY_MAPPING_AMBIGUOUS")
        mapped_symbols[mapping["symbol"]] = coupon["isin"]
        records.append({**coupon, "account_key": account["account_key"], "target_account_id": account["target_account_id"],
                        "statement_period": statement["period"], "symbol": mapping["symbol"], "data_source": "YAHOO",
                        "quantity": Decimal(1), "unit_price": Decimal(coupon["amount"]), "fee": Decimal(0),
                        "price_currency": "EUR"})
    return records


def review_coupon_cash(statement, documents):
    """Source cash conversion only; never an API/adoption/period-coverage artifact."""
    validate_ledger(statement["controls"], statement["events"])
    if any(e["date"].strftime("%Y-%m") != statement["period"] for e in statement["events"]):
        fail("OPERATION_OUTSIDE_STATEMENT_MONTH")
    if any(d["account_ref"] != statement["account_ref"] for d in documents):
        fail("NOTE_ACCOUNT_MISMATCH")
    if any(n["date"].strftime("%Y-%m") != statement["period"] for d in documents for n in d["notes"]):
        fail("OPERATION_OUTSIDE_STATEMENT_MONTH")
    events = [e for e in statement["events"] if e["label"].startswith("COUPONS ") and not e.get("skip_reason")]
    notes = [n for d in documents for n in d["notes"] if n["kind"] == "COUPON"]
    if not events or not notes:
        fail("COUPON_EVIDENCE_MISSING")
    candidates = [[i for i, n in enumerate(notes)
                   if e["label"] == "COUPONS " + n["name"]
                   and all(e[k] == n[k] for k in ("date", "debit", "credit"))]
                  for e in events]
    uses = {i: sum(i in group for group in candidates) for i in range(len(notes))}
    if any(len(c) != 1 or uses[c[0]] != 1 for c in candidates) or any(v != 1 for v in uses.values()):
        fail("COUPON_NOTE_MATCHING_NOT_COMPLETE")
    records = {}
    for event, indices in zip(events, candidates):
        note = notes[indices[0]]
        if not valid_isin(note["isin"]) or note["net_currency"] != "EUR":
            fail("COUPON_IDENTITY_OR_CURRENCY_UNVERIFIED")
        amounts = [note[k] for k in ("quantity", "unit_gross", "gross", "commission", "debit", "credit")]
        if any(not isinstance(v, Decimal) or not v.is_finite() for v in amounts):
            fail("INVALID_COUPON_AMOUNT")
        if (note["quantity"] >= 0 or note["unit_gross"] <= 0 or note["gross"] <= 0
                or note["commission"] < 0 or note["debit"] != 0 or note["credit"] <= 0):
            fail("COUPON_DIRECTION_CONFLICT")
        if any(not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", canonical_decimal(v))
               for v in (note["gross"], note["commission"], note["credit"])):
            fail("INVALID_CASH_PRECISION")
        tax_credit = note.get("tax_credit")
        if tax_credit is not None and (not isinstance(tax_credit, Decimal) or not tax_credit.is_finite()
                or tax_credit < 0 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", canonical_decimal(tax_credit))):
            fail("INVALID_COUPON_TAX_CREDIT")
        records[str(event["slot"])] = {
            "kind": "DIVIDEND", "isin": note["isin"], "source_name": note["name"],
            "operation_date": event["date"].isoformat(), "date_basis": "broker_booking_day",
            "amount": canonical_decimal(event["credit"]), "currency": "EUR", "amount_basis": "net_received",
            "source_label": event["label"], "source_slot": event["slot"], "note_slot": note["slot"],
            "source_fields": {k: canonical_decimal(note[k]) for k in ("quantity", "unit_gross", "gross", "commission")},
            "tax_credit": canonical_decimal(tax_credit) if tax_credit is not None else None,
            "withholding": None, "gross_semantics_verified": False, "import_ready": False}
    unsupported = sum(e["kind"] not in ("BUY", "SELL") and not e["label"].startswith("COUPONS ") and not e.get("skip_reason")
                      for e in statement["events"])
    blockers = ["DIVIDEND_DESTINATION_MAPPING_AND_API_QUALIFICATION_REQUIRED",
                "COMPLETE_PERIOD_CONVERSION_REQUIRED", "DESTINATION_RECONCILIATION_REQUIRED"]
    if unsupported or any(n["kind"] == "UNKNOWN" for d in documents for n in d["notes"]):
        blockers.append("UNSUPPORTED_OPERATION_PERIOD")
    return {"schema_version": 1, "artifact_kind": "source_coupon_cash_review_not_api_payload",
            "source_account_ref": statement["account_ref"], "statement_period": statement["period"],
            "policy": {"amount": "net_received", "date": "broker_booking_day", "historic_rewrite": False},
            "coupons": records, "unsupported_statement_operations": unsupported,
            "ledger_reconciled": True, "import_ready": False, "blockers": blockers}


def review_local_coupons(statement_path, note_paths, input_root, output, max_bytes, max_depth):
    paths = [Path(statement_path), *map(Path, note_paths)]
    if len(paths) > 257:
        fail("COUPON_INPUT_LIMIT_EXCEEDED")
    captures = [read_local_bytes(p, input_root, max_bytes) for p in paths]
    if sum(map(len, captures)) > 64 * 1024 * 1024:
        fail("COUPON_INPUT_LIMIT_EXCEEDED")
    statement = parse_statement(decode_document(captures[0]), max_depth)
    documents = [parse_contract_note(decode_document(raw), max_depth, include_coupons=True)
                 for raw in captures[1:]]
    artifact = review_coupon_cash(statement, documents)
    artifact["source_sha256"] = {str(i): hashlib.sha256(raw).hexdigest() for i, raw in enumerate(captures)}
    reject_output_input_collision(output, paths)
    validate_proposal_destination(output, paths)
    private_directory(Path(output).parent)
    atomic_private_yaml(output, artifact)
    return {"coupons": len(artifact["coupons"]), "ledger_reconciled": True,
            "unsupported_statement_operations": artifact["unsupported_statement_operations"],
            "import_ready": False, "blockers": artifact["blockers"]}


def canonical_decimal(value):
    if not isinstance(value, Decimal) or not value.is_finite():
        fail("INVALID_IDENTITY_DECIMAL")
    if not value:
        return "0"
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def validate_account_key(account_key):
    try:
        parsed = uuid.UUID(account_key)
    except (ValueError, TypeError, AttributeError):
        fail("INVALID_IMMUTABLE_ACCOUNT_KEY")
    if str(parsed) != account_key or parsed.version != 4:
        fail("INVALID_IMMUTABLE_ACCOUNT_KEY")


def ledger_identity(statement, account_key):
    """Private semantic snapshot; preserves identical occurrences without guessing."""
    validate_account_key(account_key)
    if any(e["kind"] not in ("BUY", "SELL", "DIVIDEND") and not e.get("skip_reason") for e in statement["events"]):
        fail("UNSUPPORTED_OPERATION_PERIOD")
    if any(e["date"].strftime("%Y-%m") != statement["period"] for e in statement["events"]):
        fail("OPERATION_OUTSIDE_STATEMENT_MONTH")
    validate_ledger(statement["controls"], statement["events"])
    occurrences = {}
    events = []
    normalized = []
    for event in statement["events"]:
        fields = (tuple(k for k in ("quantity", "unit_price", "debit", "credit") if k in event)
                  if event.get("skip_reason") or event["kind"] == "DIVIDEND" else ("quantity", "unit_price", "debit", "credit"))
        facts = ["v1", statement["period"], event["date"].isoformat(), "SKIPPED_NO_ISIN" if event.get("skip_reason") else event["kind"],
                 event["label"], *[canonical_decimal(event[k]) for k in
                                   fields]]
        encoded = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        occurrences[encoded] = occurrences.get(encoded, 0) + 1
        occurrence = occurrences[encoded]
        digest = hashlib.sha256(json.dumps([facts, occurrence], ensure_ascii=False,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
        events.append({"source_slot": event["slot"], "occurrence": occurrence,
                       "id": "BD#v1#" + account_key + "#" + digest})
        normalized.append(encoded)
    controls = [[c["kind"], c["date"].isoformat() if c["date"] else None,
                 canonical_decimal(c["debit"]), canonical_decimal(c["credit"])]
                for c in statement["controls"]]
    financial = ["v1", statement["period"], controls, sorted(normalized)]
    fingerprint = hashlib.sha256(json.dumps(financial, ensure_ascii=False,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"normalization_version": 1, "account_key": account_key, "period": statement["period"],
            "fingerprint": fingerprint, "events": events}


def register_statement_snapshot(journal, snapshot):
    """Return a keyed journal copy; caller owns private atomic persistence/locking."""
    validate_account_key(snapshot["account_key"])
    if snapshot.get("normalization_version") != 1:
        fail("IDENTITY_VERSION_CONFLICT")
    if not isinstance(journal, dict) or journal.get("schema_version") != 1 or not isinstance(journal.get("accounts"), dict):
        fail("INVALID_IDENTITY_JOURNAL")
    if not re.fullmatch(r"[0-9a-f]{64}", snapshot.get("fingerprint", "")):
        fail("INVALID_STATEMENT_FINGERPRINT")
    if not re.fullmatch(r"[0-9]{4}-(?:0[1-9]|1[0-2])", snapshot.get("period", "")):
        fail("INVALID_STATEMENT_PERIOD")
    accounts = journal["accounts"]
    owned = accounts.get(snapshot["account_key"], {})
    if not isinstance(owned, dict):
        fail("INVALID_IDENTITY_JOURNAL")
    previous = owned.get(snapshot["period"])
    current = {"normalization_version": 1, "fingerprint": snapshot["fingerprint"]}
    if previous is not None and previous != current:
        fail("STATEMENT_REVISION_CONFLICT")
    return {"schema_version": 1, "accounts": {**accounts,
            snapshot["account_key"]: {**owned, snapshot["period"]: current}}}


def read_keyed_yaml(path, input_root, max_bytes):
    raw = read_local_bytes(path, input_root, max_bytes)
    return parse_keyed_yaml(raw)


def parse_keyed_yaml(raw):
    try:
        contents = raw.decode("utf-8", errors="strict")
        if any(isinstance(t, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)) for t in yaml.scan(contents)):
            fail("YAML_ALIAS_NOT_SUPPORTED")
        node = yaml.compose(contents, Loader=yaml.SafeLoader)
        pending = [(node, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 32:
                fail("YAML_TOO_DEEP")
            if isinstance(item, yaml.MappingNode):
                keys = []
                for key, value in item.value:
                    if not isinstance(key, yaml.ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                        fail("YAML_STRING_KEYS_REQUIRED")
                    keys.append(key.value)
                    pending.append((value, depth + 1))
                if len(keys) != len(set(keys)):
                    fail("YAML_DUPLICATE_KEY")
            elif isinstance(item, yaml.SequenceNode):
                pending.extend((child, depth + 1) for child in item.value)
        try:
            value = yaml.safe_load(contents)
        except (KeyError, ValueError, IndexError, AttributeError):
            fail("INVALID_KEYED_YAML")
    except (yaml.YAMLError, UnicodeError, RecursionError):
        fail("INVALID_KEYED_YAML")
    if not isinstance(value, dict):
        fail("INVALID_KEYED_YAML")
    return value


def private_directory(path):
    path = Path(path)
    if path.is_symlink():
        fail("SYMLINK_PRIVATE_DIRECTORY")
    path.mkdir(mode=0o700, exist_ok=True)
    if not path.is_dir():
        fail("PRIVATE_DIRECTORY_NOT_REGULAR")
    path.chmod(0o700)
    return path


def atomic_private_yaml(path, value):
    atomic_private_bytes(path, yaml.safe_dump(value, sort_keys=False, allow_unicode=True).encode("utf-8"))


def atomic_private_bytes(path, raw):
    path = Path(path)
    temporary = "." + path.name + "." + uuid.uuid4().hex
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    created = False
    try:
        try:
            existing = os.stat(path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and stat.S_ISLNK(existing.st_mode):
            fail("SYMLINK_PRIVATE_FILE")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        created = True
        try:
            stream = os.fdopen(descriptor, "wb")
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    finally:
        try:
            if created:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except FileNotFoundError:
                    pass
        finally:
            os.close(directory)


def preparation_configuration(config_raw, max_bytes, max_depth):
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_SIZE_LIMIT")
    if type(max_depth) is not int or max_depth <= 0:
        fail("INVALID_DEPTH_LIMIT")
    if type(config_raw) is not bytes or len(config_raw) > max_bytes:
        fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    config = parse_keyed_yaml(config_raw)
    if set(config) != {"schema_version", "account", "mappings", "documents"} or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        fail("INVALID_PREPARATION_CONFIGURATION")
    account = config["account"]
    if not isinstance(account, dict) or set(account) != {"source_account_ref", "account_key", "target_account_id"}:
        fail("INVALID_ACCOUNT_CONFIGURATION")
    validate_account_key(account["account_key"])
    if not isinstance(account["target_account_id"], str) or not account["target_account_id"].strip():
        fail("ACCOUNT_CONFIGURATION_MISSING")
    entries = config["documents"]
    if not isinstance(entries, dict) or not entries:
        fail("PREPARATION_DOCUMENTS_MISSING")
    for alias, entry in entries.items():
        if not isinstance(alias, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", alias):
            fail("INVALID_DOCUMENT_ALIAS")
        if not isinstance(entry, dict) or set(entry) != {"statement", "notes"}:
            fail("INVALID_DOCUMENT_CONFIGURATION")
        if not isinstance(entry["statement"], str) or not isinstance(entry["notes"], list) or not entry["notes"] or not all(isinstance(n, str) for n in entry["notes"]):
            fail("INVALID_DOCUMENT_CONFIGURATION")
    return config


def capture_period(role, period):
    if type(period) is not str or role not in ("statement", "note"):
        fail("INVALID_CAPTURE_PERIOD")
    pattern = r"[0-9]{4}-[0-9]{2}" if role == "statement" else r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    if not re.fullmatch(pattern, period):
        fail("INVALID_CAPTURE_PERIOD")
    try:
        datetime.strptime(period, "%Y-%m" if role == "statement" else "%Y-%m-%d")
    except ValueError:
        fail("INVALID_CAPTURE_PERIOD")


def parse_capture_document(raw, role, period, account_ref, max_depth):
    capture_period(role, period)
    html = decode_document(raw)
    parsed = parse_statement(html, max_depth) if role == "statement" else parse_contract_note(html, max_depth)
    if parsed["account_ref"] != account_ref:
        fail("CAPTURE_ACCOUNT_CONFLICT")
    if role == "statement":
        if parsed["period"] != period:
            fail("CAPTURE_PERIOD_CONFLICT")
    elif not parsed["notes"] or any(n["date"].isoformat() != period for n in parsed["notes"]):
        fail("CAPTURE_PERIOD_CONFLICT")
    return parsed


def filter_capture_dom(raw, role, period, account_ref, max_bytes, max_depth):
    """Financial DOM only; not original HTTP bytes or authenticated freshness."""
    if type(max_bytes) is not int or max_bytes <= 0 or type(max_depth) is not int or max_depth <= 0:
        fail("INVALID_CAPTURE_LIMITS")
    if type(raw) is not bytes or len(raw) > min(max_bytes, 4 * 1024 * 1024):
        fail("CAPTURE_SIZE_LIMIT")
    before = parse_capture_document(raw, role, period, account_ref, max_depth)
    soup = BeautifulSoup(decode_document(raw), "html.parser")
    for node in soup.find_all(["script", "style", "base", "form", "input", "button", "textarea",
                               "select", "iframe", "frame", "link", "img", "object", "embed", "meta"]):
        node.decompose()
    for node in soup.find_all("a"):
        node.unwrap()
    for node in soup.find_all(string=lambda item: isinstance(item, Comment)):
        node.extract()
    for node in soup.find_all(string=lambda item: not item.strip()):
        node.extract()
    for node in soup.find_all(True):
        node.attrs = {k: v for k, v in node.attrs.items() if k in ("colspan", "rowspan")}
    meta = soup.new_tag("meta", charset="utf-8")
    if soup.head is not None:
        soup.head.insert(0, meta)
    else:
        soup.insert(0, meta)
    filtered = str(soup).encode("utf-8")
    if len(filtered) > min(max_bytes, 4 * 1024 * 1024):
        fail("CAPTURE_SIZE_LIMIT")
    if parse_capture_document(filtered, role, period, account_ref, max_depth) != before:
        fail("CAPTURE_FILTER_CHANGED_LEDGER")
    return filtered


def validate_capture_ticket(ticket, entry, account_ref):
    keys = {"account_ref", "role", "period", "origin_frame_epoch", "link_handle", "request_url",
            "target_id", "loader_id", "commit_loader_id", "load_loader_id", "sequence"}
    if not isinstance(ticket, dict) or set(ticket) != keys:
        fail("INVALID_CAPTURE_TICKET")
    if any(ticket[k] != v for k, v in (("account_ref", account_ref), ("role", entry["role"]),
                                      ("period", entry["period"]))):
        fail("CAPTURE_TICKET_CONFLICT")
    for key in ("origin_frame_epoch", "link_handle", "target_id", "loader_id", "commit_loader_id", "load_loader_id"):
        validate_account_key(ticket[key])
    if ticket["loader_id"] != ticket["commit_loader_id"] or ticket["loader_id"] != ticket["load_loader_id"]:
        fail("CAPTURE_TICKET_CONFLICT")
    if type(ticket["sequence"]) is not int or not 1 <= ticket["sequence"] <= 1000:
        fail("INVALID_CAPTURE_TICKET")
    url = ticket["request_url"]
    if type(url) is not str or len(url) > 4096 or not url.startswith("https://www.boursedirect.fr/"):
        fail("INVALID_CAPTURE_TICKET_URL")
    try:
        parts = urlsplit(url)
    except ValueError:
        fail("INVALID_CAPTURE_TICKET_URL")
    if (parts.scheme != "https" or parts.netloc != "www.boursedirect.fr" or parts.fragment
            or any(c.isspace() or ord(c) < 32 for c in url) or "\\" in url
            or re.search(r"%(?:2f|5c|2e)", parts.path, re.I) or any(p in (".", "..") for p in parts.path.split("/"))):
        fail("INVALID_CAPTURE_TICKET_URL")


def qualify_capture_bundle(manifest_raw, files, config_raw, max_bytes, max_depth):
    """Pure saved-evidence qualification; tickets are trusted, unauthenticated input."""
    if type(max_bytes) is not int or not 0 < max_bytes <= 4 * 1024 * 1024:
        fail("CAPTURE_SIZE_LIMIT")
    if type(max_depth) is not int or not 0 < max_depth <= 256:
        fail("INVALID_CAPTURE_LIMITS")
    if type(manifest_raw) is not bytes or len(manifest_raw) > min(max_bytes, 1024 * 1024):
        fail("CAPTURE_MANIFEST_LIMIT")
    config = preparation_configuration(config_raw, min(max_bytes, 1024 * 1024), max_depth)
    manifest = parse_keyed_yaml(manifest_raw)
    if (set(manifest) != {"schema_version", "artifact_kind", "status", "run_id", "account_key", "source_account_ref", "files"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or manifest["artifact_kind"] != "acquisition_bundle" or manifest["status"] != "complete"):
        fail("INVALID_COMPLETE_CAPTURE_MANIFEST")
    validate_account_key(manifest["run_id"])
    account = config["account"]
    if manifest["account_key"] != account["account_key"] or manifest["source_account_ref"] != account["source_account_ref"]:
        fail("CAPTURE_ACCOUNT_CONFLICT")
    entries = manifest["files"]
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 256 or not isinstance(files, dict) or set(files) != set(entries):
        fail("CAPTURE_FILE_INVENTORY_CONFLICT")
    if any(type(raw) is not bytes or len(raw) > max_bytes for raw in files.values()):
        fail("CAPTURE_SIZE_LIMIT")
    if sum(map(len, files.values())) > 64 * 1024 * 1024:
        fail("CAPTURE_TOTAL_LIMIT")
    seen, sequences, statements, notes = set(), set(), {}, {}
    for filename, entry in entries.items():
        if type(filename) is not str or not re.fullmatch(r"capture-[0-9a-f-]{36}\.html", filename):
            fail("INVALID_CAPTURE_FILENAME")
        validate_account_key(filename[8:-5])
        if not isinstance(entry, dict) or set(entry) != {"role", "period", "sha256", "provenance", "ticket"}:
            fail("INVALID_CAPTURE_ENTRY")
        capture_period(entry["role"], entry["period"])
        key = (entry["role"], entry["period"])
        if key in seen:
            fail("DUPLICATE_CAPTURE_ROLE_PERIOD")
        seen.add(key)
        if entry["provenance"] != "browser_dom_utf8_filtered":
            fail("CAPTURE_PROVENANCE_REQUIRED")
        if type(entry["sha256"]) is not str or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            fail("INVALID_CAPTURE_DIGEST")
        raw = files[filename]
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            fail("CAPTURE_DIGEST_CONFLICT")
        validate_capture_ticket(entry["ticket"], entry, account["source_account_ref"])
        sequence = entry["ticket"]["sequence"]
        if sequence in sequences:
            fail("DUPLICATE_CAPTURE_SEQUENCE")
        sequences.add(sequence)
        # Refiltering must be semantically identical and already free of active DOM.
        filtered = filter_capture_dom(raw, entry["role"], entry["period"], account["source_account_ref"], max_bytes, max_depth)
        if raw != filtered:
            fail("CAPTURE_NOT_FILTERED_UTF8")
        if entry["role"] == "statement":
            statements[entry["period"]] = filename
        else:
            notes[entry["period"]] = filename
    if not statements or any(day[:7] not in statements for day in notes):
        fail("CAPTURE_MONTH_COVERAGE_CONFLICT")
    documents = {}
    captures = {}
    for month, filename in sorted(statements.items()):
        matching = [notes[day] for day in sorted(notes) if day[:7] == month]
        if not matching:
            fail("CAPTURE_NOTES_MISSING")
        alias = "month-" + month
        documents[alias] = {"statement": filename, "notes": matching}
        captures[alias] = {"statement": files[filename], "notes": [files[n] for n in matching]}
    proposal = {**config, "documents": documents}
    proposed_raw = yaml.safe_dump(proposal, sort_keys=False).encode("utf-8")
    result = compute_prepared_sources(proposed_raw, captures, max_bytes, max_depth)
    return {"configuration": proposal, "report": {"schema_version": 1,
        "artifact_kind": "qualified_capture_proposal_not_import", "import_ready": False,
        "freshness_verified": False, "source_authenticity_verified": False,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "configuration_sha256": hashlib.sha256(config_raw).hexdigest(),
        "run_id": manifest["run_id"], "account_key": account["account_key"],
        "file_count": len(files), "statement_periods": len(statements),
        "prepared_activities": len(result["artifact"]["activities"]),
        "files": {name: {"role": entry["role"], "period": entry["period"],
                         "sha256": entry["sha256"], "sequence": entry["ticket"]["sequence"]}
                  for name, entry in entries.items()}}}


def capture_path_without_symlinks(path):
    path = Path(os.path.abspath(path))
    for ancestor in (path, *path.parents):
        if ancestor.is_symlink():
            fail("CAPTURE_SYMLINK_PATH")
    return path


def qualify_local_captures(manifest_path, config_path, input_root, output, max_bytes, max_depth):
    if type(max_bytes) is not int or not 0 < max_bytes <= 4 * 1024 * 1024:
        fail("CAPTURE_SIZE_LIMIT")
    root = capture_path_without_symlinks(input_root).resolve(strict=True)
    manifest_path = capture_path_without_symlinks(manifest_path)
    config_path = capture_path_without_symlinks(config_path)
    manifest_raw = read_local_bytes(manifest_path, root, min(max_bytes, 1024 * 1024))
    config_raw = read_local_bytes(config_path, root, min(max_bytes, 1024 * 1024))
    manifest = parse_keyed_yaml(manifest_raw)
    entries = manifest.get("files")
    if not isinstance(entries, dict) or not 1 <= len(entries) <= 256:
        fail("CAPTURE_FILE_INVENTORY_CONFLICT")
    bundle = manifest_path.parent
    if manifest_path.name != "manifest.yaml" or set(p.name for p in bundle.iterdir()) != {"manifest.yaml", "sources"}:
        fail("CAPTURE_FILE_INVENTORY_CONFLICT")
    sources = capture_path_without_symlinks(bundle / "sources")
    if not sources.is_dir() or set(p.name for p in sources.iterdir()) != set(entries):
        fail("CAPTURE_FILE_INVENTORY_CONFLICT")
    paths = [manifest_path, config_path]
    files = {}
    total = 0
    for filename in entries:
        if type(filename) is not str or not re.fullmatch(r"capture-[0-9a-f-]{36}\.html", filename):
            fail("INVALID_CAPTURE_FILENAME")
        source = capture_path_without_symlinks(sources / filename)
        files[filename] = read_local_bytes(source, root, min(max_bytes, 4 * 1024 * 1024))
        total += len(files[filename])
        if total > 64 * 1024 * 1024:
            fail("CAPTURE_TOTAL_LIMIT")
        paths.append(source)
    destination = capture_path_without_symlinks(output)
    reject_output_input_collision(destination, paths)
    if destination.exists():
        fail("CAPTURE_OUTPUT_EXISTS")
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        fail("CAPTURE_OUTPUT_INPUT_TREE_CONFLICT")
    parent = destination.parent
    mode = parent.stat()
    if not parent.is_dir() or mode.st_uid != os.getuid() or stat.S_IMODE(mode.st_mode) & 0o077:
        fail("CAPTURE_OUTPUT_PARENT_NOT_PRIVATE")
    qualified = qualify_capture_bundle(manifest_raw, files, config_raw, max_bytes, max_depth)
    for entry in qualified["configuration"]["documents"].values():
        entry["statement"] = str(sources / entry["statement"])
        entry["notes"] = [str(sources / n) for n in entry["notes"]]
    # Exclusive directory publication never replaces an input, prior proposal, or alias.
    destination.mkdir(mode=0o700)
    atomic_private_yaml(destination / "prepare-proposal.yaml", qualified["configuration"])
    atomic_private_yaml(destination / "qualification.yaml", qualified["report"])
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return {k: qualified["report"][k] for k in ("import_ready", "freshness_verified", "source_authenticity_verified",
                                               "file_count", "statement_periods", "prepared_activities")}


def compute_prepared_sources(config_raw, documents, max_bytes, max_depth):
    """Pure current-config derivation; no historical config authenticity claim."""
    config = preparation_configuration(config_raw, max_bytes, max_depth)
    entries = config["documents"]
    account = config["account"]
    if not isinstance(documents, dict) or set(documents) != set(entries):
        fail("INVALID_PREPARATION_CAPTURES")
    # Check every capture before parsing even the first HTML document.
    for alias, entry in entries.items():
        capture = documents[alias]
        if (not isinstance(capture, dict) or set(capture) != {"statement", "notes"}
                or not isinstance(capture["notes"], list)
                or len(capture["notes"]) != len(entry["notes"])):
            fail("INVALID_PREPARATION_CAPTURES")
        for raw in [capture["statement"], *capture["notes"]]:
            if type(raw) is not bytes or len(raw) > max_bytes:
                fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    plans = []
    snapshots = []
    raw_digests = {}
    seen_periods = set()
    for alias in entries:
        capture = documents[alias]
        statement_raw = capture["statement"]
        statement = parse_statement(decode_document(statement_raw), max_depth)
        if statement["period"] in seen_periods:
            fail("DUPLICATE_STATEMENT_PERIOD")
        seen_periods.add(statement["period"])
        notes = [parse_contract_note(decode_document(raw), max_depth, include_coupons=True, skip_missing_isin=True) for raw in capture["notes"]]
        statement = match_missing_isin_skips(statement, notes)
        activities = convert_matched_trades(statement, notes, account, config["mappings"], include_dividends=True)
        coupon_slots = {a["source_slot"] for a in activities if a["kind"] == "DIVIDEND"}
        statement = {**statement, "events": [{**e, "kind": "DIVIDEND"} if e["slot"] in coupon_slots else e for e in statement["events"]]}
        snapshot = ledger_identity(statement, account["account_key"])
        identities = {e["source_slot"]: e["id"] for e in snapshot["events"]}
        for activity in activities:
            output = {k: canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v
                      for k, v in activity.items()}
            output["id"] = identities[activity["source_slot"]]
            output["document_alias"] = alias
            plans.append(output)
        snapshots.append(snapshot)
        raw_digests[alias] = {"statement": hashlib.sha256(statement_raw).hexdigest(),
                              "notes": [hashlib.sha256(raw).hexdigest() for raw in capture["notes"]]}
    plans.sort(key=lambda a: (a["operation_date"], a["id"]))
    artifact = {"schema_version": 1, "artifact_kind": "internal_activity_review_not_api_payload",
                "import_ready": False, "blockers": ["REMOTE_ADOPTION_UNVERIFIED", "ISOLATED_API_CONTRACT_UNVERIFIED"],
                "account_key": account["account_key"], "target_account_id": account["target_account_id"],
                "source_digests": raw_digests, "activities": {a["id"]: a for a in plans}}
    return {"artifact": artifact, "snapshots": snapshots}


def validate_prepared_sources(prepared_raw, config_raw, documents, max_bytes, max_depth):
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_SIZE_LIMIT")
    if (type(prepared_raw) is not bytes or len(prepared_raw) > max_bytes
            or type(config_raw) is not bytes or len(config_raw) > max_bytes):
        fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    config = parse_keyed_yaml(config_raw)
    result = (compute_prepared_notices(config_raw, documents, max_bytes, max_depth)
              if config.get("source_mode") == "notices" else compute_prepared_sources(config_raw, documents, max_bytes, max_depth))
    observed = parse_keyed_yaml(prepared_raw)
    expected = result["artifact"]
    if yaml.safe_dump(observed, sort_keys=True, allow_unicode=True) != yaml.safe_dump(expected, sort_keys=True, allow_unicode=True):
        fail("PREPARED_SOURCE_CONTENT_CONFLICT")
    return expected


def capture_preparation_sources(config_raw, input_root, max_bytes, max_depth):
    if type(max_bytes) is not int or max_bytes <= 0 or type(config_raw) is not bytes or len(config_raw) > max_bytes:
        fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    if parse_keyed_yaml(config_raw).get("source_mode") == "notices":
        config = notice_preparation_configuration(config_raw, max_bytes, max_depth)
        paths = [Path(input_root) / entry["document"] for entry in config["notices"].values()]
        return {alias: {"notice": read_local_bytes(path, input_root, max_bytes)}
                for (alias, entry), path in zip(config["notices"].items(), paths)}, paths
    config = preparation_configuration(config_raw, max_bytes, max_depth)
    documents = {}
    input_paths = []
    for alias, entry in config["documents"].items():
        statement_path = Path(input_root) / entry["statement"]
        note_paths = [Path(input_root) / path for path in entry["notes"]]
        input_paths.extend([statement_path, *note_paths])
        documents[alias] = {"statement": read_local_bytes(statement_path, input_root, max_bytes),
                            "notes": [read_local_bytes(path, input_root, max_bytes) for path in note_paths]}
    return documents, input_paths


def prepare_local_plan(config_path, input_root, max_bytes, max_depth):
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    notice_only = parse_keyed_yaml(config_raw).get("source_mode") == "notices"
    config = (notice_preparation_configuration(config_raw, max_bytes, max_depth) if notice_only
              else preparation_configuration(config_raw, max_bytes, max_depth))
    documents, document_paths = capture_preparation_sources(config_raw, input_root, max_bytes, max_depth)
    input_paths = [Path(config_path), *document_paths]
    computed = (compute_prepared_notices(config_raw, documents, max_bytes, max_depth) if notice_only
                else compute_prepared_sources(config_raw, documents, max_bytes, max_depth))
    artifact = computed["artifact"]
    snapshots = computed.get("snapshots", [])
    account = config["account"]
    state = Path("state")
    output_root = Path("outputs")
    target = hashlib.sha256(account["target_account_id"].encode("utf-8")).hexdigest()
    journal_path = state / (("notice-preparation-" if notice_only else "ledger-") + target + ".yaml")
    binding_path = state / ("binding-" + account["account_key"] + ".yaml")
    artifact_path = output_root / ("prepared-" + account["account_key"] + ".yaml")
    for destination in (journal_path, binding_path, artifact_path,
                        state / ("prepare-" + target + ".lock"),
                        state / ("account-" + account["account_key"] + ".lock")):
        reject_output_input_collision(destination, input_paths)
    private_directory(state)
    private_directory(output_root)
    lock = os.open(state / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    namespace_lock = None
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_PREPARATION_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("PREPARATION_TARGET_LOCKED")
        namespace_lock = os.open(state / ("account-" + account["account_key"] + ".lock"),
                                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        if not stat.S_ISREG(os.fstat(namespace_lock).st_mode):
            fail("INVALID_PREPARATION_LOCK")
        try:
            fcntl.flock(namespace_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("PREPARATION_ACCOUNT_LOCKED")
        binding = {k: account[k] for k in ("source_account_ref", "account_key", "target_account_id")}
        if binding_path.exists() or binding_path.is_symlink():
            if read_keyed_yaml(binding_path, state, max_bytes) != binding:
                fail("ACCOUNT_BINDING_MIGRATION_REQUIRED")
        if journal_path.exists() or journal_path.is_symlink():
            journal = read_keyed_yaml(journal_path, state, max_bytes)
            if journal.get("binding") != binding:
                fail("ACCOUNT_BINDING_MIGRATION_REQUIRED")
        else:
            journal = {"schema_version": 1, "accounts": {}}
        if notice_only:
            if journal_path.exists() or journal_path.is_symlink():
                if (set(journal) != {"schema_version", "binding", "notice_hashes", "as_of"}
                        or type(journal["schema_version"]) is not int or journal["schema_version"] != 1
                        or not isinstance(journal["notice_hashes"], dict)
                        or daily_preview_day(journal["as_of"]) > daily_preview_day(config["as_of"])):
                    fail("INVALID_NOTICE_JOURNAL")
                hashes = dict(journal["notice_hashes"])
            else:
                hashes = {}
            for saved_day, digest in hashes.items():
                capture_period("note", saved_day)
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    fail("INVALID_NOTICE_JOURNAL")
            for alias, entry in config["notices"].items():
                digest = artifact["source_digests"][alias]["notice"]
                if entry["date"] in hashes and hashes[entry["date"]] != digest:
                    fail("NOTICE_SOURCE_REVISION")
                hashes[entry["date"]] = digest
            journal = {"schema_version": 1, "binding": binding, "notice_hashes": hashes, "as_of": config["as_of"]}
        for snapshot in snapshots:
            journal = register_statement_snapshot(journal, snapshot)
        journal["binding"] = binding
        # Persist revision guard first. Failed artifact write can be retried safely;
        # neither file is evidence that an external activity was created.
        atomic_private_yaml(binding_path, binding)
        atomic_private_yaml(journal_path, journal)
        atomic_private_yaml(artifact_path, artifact)
        return {"prepared_activities": len(artifact["activities"]), "statement_periods": len(snapshots),
                "import_ready": False, "blockers": artifact["blockers"]}
    finally:
        if namespace_lock is not None:
            os.close(namespace_lock)
        os.close(lock)


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def remote_decimal(value):
    # json.loads(parse_float=Decimal) avoids rounding through binary Python floats.
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        fail("REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED")
    number = Decimal(value)
    if not number.is_finite():
        fail("REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED")
    return number


def remote_active_context(activity):
    account = activity.get("account")
    unassigned = activity.get("accountId") is None and "account" in activity and account is None
    if not unassigned and not isinstance(account, dict):
        fail("REMOTE_ACCOUNT_CONTEXT_MISSING")
    if not unassigned and account.get("id") != activity["accountId"]:
        fail("REMOTE_ACCOUNT_CONTEXT_CONFLICT")
    if "isActive" in activity and not isinstance(activity["isActive"], bool):
        fail("REMOTE_ACTIVE_FLAG_INVALID")
    inactive = unassigned or activity.get("isActive") is False
    reserved = {"0c077abd-eca2-4cbb-818c-6cefbf2d169a", "f2e868af-8333-459f-b161-cbc6544c24bd"}
    for context in (activity,) if unassigned else (activity, account):
        for flag in ("isDraft", "isExcluded"):
            if flag in context:
                if not isinstance(context[flag], bool):
                    fail("REMOTE_ACTIVE_FLAG_INVALID")
                inactive = inactive or context[flag]
        tags = context.get("tags")
        if not isinstance(tags, list) or any(not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"] for t in tags):
            fail("REMOTE_ACTIVE_TAGS_MISSING_OR_INVALID")
        inactive = inactive or any(t["id"] in reserved for t in tags)
    return not inactive


def parse_remote_activity_snapshot(raw, retain_stored_date=False):
    try:
        data = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_json_object)
    except (ValueError, TypeError, RecursionError):
        fail("INVALID_REMOTE_ACTIVITY_JSON")
    if not isinstance(data, dict) or not isinstance(data.get("activities"), list):
        fail("INVALID_REMOTE_ACTIVITY_SNAPSHOT")
    if type(data.get("count")) is not int or data["count"] != len(data["activities"]):
        fail("REMOTE_ACTIVITY_COUNT_MISMATCH")
    normalized = []
    seen = set()
    for row in data["activities"]:
        if not isinstance(row, dict):
            fail("INVALID_REMOTE_ACTIVITY_SNAPSHOT")
        for key in ("id", "type", "date"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                fail("REMOTE_ACTIVITY_CONTEXT_MISSING")
        if "accountId" not in row or row["accountId"] is not None and (not isinstance(row["accountId"], str) or not row["accountId"].strip()):
            fail("REMOTE_ACTIVITY_CONTEXT_MISSING")
        if row["accountId"] is None and ("account" not in row or row["account"] is not None):
            fail("REMOTE_ACCOUNT_CONTEXT_CONFLICT")
        profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile")
        if "currency" not in row:
            fail("REMOTE_ACTIVITY_CONTEXT_MISSING")
        inherited_currency = row["currency"] is None
        price_currency = profile.get("currency") if inherited_currency and isinstance(profile, dict) else row["currency"]
        if not isinstance(price_currency, str) or not price_currency.strip():
            fail("REMOTE_ACTIVITY_CONTEXT_MISSING")
        if row["id"] in seen:
            fail("REMOTE_ACTIVITY_ID_DUPLICATE")
        seen.add(row["id"])
        if "comment" not in row or row["comment"] is not None and not isinstance(row["comment"], str):
            fail("REMOTE_COMMENT_CONTEXT_MISSING")
        amount = {k: remote_decimal(row.get(k)) for k in ("quantity", "unitPrice", "fee")}
        active = remote_active_context(row)
        try:
            instant = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
        except ValueError:
            fail("INVALID_REMOTE_ACTIVITY_DATE")
        if instant.tzinfo is None:
            fail("REMOTE_ACTIVITY_TIMEZONE_MISSING")
        utc = instant.astimezone(timezone.utc)
        active = active and utc <= datetime.now(timezone.utc)
        financial_context_verified = True
        if row["type"] in ("BUY", "SELL"):
            if amount["quantity"] <= 0 or amount["unitPrice"] < 0 or amount["fee"] < 0:
                fail("INVALID_REMOTE_TRADE_AMOUNT")
            if not isinstance(profile, dict):
                fail("REMOTE_ASSET_PROFILE_INVALID")
            for key in ("symbol", "dataSource", "currency"):
                if not isinstance(profile.get(key), str) or not profile[key].strip():
                    fail("REMOTE_ASSET_PROFILE_INVALID")
            financial_context_verified = profile["currency"] == price_currency and amount["unitPrice"] > 0
            symbol, source = profile["symbol"], profile["dataSource"]
        elif row["type"] == "DIVIDEND":
            # Preserve legacy cash rows for inspection even without a usable
            # profile; only exact positive Yahoo/EUR context can qualify.
            valid_profile = isinstance(profile, dict) and all(isinstance(profile.get(k), str) and profile[k].strip()
                                                           for k in ("symbol", "dataSource", "currency"))
            symbol, source = (profile["symbol"], profile["dataSource"]) if valid_profile else (None, None)
            financial_context_verified = bool(valid_profile and profile["currency"] == price_currency
                                              and amount["quantity"] > 0 and amount["unitPrice"] > 0 and amount["fee"] >= 0)
        else:
            symbol, source = None, None
        normalized.append({"remote_id": row["id"], "target_account_id": row["accountId"],
                           "kind": row["type"], "symbol": symbol, "data_source": source,
                           "price_currency": price_currency, "quantity": amount["quantity"],
                           "currency_origin": "asset_profile_default" if inherited_currency else "explicit",
                           "financial_context_verified": financial_context_verified,
                           "unit_price": amount["unitPrice"], "fee": amount["fee"],
                           "operation_date": utc.date().isoformat(),
                           "date_context_verified": utc.hour == utc.minute == utc.second == utc.microsecond == 0,
                           "active": active, "comment": row["comment"]})
        if retain_stored_date:
            normalized[-1]["stored_date"] = row["date"]
            normalized[-1]["stored_activity"] = json.dumps(row, sort_keys=True, default=canonical_decimal)
    return normalized


def activity_financial_fingerprint(activity):
    fields = ("target_account_id", "operation_date", "kind", "symbol", "data_source", "price_currency")
    values = [activity[k].isoformat() if hasattr(activity[k], "isoformat") else activity[k] for k in fields]
    for key in ("quantity", "unit_price", "fee"):
        value = activity[key]
        if isinstance(value, str):
            if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
                fail("INVALID_ACTIVITY_DECIMAL")
            value = Decimal(value)
        values.append(canonical_decimal(value))
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def compare_coupon_snapshot(source_reviews, account, mappings, snapshot_raw):
    """Exact representation observations and retained legacy uncertainty; no writes."""
    if not isinstance(account, dict) or set(account) != {"account_key", "source_account_ref", "target_account_id"}:
        fail("INVALID_ACCOUNT_CONFIGURATION")
    validate_account_key(account["account_key"])
    if any(type(account[k]) is not str or not account[k].strip() for k in ("source_account_ref", "target_account_id")):
        fail("ACCOUNT_CONFIGURATION_MISSING")
    if not isinstance(mappings, dict) or not isinstance(source_reviews, dict) or not source_reviews:
        fail("INVALID_COUPON_RECONCILIATION")
    remote = parse_remote_activity_snapshot(snapshot_raw)
    original = json.loads(snapshot_raw, parse_float=Decimal, object_pairs_hook=unique_json_object)
    originals = {r["id"]: r for r in original["activities"]}
    coupons, periods = {}, set()
    for review in source_reviews.values():
        if (review.get("artifact_kind") != "source_coupon_cash_review_not_api_payload"
                or review.get("import_ready") is not False or review.get("source_account_ref") != account["source_account_ref"]
                or review.get("policy") != {"amount": "net_received", "date": "broker_booking_day", "historic_rewrite": False}):
            fail("INVALID_COUPON_RECONCILIATION_SOURCE")
        period = review["statement_period"]
        if period in periods:
            fail("MULTIPLE_STATEMENT_VERSIONS")
        periods.add(period)
        for slot, coupon in review["coupons"].items():
            coupons[period + "/" + slot] = coupon
    if len(coupons) * len(remote) > 1000000:
        fail("DIAGNOSIS_COMPARISON_LIMIT_EXCEEDED")
    source_keys, mapped_isins = {}, {}
    observations, remote_evidence, exact = {}, {}, {}
    for key, coupon in coupons.items():
        mapping = mappings.get(coupon["isin"])
        if mapping is None:
            observations[key] = {"isin": coupon["isin"], "status": "SECURITY_MAPPING_MISSING", "candidates": {}}
            continue
        if (not isinstance(mapping, dict) or mapping.get("data_source") != "YAHOO"
                or mapping.get("target_currency") != "EUR"
                or type(mapping.get("target_security_evidence")) is not str or not mapping["target_security_evidence"].strip()
                or type(mapping.get("symbol")) is not str
                or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,63}", mapping["symbol"])):
            fail("SECURITY_MAPPING_UNVERIFIED")
        if mapping["symbol"] in mapped_isins and mapped_isins[mapping["symbol"]] != coupon["isin"]:
            fail("SECURITY_MAPPING_AMBIGUOUS")
        mapped_isins[mapping["symbol"]] = coupon["isin"]
        amount = Decimal(coupon["amount"])
        signature = (coupon["operation_date"], mapping["symbol"], canonical_decimal(amount))
        source_keys[key] = signature
        candidates, exact[key] = {}, []
        for row in remote:
            if row["kind"] != "DIVIDEND" or row["target_account_id"] != account["target_account_id"]:
                continue
            raw = originals[row["remote_id"]]
            profile = raw["assetProfile"] if "assetProfile" in raw else raw.get("SymbolProfile")
            if not isinstance(profile, dict):
                fail("REMOTE_ASSET_PROFILE_INVALID")
            if profile.get("symbol") != mapping["symbol"]:
                continue
            if any(type(profile.get(k)) is not str or not profile[k].strip() for k in ("symbol", "dataSource", "currency")):
                fail("REMOTE_ASSET_PROFILE_INVALID")
            with localcontext() as context:
                context.prec = max(28, sum(len(v.as_tuple().digits) for v in (row["quantity"], row["unit_price"], row["fee"], amount)) + 8)
                product = row["quantity"] * row["unit_price"]
                delta = product - amount
            same = (row["operation_date"] == coupon["operation_date"] and row["quantity"] == 1
                    and row["unit_price"] == amount and row["fee"] == 0
                    and row["price_currency"] == profile["currency"] == "EUR" and profile["dataSource"] == "YAHOO")
            financial = (row["quantity"] > 0 and row["unit_price"] > 0 and row["fee"] >= 0
                         and row["price_currency"] == profile["currency"] == "EUR" and profile["dataSource"] == "YAHOO")
            eligible = financial and row["active"] and row["date_context_verified"]
            foreign = isinstance(row["comment"], str) and row["comment"].startswith("BD#")
            if same:
                exact[key].append(row["remote_id"])
            candidates[row["remote_id"]] = {"exact_net_representation": same, "eligible": eligible,
                "foreign_BD_ownership": foreign, "same_quantity_price_product": product == amount,
                "product_minus_source_cash": canonical_decimal(delta),
                "utc_day_minus_source_day": (datetime.fromisoformat(row["operation_date"]).date()
                    - datetime.fromisoformat(coupon["operation_date"]).date()).days}
            remote_evidence[row["remote_id"]] = {"original_timestamp": raw["date"], "utc_day": row["operation_date"],
                "symbol": profile["symbol"], "data_source": profile["dataSource"],
                "price_currency": row["price_currency"], "profile_currency": profile["currency"],
                "quantity": canonical_decimal(row["quantity"]), "unit_price": canonical_decimal(row["unit_price"]),
                "quantity_price_product": canonical_decimal(product), "fee": canonical_decimal(row["fee"]),
                "active_at_evaluation": row["active"], "date_context_verified": row["date_context_verified"]}
        observations[key] = {"isin": coupon["isin"], "symbol": mapping["symbol"],
            "source_booking_day": coupon["operation_date"], "net_received": coupon["amount"],
            "candidates": candidates, "status": "LEGACY_CANDIDATES_REQUIRE_REVIEW" if candidates else "NO_CANDIDATE_IN_SAVED_SNAPSHOT"}
    # Assignment is global across all supplied source periods, not greedy per row.
    for key, ids in exact.items():
        if not ids:
            continue
        unique_source = sum(value == source_keys[key] for value in source_keys.values()) == 1
        unique_remote = len(ids) == 1 and sum(ids[0] in group for group in exact.values()) == 1
        candidate = observations[key]["candidates"][ids[0]]
        certain = unique_source and unique_remote and candidate["eligible"] and not candidate["foreign_BD_ownership"]
        observations[key]["status"] = "CERTAIN_UNIQUE_NET_REPRESENTATION_OBSERVED" if certain else "DIVIDEND_MATCH_UNCERTAIN"
        if certain:
            observations[key]["certain_remote_id"] = ids[0]
    blockers = ["COMPLETE_PERIOD_CONVERSION_REQUIRED", "ACQUISITION_HISTORY_UNVERIFIED", "DIVIDEND_APPLICATION_NOT_ACTIVATED"]
    if any("UNSUPPORTED_OPERATION_PERIOD" in review["blockers"] for review in source_reviews.values()):
        blockers.append("UNSUPPORTED_OPERATION_PERIOD")
    return {"schema_version": 1, "artifact_kind": "coupon_reconciliation_preview_not_api_payload",
        "account_key": account["account_key"], "target_account_id": account["target_account_id"],
        "observations": observations, "remote_evidence": remote_evidence, "source_reviews": source_reviews,
        "import_ready": False, "blockers": blockers}


def reconcile_local_coupons(config_path, input_root, output, max_bytes, max_depth):
    if type(max_bytes) is not int or not 0 < max_bytes <= 64 * 1024 * 1024 or type(max_depth) is not int or not 0 < max_depth <= 256:
        fail("INVALID_COUPON_RECONCILIATION_LIMITS")
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = parse_keyed_yaml(config_raw)
    if set(config) != {"schema_version", "account", "mappings", "documents", "snapshot"} or type(config.get("snapshot")) is not str:
        fail("INVALID_COUPON_RECONCILIATION_CONFIGURATION")
    prep_raw = yaml.safe_dump({k: v for k, v in config.items() if k != "snapshot"}).encode()
    preparation_configuration(prep_raw, max_bytes, max_depth)
    if sum(1 + len(entry["notes"]) for entry in config["documents"].values()) > 256:
        fail("COUPON_INPUT_LIMIT_EXCEEDED")
    snapshot_path = Path(input_root) / config["snapshot"]
    snapshot_raw = read_local_bytes(snapshot_path, input_root, max_bytes)
    captured = [config_raw, snapshot_raw]
    paths = []
    reviews = {}
    for alias, entry in config["documents"].items():
        document = []
        for path in (entry["statement"], *entry["notes"]):
            paths.append(Path(input_root) / path)
            raw = read_local_bytes(paths[-1], input_root, min(max_bytes, 4 * 1024 * 1024))
            captured.append(raw)
            if sum(map(len, captured)) > 64 * 1024 * 1024:
                fail("COUPON_INPUT_LIMIT_EXCEEDED")
            document.append(raw)
        statement = parse_statement(decode_document(document[0]), max_depth)
        notes = [parse_contract_note(decode_document(raw), max_depth, include_coupons=True) for raw in document[1:]]
        reviews[alias] = review_coupon_cash(statement, notes)
    if sum(map(len, captured)) > 64 * 1024 * 1024:
        fail("COUPON_INPUT_LIMIT_EXCEEDED")
    artifact = compare_coupon_snapshot(reviews, config["account"], config["mappings"], snapshot_raw)
    artifact["input_sha256"] = {str(i): hashlib.sha256(raw).hexdigest() for i, raw in enumerate(captured)}
    encoded = yaml.safe_dump(artifact, sort_keys=False, allow_unicode=True).encode()
    if len(encoded) > max_bytes:
        fail("DIAGNOSIS_REPORT_LIMIT_EXCEEDED")
    validate_proposal_destination(output, [Path(config_path), snapshot_path, *paths])
    private_directory(Path(output).parent)
    atomic_private_bytes(output, encoded)
    counts = {status: sum(o["status"] == status for o in artifact["observations"].values())
        for status in sorted({o["status"] for o in artifact["observations"].values()})}
    return {"coupons": len(artifact["observations"]), "status_counts": counts,
            "import_ready": False, "blockers": artifact["blockers"]}


def daily_preview_today():
    return datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()


def daily_preview_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        fail("INVALID_DAILY_PREVIEW_DAY")
    try:
        day = datetime.strptime(value, "%Y-%m-%d").date()
        day - timedelta(days=89)
    except (ValueError, OverflowError):
        fail("INVALID_DAILY_PREVIEW_DAY")
    return day


def daily_months(first, last):
    capture_period("statement", first)
    capture_period("statement", last)
    start = int(first[:4]) * 12 + int(first[5:]) - 1
    stop = int(last[:4]) * 12 + int(last[5:]) - 1
    if not 0 <= stop - start <= 2400:
        fail("DAILY_COVERAGE_RANGE_INVALID")
    return [f"{n // 12:04d}-{n % 12 + 1:02d}" for n in range(start, stop + 1)]


def daily_current_configuration(entry, as_of):
    if (not isinstance(entry, dict)
            or set(entry) != {"period", "index", "index_metadata", "index_encoding", "notes"}
            or entry["period"] != as_of[:7]
            or entry["index_encoding"] not in ("declared", "observed_cp1252_declared_utf8")
            or not isinstance(entry["notes"], dict) or len(entry["notes"]) > 31):
        fail("INVALID_CURRENT_PERIOD_CONFIGURATION")
    references = {"index": entry["index"], "index_metadata": entry["index_metadata"]}
    for day, note in entry["notes"].items():
        capture_period("note", day)
        if day[:7] != as_of[:7] or day > as_of:
            fail("CURRENT_NOTE_DAY_CONFLICT")
        if not isinstance(note, dict) or set(note) != {"document", "metadata"}:
            fail("INVALID_CURRENT_PERIOD_CONFIGURATION")
        references.update({day + ":" + key: value for key, value in note.items()})
    if any(not isinstance(path, str) or not path.strip() for path in references.values()):
        fail("INVALID_CURRENT_PERIOD_CONFIGURATION")
    return references


def daily_current_metadata(raw, body, account, role):
    metadata = parse_keyed_yaml(raw)
    if (not isinstance(metadata, dict) or metadata.get("role") != role
            or metadata.get("account_wrapper") not in ("PEA", "PEA-PME")
            or not isinstance(metadata.get("broker_account_id"), str)
            or not metadata["broker_account_id"]
            or metadata["broker_account_id"] + " " + metadata["account_wrapper"] != account["source_account_ref"]
            or metadata.get("sha256") != hashlib.sha256(body).hexdigest()
            or not isinstance(metadata.get("url"), str)):
        fail("CURRENT_CAPTURE_BINDING_CONFLICT")
    if any(ord(character) <= 32 or ord(character) == 127 for character in metadata["url"]):
        fail("CURRENT_CAPTURE_ORIGIN_CONFLICT")
    try:
        parts = urlsplit(metadata["url"])
    except ValueError:
        fail("CURRENT_CAPTURE_ORIGIN_CONFLICT")
    if parts.scheme != "https" or parts.netloc != "www.boursedirect.fr" or parts.fragment:
        fail("CURRENT_CAPTURE_ORIGIN_CONFLICT")
    return metadata


def inspect_daily_current(config, capture, snapshot_raw, remote, as_of, max_depth):
    """Account-bound inventory and note observations, never financial preparation."""
    entry, account = config["current_period"], config["account"]
    raw = capture["index"]
    meta = daily_current_metadata(capture["index_metadata"], raw, account, "frame_document")
    index_url = urlsplit(meta["url"])
    try:
        query = parse_qs(index_url.query, strict_parsing=True)
    except ValueError:
        fail("CURRENT_INDEX_URL_CONFLICT")
    if index_url.path != "/priv/new/avis-operes.php" or set(query) != {"ong", "nc"} or query["ong"] != ["5"] or len(query["nc"]) != 1 or not re.fullmatch(r"[1-9][0-9]*", query["nc"][0]):
        fail("CURRENT_INDEX_URL_CONFLICT")
    if entry["index_encoding"] == "observed_cp1252_declared_utf8":
        declarations = re.findall(rb"<meta\b[^>]*\bcharset\s*=\s*[\"']?\s*([a-zA-Z0-9_-]+)", raw, re.I)
        if not declarations or {v.lower() for v in declarations} != {b"utf-8"} or b"\x00" in raw or raw.startswith(b"\xef\xbb\xbf"):
            fail("CURRENT_INDEX_ENCODING_PROFILE_CONFLICT")
        try:
            html = raw.decode("cp1252", errors="strict")
        except UnicodeDecodeError:
            fail("CURRENT_INDEX_ENCODING_PROFILE_CONFLICT")
        try:
            raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            pass
        else:
            fail("CURRENT_INDEX_ENCODING_PROFILE_CONFLICT")
    else:
        html = decode_document(raw)
    soup = BeautifulSoup(html, "html.parser")
    pending = [(soup, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > max_depth:
            fail("INPUT_TOO_DEEP")
        pending.extend((child, depth + 1) for child in node.children if getattr(child, "name", None))
    navigation, offered = {}, {}
    months = ("Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre")
    headings = [[text(span) for span in cell.find_all("span", recursive=False) if not span.get("class")]
                for cell in soup.find_all("td", class_="topdatas")]
    if headings != [[entry["period"][:4]], [months[int(entry["period"][5:]) - 1]]]:
        fail("CURRENT_INDEX_PERIOD_CONFLICT")
    for link in soup.find_all("a", href=True):
        href = link["href"]
        nav = re.fullmatch(r"javascript:(AnneePrecedente|AnneeSuivante|MoisPrecedent|MoisSuivant)\('RO',([1-9][0-9]*),([0-9]{1,2}),([0-9]{4})\)", href)
        if nav:
            if nav[1] in navigation or nav[2] != query["nc"][0] or f"{nav[4]}-{int(nav[3]):02d}" != entry["period"]:
                fail("CURRENT_INDEX_PERIOD_CONFLICT")
            navigation[nav[1]] = True
        if "releveOpe.php" not in href:
            continue
        match = re.fullmatch(r"javascript:ouvrePopup\('([^']+)','encours'\);", href)
        if not match:
            fail("CURRENT_INDEX_LINK_UNSUPPORTED")
        if any(ord(character) <= 32 or ord(character) == 127 for character in match[1]):
            fail("CURRENT_INDEX_LINK_CONFLICT")
        url = urljoin(meta["url"], match[1])
        try:
            parts = urlsplit(url)
            values = parse_qs(parts.query, strict_parsing=True)
        except ValueError:
            fail("CURRENT_INDEX_LINK_CONFLICT")
        if (parts.scheme != "https" or parts.netloc != "www.boursedirect.fr" or parts.fragment
                or parts.path != "/priv/new/releveOpe.php" or set(values) != {"nc", "type", "year", "month", "day", "trash"}
                or any(len(v) != 1 for v in values.values()) or values["nc"] != query["nc"]
                or values["type"] != ["RO"] or values["trash"] != ["/avis.pdf"]
                or not re.fullmatch(r"[0-9]{1,2}", values["day"][0])
                or values["year"][0] != entry["period"][:4] or values["month"][0] != str(int(entry["period"][5:]))):
            fail("CURRENT_INDEX_LINK_CONFLICT")
        day = entry["period"] + "-" + values["day"][0].zfill(2)
        capture_period("note", day)
        if day > as_of or day in offered or text(link) != day[-2:]:
            fail("CURRENT_INDEX_DAY_CONFLICT")
        offered[day] = url
    if set(navigation) != {"AnneePrecedente", "AnneeSuivante", "MoisPrecedent", "MoisSuivant"}:
        fail("CURRENT_INDEX_PERIOD_UNVERIFIED")
    empty = [text(n) for n in soup.select("div.msg.texte1T7A")]
    if (not offered and empty != ["Vous n'avez pas effectué d'opération ce mois-ci."]
            or offered and empty or set(offered) != set(entry["notes"])):
        fail("CURRENT_INDEX_NOTE_INVENTORY_CONFLICT")
    originals = json.loads(snapshot_raw, object_pairs_hook=unique_json_object)
    timestamps = {row["id"]: row["date"] for row in originals["activities"]}
    observations, exceptions, comparisons = {}, {}, 0
    for day in sorted(offered):
        body = capture[day + ":document"]
        note_meta = daily_current_metadata(capture[day + ":metadata"], body, account, "contract_note")
        if note_meta["url"] != offered[day] or note_meta["broker_account_id"] != meta["broker_account_id"]:
            fail("CURRENT_NOTE_URL_CONFLICT")
        html = decode_document(body)
        note_soup = BeautifulSoup(html, "html.parser")
        refs = [text(cells(row)[1]) for row in note_soup.find_all("tr") if len(cells(row)) == 2 and text(cells(row)[0]) == "COMPTE N°"]
        if refs != [account["source_account_ref"]]:
            fail("DAILY_SOURCE_ACCOUNT_CONFLICT")
        key = "current_note:" + note_meta["sha256"]
        observation = {"note_sha256": note_meta["sha256"], "metadata_sha256": hashlib.sha256(capture[day + ":metadata"]).hexdigest(), "operation_date": day, "notes": []}
        code = "CURRENT_NOTE_REQUIRES_CLOSED_STATEMENT"
        try:
            parsed = parse_contract_note(html, max_depth, include_coupons=True, skip_missing_isin=True)
        except RuntimeError as error:
            code = str(error)
            observation["operation_date_verified"] = False
            if code == "INVALID_NOTE_SECURITY":
                rows = direct_rows(contract_note_ledger(note_soup))
                if len(rows) != 2 or len(cells(rows[1])) != 4:
                    fail("CURRENT_NOTE_DAY_UNVERIFIED")
                dates = cells(rows[1])[0].find_all("table", recursive=False)
                if len(dates) != 1:
                    fail("CURRENT_NOTE_DAY_UNVERIFIED")
                date_rows = direct_rows(dates[0])
                if any(len(cells(row)) != 1 or cells(row)[0].find("table") for row in date_rows):
                    fail("CURRENT_NOTE_DAY_UNVERIFIED")
                source_days = [parse_date(text(cells(row)[0])).isoformat() for row in date_rows if text(cells(row)[0])]
                if not source_days or any(value != day for value in source_days):
                    fail("CURRENT_NOTE_DAY_CONFLICT")
                observation["operation_date_verified"] = True
        else:
            if any(note["date"].isoformat() != day for note in parsed["notes"]):
                fail("CURRENT_NOTE_DAY_CONFLICT")
            observation["operation_date_verified"] = True
            comparisons += len(parsed["notes"]) * len(remote)
            if comparisons > 1000000:
                fail("DAILY_CURRENT_COMPARISON_LIMIT_EXCEEDED")
            for note in parsed["notes"]:
                selected = ({k: note[k] for k in ("slot", "kind", "isin", "date", "net_currency", "debit", "credit", "skip_reason", "financial_conversion")}
                            if note["kind"] == "SKIPPED_NO_ISIN" else note)
                record = {k: canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v for k, v in selected.items()}
                mapping = config["mappings"].get(note["isin"])
                record["destination_candidates"] = []
                if note["kind"] in ("BUY", "SELL") and isinstance(mapping, dict):
                    symbol = mapping.get("symbol")
                    if (isinstance(symbol, str) and re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,63}", symbol)
                            and mapping.get("data_source") == "YAHOO" and mapping.get("target_currency") == "EUR"
                            and isinstance(mapping.get("target_security_evidence"), str) and mapping["target_security_evidence"].strip()):
                        record["target_symbol"] = symbol
                        for row in remote:
                            if (row["target_account_id"] == account["target_account_id"] and row["symbol"] == symbol
                                    and row["data_source"] == "YAHOO" and row["kind"] == note["kind"]
                                    and row["quantity"] == note["quantity"].copy_abs() and row["unit_price"] == note["unit_price"]
                                    and abs((datetime.fromisoformat(row["operation_date"]).date() - note["date"]).days) <= 1):
                                with localcontext() as context:
                                    context.prec = max(28, sum(len(v.as_tuple().digits) + abs(v.as_tuple().exponent) for v in (row["fee"], note["brokerage"], note["vat"])) + 4)
                                    fee_delta = canonical_decimal(row["fee"] - note["brokerage"] - note["vat"])
                                record["destination_candidates"].append({"remote_id": row["remote_id"], "original_timestamp": timestamps[row["remote_id"]],
                                    "date_context_verified": row["date_context_verified"], "financial_context_verified": row["financial_context_verified"],
                                    "remote_currency": row["price_currency"], "remote_fee": canonical_decimal(row["fee"]),
                                    "fee_delta_remote_minus_source": fee_delta,
                                    "certain_match": False})
                observation["notes"].append(record)
        if observation["notes"] and all(n["kind"] == "SKIPPED_NO_ISIN" for n in observation["notes"]):
            code = "SKIPPED_NO_ISIN"
        observation["code"] = code
        observations[day] = observation
        exceptions[key] = {"period": entry["period"], "operation_date": day, "status": "resolved_by_saved_evidence" if code == "SKIPPED_NO_ISIN" else "unresolved", "code": code, "note_sha256": note_meta["sha256"]}
    return {"period": entry["period"], "index_sha256": hashlib.sha256(raw).hexdigest(), "index_metadata_sha256": hashlib.sha256(capture["index_metadata"]).hexdigest(),
            "index_encoding": entry["index_encoding"], "offered_note_days": sorted(offered), "every_offered_note_retained": True,
            "notes": observations, "through_day_verified": False, "monthly_cash_controls_verified": False, "import_ready": False}, exceptions


def compute_daily_preview(config, documents, snapshot_raw, previous, as_of, max_bytes, max_depth, current_capture=None):
    """Saved-source continuity and candidate evidence; no acquisition clock or remote write."""
    day = daily_preview_day(as_of)
    window_start = (day - timedelta(days=89)).isoformat()
    account = config["account"]
    if previous is None:
        previous = {"schema_version": 1, "binding": account, "first_required_period": window_start[:7],
                    "last_preview_day": as_of, "periods": {}, "exceptions": {}}
    if (set(previous) != {"schema_version", "binding", "first_required_period", "last_preview_day", "periods", "exceptions"}
            or type(previous["schema_version"]) is not int or previous["schema_version"] != 1
            or previous["binding"] != account or not isinstance(previous["periods"], dict)
            or not isinstance(previous["exceptions"], dict)):
        fail("INVALID_DAILY_JOURNAL_OR_BINDING")
    daily_preview_day(previous["last_preview_day"])
    if as_of < previous["last_preview_day"]:
        fail("DAILY_PREVIEW_CLOCK_REVERSED")
    required = daily_months(previous["first_required_period"], as_of[:7])
    for period, evidence in previous["periods"].items():
        capture_period("statement", period)
        if (not isinstance(evidence, dict) or set(evidence) != {"financial_sha256", "statement_sha256", "note_sha256", "complete_source_matching"}
                or type(evidence["complete_source_matching"]) is not bool
                or not isinstance(evidence["note_sha256"], list)
                or any(not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v)
                       for v in [evidence["financial_sha256"], evidence["statement_sha256"], *evidence["note_sha256"]])):
            fail("INVALID_DAILY_JOURNAL_OR_BINDING")
    for key, exception in previous["exceptions"].items():
        if (not isinstance(key, str) or not isinstance(exception, dict)
                or exception.get("status") not in ("unresolved", "resolved_by_saved_evidence")
                or not isinstance(exception.get("code"), str)):
            fail("INVALID_DAILY_JOURNAL_OR_BINDING")
        capture_period("statement", exception.get("period"))
    # Detach nested structures; failed recomputation must preserve retained state.
    journal = parse_keyed_yaml(yaml.safe_dump(previous, sort_keys=False).encode())
    remote = parse_remote_activity_snapshot(snapshot_raw)
    reviews = {}
    trade_observations = {}
    prepared_periods = {}
    window_events = {}
    skipped_operations = {}
    seen = set()
    for alias, capture in documents.items():
        statement = parse_statement(decode_document(capture["statement"]), max_depth)
        period = statement["period"]
        if statement["account_ref"] != account["source_account_ref"]:
            fail("DAILY_SOURCE_ACCOUNT_CONFLICT")
        if period in seen:
            fail("DUPLICATE_STATEMENT_PERIOD")
        if period >= as_of[:7]:
            fail("DAILY_STATEMENT_NOT_CLOSED")
        seen.add(period)
        # Exclude presentation slots, retain economic multiplicity and all controls.
        events = [{k: canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v
                   for k, v in event.items() if k != "slot"} for event in statement["events"]]
        window_events[period] = [event for event in events if window_start <= event["date"] <= as_of]
        semantic = {"period": period, "events": sorted(events, key=lambda e: json.dumps(e, sort_keys=True)),
                    "controls": [{k: canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v
                                  for k, v in control.items() if k != "slot"} for control in statement["controls"]]}
        fingerprint = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        retained = journal["periods"].get(period)
        if retained is not None and retained.get("financial_sha256") != fingerprint:
            # The previous parser kept foreign sales as UNKNOWN. Qualify only
            # that exact projection, with byte-identical statement and notes.
            legacy_events = [{**{k: v for k, v in event.items() if k not in ("quantity", "unit_price")}, "kind": "UNKNOWN"}
                             if event["kind"] == "SELL" and event["label"].startswith("VENTE ETRANGER ") else event
                             for event in events]
            legacy = {**semantic, "events": sorted(legacy_events, key=lambda e: json.dumps(e, sort_keys=True))}
            legacy_fingerprint = hashlib.sha256(json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if (legacy_fingerprint != retained["financial_sha256"]
                    or retained["statement_sha256"] != hashlib.sha256(capture["statement"]).hexdigest()
                    or retained["note_sha256"] != sorted(hashlib.sha256(raw).hexdigest() for raw in capture["notes"])):
                fail("DAILY_SOURCE_REVISION_REVIEW_REQUIRED")
            journal["exceptions"][period + ":foreign_sale_parser_upgrade"] = {
                "period": period, "status": "resolved_by_saved_evidence",
                "code": "BYTE_IDENTICAL_FOREIGN_SALE_CLASSIFICATION_UPGRADE",
                "previous_financial_sha256": legacy_fingerprint, "financial_sha256": fingerprint,
                "statement_sha256": retained["statement_sha256"], "note_sha256": retained["note_sha256"]}
        source = {"financial_sha256": fingerprint, "statement_sha256": hashlib.sha256(capture["statement"]).hexdigest(),
                  "note_sha256": sorted(hashlib.sha256(raw).hexdigest() for raw in capture["notes"]),
                  "complete_source_matching": False}
        problems = {}
        try:
            notes = [parse_contract_note(decode_document(raw), max_depth, include_coupons=True, skip_missing_isin=True) for raw in capture["notes"]]
            statement = match_missing_isin_skips(statement, notes)
        except RuntimeError as error:
            if str(error) == "NOTE_ACCOUNT_MISMATCH":
                fail("DAILY_SOURCE_ACCOUNT_CONFLICT")
            # Retain a refused period; never invent missing security identity or
            # promote a partially parsed note to source-complete evidence.
            notes = None
            problems["source"] = str(error)
        if notes is not None:
            skipped_operations[period] = [{"source_slot": e["slot"], "operation_date": e["date"].isoformat(),
                "source_label_sha256": hashlib.sha256(e["label"].encode()).hexdigest(), "debit": canonical_decimal(e["debit"]), "credit": canonical_decimal(e["credit"]),
                "currency": "EUR", "skip_reason": "SOURCE_ISIN_ABSENT", "financial_conversion": False}
                for e in statement["events"] if e.get("skip_reason")]
        if notes is not None and any(n["account_ref"] != account["source_account_ref"] for n in notes):
            fail("DAILY_SOURCE_ACCOUNT_CONFLICT")
        if notes is None:
            pass
        elif all(event["kind"] in ("BUY", "SELL") or event.get("skip_reason") or event["label"].startswith("COUPONS ") for event in statement["events"]):
            one = {k: v for k, v in config.items() if k not in ("snapshot", "current_period")}
            one["documents"] = {alias: config["documents"][alias]}
            try:
                if any(n["kind"] == "COUPON" for doc in notes for n in doc["notes"]):
                    reviews[period] = review_coupon_cash(statement, notes)
                prepared = compute_prepared_sources(yaml.safe_dump(one).encode(), {alias: capture}, max_bytes, max_depth)["artifact"]["activities"]
            except RuntimeError as error:
                problems["source"] = str(error)
            else:
                source["complete_source_matching"] = True
                prepared_periods[period] = prepared
                try:
                    trade_observations[period] = reconcile_existing_activities(prepared, remote, {}, automatic=True)
                except RuntimeError as error:
                    problems["destination"] = str(error)
                else:
                    problems["destination"] = "TRADE_HOLDINGS_AND_APPLICATION_UNVERIFIED"
        else:
            try:
                reviews[period] = review_coupon_cash(statement, notes)
            except RuntimeError as error:
                problems["source"] = str(error)
            else:
                # Mixed/unknown periods cannot become complete through coupon-only matching.
                source["complete_source_matching"] = (bool(statement["events"])
                    and all(e["label"].startswith("COUPONS ") or e.get("skip_reason") for e in statement["events"])
                    and all(n["kind"] in ("COUPON", "SKIPPED_NO_ISIN") for doc in notes for n in doc["notes"]))
                if not source["complete_source_matching"]:
                    problems["source"] = "COMPLETE_PERIOD_CONVERSION_REQUIRED"
        journal["periods"][period] = source
        for role in ("source", "destination"):
            key = period + ":" + role
            if role in problems:
                journal["exceptions"][key] = {"period": period, "status": "unresolved", "code": problems[role]}
            elif key in journal["exceptions"] and (role == "source" or source["complete_source_matching"]):
                journal["exceptions"][key]["status"] = "resolved_by_saved_evidence"
    # Reconcile the entire qualified set before selecting days. Window
    # filtering must not hide duplicate source occurrences or ownership.
    all_prepared = {marker: activity for period in sorted(prepared_periods)
                    for marker, activity in prepared_periods[period].items()}
    destination_diagnosis = observe_snapshot_discrepancies(all_prepared, remote, snapshot_raw)
    candidate_export = {"artifact_kind": "daily_candidate_wire_not_apply_authorization",
                        "import_ready": False, "activity_count": 0, "wire": None,
                        "excluded_outside_window": 0, "owned_count": 0, "adopted_count": 0,
                        "source_complete_periods": sorted(prepared_periods),
                        "blocked_source_periods": sorted(p for p, evidence in journal["periods"].items()
                                                         if not evidence["complete_source_matching"]),
                        "reconciliation_code": None}
    try:
        combined = reconcile_existing_activities(all_prepared, remote, {}, automatic=True)
    except RuntimeError as error:
        candidate_export["reconciliation_code"] = str(error)
    else:
        candidate_export["owned_count"] = len(combined["owned"])
        candidate_export["adopted_count"] = len(combined["adopted"])
        if combined["candidates"]:
            candidate_export["reconciliation_code"] = "AUTOMATIC_ACTIVITY_ADOPTION_UNCERTAIN"
        else:
            selected = {marker: all_prepared[marker] for marker in combined["new"]
                        if window_start <= all_prepared[marker]["operation_date"] <= as_of}
            candidate_export["excluded_outside_window"] = len(combined["new"]) - len(selected)
            try:
                candidate_wire = build_wire_payload(selected) if selected else None
            except RuntimeError as error:
                candidate_export["reconciliation_code"] = str(error)
            else:
                candidate_export["activity_count"] = len(selected)
                candidate_export["wire"] = None if candidate_wire is None else {
                    "body_utf8": candidate_wire["body"].decode("utf-8"), "sha256": candidate_wire["sha256"]}
    coupons = compare_coupon_snapshot(reviews, account, config["mappings"], snapshot_raw) if reviews else None
    if coupons is not None:
        occurrences = {}
        for observation_key, observation in sorted(coupons["observations"].items()):
            period, slot = observation_key.split("/")
            coupon = reviews[period]["coupons"][slot]
            identity = {k: coupon[k] for k in ("operation_date", "isin", "amount", "currency")}
            digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            occurrences[digest] = occurrences.get(digest, 0) + 1
            key = "coupon:" + digest + ":" + str(occurrences[digest])
            journal["exceptions"][key] = {"period": coupon["operation_date"][:7], "operation_date": coupon["operation_date"],
                "status": "resolved_by_saved_evidence" if observation["status"] == "CERTAIN_UNIQUE_NET_REPRESENTATION_OBSERVED" else "unresolved",
                "code": observation["status"], "evidence": json.loads(json.dumps(observation))}
    current = None
    if "current_period" in config:
        daily_current_configuration(config["current_period"], as_of)
        if current_capture is None:
            fail("CURRENT_PERIOD_CAPTURE_MISSING")
        current, exceptions = inspect_daily_current(config, current_capture, snapshot_raw, remote, as_of, max_depth)
        journal["exceptions"].update(exceptions)
    for key, exception in journal["exceptions"].items():
        if key.startswith("current_note:") and exception.get("code") == "CURRENT_NOTE_REQUIRES_CLOSED_STATEMENT":
            closed = journal["periods"].get(exception["period"], {})
            if closed.get("complete_source_matching") and exception.get("note_sha256") in closed.get("note_sha256", []):
                exception["status"] = "resolved_by_saved_evidence"
    gaps = [period for period in required[:-1] if not journal["periods"].get(period, {}).get("complete_source_matching")]
    stale = [period for period in gaps if period < window_start[:7]]
    completed = [p for p, evidence in journal["periods"].items() if evidence.get("complete_source_matching")]
    journal["last_preview_day"] = as_of
    journal["periods"] = dict(sorted(journal["periods"].items()))
    journal["exceptions"] = dict(sorted(journal["exceptions"].items()))
    unresolved = {k: v for k, v in journal["exceptions"].items() if v["status"] == "unresolved"}
    report = {"schema_version": 1, "artifact_kind": "daily_saved_input_preview_not_api_payload", "binding": account,
              "window": {"first_day": window_start, "last_day": as_of, "days": 90},
              "last_completed_acquisition_period": max(completed) if completed else None,
              "missing_or_unqualified_closed_periods": gaps, "gaps_outside_window": stale,
              "missing_closed_statement_periods": [p for p in gaps if p not in journal["periods"]],
              "unqualified_observed_closed_periods": [p for p in gaps if p in journal["periods"]],
              "current_period_through_day_verified": False, "resume_requires_catchup": bool(stale),
              "exceptions": unresolved, "trade_observations": trade_observations, "coupon_observations": coupons,
              "window_source_events": window_events, "skipped_source_operations": skipped_operations,
              "candidate_export": candidate_export, "destination_diagnosis": destination_diagnosis,
              "snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(), "import_ready": False,
              "blockers": ["CURRENT_PERIOD_CUTOFF_UNVERIFIED", "FINANCIAL_APPLICATION_NOT_ACTIVATED"]}
    if gaps:
        report["blockers"].append("ACQUISITION_COVERAGE_GAP")
    if current is not None:
        report["current_period_observations"] = current
    if stale:
        report["blockers"].append("DAILY_RESUME_CATCHUP_REQUIRED")
    return journal, report


def discover_daily_acquisitions(config, input_root, as_of, max_bytes, max_depth):
    """Resolve original collector receipts; no fetching or freshness inference."""
    notice_only = config.get("source_mode") == "notices"
    runs = config.get("acquisition_runs")
    if (not isinstance(runs, dict) or not 0 < len(runs) <= 16
            or any(not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", k)
                   or not isinstance(v, str) or not v.strip() for k, v in runs.items())
            or not notice_only and config.get("index_encoding") not in ("declared", "observed_cp1252_declared_utf8")):
        fail("INVALID_DAILY_ACQUISITION_CONFIGURATION")
    account = config["account"]
    if not isinstance(account, dict) or not isinstance(account.get("source_account_ref"), str):
        fail("INVALID_ACCOUNT_CONFIGURATION")
    ref = account["source_account_ref"]
    wrapper = next((w for w in ("PEA-PME", "PEA") if ref.endswith(" " + w)), None)
    if wrapper is None:
        fail("DAILY_ACQUISITION_ACCOUNT_UNVERIFIED")
    broker_id = ref[:-(len(wrapper) + 1)]
    paths, total, count, selected, captured = [], 0, 0, {}, {}
    evidence = {}

    def read(reference):
        nonlocal total
        path = Path(input_root) / reference
        try:
            raw = read_local_bytes(path, input_root, min(max_bytes, 4 * 1024 * 1024))
        except OSError:
            fail("DAILY_ACQUISITION_INPUT_UNAVAILABLE")
        total += len(raw)
        if total > 64 * 1024 * 1024:
            fail("DAILY_INPUT_LIMIT_EXCEEDED")
        paths.append(path)
        captured[str(reference)] = raw
        return raw

    for alias, directory in sorted(runs.items()):
        root = Path(directory)
        raw = read(root / "qualification.yaml")
        receipt = parse_keyed_yaml(raw)
        if "import_account_config_sha256" in receipt and "account_binding" not in receipt:
            fail("DAILY_ACQUISITION_RUN_UNVERIFIED")
        if "account_binding" in receipt and receipt["account_binding"] != account:
            fail("DAILY_ACQUISITION_RUN_UNVERIFIED")
        if (receipt.get("schema_version") != 1 or type(receipt.get("schema_version")) is not int
                or receipt.get("state") != "owned_session_closed"
                or any(receipt.get(k) is not True for k in ("accounts_verified", "session_logged_out", "browser_exit_verified"))
                or not isinstance(receipt.get("account_ids"), dict)
                or receipt["account_ids"].get(wrapper) != broker_id
                or not isinstance(receipt.get("accounts"), dict)
                or not isinstance(receipt["accounts"].get(wrapper), str)
                or not re.fullmatch(r"[1-9][0-9]*", receipt["accounts"][wrapper])
                or type(receipt.get("captures")) is not int or not 0 < receipt["captures"] <= 256):
            fail("DAILY_ACQUISITION_RUN_UNVERIFIED")
        count += receipt["captures"]
        if count > 256:
            fail("DAILY_INPUT_LIMIT_EXCEEDED")
        nc = receipt["accounts"][wrapper]
        evidence[alias] = {"receipt_sha256": hashlib.sha256(raw).hexdigest(), "captures": receipt["captures"]}
        for n in range(1, receipt["captures"] + 1):
            metadata_ref = root / f"document-{n}.yaml"
            metadata_raw = read(metadata_ref)
            metadata = parse_keyed_yaml(metadata_raw)
            role = metadata.get("role")
            if notice_only and role != "contract_note":
                continue
            if metadata.get("account_wrapper") != wrapper or role not in ("monthly_statement", "contract_note", "frame_document"):
                continue
            # Ignore other frame roles without reading their bodies.
            if role == "frame_document":
                if not isinstance(metadata.get("url"), str):
                    fail("DAILY_ACQUISITION_URL_CONFLICT")
                try:
                    frame_path = urlsplit(metadata["url"]).path
                except ValueError:
                    fail("DAILY_ACQUISITION_URL_CONFLICT")
                if frame_path != "/priv/new/avis-operes.php":
                    continue
            if metadata.get("path") != f"document-{n}.html":
                fail("DAILY_ACQUISITION_PATH_CONFLICT")
            body_ref = root / metadata["path"]
            body = read(body_ref)
            meta = daily_current_metadata(metadata_raw, body, account, role)
            url = urlsplit(meta["url"])
            try:
                query = parse_qs(url.query, strict_parsing=True)
            except ValueError:
                fail("DAILY_ACQUISITION_URL_CONFLICT")
            if any(len(v) != 1 for v in query.values()) or query.get("nc") != [nc]:
                fail("DAILY_ACQUISITION_URL_CONFLICT")
            if role == "monthly_statement":
                if (url.path != "/priv/new/releveCompte.php" or set(query) != {"nc", "dt", "type"}
                        or query["type"] != ["RE"] or not re.fullmatch(r"[0-9]{8}", query["dt"][0])):
                    fail("DAILY_ACQUISITION_URL_CONFLICT")
                parsed = parse_statement(decode_document(body), max_depth)
                period = parsed["period"]
                next_month = (datetime.strptime(period, "%Y-%m").replace(day=28) + timedelta(days=4)).replace(day=1)
                if (parsed["account_ref"] != ref or query["dt"][0] != (next_month - timedelta(days=1)).strftime("%Y%m%d")
                        or period >= as_of[:7]):
                    fail("DAILY_ACQUISITION_STATEMENT_CONFLICT")
            elif role == "contract_note":
                if (url.path != "/priv/new/releveOpe.php" or set(query) != {"nc", "type", "year", "month", "day", "trash"}
                        or query["type"] != ["RO"] or query["trash"] != ["/avis.pdf"]
                        or not re.fullmatch(r"[0-9]{4}", query["year"][0])
                        or any(not re.fullmatch(r"[0-9]{1,2}", query[k][0]) for k in ("month", "day"))):
                    fail("DAILY_ACQUISITION_URL_CONFLICT")
                period = query["year"][0] + "-" + query["month"][0].zfill(2) + "-" + query["day"][0].zfill(2)
                capture_period("note", period)
                if period > as_of:
                    fail("CURRENT_NOTE_DAY_CONFLICT")
                soup = BeautifulSoup(decode_document(body), "html.parser")
                refs = [text(cells(row)[1]) for row in soup.find_all("tr") if len(cells(row)) == 2 and text(cells(row)[0]) == "COMPTE N°"]
                if refs != [ref]:
                    fail("DAILY_SOURCE_ACCOUNT_CONFLICT")
                try:
                    parsed_note = parse_contract_note(decode_document(body), max_depth, include_coupons=True)
                except RuntimeError:
                    # The preview retains the original refusal for this period.
                    pass
                else:
                    financial_days = sorted({note["date"].isoformat() for note in parsed_note["notes"]})
                    if (any(day[:7] != period[:7] for day in financial_days)
                            or period[:7] == as_of[:7] and financial_days != [period]):
                        fail("DAILY_ACQUISITION_NOTE_DAY_CONFLICT")
                    if financial_days != [period]:
                        evidence[alias].setdefault("note_date_differences", {})[meta["sha256"]] = {
                            "calendar_day": period, "financial_days": financial_days}
            else:
                periods = set(re.findall(rb"javascript:(?:AnneePrecedente|AnneeSuivante|MoisPrecedent|MoisSuivant)\('RO',[1-9][0-9]*,([0-9]{1,2}),([0-9]{4})\)", body))
                if len(periods) != 1:
                    fail("CURRENT_INDEX_PERIOD_UNVERIFIED")
                month, year = next(iter(periods))
                period = year.decode("ascii") + "-" + month.decode("ascii").zfill(2)
                capture_period("statement", period)
                if period != as_of[:7]:
                    if (set(query) not in ({"nc", "tr", "month", "year"}, {"nc", "tr", "month", "year", "ong"})
                            or query.get("tr") != ["RO"] or query.get("year") != [period[:4]]
                            or query.get("month") != [str(int(period[5:]))]
                            or "ong" in query and query["ong"] != ["5"]):
                        fail("DAILY_ACQUISITION_URL_CONFLICT")
                    continue
                if set(query) != {"nc", "ong"} or query["ong"] != ["5"]:
                    fail("DAILY_ACQUISITION_URL_CONFLICT")
            key = (role, period)
            existing = selected.get(key)
            if existing is not None and existing["sha256"] != meta["sha256"]:
                fail("DAILY_ACQUISITION_CAPTURE_CONFLICT")
            if existing is None:
                selected[key] = {"document": str(body_ref), "metadata": str(metadata_ref), "sha256": meta["sha256"], "url": meta["url"]}
    statements = {period: value for (role, period), value in selected.items() if role == "monthly_statement"}
    notes = {period: value for (role, period), value in selected.items() if role == "contract_note"}
    if notice_only:
        return notes, paths, total, evidence, captured
    if any(day[:7] != as_of[:7] and day[:7] not in statements for day in notes):
        fail("DAILY_ACQUISITION_NOTE_WITHOUT_STATEMENT")
    expanded = {k: v for k, v in config.items() if k not in ("acquisition_runs", "index_encoding")}
    expanded["documents"] = {"period_" + period.replace("-", "_"): {"statement": value["document"],
        "notes": [note["document"] for day, note in sorted(notes.items()) if day[:7] == period]}
        for period, value in sorted(statements.items())}
    index = selected.get(("frame_document", as_of[:7]))
    if index is None:
        fail("DAILY_ACQUISITION_CURRENT_INDEX_MISSING")
    expanded["current_period"] = {"period": as_of[:7], "index": index["document"], "index_metadata": index["metadata"],
        "index_encoding": config["index_encoding"], "notes": {day: {k: note[k] for k in ("document", "metadata")}
            for day, note in sorted(notes.items()) if day[:7] == as_of[:7]}}
    return expanded, paths, total, evidence, captured


def notice_activity(note, account, mappings):
    """Independent notice conversion; never manufacture a monthly ledger."""
    if note["kind"] not in ("BUY", "SELL", "COUPON"):
        fail("UNSUPPORTED_NOTICE_OPERATION")
    mapping = mappings.get(note["isin"])
    if (not isinstance(mapping, dict) or mapping.get("data_source") != "YAHOO"
            or mapping.get("target_currency") != "EUR"
            or not isinstance(mapping.get("target_security_evidence"), str) or not mapping["target_security_evidence"].strip()
            or not isinstance(mapping.get("symbol"), str)
            or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,63}", mapping["symbol"])):
        fail("SECURITY_MAPPING_UNVERIFIED")
    if note["kind"] != "COUPON":
        if (mapping.get("execution_price_currency") != "EUR"
                or not isinstance(mapping.get("currency_evidence"), str) or not mapping["currency_evidence"].strip()):
            fail("SECURITY_CURRENCY_CONFLICT")
        if note["price_currency"] not in (None, "EUR") or note["net_currency"] != "EUR":
            fail("SOURCE_PRICE_CURRENCY_CONFLICT")
        if note["vat"] != 0:
            fail("UNVERIFIED_VAT_TREATMENT")
    record = {"account_key": account["account_key"], "target_account_id": account["target_account_id"],
              "operation_date": note["date"].isoformat(), "isin": note["isin"],
              "symbol": mapping["symbol"], "data_source": "YAHOO", "price_currency": "EUR",
              "kind": "DIVIDEND" if note["kind"] == "COUPON" else note["kind"],
              "quantity": "1" if note["kind"] == "COUPON" else canonical_decimal(note["quantity"].copy_abs()),
              "unit_price": canonical_decimal(note["credit"] if note["kind"] == "COUPON" else note["unit_price"]),
              "fee": "0" if note["kind"] == "COUPON" else canonical_decimal(note["brokerage"])}
    if note["kind"] == "COUPON":
        record["amount_basis"] = "net_received"
    else:
        record["execution_time"] = note["execution_time"]
    return record


def notice_preparation_configuration(config_raw, max_bytes, max_depth):
    if (type(max_bytes) is not int or max_bytes <= 0 or type(max_depth) is not int or max_depth <= 0
            or type(config_raw) is not bytes or len(config_raw) > max_bytes):
        fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    config = parse_keyed_yaml(config_raw)
    if (set(config) != {"schema_version", "source_mode", "account", "mappings", "notices", "as_of"}
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or config["source_mode"] != "notices" or not isinstance(config["mappings"], dict)):
        fail("INVALID_NOTICE_PREPARATION_CONFIGURATION")
    daily_preview_day(config["as_of"])
    account = config["account"]
    if (not isinstance(account, dict) or set(account) != {"source_account_ref", "account_key", "target_account_id"}
            or any(not isinstance(v, str) or not v.strip() for v in account.values())):
        fail("INVALID_ACCOUNT_CONFIGURATION")
    validate_account_key(account["account_key"])
    if not isinstance(config["notices"], dict) or not 0 < len(config["notices"]) <= 256:
        fail("INVALID_NOTICE_PREPARATION_CONFIGURATION")
    days = set()
    for alias, entry in config["notices"].items():
        if (not isinstance(alias, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", alias)
                or not isinstance(entry, dict) or set(entry) != {"date", "document"}
                or not isinstance(entry["document"], str) or not entry["document"].strip()):
            fail("INVALID_NOTICE_PREPARATION_CONFIGURATION")
        capture_period("note", entry["date"])
        if entry["date"] in days or entry["date"] > config["as_of"]:
            fail("INVALID_NOTICE_PREPARATION_CONFIGURATION")
        days.add(entry["date"])
    return config


def compute_prepared_notices(config_raw, documents, max_bytes, max_depth):
    """Replay original independent notices for the existing application boundary."""
    config = notice_preparation_configuration(config_raw, max_bytes, max_depth)
    if not isinstance(documents, dict) or set(documents) != set(config["notices"]):
        fail("INVALID_PREPARATION_CAPTURES")
    notes, captured, digests = {}, {}, {}
    total = len(config_raw)
    for alias, entry in config["notices"].items():
        capture = documents[alias]
        if (not isinstance(capture, dict) or set(capture) != {"notice"}
                or type(capture["notice"]) is not bytes or len(capture["notice"]) > max_bytes):
            fail("INVALID_PREPARATION_CAPTURES")
        raw = capture["notice"]
        total += len(raw)
        if total > 64 * 1024 * 1024:
            fail("DAILY_INPUT_LIMIT_EXCEEDED")
        digest = hashlib.sha256(raw).hexdigest()
        captured[alias] = raw
        notes[entry["date"]] = {"document": alias, "sha256": digest}
        digests[alias] = {"notice": digest}
    _, report = compute_notice_preview(config["account"], config["mappings"], notes, captured,
                                       b'{"count":0,"activities":[]}', None, config["as_of"], max_depth)
    # Diagnostic partial candidates remain available in daily-preview. Execution
    # replay must qualify every supplied original notice before any dispatch.
    if report["exceptions"]:
        fail("NOTICE_APPLICATION_SOURCE_UNQUALIFIED")
    activities = {marker: {**activity, "import_ready": False}
                  for marker, activity in report["activities"].items()}
    artifact = {"schema_version": 1, "artifact_kind": "internal_activity_review_not_api_payload",
                "import_ready": False, "blockers": ["REMOTE_ADOPTION_UNVERIFIED", "ISOLATED_API_CONTRACT_UNVERIFIED"],
                "account_key": config["account"]["account_key"], "target_account_id": config["account"]["target_account_id"],
                "source_digests": digests, "activities": activities}
    return {"artifact": artifact}


def compute_notice_preview(account, mappings, notes, captured, snapshot_raw, previous, as_of, max_depth):
    """Diagnostic candidates survive legacy differences; no application authority."""
    day = daily_preview_day(as_of)
    first = (day - timedelta(days=89)).isoformat()
    remote = parse_remote_activity_snapshot(snapshot_raw)
    if previous is None:
        previous = {"schema_version": 1, "binding": account, "as_of": as_of, "notice_hashes": {}, "exceptions": {}}
    if (not isinstance(previous, dict) or set(previous) != {"schema_version", "binding", "as_of", "notice_hashes", "exceptions"}
            or type(previous["schema_version"]) is not int or previous["schema_version"] != 1
            or previous["binding"] != account or not isinstance(previous["notice_hashes"], dict)
            or not isinstance(previous["exceptions"], dict)):
        fail("INVALID_NOTICE_JOURNAL")
    if daily_preview_day(previous["as_of"]) > day:
        fail("DAILY_CLOCK_REVERSED")
    for calendar_day, digest in previous["notice_hashes"].items():
        capture_period("note", calendar_day)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            fail("INVALID_NOTICE_JOURNAL")
    hashes, exceptions = dict(previous["notice_hashes"]), dict(previous["exceptions"])
    activities, skips, source_fields, occurrences, symbols = {}, {}, {}, {}, {}
    for calendar_day, entry in sorted(notes.items()):
        capture_period("note", calendar_day)
        digest = entry["sha256"]
        if calendar_day in hashes and hashes[calendar_day] != digest:
            fail("NOTICE_SOURCE_REVISION")
        hashes[calendar_day] = digest
        body = captured[entry["document"]]
        if hashlib.sha256(body).hexdigest() != digest:
            fail("NOTICE_CAPTURE_CONFLICT")
        try:
            document = parse_contract_note(decode_document(body), max_depth, include_coupons=True, skip_missing_isin=True)
        except RuntimeError as error:
            exceptions[digest] = {"code": str(error), "source_sha256": digest}
            continue
        if document["account_ref"] != account["source_account_ref"]:
            fail("DAILY_SOURCE_ACCOUNT_CONFLICT")
        exceptions.pop(digest, None)
        for note in document["notes"]:
            financial_day = note["date"].isoformat()
            if financial_day[:7] != calendar_day[:7] or financial_day > as_of:
                fail("DAILY_ACQUISITION_NOTE_DAY_CONFLICT")
            if not first <= financial_day <= as_of:
                continue
            key = digest + ":" + str(note["slot"])
            if note["kind"] == "SKIPPED_NO_ISIN":
                skips[key] = {"date": financial_day, "reason": "SOURCE_ISIN_ABSENT",
                              "debit": canonical_decimal(note["debit"]), "credit": canonical_decimal(note["credit"])}
                exceptions.pop(key, None)
                continue
            try:
                activity = notice_activity(note, account, mappings)
            except RuntimeError as error:
                exceptions[key] = {"code": str(error), "source_sha256": digest, "source_slot": note["slot"]}
                continue
            if activity["symbol"] in symbols and symbols[activity["symbol"]] != activity["isin"]:
                fail("SECURITY_MAPPING_AMBIGUOUS")
            symbols[activity["symbol"]] = activity["isin"]
            source_identity = {k: canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v
                               for k, v in note.items() if k not in ("slot", "name", "venue")}
            identity = json.dumps({"basis": "independent_notice_v1", "source": source_identity}, sort_keys=True, separators=(",", ":"))
            occurrence = occurrences.get(identity, 0) + 1
            occurrences[identity] = occurrence
            marker = "BD#v1#" + account["account_key"] + "#" + hashlib.sha256((identity + ":" + str(occurrence)).encode()).hexdigest()
            activities[marker] = {**activity, "id": marker}
            source_fields[marker] = {"source_sha256": digest, "source_slot": note["slot"],
                                     "fields": {k: canonical_decimal(v) if isinstance(v, Decimal) else v.isoformat() if hasattr(v, "isoformat") else v
                                                for k, v in note.items()}}
            exceptions.pop(key, None)
    diagnosis = observe_snapshot_discrepancies(activities, remote, snapshot_raw)
    dispositions = {}
    new = {}
    for marker, activity in activities.items():
        entry = diagnosis["activities"][marker]
        candidates = entry["candidates"]
        owned = [r for r in remote if r["comment"] == marker]
        if owned:
            status = "OWNED_OBSERVED" if len(owned) == 1 and activity_financial_fingerprint(owned[0]) == activity_financial_fingerprint(activity) else "OWNED_CONFLICT"
        elif candidates:
            status = "EXISTING_CANDIDATE_REVIEW"
        else:
            status = "NO_EXISTING_CANDIDATE_OBSERVED"
            new[marker] = activity
        dispositions[marker] = status
    report = {"schema_version": 1, "source_mode": "notices", "as_of": as_of,
              "window": {"first": first, "last": as_of}, "import_ready": False,
              "blockers": ["FINANCIAL_APPLICATION_NOT_AUTHORIZED"], "activities": activities,
              "source_evidence": source_fields, "skipped_source_operations": skips, "exceptions": exceptions,
              "destination_diagnosis": diagnosis, "dispositions": dispositions,
              "candidate_export": build_wire_payload(activities)["body"].decode() if activities else None,
              "new_candidate_export": build_wire_payload(new)["body"].decode() if new else None,
              "snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest()}
    journal = {"schema_version": 1, "binding": account, "as_of": as_of, "notice_hashes": hashes, "exceptions": exceptions}
    return journal, report


def preview_local_notices(config, config_path, config_raw, input_root, as_of, max_bytes, max_depth):
    if (set(config) not in ({"schema_version", "source_mode", "account", "mappings", "snapshot", "acquisition_runs"},
                           {"schema_version", "source_mode", "account", "mappings", "snapshot", "acquisition_runs", "index_encoding"})
            or type(config["schema_version"]) is not int or config["schema_version"] != 1):
        fail("INVALID_NOTICE_CONFIGURATION")
    account = config["account"]
    if (not isinstance(account, dict) or set(account) != {"source_account_ref", "account_key", "target_account_id"}
            or any(not isinstance(v, str) or not v.strip() for v in account.values())
            or not isinstance(config["mappings"], dict) or not isinstance(config["snapshot"], str)):
        fail("INVALID_NOTICE_CONFIGURATION")
    validate_account_key(account["account_key"])
    notes, paths, total, evidence, captured = discover_daily_acquisitions(config, input_root, as_of, max_bytes, max_depth)
    snapshot_path = Path(input_root) / config["snapshot"]
    snapshot_raw = read_local_bytes(snapshot_path, input_root, max_bytes)
    if total + len(config_raw) + len(snapshot_raw) > 64 * 1024 * 1024:
        fail("DAILY_INPUT_LIMIT_EXCEEDED")
    paths.extend([Path(config_path), snapshot_path])
    state = Path("state")
    output = Path("outputs") / ("daily-notices-" + account["account_key"] + ".yaml")
    target = hashlib.sha256(account["target_account_id"].encode()).hexdigest()
    journal_path = state / ("daily-notices-" + target + ".yaml")
    binding = state / ("binding-" + account["account_key"] + ".yaml")
    locks = [state / ("prepare-" + target + ".lock"), state / ("account-" + account["account_key"] + ".lock")]
    for path in (output, journal_path, binding, *locks):
        reject_output_input_collision(path, paths)
    private_directory(state)
    private_directory(output.parent)
    descriptors = []
    try:
        for lock in locks:
            descriptor = os.open(lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            descriptors.append(descriptor)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                fail("INVALID_DAILY_LOCK")
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail("DAILY_ACCOUNT_OR_TARGET_LOCKED")
        if binding.exists() or binding.is_symlink():
            if read_keyed_yaml(binding, state, max_bytes) != account:
                fail("ACCOUNT_BINDING_MIGRATION_REQUIRED")
        previous = read_keyed_yaml(journal_path, state, max_bytes) if journal_path.exists() or journal_path.is_symlink() else None
        journal, report = compute_notice_preview(account, config["mappings"], notes, captured, snapshot_raw, previous, as_of, max_depth)
        report["acquisition_runs"] = evidence
        report["config_sha256"] = hashlib.sha256(config_raw).hexdigest()
        if any(len(yaml.safe_dump(value).encode()) > max_bytes for value in (journal, report)):
            fail("DAILY_REPORT_LIMIT_EXCEEDED")
        atomic_private_yaml(binding, account)
        atomic_private_yaml(journal_path, journal)
        atomic_private_yaml(output, report)
        return {"source_mode": "notices", "source_activities": len(report["activities"]),
                "skipped_operations": len(report["skipped_source_operations"]), "unresolved_exceptions": len(report["exceptions"]),
                "import_ready": False, "blockers": report["blockers"]}
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def preview_local_daily(config_path, input_root, as_of, max_bytes, max_depth):
    if type(max_bytes) is not int or not 0 < max_bytes <= 64 * 1024 * 1024 or type(max_depth) is not int or not 0 < max_depth <= 256:
        fail("INVALID_DAILY_PREVIEW_LIMITS")
    daily_preview_day(as_of)
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = parse_keyed_yaml(config_raw)
    if isinstance(config, dict) and config.get("source_mode") == "notices":
        return preview_local_notices(config, config_path, config_raw, input_root, as_of, max_bytes, max_depth)
    acquisition_paths, acquisition_bytes, acquisition_evidence, acquisition_capture = [], 0, None, None
    if isinstance(config, dict) and "acquisition_runs" in config:
        if set(config) != {"schema_version", "account", "mappings", "snapshot", "acquisition_runs", "index_encoding"}:
            fail("INVALID_DAILY_ACQUISITION_CONFIGURATION")
        config, acquisition_paths, acquisition_bytes, acquisition_evidence, acquisition_capture = discover_daily_acquisitions(config, input_root, as_of, max_bytes, max_depth)
    if (not isinstance(config, dict) or set(config) not in ({"schema_version", "account", "mappings", "documents", "snapshot"},
            {"schema_version", "account", "mappings", "documents", "snapshot", "current_period"}) or type(config["snapshot"]) is not str):
        fail("INVALID_DAILY_PREVIEW_CONFIGURATION")
    prep_raw = yaml.safe_dump({k: v for k, v in config.items() if k not in ("snapshot", "current_period")}).encode()
    preparation_configuration(prep_raw, max_bytes, max_depth)
    if sum(1 + len(entry["notes"]) for entry in config["documents"].values()) > 256:
        fail("DAILY_INPUT_LIMIT_EXCEEDED")
    if acquisition_capture is None:
        documents, paths = capture_preparation_sources(prep_raw, input_root, min(max_bytes, 4 * 1024 * 1024), max_depth)
    else:
        documents = {alias: {"statement": acquisition_capture[entry["statement"]],
            "notes": [acquisition_capture[path] for path in entry["notes"]]}
            for alias, entry in config["documents"].items()}
        paths = []
    current_capture = None
    if "current_period" in config:
        references = daily_current_configuration(config["current_period"], as_of)
        if len(references) + sum(1 + len(entry["notes"]) for entry in config["documents"].values()) > 256:
            fail("DAILY_INPUT_LIMIT_EXCEEDED")
        current_capture = {}
        captured_bytes = len(config_raw) + sum(len(c["statement"]) + sum(map(len, c["notes"])) for c in documents.values())
        for key, reference in references.items():
            path = Path(input_root) / reference
            body = (read_local_bytes(path, input_root, min(max_bytes, 4 * 1024 * 1024))
                    if acquisition_capture is None else acquisition_capture[reference])
            captured_bytes += len(body)
            if captured_bytes > 64 * 1024 * 1024:
                fail("DAILY_INPUT_LIMIT_EXCEEDED")
            current_capture[key] = body
            paths.append(path)
    snapshot_path = Path(input_root) / config["snapshot"]
    snapshot_raw = read_local_bytes(snapshot_path, input_root, max_bytes)
    if len(config_raw) + len(snapshot_raw) + sum(len(c["statement"]) + sum(map(len, c["notes"])) for c in documents.values()) + sum(map(len, (current_capture or {}).values())) > 64 * 1024 * 1024:
        fail("DAILY_INPUT_LIMIT_EXCEEDED")
    if acquisition_bytes + len(config_raw) + len(snapshot_raw) > 64 * 1024 * 1024:
        fail("DAILY_INPUT_LIMIT_EXCEEDED")
    inputs = [Path(config_path), snapshot_path, *paths, *acquisition_paths]
    account = config["account"]
    target = hashlib.sha256(account["target_account_id"].encode()).hexdigest()
    state = Path("state")
    binding = state / ("binding-" + account["account_key"] + ".yaml")
    ledger = state / ("ledger-" + target + ".yaml")
    journal_path = state / ("daily-" + target + ".yaml")
    output = Path("outputs") / ("daily-" + account["account_key"] + ".yaml")
    locks = [state / ("prepare-" + target + ".lock"), state / ("account-" + account["account_key"] + ".lock")]
    for destination in (binding, journal_path, output, *locks):
        reject_output_input_collision(destination, inputs)
    private_directory(state)
    private_directory(output.parent)
    descriptors = []
    try:
        for path in locks:
            descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            descriptors.append(descriptor)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                fail("INVALID_DAILY_LOCK")
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail("DAILY_ACCOUNT_OR_TARGET_LOCKED")
        if binding.exists() or binding.is_symlink():
            if read_keyed_yaml(binding, state, max_bytes) != account:
                fail("ACCOUNT_BINDING_MIGRATION_REQUIRED")
        if ledger.exists() or ledger.is_symlink():
            if read_keyed_yaml(ledger, state, max_bytes).get("binding") != account:
                fail("ACCOUNT_BINDING_MIGRATION_REQUIRED")
        previous = read_keyed_yaml(journal_path, state, max_bytes) if journal_path.exists() or journal_path.is_symlink() else None
        journal, report = compute_daily_preview(config, documents, snapshot_raw, previous, as_of, max_bytes, max_depth, current_capture)
        if acquisition_evidence is not None:
            report["acquisition_runs"] = acquisition_evidence
        if any(len(yaml.safe_dump(value).encode()) > max_bytes for value in (journal, report)):
            fail("DAILY_REPORT_LIMIT_EXCEEDED")
        atomic_private_yaml(binding, account)
        atomic_private_yaml(journal_path, journal)
        atomic_private_yaml(output, report)
        return {"closed_period_gaps": len(report["missing_or_unqualified_closed_periods"]),
                "unresolved_exceptions": len(report["exceptions"]), "resume_requires_catchup": report["resume_requires_catchup"],
                "import_ready": False, "blockers": report["blockers"]}
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def legacy_duplicate_candidate(activity, row):
    """Bounded similarity for rejection/diagnosis only, never adoption."""
    day = activity["operation_date"]
    source_day = datetime.fromisoformat(day.isoformat() if hasattr(day, "isoformat") else day).date()
    if activity["kind"] == "DIVIDEND":
        return (row["kind"] == "DIVIDEND" and row["target_account_id"] == activity["target_account_id"]
                and row["symbol"] in (None, activity["symbol"])
                and abs((datetime.fromisoformat(row["operation_date"]).date() - source_day).days) <= 90)
    identity = ("target_account_id", "symbol", "data_source", "kind")
    if row["kind"] not in ("BUY", "SELL") or any(row[k] != activity[k] for k in identity):
        return False
    return (row["quantity"] == Decimal(activity["quantity"])
            and row["unit_price"] == Decimal(activity["unit_price"])
            and abs((datetime.fromisoformat(row["operation_date"]).date() - source_day).days) <= 1)


def reconcile_existing_activities(prepared, remote, resolutions, automatic=False):
    """Private offline adoption proposal; never changes remote records or readiness."""
    if (not isinstance(prepared, dict) or not isinstance(resolutions, dict)
            or type(automatic) is not bool or automatic and resolutions):
        fail("INVALID_ADOPTION_CONFIGURATION")
    if set(resolutions) - set(prepared):
        fail("STALE_ADOPTION_RESOLUTION")
    result = {"new": [], "owned": [], "adopted": {}, "candidates": {},
              "blockers": {"ISOLATED_API_CONTRACT_UNVERIFIED", "OPENING_HOLDINGS_UNVERIFIED"},
              "import_ready": False}
    owned = {}
    for row in remote:
        comment = row["comment"]
        if comment in prepared:
            if comment in owned:
                fail("REMOTE_OWNED_MARKER_DUPLICATE")
            owned[comment] = row
    owned_remote = {row["remote_id"] for row in owned.values()}
    unowned_counts = {}
    if automatic:
        for event_id, activity in prepared.items():
            if event_id not in owned:
                fingerprint = activity_financial_fingerprint(activity)
                unowned_counts[fingerprint] = unowned_counts.get(fingerprint, 0) + 1
    claimed_remote = set()
    for event_id, activity in prepared.items():
        if activity.get("id") != event_id:
            fail("PREPARED_IDENTITY_CONFLICT")
        fingerprint = activity_financial_fingerprint(activity)
        if event_id in owned:
            row = owned[event_id]
            if not row["active"] or not row["date_context_verified"] or not row["financial_context_verified"] or activity_financial_fingerprint(row) != fingerprint:
                fail("REMOTE_OWNED_ACTIVITY_CONFLICT")
            if event_id in resolutions:
                fail("STALE_ADOPTION_RESOLUTION")
            result["owned"].append(event_id)
            claimed_remote.add(row["remote_id"])
            continue
        candidates = [r for r in remote if r["kind"] in ("BUY", "SELL", "DIVIDEND") and r["target_account_id"] == activity["target_account_id"]
                      and activity_financial_fingerprint(r) == fingerprint]
        if any(not r["active"] or not r["date_context_verified"] or not r["financial_context_verified"] for r in candidates):
            fail("REMOTE_CANDIDATE_CONTEXT_UNVERIFIED")
        if not candidates:
            if event_id in resolutions:
                fail("STALE_ADOPTION_RESOLUTION")
            # Different fees/currency or legacy timestamps must not erase a
            # potential duplicate. This rejects similarity; it never adopts it.
            if any(legacy_duplicate_candidate(activity, r) for r in remote):
                fail("REMOTE_LEGACY_DUPLICATE_REVIEW_REQUIRED")
            result["new"].append(event_id)
            continue
        resolution = resolutions.get(event_id)
        if automatic:
            available = [r for r in candidates if r["remote_id"] not in owned_remote]
            foreign = any(isinstance(r["comment"], str) and r["comment"].startswith("BD#")
                          for r in available)
            if unowned_counts[fingerprint] == 1 and len(available) == 1 and not foreign:
                resolution = {"remote_id": available[0]["remote_id"], "financial_fingerprint": fingerprint}
            else:
                result["candidates"][event_id] = sorted(r["remote_id"] for r in candidates)
                result["blockers"].add("AUTOMATIC_ACTIVITY_ADOPTION_UNCERTAIN")
                continue
        if resolution is None:
            result["candidates"][event_id] = [r["remote_id"] for r in candidates]
            result["blockers"].add("MANUAL_ACTIVITY_ADOPTION_REQUIRED")
            continue
        if not isinstance(resolution, dict) or set(resolution) != {"remote_id", "financial_fingerprint"}:
            fail("INVALID_ADOPTION_RESOLUTION")
        selected = [r for r in candidates if r["remote_id"] == resolution["remote_id"]]
        if len(selected) != 1 or resolution["financial_fingerprint"] != fingerprint:
            fail("STALE_ADOPTION_RESOLUTION")
        row = selected[0]
        if row["remote_id"] in claimed_remote:
            fail("ADOPTION_MULTIPLICITY_CONFLICT")
        # Another stable marker cannot be silently adopted under a new owner.
        if isinstance(row["comment"], str) and row["comment"].startswith("BD#"):
            fail("FOREIGN_BD_OWNERSHIP_CONFLICT")
        claimed_remote.add(row["remote_id"])
        result["adopted"][event_id] = dict(resolution)
    result["blockers"] = sorted(result["blockers"])
    return result


def wire_number(value):
    """Accept only source values preserved by the emitted binary64 JSON token."""
    if isinstance(value, str):
        if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", value):
            fail("INVALID_WIRE_DECIMAL")
        value = Decimal(value)
    if not isinstance(value, Decimal) or not value.is_finite():
        fail("INVALID_WIRE_DECIMAL")
    try:
        number = float(value)
        token = json.dumps(number, allow_nan=False)
    except (OverflowError, ValueError):
        fail("WIRE_NUMERIC_PRECISION_LOSS")
    if Decimal(token) != value:
        fail("WIRE_NUMERIC_PRECISION_LOSS")
    # Integer tokens must also survive JavaScript Number, checked above.
    return int(value) if value == value.to_integral_value() and abs(value) <= 2 ** 53 else number


def build_wire_payload(activities):
    """Pure private byte review; does not grant permission or import readiness."""
    if not isinstance(activities, dict) or not activities or any(not isinstance(k, str) for k in activities):
        fail("INVALID_WIRE_ACTIVITIES")
    rows = []
    binding = None
    for marker in sorted(activities):
        activity = activities[marker]
        if not isinstance(activity, dict) or activity.get("id") != marker:
            fail("WIRE_IDENTITY_CONFLICT")
        account_key = activity.get("account_key")
        validate_account_key(account_key)
        if not isinstance(marker, str) or not re.fullmatch(r"BD#v1#" + re.escape(account_key) + r"#[0-9a-f]{64}", marker):
            fail("WIRE_IDENTITY_CONFLICT")
        target = activity.get("target_account_id")
        if not isinstance(target, str) or not target.strip() or target != target.strip():
            fail("WIRE_ACCOUNT_INVALID")
        current = (account_key, target)
        if binding is not None and current != binding:
            fail("WIRE_ACCOUNT_BINDING_CONFLICT")
        binding = current
        if activity.get("kind") not in ("BUY", "SELL", "DIVIDEND") or activity.get("data_source") != "YAHOO" or activity.get("price_currency") != "EUR":
            fail("UNSUPPORTED_WIRE_TRADE")
        symbol = activity.get("symbol")
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]{0,63}", symbol):
            fail("WIRE_SYMBOL_INVALID")
        day = activity.get("operation_date")
        day = day.isoformat() if hasattr(day, "isoformat") else day
        if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            fail("WIRE_DATE_INVALID")
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            fail("WIRE_DATE_INVALID")
        amounts = {key: wire_number(activity.get(key)) for key in ("quantity", "unit_price", "fee")}
        if amounts["quantity"] <= 0 or amounts["unit_price"] <= 0 or amounts["fee"] < 0:
            fail("WIRE_TRADE_AMOUNT_INVALID")
        if activity["kind"] == "DIVIDEND" and (amounts["quantity"] != 1 or amounts["fee"] != 0):
            fail("WIRE_DIVIDEND_NET_REPRESENTATION_REQUIRED")
        rows.append({"accountId": target, "comment": marker, "currency": "EUR", "dataSource": "YAHOO",
                     "date": day + "T00:00:00.000Z", "fee": amounts["fee"], "quantity": amounts["quantity"],
                     "symbol": symbol, "type": activity["kind"], "unitPrice": amounts["unit_price"]})
    # Chronological days; stable marker breaks ties without inventing clock zones.
    rows.sort(key=lambda row: (row["date"], row["comment"]))
    body = json.dumps({"activities": rows}, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"body": body, "sha256": hashlib.sha256(body).hexdigest(), "import_ready": False}


def reviewed_wire_rows(review):
    """Reject tampered, noncanonical or nonallowlisted review bytes."""
    if not isinstance(review, dict) or not isinstance(review.get("body"), bytes):
        fail("INVALID_WIRE_REVIEW")
    body = review["body"]
    if review.get("sha256") != hashlib.sha256(body).hexdigest() or review.get("import_ready") is not False:
        fail("WIRE_REVIEW_CONFLICT")
    try:
        data = json.loads(body, parse_float=Decimal, object_pairs_hook=unique_json_object)
    except (ValueError, TypeError, RecursionError):
        fail("INVALID_WIRE_REVIEW_JSON")
    if not isinstance(data, dict) or set(data) != {"activities"} or not isinstance(data["activities"], list):
        fail("INVALID_WIRE_REVIEW")
    activities = {}
    keys = {"accountId", "comment", "currency", "dataSource", "date", "fee", "quantity", "symbol", "type", "unitPrice"}
    for row in data["activities"]:
        if not isinstance(row, dict) or set(row) != keys or not isinstance(row.get("comment"), str):
            fail("INVALID_WIRE_REVIEW")
        marker = row["comment"]
        if marker in activities or len(marker.split("#")) != 4:
            fail("WIRE_IDENTITY_CONFLICT")
        if not isinstance(row["date"], str) or not row["date"].endswith("T00:00:00.000Z"):
            fail("WIRE_DATE_INVALID")
        activities[marker] = {"id": marker, "account_key": marker.split("#")[2],
                              "target_account_id": row["accountId"], "price_currency": row["currency"],
                              "data_source": row["dataSource"], "operation_date": row["date"][:-14],
                              "kind": row["type"], "symbol": row["symbol"],
                              "quantity": remote_decimal(row["quantity"]),
                              "unit_price": remote_decimal(row["unitPrice"]), "fee": remote_decimal(row["fee"])}
    if build_wire_payload(activities)["body"] != body:
        fail("WIRE_REVIEW_NONCANONICAL")
    return {row["comment"]: row for row in data["activities"]}


def compare_import_response(review, raw):
    """Exact POST evidence only; full readback and uncertainty fences remain gates."""
    return compare_expected_import_response(reviewed_wire_rows(review), raw)


def compare_expected_import_response(expected, raw):
    """POST projection needs no GET-only account/tags context."""
    result = {"status": "conflicting", "accepted": {}, "missing": sorted(expected),
              "import_ready": False, "blockers": ["COMPLETE_READBACK_REQUIRED", "UNCERTAIN_WRITE_RECOVERY_UNVERIFIED"]}
    try:
        data = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_json_object)
        if not isinstance(data, dict) or not isinstance(data.get("activities"), list):
            fail("INVALID_IMPORT_RESPONSE")
        seen_ids = set()
        for row in data["activities"]:
            if (not isinstance(row, dict) or row.get("error") or row.get("isDraft") is True
                    or row.get("isActive") is False):
                fail("INVALID_IMPORT_RESPONSE")
            marker, remote_id = row.get("comment"), row.get("id")
            if not isinstance(marker, str) or marker not in expected or marker in result["accepted"]:
                fail("IMPORT_RESPONSE_OWNERSHIP_CONFLICT")
            if not isinstance(remote_id, str) or not remote_id.strip() or remote_id in seen_ids:
                fail("IMPORT_RESPONSE_ID_CONFLICT")
            sent = expected[marker]
            if any(row.get(key) != sent[key] for key in ("accountId", "currency", "type")):
                fail("IMPORT_RESPONSE_FINANCIAL_CONFLICT")
            profile = row["assetProfile"] if "assetProfile" in row else row.get("SymbolProfile")
            if not isinstance(profile, dict) or any(profile.get(k) != sent[k] for k in ("symbol", "dataSource", "currency")):
                fail("IMPORT_RESPONSE_PROFILE_CONFLICT")
            if any(remote_decimal(row.get(key)) != remote_decimal(sent[key]) for key in ("quantity", "unitPrice", "fee")):
                fail("IMPORT_RESPONSE_FINANCIAL_CONFLICT")
            if not isinstance(row.get("date"), str):
                fail("IMPORT_RESPONSE_DATE_CONFLICT")
            try:
                instant = datetime.fromisoformat(row["date"].replace("Z", "+00:00"))
            except ValueError:
                fail("IMPORT_RESPONSE_DATE_CONFLICT")
            if instant.tzinfo is None or instant.astimezone(timezone.utc) != datetime.fromisoformat(sent["date"].replace("Z", "+00:00")):
                fail("IMPORT_RESPONSE_DATE_CONFLICT")
            result["accepted"][marker] = remote_id
            seen_ids.add(remote_id)
    except (ValueError, TypeError, RecursionError):
        result["conflict_code"] = "INVALID_IMPORT_RESPONSE_JSON"
    except RuntimeError as error:
        result["conflict_code"] = str(error)
    else:
        result["status"] = "complete" if len(result["accepted"]) == len(expected) else "partial" if result["accepted"] else "skipped"
    result["missing"] = sorted(set(expected) - set(result["accepted"]))
    return result


def validate_write_journal(journal):
    if not isinstance(journal, dict) or set(journal) != {"schema_version", "binding", "intents"} or type(journal["schema_version"]) is not int or journal["schema_version"] != 1:
        fail("INVALID_WRITE_JOURNAL")
    binding = journal["binding"]
    if not isinstance(binding, dict) or set(binding) != {"account_key", "target_account_id"}:
        fail("INVALID_WRITE_JOURNAL")
    validate_account_key(binding["account_key"])
    if not isinstance(binding["target_account_id"], str) or not binding["target_account_id"].strip():
        fail("INVALID_WRITE_JOURNAL")
    if not isinstance(journal["intents"], dict):
        fail("INVALID_WRITE_JOURNAL")
    for digest, intent in journal["intents"].items():
        if not isinstance(intent, dict) or set(intent) != {"body", "state", "resolution"} or not isinstance(intent["body"], str):
            fail("INVALID_WRITE_JOURNAL")
        rows = reviewed_wire_rows({"body": intent["body"].encode("utf-8"), "sha256": digest, "import_ready": False})
        if any(r["accountId"] != binding["target_account_id"] or r["comment"].split("#")[2] != binding["account_key"] for r in rows.values()):
            fail("WRITE_JOURNAL_BINDING_CONFLICT")
        resolution = intent["resolution"]
        if intent["state"] == "uncertain":
            if resolution is not None:
                fail("INVALID_WRITE_JOURNAL")
        elif intent["state"] in ("confirmed", "quiescent"):
            if not isinstance(resolution, dict) or set(resolution) != {"snapshot_sha256", "accepted", "completion_evidence"}:
                fail("INVALID_WRITE_JOURNAL")
            if not isinstance(resolution["snapshot_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", resolution["snapshot_sha256"]):
                fail("INVALID_WRITE_JOURNAL")
            accepted = resolution["accepted"]
            if not isinstance(accepted, dict) or set(accepted) - set(rows) or any(not isinstance(v, str) or not v.strip() for v in accepted.values()) or len(set(accepted.values())) != len(accepted):
                fail("INVALID_WRITE_JOURNAL")
            if intent["state"] == "confirmed":
                if set(accepted) != set(rows) or resolution["completion_evidence"] is not None:
                    fail("INVALID_WRITE_JOURNAL")
            else:
                validate_completion_evidence(resolution["completion_evidence"], digest)
        else:
            fail("INVALID_WRITE_JOURNAL")


def validate_completion_evidence(evidence, digest):
    # Explicit operator review is data, not automatically inferred from elapsed time.
    if not isinstance(evidence, dict) or set(evidence) != {"kind", "reviewed_by", "reference", "wire_sha256"}:
        fail("INDEPENDENT_COMPLETION_EVIDENCE_REQUIRED")
    if evidence["kind"] not in ("independently_completed", "independently_cancelled") or evidence["wire_sha256"] != digest:
        fail("INDEPENDENT_COMPLETION_EVIDENCE_REQUIRED")
    if any(not isinstance(evidence[k], str) or not evidence[k].strip() for k in ("reviewed_by", "reference")):
        fail("INDEPENDENT_COMPLETION_EVIDENCE_REQUIRED")


def write_intent_transition(journal, review):
    validate_write_journal(journal)
    rows = reviewed_wire_rows(review)
    binding = journal["binding"]
    if any(r["accountId"] != binding["target_account_id"] or r["comment"].split("#")[2] != binding["account_key"] for r in rows.values()):
        fail("WRITE_JOURNAL_BINDING_CONFLICT")
    if any(i["state"] == "uncertain" for i in journal["intents"].values()):
        fail("ACCOUNT_WRITE_UNCERTAIN")
    if review["sha256"] in journal["intents"]:
        fail("WRITE_INTENT_ALREADY_RECORDED")
    previously_accepted = {marker for i in journal["intents"].values()
                           for marker in i["resolution"]["accepted"]}
    if set(rows) & previously_accepted:
        fail("WRITE_INTENT_PREVIOUSLY_ACCEPTED")
    # Conservative crash window: already uncertain before any dispatch can occur.
    return {**journal, "intents": {**journal["intents"], review["sha256"]:
            {"body": review["body"].decode("utf-8"), "state": "uncertain", "resolution": None}}}


def resolve_write_intent(journal, digest, raw_snapshot, completion_evidence=None):
    """Pure resolution: all-positive complete context, or explicit independent proof."""
    validate_write_journal(journal)
    intent = journal["intents"].get(digest)
    if intent is None or intent["state"] != "uncertain":
        fail("WRITE_INTENT_NOT_UNCERTAIN")
    review = {"body": intent["body"].encode("utf-8"), "sha256": digest, "import_ready": False}
    expected = reviewed_wire_rows(review)
    normalized = parse_remote_activity_snapshot(raw_snapshot)
    selected = [r for r in normalized if r["comment"] in expected]
    if any(not r["active"] or not r["date_context_verified"] or not r["financial_context_verified"] for r in selected):
        fail("WRITE_READBACK_CONTEXT_CONFLICT")
    accepted = {}
    for row in selected:
        marker = row["comment"]
        sent = expected[marker]
        comparison = {"target_account_id": sent["accountId"], "operation_date": sent["date"][:10],
                      "kind": sent["type"], "symbol": sent["symbol"], "data_source": sent["dataSource"],
                      "price_currency": sent["currency"], "quantity": remote_decimal(sent["quantity"]),
                      "unit_price": remote_decimal(sent["unitPrice"]), "fee": remote_decimal(sent["fee"])}
        if marker in accepted or activity_financial_fingerprint(row) != activity_financial_fingerprint(comparison):
            fail("WRITE_READBACK_CONFLICT")
        accepted[marker] = row["remote_id"]
    if set(accepted) == set(expected):
        state, completion_evidence = "confirmed", None
    else:
        validate_completion_evidence(completion_evidence, digest)
        state = "quiescent"
    raw = raw_snapshot.encode("utf-8") if isinstance(raw_snapshot, str) else raw_snapshot
    resolution = {"snapshot_sha256": hashlib.sha256(raw).hexdigest(), "accepted": accepted,
                  "completion_evidence": dict(completion_evidence) if completion_evidence is not None else None}
    return {**journal, "intents": {**journal["intents"], digest: {**intent, "state": state, "resolution": resolution}}}


def _acquire_write_locks(root, binding):
    target = hashlib.sha256(binding["target_account_id"].encode()).hexdigest()
    descriptors = []
    try:
        for name, code in (("prepare-" + target, "WRITE_TARGET_LOCKED"),
                           ("account-" + binding["account_key"], "WRITE_ACCOUNT_LOCKED")):
            descriptor = os.open(root / (name + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
            descriptors.append(descriptor)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                fail("INVALID_WRITE_LOCK")
            os.fchmod(descriptor, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail(code)
        return target, descriptors
    except BaseException:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _persist_write_transition_locked(root, binding, target, max_bytes, action, review=None,
                                     digest=None, raw_snapshot=None, completion_evidence=None):
    """Internal: caller holds both target and namespace locks."""
    binding_path = root / ("write-binding-" + binding["account_key"] + ".yaml")
    if binding_path.exists() or binding_path.is_symlink():
        if read_keyed_yaml(binding_path, root, max_bytes) != binding:
            fail("WRITE_JOURNAL_BINDING_CONFLICT")
    path = root / ("writes-" + target + ".yaml")
    journal = read_keyed_yaml(path, root, max_bytes) if path.exists() or path.is_symlink() else {"schema_version": 1, "binding": dict(binding), "intents": {}}
    if journal.get("binding") != binding:
        fail("WRITE_JOURNAL_BINDING_CONFLICT")
    if action == "intent":
        updated = write_intent_transition(journal, review)
    elif action == "resolve":
        updated = resolve_write_intent(journal, digest, raw_snapshot, completion_evidence)
    else:
        fail("INVALID_WRITE_TRANSITION")
    encoded = yaml.safe_dump(updated, sort_keys=False, allow_unicode=True).encode("utf-8")
    if max_bytes <= 0 or len(encoded) > max_bytes:
        fail("WRITE_JOURNAL_TOO_LARGE")
    atomic_private_yaml(binding_path, binding)
    atomic_private_yaml(path, updated)
    return {"wire_sha256": review["sha256"] if action == "intent" else digest,
            "account_fenced": any(i["state"] == "uncertain" for i in updated["intents"].values()),
            "import_ready": False}


def persist_write_transition(state_root, binding, max_bytes, action, review=None,
                             digest=None, raw_snapshot=None, completion_evidence=None):
    """Locked local durability boundary only; no dispatch, response or replay API."""
    validate_write_journal({"schema_version": 1, "binding": binding, "intents": {}})
    root = private_directory(state_root)
    target, locks = _acquire_write_locks(root, binding)
    try:
        return _persist_write_transition_locked(root, binding, target, max_bytes, action,
            review=review, digest=digest, raw_snapshot=raw_snapshot, completion_evidence=completion_evidence)
    finally:
        for descriptor in reversed(locks):
            os.close(descriptor)


def _dispatch_json(raw, max_bytes):
    if not isinstance(raw, bytes) or len(raw) > max_bytes:
        fail("LAB_DISPATCH_BODY_LIMIT_OR_TYPE")
    try:
        data = json.loads(raw, parse_float=Decimal, parse_int=Decimal,
                          parse_constant=lambda value: fail("INVALID_LAB_DISPATCH_JSON"),
                          object_pairs_hook=unique_json_object)
    except (ValueError, TypeError, RecursionError, InvalidOperation):
        fail("INVALID_LAB_DISPATCH_JSON")
    pending = [data]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, Decimal):
            bound_decimal_shape(value, max_bytes)
    return data


def _dispatch_snapshot(raw, max_bytes):
    # Separate richer comparison context; existing normalizer schema is unchanged.
    _dispatch_json(raw, max_bytes)
    try:
        normalized = bounded_remote_snapshot(raw, max_bytes)
    except (ValueError, OverflowError, InvalidOperation):
        fail("INVALID_LAB_DISPATCH_SNAPSHOT")
    original = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_json_object)
    semantic = {}
    for row, source in zip(normalized, original["activities"]):
        contexts = []
        for context in (source, source["account"]):
            contexts.append(None if context is None else {
                "flags": {k: (k in context, context.get(k)) for k in ("isDraft", "isExcluded")},
                "tags": sorted(t["id"] for t in context["tags"])})
        profile = source["assetProfile"] if "assetProfile" in source else source.get("SymbolProfile")
        semantic[row["remote_id"]] = {**row,
            "full_utc_instant": datetime.fromisoformat(source["date"].replace("Z", "+00:00")).astimezone(timezone.utc).isoformat(),
            "persistent_context": contexts,
            "profile_identity": None if not isinstance(profile, dict) else {
                k: (k in profile, profile.get(k)) for k in ("id", "symbol", "dataSource", "currency")}}
    return semantic


def _dispatch_single_intent(state_root, binding, reviewed, baseline_raw, max_bytes, request):
    """Protocol core; caller owns source qualification and invocation authority."""
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_LAB_DISPATCH_LIMIT")
    if not isinstance(reviewed, dict) or not isinstance(reviewed.get("body"), bytes) or len(reviewed["body"]) > max_bytes:
        fail("LAB_DISPATCH_BODY_LIMIT_OR_TYPE")
    _dispatch_json(reviewed["body"], max_bytes)
    expected = reviewed_wire_rows(reviewed)
    if len(expected) != 1:
        fail("LAB_DISPATCH_SINGLE_ACTIVITY_REQUIRED")
    validate_write_journal({"schema_version": 1, "binding": binding, "intents": {}})
    marker, sent = next(iter(expected.items()))
    if sent["accountId"] != binding["target_account_id"] or marker.split("#")[2] != binding["account_key"]:
        fail("WRITE_JOURNAL_BINDING_CONFLICT")
    baseline = _dispatch_snapshot(baseline_raw, max_bytes)
    if any(row["comment"] == marker for row in baseline.values()):
        fail("LAB_DISPATCH_MARKER_ALREADY_PRESENT")
    if datetime.fromisoformat(sent["date"].replace("Z", "+00:00")) > datetime.now(timezone.utc):
        fail("LAB_DISPATCH_FUTURE_ACTIVITY")
    def call(method, body=None):
        try:
            response = request(method, "/api/v1/import" if method == "POST" else "/api/v1/activities", body)
        except Exception:
            raise RuntimeError("LAB_DISPATCH_TRANSPORT_FAILED") from None
        if not isinstance(response, tuple) or len(response) != 2 or type(response[0]) is not int or not isinstance(response[1], bytes):
            fail("LAB_DISPATCH_RESPONSE_INVALID")
        if len(response[1]) > max_bytes:
            fail("LAB_DISPATCH_RESPONSE_TOO_LARGE")
        return response
    root = private_directory(state_root)
    target, locks = _acquire_write_locks(root, binding)
    try:
        binding_path = root / ("write-binding-" + binding["account_key"] + ".yaml")
        if (binding_path.exists() or binding_path.is_symlink()) and read_keyed_yaml(binding_path, root, max_bytes) != binding:
            fail("WRITE_JOURNAL_BINDING_CONFLICT")
        path = root / ("writes-" + target + ".yaml")
        journal = read_keyed_yaml(path, root, max_bytes) if path.exists() or path.is_symlink() else {"schema_version": 1, "binding": dict(binding), "intents": {}}
        if journal.get("binding") != binding:
            fail("WRITE_JOURNAL_BINDING_CONFLICT")
        # All fences and tombstones must reject before even the first GET.
        write_intent_transition(journal, reviewed)
        status, raw = call("GET")
        if status != 200 or _dispatch_snapshot(raw, max_bytes) != baseline:
            fail("LAB_DISPATCH_BASELINE_CHANGED")
        try:
            _persist_write_transition_locked(root, binding, target, max_bytes, "intent", review=reviewed)
        except OSError:
            raise RuntimeError("LAB_DISPATCH_PERSISTENCE_FAILED") from None
        status, raw = call("POST", reviewed["body"])
        if status != 201:
            fail("LAB_DISPATCH_ACCEPTANCE_FAILED")
        _dispatch_json(raw, max_bytes)
        try:
            comparison = compare_import_response(reviewed, raw)
        except (InvalidOperation, ValueError, OverflowError, TypeError):
            fail("LAB_DISPATCH_ACCEPTANCE_FAILED")
        if comparison["status"] != "complete" or set(comparison["accepted"]) != {marker}:
            fail("LAB_DISPATCH_ACCEPTANCE_FAILED")
        remote_id = comparison["accepted"][marker]
        if remote_id in baseline:
            fail("LAB_DISPATCH_ACCEPTED_ID_ALREADY_PRESENT")
        status, raw = call("GET")
        if status != 200:
            fail("LAB_DISPATCH_READBACK_FAILED")
        readback = _dispatch_snapshot(raw, max_bytes)
        if (set(readback) != set(baseline) | {remote_id}
                or any(readback[k] != v for k, v in baseline.items())):
            fail("LAB_DISPATCH_TRANSITION_CONFLICT")
        row = readback[remote_id]
        wanted = {"target_account_id": sent["accountId"], "operation_date": sent["date"][:10],
            "kind": sent["type"], "symbol": sent["symbol"], "data_source": sent["dataSource"],
            "price_currency": sent["currency"], "quantity": remote_decimal(sent["quantity"]),
            "unit_price": remote_decimal(sent["unitPrice"]), "fee": remote_decimal(sent["fee"])}
        if (row["comment"] != marker or not row["active"] or not row["date_context_verified"]
                or not row["financial_context_verified"]
                or activity_financial_fingerprint(row) != activity_financial_fingerprint(wanted)
                or sum(r["comment"] == marker for r in readback.values()) != 1):
            fail("LAB_DISPATCH_TRANSITION_CONFLICT")
        try:
            _persist_write_transition_locked(root, binding, target, max_bytes, "resolve",
                digest=reviewed["sha256"], raw_snapshot=raw)
        except OSError:
            raise RuntimeError("LAB_DISPATCH_PERSISTENCE_FAILED") from None
        return {"accepted": 1, "readback": raw, "import_ready": False}
    finally:
        for descriptor in reversed(locks):
            os.close(descriptor)


def verify_chronological_holdings(prepared, raw_snapshot, resolutions, history_evidence, automatic=False, as_of=None):
    """Pure conservative coverage proof; never invent opening acquisitions."""
    build_wire_payload(prepared)
    remote = parse_remote_activity_snapshot(raw_snapshot)
    adoption = reconcile_existing_activities(prepared, remote, resolutions, automatic=automatic)
    raw = raw_snapshot.encode("utf-8") if isinstance(raw_snapshot, str) else raw_snapshot
    snapshot_digest = hashlib.sha256(raw).hexdigest()
    target = next(iter(prepared.values()))["target_account_id"]
    keys = {"kind", "target_account_id", "snapshot_sha256", "confirmed_by", "reference"}
    if not isinstance(history_evidence, dict) or set(history_evidence) != keys or history_evidence.get("kind") != "complete_acquisition_history" or history_evidence.get("target_account_id") != target or history_evidence.get("snapshot_sha256") != snapshot_digest:
        fail("COMPLETE_ACQUISITION_HISTORY_EVIDENCE_REQUIRED")
    if any(not isinstance(history_evidence[k], str) or not history_evidence[k].strip() for k in ("confirmed_by", "reference")):
        fail("COMPLETE_ACQUISITION_HISTORY_EVIDENCE_REQUIRED")
    if adoption["candidates"]:
        fail("HOLDINGS_ADOPTION_UNRESOLVED")
    selected_new = adoption["new"]
    if as_of is not None:
        first_day = (daily_preview_day(as_of) - timedelta(days=89)).isoformat()
        selected_new = [marker for marker in selected_new
                        if first_day <= str(prepared[marker]["operation_date"]) <= as_of]
    symbols = {a["symbol"] for a in prepared.values() if a["kind"] in ("BUY", "SELL")}
    events = []
    for row in remote:
        if row["target_account_id"] != target or not row["active"]:
            continue
        if row["kind"] in ("DIVIDEND", "FEE", "INTEREST"):
            continue  # These do not change security quantities in the pinned enum.
        if row["kind"] not in ("BUY", "SELL"):
            fail("UNSUPPORTED_HOLDINGS_ACTIVITY")
        if row["symbol"] not in symbols:
            continue
        if not row["date_context_verified"] or not row["financial_context_verified"] or row["data_source"] != "YAHOO" or row["price_currency"] != "EUR":
            fail("HOLDINGS_SECURITY_OR_DATE_CONTEXT_UNVERIFIED")
        events.append(row)
    for marker in selected_new:
        activity = prepared[marker]
        if activity["kind"] == "DIVIDEND":
            continue
        day = activity["operation_date"]
        day = day.isoformat() if hasattr(day, "isoformat") else day
        if day > datetime.now(timezone.utc).date().isoformat():
            fail("FUTURE_HOLDINGS_ACTIVITY")
        quantity = Decimal(activity["quantity"]) if isinstance(activity["quantity"], str) else activity["quantity"]
        events.append({"operation_date": day, "symbol": activity["symbol"], "kind": activity["kind"], "quantity": quantity})
    grouped = {}
    for event in events:
        key = (event["operation_date"], event["symbol"])
        grouped.setdefault(key, []).append(event)
    balances, shortages = {}, []
    quantities = [e["quantity"] for e in events]
    with localcontext() as context:
        context.prec = max(28, sum(len(q.as_tuple().digits) + abs(q.as_tuple().exponent) for q in quantities) + 8)
        for (day, symbol), trades in sorted(grouped.items()):
            before = balances.get(symbol, Decimal(0))
            buys = sum((t["quantity"] for t in trades if t["kind"] == "BUY"), Decimal(0))
            sells = sum((t["quantity"] for t in trades if t["kind"] == "SELL"), Decimal(0))
            if sells > 0 and sells > before:
                shortages.append({"date": day, "symbol": symbol, "available_before_day": canonical_decimal(before),
                                  "sales": canonical_decimal(sells), "same_day_buys": canonical_decimal(buys)})
            balances[symbol] = before + buys - sells
    result = {"snapshot_sha256": snapshot_digest, "coverage_verified": not shortages,
            "shortages": shortages, "ending_quantities": {k: canonical_decimal(v) for k, v in sorted(balances.items())},
            "adoption": adoption, "import_ready": False,
            "blockers": ["DESTINATION_VALIDATION_REQUIRED", "SECURITY_REVIEW_REQUIRED"] + (["CHRONOLOGICAL_HOLDINGS_SHORTFALL"] if shortages else [])}
    if as_of is not None:
        result["booking_window"] = {"first_day": first_day, "last_day": as_of, "days": 90}
        result["selected_new"] = selected_new
    return result


def validated_prepared_review(raw):
    """Shared existing preparation checks; transient numeric validation only."""
    prepared = parse_keyed_yaml(raw)
    expected = {"schema_version", "artifact_kind", "import_ready", "blockers", "account_key", "target_account_id", "source_digests", "activities"}
    if set(prepared) != expected or type(prepared["schema_version"]) is not int or prepared["schema_version"] != 1 or prepared["artifact_kind"] != "internal_activity_review_not_api_payload" or prepared["import_ready"] is not False:
        fail("INVALID_PREPARED_REVIEW_ARTIFACT")
    activities = prepared["activities"]
    build_wire_payload(activities)
    for activity in activities.values():
        if activity["account_key"] != prepared["account_key"] or activity["target_account_id"] != prepared["target_account_id"] or activity.get("import_ready") is not False:
            fail("PREPARED_REVIEW_BINDING_CONFLICT")
    return prepared


def reject_output_input_collision(destination, input_paths):
    destination = Path(destination)
    try:
        resolved = destination.resolve()
        paths = [(Path(path), Path(path).resolve()) for path in input_paths]
    except (OSError, RuntimeError):
        fail("INVALID_OUTPUT_PATH")
    for path, source in paths:
        if resolved == source or destination.exists() and destination.samefile(path):
            fail("OUTPUT_INPUT_COLLISION")


def observe_snapshot_discrepancies(activities, remote, snapshot_raw):
    """Bounded source/snapshot evidence only; no adoption or date normalization."""
    if len(activities) * len(remote) > 1000000:
        fail("DIAGNOSIS_COMPARISON_LIMIT_EXCEEDED")
    original = json.loads(snapshot_raw, parse_float=Decimal, object_pairs_hook=unique_json_object)
    timestamps = {r["id"]: r["date"] for r in original["activities"]}
    fingerprints = {r["remote_id"]: activity_financial_fingerprint(r) for r in remote}
    fields = ("target_account_id", "operation_date", "kind", "symbol", "data_source", "price_currency",
              "quantity", "unit_price", "fee")
    numeric = ("quantity", "unit_price", "fee")
    sources, evidence, uses = {}, {}, {}
    candidate_count = 0
    for marker, activity in sorted(activities.items()):
        source = {k: canonical_decimal(Decimal(activity[k])) if k in numeric else activity[k] for k in fields}
        if hasattr(source["operation_date"], "isoformat"):
            source["operation_date"] = source["operation_date"].isoformat()
        fingerprint = activity_financial_fingerprint(activity)
        candidates, codes, owned_count = {}, set(), 0
        for row in remote:
            remote_id = row["remote_id"]
            exact = fingerprints[remote_id] == fingerprint
            nearby = legacy_duplicate_candidate(activity, row)
            owned = row["comment"] == marker
            if not (exact or nearby or owned):
                continue
            candidate_count += 1
            if candidate_count > 10000:
                fail("DIAGNOSIS_CANDIDATE_LIMIT_EXCEEDED")
            values = {k: canonical_decimal(row[k]) if k in numeric else row[k] for k in fields}
            verified = row["active"] and row["date_context_verified"] and row["financial_context_verified"]
            ownership = ("SELF_MARKER" if owned else "FOREIGN_BD_MARKER" if isinstance(row["comment"], str)
                         and row["comment"].startswith("BD#") else "OTHER_COMMENT" if row["comment"] else "UNMARKED")
            # No full raw record or free-text comment enters the report.
            evidence[remote_id] = {**values, "original_timestamp": timestamps[remote_id],
                                   "active_at_evaluation": row["active"],
                                   "date_context_verified": row["date_context_verified"],
                                   "financial_context_verified": row["financial_context_verified"],
                                   "currency_origin": row["currency_origin"]}
            candidates[remote_id] = {"exact_financial_match": exact, "nearby_legacy_candidate": nearby,
                                     "ownership": ownership,
                                     "different_fields": [k for k in fields if source[k] != values[k]]}
            uses[remote_id] = uses.get(remote_id, 0) + 1
            if owned:
                owned_count += 1
                codes.add("OWNED_MARKER_OBSERVED")
                if not exact:
                    codes.add("OWNED_MARKER_FINANCIAL_CONFLICT")
            if exact:
                codes.add("EXACT_FINANCIAL_MATCH_OBSERVED")
            elif nearby:
                codes.add("NEAR_LEGACY_CANDIDATE_OBSERVED")
            if not verified:
                codes.add("CANDIDATE_CONTEXT_UNVERIFIED")
        if owned_count > 1:
            codes.add("OWNED_MARKER_DUPLICATE")
        if not candidates:
            codes.add("NO_CANDIDATE_IN_BOUNDED_CHECK")
        sources[marker] = {"source": source, "candidates": candidates, "codes": sorted(codes)}
    for entry in sources.values():
        if any(uses[key] > 1 for key in entry["candidates"]):
            entry["codes"] = sorted(set(entry["codes"]) | {"SHARED_CANDIDATE_REVIEW_REQUIRED"})
    return {"activities": sources, "remote_evidence": evidence}


def diagnose_local_snapshot(config_path, input_root, max_bytes):
    """Private uncertainty evidence, without adoption/history/delivery claims."""
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = parse_keyed_yaml(config_raw)
    if set(config) != {"schema_version", "prepared", "snapshot"} or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        fail("INVALID_DIAGNOSIS_CONFIGURATION")
    captures = {}
    paths = [Path(config_path)]
    for key in ("prepared", "snapshot"):
        if not isinstance(config[key], str) or not config[key].strip():
            fail("INVALID_DIAGNOSIS_CONFIGURATION")
        paths.append(Path(input_root) / config[key])
        captures[key] = read_local_bytes(paths[-1], input_root, max_bytes)
    prepared = validated_prepared_review(captures["prepared"])
    started_at = datetime.now(timezone.utc).isoformat()
    remote = parse_remote_activity_snapshot(captures["snapshot"])
    diagnosis = observe_snapshot_discrepancies(prepared["activities"], remote, captures["snapshot"])
    sources, evidence = diagnosis["activities"], diagnosis["remote_evidence"]
    artifact = {"schema_version": 1, "artifact_kind": "offline_diagnosis_not_adoption_or_delivery",
                "engine_contract": "strict-offline-diagnosis-v1", "import_ready": False,
                "evaluation_started_at_utc": started_at, "account_key": prepared["account_key"],
                "target_account_id": prepared["target_account_id"], "source_digests": prepared["source_digests"],
                "input_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in {"config": config_raw, **captures}.items()},
                "activities": sources, "remote_evidence": evidence,
                "blockers": ["DIAGNOSIS_IS_NOT_ADOPTION", "COMPLETE_ACQUISITION_HISTORY_EVIDENCE_REQUIRED",
                             "PRODUCTION_WRITES_NOT_AUTHORIZED"]}
    raw = yaml.safe_dump(artifact, sort_keys=False, allow_unicode=True).encode("utf-8")
    if len(raw) > max_bytes:
        fail("DIAGNOSIS_OUTPUT_LIMIT_EXCEEDED")
    output = Path("outputs") / ("diagnosis-" + prepared["account_key"] + ".yaml")
    reject_output_input_collision(output, paths)
    private_directory("outputs")
    state = private_directory("state")
    target = hashlib.sha256(prepared["target_account_id"].encode("utf-8")).hexdigest()
    lock = os.open(state / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_DIAGNOSIS_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("DIAGNOSIS_TARGET_LOCKED")
        atomic_private_bytes(output, raw)
    finally:
        os.close(lock)
    return {"source_activities": len(sources), "sources_with_candidates": sum(bool(s["candidates"]) for s in sources.values()),
            "remote_candidates": len(evidence), "import_ready": False, "blockers": artifact["blockers"]}


def review_capture_configuration(config_raw):
    config = parse_keyed_yaml(config_raw)
    roles = ("prepared", "snapshot", "resolutions", "history_evidence")
    version = config.get("schema_version")
    keys = {"schema_version", *roles} | ({"adoption_mode"} if version in (2, 3) else set())
    if version == 3:
        keys.add("as_of")
    if (set(config) != keys or type(version) is not int or version not in (1, 2, 3)
            or version in (2, 3) and config.get("adoption_mode") != "certain_unique"
            or any(not isinstance(config[k], str) or not config[k].strip() for k in roles)):
        fail("INVALID_REVIEW_CONFIGURATION")
    if version == 3:
        daily_preview_day(config["as_of"])
    return config


def compute_offline_review(config_raw, captures, max_bytes):
    """Side-effect-free bounded computation at current eligibility time."""
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_FROZEN_REVIEW_BYTE_LIMIT")
    roles = {"prepared", "snapshot", "resolutions", "history_evidence"}
    if type(captures) is not dict or set(captures) != roles:
        fail("INVALID_FROZEN_REVIEW_CAPTURES")
    for raw in (config_raw, *captures.values()):
        if type(raw) is not bytes or len(raw) > max_bytes:
            fail("FROZEN_REVIEW_INPUT_LIMIT_EXCEEDED")
    config = review_capture_configuration(config_raw)
    prepared = validated_prepared_review(captures["prepared"])
    activities = prepared["activities"]
    resolutions = parse_keyed_yaml(captures["resolutions"])
    history = parse_keyed_yaml(captures["history_evidence"])
    remote = bounded_remote_snapshot(captures["snapshot"], max_bytes)
    target = prepared["target_account_id"]
    symbols = {a["symbol"] for a in activities.values()}
    quantities = [Decimal(a["quantity"]) for a in activities.values()]
    quantities.extend(r["quantity"] for r in remote if r["target_account_id"] == target
                      and r["symbol"] in symbols and r["kind"] in ("BUY", "SELL"))
    precision = max(28, sum(len(q.as_tuple().digits) + abs(q.as_tuple().exponent)
                            for q in quantities) + 8)
    if precision > min(FROZEN_REVIEW_PRECISION_LIMIT, max_bytes):
        fail("FROZEN_REVIEW_PRECISION_LIMIT_EXCEEDED")
    coverage = verify_chronological_holdings(activities, captures["snapshot"], resolutions, history,
                                             automatic=config.get("adoption_mode") == "certain_unique",
                                             as_of=config.get("as_of"))
    adoption = coverage["adoption"]
    new = {marker: activities[marker] for marker in coverage.get("selected_new", adoption["new"])}
    wire = build_wire_payload(new) if new else None
    blockers = set(coverage["blockers"])
    blockers.update({"PRODUCTION_WRITES_NOT_AUTHORIZED", "DESTINATION_VERSION_AND_DISPLAY_UNVERIFIED"})
    artifact = {"schema_version": 1, "artifact_kind": "offline_reconciliation_review_not_apply_authorization",
                "engine_contract": "strict-offline-review-v1", "import_ready": False, "blockers": sorted(blockers),
                "account_key": prepared["account_key"], "target_account_id": prepared["target_account_id"],
                "input_sha256": {key: hashlib.sha256(value).hexdigest() for key, value in {"config": config_raw, **captures}.items()},
                "source_digests": prepared["source_digests"], "adoption": adoption,
                "holdings": {k: v for k, v in coverage.items() if k != "adoption"},
                "wire": None if wire is None else {"body_utf8": wire["body"].decode("utf-8"),
                                                    "sha256": wire["sha256"], "activity_count": len(new)}}
    return artifact


def validate_frozen_review(review_raw, review_sha256, config_raw, captures, max_bytes):
    """Compare externally pinned report bytes with a full typed recomputation."""
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_FROZEN_REVIEW_BYTE_LIMIT")
    if type(review_raw) is not bytes or len(review_raw) > max_bytes:
        fail("FROZEN_REVIEW_INPUT_LIMIT_EXCEEDED")
    if (not isinstance(review_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", review_sha256)
            or hashlib.sha256(review_raw).hexdigest() != review_sha256):
        fail("FROZEN_REVIEW_DIGEST_CONFLICT")
    observed = parse_keyed_yaml(review_raw)
    expected = compute_offline_review(config_raw, captures, max_bytes)
    # Restricted YAML graphs preserve scalar types and sequence order; only key order normalizes.
    if yaml.safe_dump(observed, sort_keys=True, allow_unicode=True) != yaml.safe_dump(expected, sort_keys=True, allow_unicode=True):
        fail("FROZEN_REVIEW_CONTENT_CONFLICT")
    return expected


def dispatch_single_lab_intent(state_root, binding, reviewed, baseline_raw, max_bytes, request):
    """Trusted owned-lab adapter; never supplies production authority."""
    return _dispatch_single_intent(state_root, binding, reviewed, baseline_raw, max_bytes, request)


def dispatch_frozen_lab_review(state_root, binding, review_raw, review_sha256,
                               config_raw, captures, max_bytes, request, observe_confirmation):
    """Trusted owned-lab sequence only; no production transport or authorization."""
    artifact = validate_frozen_review(review_raw, review_sha256, config_raw, captures, max_bytes)
    validate_write_journal({"schema_version": 1, "binding": binding, "intents": {}})
    binding = dict(binding)
    if any(binding[k] != artifact[k] for k in ("account_key", "target_account_id")):
        fail("WRITE_JOURNAL_BINDING_CONFLICT")
    if not callable(request) or not callable(observe_confirmation):
        fail("INVALID_LAB_SEQUENCE_CALLBACK")
    if artifact["holdings"]["shortages"] or artifact["adoption"]["candidates"]:
        fail("LAB_SEQUENCE_FINANCIAL_REVIEW_BLOCKED")
    prepared = validated_prepared_review(captures["prepared"])["activities"]
    baseline = captures["snapshot"]
    proposal = artifact["wire"]
    if proposal is None:
        return {"accepted_events": 0, "readback": baseline, "import_ready": False}
    full = {"body": proposal["body_utf8"].encode(), "sha256": proposal["sha256"], "import_ready": False}
    expected = reviewed_wire_rows(full)
    wires = []
    for marker, row in expected.items():
        wire = build_wire_payload({marker: prepared[marker]})
        if len(wire["body"]) > max_bytes or reviewed_wire_rows(wire) != {marker: row}:
            fail("LAB_SEQUENCE_WIRE_CONFLICT")
        wires.append(wire)
    return _dispatch_review_sequence(state_root, binding, wires, baseline, max_bytes,
                                     request, observe_confirmation)


def _dispatch_review_sequence(state_root, binding, wires, baseline, max_bytes,
                              request, observe_confirmation):
    for ordinal, wire in enumerate(wires):
        result = _dispatch_single_intent(state_root, binding, wire, baseline, max_bytes, request)
        readback = result["readback"]
        try:
            observe_confirmation(ordinal, dict(wire), baseline, readback)
        except Exception:
            raise RuntimeError("LAB_SEQUENCE_OBSERVER_FAILED") from None
        baseline = readback
    return {"accepted_events": len(wires), "readback": baseline, "import_ready": False}


def capture_local_frozen_review(config_path, review_path, review_sha256, input_root, max_bytes):
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_FROZEN_REVIEW_BYTE_LIMIT")
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    review_raw = read_local_bytes(review_path, input_root, max_bytes)
    config = review_capture_configuration(config_raw)
    paths = [Path(config_path), Path(review_path)]
    captures = {}
    for key in ("prepared", "snapshot", "resolutions", "history_evidence"):
        paths.append(Path(input_root) / config[key])
        captures[key] = read_local_bytes(paths[-1], input_root, max_bytes)
    return validate_frozen_review(review_raw, review_sha256, config_raw, captures, max_bytes), paths


def frozen_review_summary(artifact):
    return {"review_verified": True, "new_activities": len(artifact["holdings"].get("selected_new", artifact["adoption"]["new"])),
            "owned_activities": len(artifact["adoption"]["owned"]),
            "adopted_activities": len(artifact["adoption"]["adopted"]),
            "holdings_shortfalls": len(artifact["holdings"]["shortages"]),
            "import_ready": False, "blockers": artifact["blockers"]}


def check_local_frozen_review(config_path, review_path, review_sha256, input_root, max_bytes):
    """Read-only operator capture and verification; no publication or authority."""
    artifact, _ = capture_local_frozen_review(config_path, review_path, review_sha256, input_root, max_bytes)
    return frozen_review_summary(artifact)


def validate_proposal_destination(destination, input_paths):
    """Validate every local publication boundary before permission/file mutation."""
    path = Path(destination)
    root = Path("outputs").absolute()
    try:
        absolute = path.absolute()
        if any(p.is_symlink() for p in (absolute, *absolute.parents, root)):
            fail("SYMLINK_PROPOSAL_PATH")
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()) or resolved == root.resolve():
            fail("PROPOSAL_OUTSIDE_OUTPUTS")
        if root.exists() and not root.is_dir():
            fail("INVALID_PROPOSAL_DIRECTORY")
        if path.parent.absolute() != root and not path.parent.is_dir():
            fail("INVALID_PROPOSAL_DIRECTORY")
        if path.exists() and not path.is_file():
            fail("INVALID_PROPOSAL_FILE")
        reject_output_input_collision(path, input_paths)
    except OSError:
        raise RuntimeError("INVALID_PROPOSAL_PATH") from None
    return path


def preview_local_application(config_path, review_path, review_sha256, input_root, max_bytes,
                              export_path=None, execute=False):
    """Default offline application preview; export is a proposal, never acceptance."""
    dry_run = os.environ.get("DRY_RUN", "1")
    if dry_run not in ("0", "1"):
        fail("INVALID_DRY_RUN")
    if execute and dry_run == "0":
        fail("APPLICATION_EXECUTION_GATE_REQUIRED")
    artifact, paths = capture_local_frozen_review(config_path, review_path, review_sha256, input_root, max_bytes)
    result = {**frozen_review_summary(artifact), "dry_run": True, "proposal_exported": False}
    if export_path is not None:
        if artifact["holdings"]["shortages"] or artifact["adoption"]["candidates"]:
            fail("APPLICATION_FINANCIAL_REVIEW_BLOCKED")
        if artifact["wire"] is None:
            fail("NO_NEW_ACTIVITIES_TO_EXPORT")
        body = artifact["wire"]["body_utf8"].encode()
        if len(body) > max_bytes:
            fail("APPLICATION_PROPOSAL_LIMIT_EXCEEDED")
        destination = validate_proposal_destination(export_path, paths)
        private_directory("outputs")
        if destination.parent.absolute() != Path("outputs").absolute():
            destination.parent.chmod(0o700)
        atomic_private_bytes(destination, body)
        result["proposal_exported"] = True
    return result


def validate_qualified_application(bundle, max_bytes, max_depth):
    """Pure source/report/declaration consistency; external statements are not proofs."""
    keys = {"declaration", "declaration_sha256", "review", "review_sha256", "config",
            "captures", "prepare_config", "documents"}
    if not isinstance(bundle, dict) or set(bundle) != keys:
        fail("INVALID_APPLICATION_BUNDLE")
    if type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_SIZE_LIMIT")
    raw = bundle["declaration"]
    if type(raw) is not bytes or len(raw) > max_bytes:
        fail("APPLICATION_DECLARATION_LIMIT_EXCEEDED")
    pin = bundle["declaration_sha256"]
    if (not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{64}", pin)
            or hashlib.sha256(raw).hexdigest() != pin):
        fail("APPLICATION_DECLARATION_DIGEST_CONFLICT")
    declaration = parse_keyed_yaml(raw)
    fields = {"schema_version", "artifact_kind", "review_sha256", "prepare_config",
              "prepare_config_sha256", "allowed_origin", "account_key", "target_account_id",
              "snapshot_sha256", "destination_version", "display_timezone", "confirmations"}
    if (set(declaration) != fields or type(declaration["schema_version"]) is not int
            or declaration["schema_version"] != 1
            or declaration["artifact_kind"] != "operator_execution_declaration_not_authenticated_approval"):
        fail("INVALID_APPLICATION_DECLARATION")
    for field in fields - {"schema_version", "confirmations"}:
        if not isinstance(declaration[field], str) or not declaration[field].strip():
            fail("INVALID_APPLICATION_DECLARATION")
    if Path(declaration["prepare_config"]).is_absolute():
        fail("INVALID_APPLICATION_PREPARATION_PATH")
    validated_ghost_origin(declaration["allowed_origin"])
    if declaration["destination_version"] not in ("3.81.0", "3.83.0") or declaration["display_timezone"] not in ("Europe/Paris", "Europe/Zurich"):
        fail("APPLICATION_DESTINATION_SCOPE_UNVERIFIED")
    confirmations = declaration["confirmations"]
    names = {"source_acceptance", "destination_validation", "security_review",
             "recovery_procedure", "exclusive_access", "write_authorization"}
    if not isinstance(confirmations, dict) or set(confirmations) != names:
        fail("APPLICATION_EXTERNAL_CONFIRMATIONS_REQUIRED")
    for record in confirmations.values():
        if (not isinstance(record, dict) or set(record) != {"confirmed", "confirmed_by", "reference"}
                or record["confirmed"] is not True
                or any(not isinstance(record[k], str) or not record[k].strip() for k in ("confirmed_by", "reference"))):
            fail("APPLICATION_EXTERNAL_CONFIRMATIONS_REQUIRED")
    prepare_raw = bundle["prepare_config"]
    if type(prepare_raw) is not bytes or len(prepare_raw) > max_bytes:
        fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    if (not re.fullmatch(r"[0-9a-f]{64}", declaration["prepare_config_sha256"])
            or hashlib.sha256(prepare_raw).hexdigest() != declaration["prepare_config_sha256"]):
        fail("APPLICATION_PREPARATION_DIGEST_CONFLICT")
    artifact = validate_frozen_review(bundle["review"], bundle["review_sha256"],
                                     bundle["config"], bundle["captures"], max_bytes)
    if (declaration["review_sha256"] != bundle["review_sha256"]
            or any(declaration[k] != artifact[k] for k in ("account_key", "target_account_id"))
            or declaration["snapshot_sha256"] != artifact["input_sha256"]["snapshot"]):
        fail("APPLICATION_DECLARATION_CONTEXT_CONFLICT")
    validate_prepared_sources(bundle["captures"]["prepared"], prepare_raw,
                              bundle["documents"], max_bytes, max_depth)
    binding = {k: declaration[k] for k in ("account_key", "target_account_id")}
    validate_write_journal({"schema_version": 1, "binding": binding, "intents": {}})
    if artifact["holdings"]["shortages"] or artifact["adoption"]["candidates"]:
        fail("APPLICATION_FINANCIAL_REVIEW_BLOCKED")
    prepared = validated_prepared_review(bundle["captures"]["prepared"])["activities"]
    wires = []
    if artifact["wire"] is not None:
        proposal = artifact["wire"]
        full = {"body": proposal["body_utf8"].encode(), "sha256": proposal["sha256"], "import_ready": False}
        for marker, row in reviewed_wire_rows(full).items():
            wire = build_wire_payload({marker: prepared[marker]})
            if len(wire["body"]) > max_bytes or reviewed_wire_rows(wire) != {marker: row}:
                fail("APPLICATION_WIRE_CONFLICT")
            wires.append(wire)
    return {"artifact": artifact, "declaration": declaration, "binding": binding, "wires": wires}


def validate_application_destinations(state_root, archive_root, archive, binding, input_paths):
    target = hashlib.sha256(binding["target_account_id"].encode()).hexdigest()
    state = Path(state_root).absolute()
    root = Path(archive_root).absolute()
    archive = Path(archive).absolute()
    for directory in (state, root, archive):
        if any(p.is_symlink() for p in (directory, *directory.parents)):
            fail("SYMLINK_APPLICATION_DIRECTORY")
        if directory.exists() and not directory.is_dir():
            fail("INVALID_APPLICATION_DIRECTORY")
    if archive.parent != root or archive.exists():
        fail("APPLICATION_ARCHIVE_NOT_NEW")
    for name in ("prepare-" + target + ".lock", "account-" + binding["account_key"] + ".lock",
                 "write-binding-" + binding["account_key"] + ".yaml", "writes-" + target + ".yaml"):
        destination = state / name
        reject_output_input_collision(destination, input_paths)
        if destination.is_symlink():
            fail("SYMLINK_APPLICATION_STATE")
        if destination.exists() and not destination.is_file():
            fail("INVALID_APPLICATION_STATE")
    # New generated children cannot alias inputs unless the archive/root already exists.
    for destination in (state, root, archive):
        reject_output_input_collision(destination, input_paths)


def initialize_application_archive(archive_root, archive, bundle, max_bytes, max_depth):
    private_directory(archive_root)
    Path(archive).mkdir(mode=0o700)
    archive = Path(archive)
    roles = {"declaration": bundle["declaration"], "review": bundle["review"],
             "config": bundle["config"], "prepare_config": bundle["prepare_config"], **bundle["captures"]}
    documents = {}
    for index, (alias, captures) in enumerate(bundle["documents"].items()):
        if set(captures) == {"notice"}:
            role = "source-" + str(index) + "-notice"
            roles[role] = captures["notice"]
            documents[alias] = {"notice": role}
            continue
        statement = "source-" + str(index) + "-statement"
        notes = ["source-" + str(index) + "-note-" + str(n) for n in range(len(captures["notes"]))]
        roles[statement] = captures["statement"]
        roles.update(zip(notes, captures["notes"]))
        documents[alias] = {"statement": statement, "notes": notes}
    manifest = {"schema_version": 1, "artifact_kind": "application_run_evidence_not_approval",
                "run_id": archive.name, "max_bytes": max_bytes, "max_depth": max_depth,
                "declaration_sha256": bundle["declaration_sha256"],
                "review_sha256": bundle["review_sha256"], "documents": documents,
                "roles": {role: {"file": role + ".bytes", "sha256": hashlib.sha256(raw).hexdigest()}
                          for role, raw in roles.items()}}
    # Ownership/evidence manifest precedes role files; incomplete archives remain visible.
    atomic_private_yaml(archive / "manifest.yaml", manifest)
    for role, raw in roles.items():
        atomic_private_bytes(archive / (role + ".bytes"), raw)
    # Persist archive's entry in its parent before any request callback.
    for directory in (Path(archive_root), Path(archive_root).parent):
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def dispatch_qualified_application(state_root, archive_root, bundle, max_bytes, max_depth,
                                   request, observe_confirmation=None, input_paths=()):
    qualification = validate_qualified_application(bundle, max_bytes, max_depth)
    wires = qualification["wires"]
    baseline = bundle["captures"]["snapshot"]
    if not wires:
        return {"accepted_events": 0, "readback": baseline, "import_ready": False}
    if not callable(request) or (observe_confirmation is not None and not callable(observe_confirmation)):
        fail("INVALID_APPLICATION_CALLBACK")
    # Immutable captures and freshly computed wires/binding are detached before callbacks.
    binding = qualification["binding"]
    archive = Path(archive_root) / ("application-" + uuid.uuid4().hex)
    validate_application_destinations(state_root, archive_root, archive, binding, input_paths)
    initialize_application_archive(archive_root, archive, bundle, max_bytes, max_depth)
    batch_pin = qualification["artifact"]["wire"]["sha256"]
    def observer(ordinal, wire, before, after):
        prefix = archive / ("event-" + str(ordinal))
        atomic_private_bytes(prefix.with_suffix(".wire.json"), wire["body"])
        atomic_private_bytes(prefix.with_suffix(".readback.json"), after)
        atomic_private_yaml(prefix.with_suffix(".provenance.yaml"), {
            "schema_version": 1, "run_id": archive.name, "ordinal": ordinal,
            "wire_sha256": wire["sha256"], "proposal_batch_sha256": batch_pin,
            "baseline_sha256": hashlib.sha256(before).hexdigest(),
            "readback_sha256": hashlib.sha256(after).hexdigest()})
        if observe_confirmation is not None:
            observe_confirmation(ordinal, dict(wire), before, after)
    return _dispatch_review_sequence(state_root, binding, wires, baseline, max_bytes, request, observer)


def capture_local_application(config_path, review_path, review_sha256, execution_path,
                              execution_sha256, input_root, max_bytes, max_depth):
    if execution_path is None or execution_sha256 is None:
        fail("APPLICATION_EXECUTION_GATE_REQUIRED")
    paths = [Path(config_path), Path(review_path), Path(execution_path)]
    config_raw, review_raw, declaration_raw = [read_local_bytes(path, input_root, max_bytes) for path in paths]
    config = review_capture_configuration(config_raw)
    captures = {}
    for role in ("prepared", "snapshot", "resolutions", "history_evidence"):
        path = Path(input_root) / config[role]
        paths.append(path)
        captures[role] = read_local_bytes(path, input_root, max_bytes)
    # Validate declaration pin before using its preparation path to read another file.
    if (not isinstance(execution_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", execution_sha256)
            or hashlib.sha256(declaration_raw).hexdigest() != execution_sha256):
        fail("APPLICATION_DECLARATION_DIGEST_CONFLICT")
    declaration = parse_keyed_yaml(declaration_raw)
    path = declaration.get("prepare_config")
    if not isinstance(path, str) or not path.strip() or Path(path).is_absolute():
        fail("INVALID_APPLICATION_PREPARATION_PATH")
    prepare_path = Path(input_root) / path
    prepare_raw = read_local_bytes(prepare_path, input_root, max_bytes)
    documents, document_paths = capture_preparation_sources(prepare_raw, input_root, max_bytes, max_depth)
    paths.extend([prepare_path, *document_paths])
    bundle = {"declaration": declaration_raw, "declaration_sha256": execution_sha256,
              "review": review_raw, "review_sha256": review_sha256, "config": config_raw,
              "captures": captures, "prepare_config": prepare_raw, "documents": documents}
    return bundle, paths


def execute_local_application(config_path, review_path, review_sha256, input_root, max_bytes,
                              execution_path, execution_sha256, max_depth, timeout, export_path=None):
    if export_path is not None:
        fail("APPLICATION_EXECUTE_EXPORT_CONFLICT")
    if type(timeout) is not int or not 1 <= timeout <= 120:
        fail("INVALID_APPLICATION_TIMEOUT")
    bundle, paths = capture_local_application(config_path, review_path, review_sha256, execution_path,
                                             execution_sha256, input_root, max_bytes, max_depth)
    qualified = validate_qualified_application(bundle, max_bytes, max_depth)
    result = {**frozen_review_summary(qualified["artifact"]), "dry_run": False,
              "accepted_events": 0, "proposal_exported": False}
    if not qualified["wires"]:
        return result
    # Validate all writable namespaces before credentials, mkdir or permission changes.
    candidate = Path("outputs") / ("application-" + uuid.uuid4().hex)
    validate_application_destinations("state", "outputs", candidate, qualified["binding"], paths)
    request = make_ghostfolio_request(qualified["declaration"]["allowed_origin"], max_bytes, timeout)
    dispatched = dispatch_qualified_application("state", "outputs", bundle, max_bytes, max_depth,
                                                request, input_paths=paths)
    result["accepted_events"] = dispatched["accepted_events"]
    return result


def review_local_snapshot(config_path, input_root, max_bytes):
    """Private end-to-end offline review; exact bytes, no remote calls or intent."""
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = review_capture_configuration(config_raw)
    captures = {k: read_local_bytes(Path(input_root) / config[k], input_root, max_bytes)
                for k in ("prepared", "snapshot", "resolutions", "history_evidence")}
    artifact = compute_offline_review(config_raw, captures, max_bytes)
    output = Path("outputs") / ("review-" + artifact["account_key"] + ".yaml")
    reject_output_input_collision(output, [Path(config_path),
                                  *(Path(input_root) / config[k] for k in ("prepared", "snapshot", "resolutions", "history_evidence"))])
    private_directory("outputs")
    state = private_directory("state")
    target = hashlib.sha256(artifact["target_account_id"].encode("utf-8")).hexdigest()
    lock = os.open(state / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_REVIEW_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("REVIEW_TARGET_LOCKED")
        atomic_private_yaml(output, artifact)
    finally:
        os.close(lock)
    return {"new_activities": len(artifact["holdings"].get("selected_new", artifact["adoption"]["new"])), "owned_activities": len(artifact["adoption"]["owned"]),
            "adopted_activities": len(artifact["adoption"]["adopted"]), "holdings_shortfalls": len(artifact["holdings"]["shortages"]),
            "import_ready": False, "blockers": artifact["blockers"]}


def bound_decimal_shape(number, max_bytes):
    if not number:
        return
    sign, digits, exponent = number.as_tuple()
    point = len(digits) + exponent
    length = (point if exponent >= 0 else len(digits) + 1 if point > 0 else 2 - exponent) + sign
    if length > min(VERIFICATION_DECIMAL_CHAR_LIMIT, max_bytes):
        fail("VERIFICATION_DECIMAL_LIMIT_EXCEEDED")


def bounded_remote_snapshot(raw, max_bytes):
    try:
        rows = parse_remote_activity_snapshot(raw)
    except InvalidOperation:
        fail("INVALID_REMOTE_ACTIVITY_JSON")
    for row in rows:
        for key in ("quantity", "unit_price", "fee"):
            bound_decimal_shape(row[key], max_bytes)
    return rows


def observe_retained_intents(captures, max_bytes):
    """Pure bounded observations from captured journal/snapshot bytes."""
    journal = parse_keyed_yaml(captures["journal"])
    validate_write_journal(journal)
    started = datetime.now(timezone.utc).isoformat()
    remote = bounded_remote_snapshot(captures["snapshot"], max_bytes)
    rows_by_id = {r["remote_id"]: r for r in remote}
    rows_by_marker = {}
    for row in remote:
        rows_by_marker.setdefault(row["comment"], []).append(row)
    originals = json.loads(captures["snapshot"], parse_float=Decimal, object_pairs_hook=unique_json_object)
    timestamps = {r["id"]: r["date"] for r in originals["activities"]}
    observations, evidence = {}, {}
    expected_count = candidate_count = 0
    fields = ("target_account_id", "operation_date", "kind", "symbol", "data_source", "price_currency")
    def retain(row):
        evidence[row["remote_id"]] = {**{k: row[k] for k in fields},
            **{k: canonical_decimal(row[k]) for k in ("quantity", "unit_price", "fee")},
            "original_timestamp": timestamps[row["remote_id"]], "active_at_evaluation": row["active"],
            "date_context_verified": row["date_context_verified"],
            "financial_context_verified": row["financial_context_verified"]}
    for digest, intent in journal["intents"].items():
        expected = reviewed_wire_rows({"body": intent["body"].encode(), "sha256": digest, "import_ready": False})
        expected_count += len(expected)
        if expected_count > VERIFICATION_REFERENCE_LIMIT:
            fail("VERIFICATION_MARKER_LIMIT_EXCEEDED")
        accepted = {} if intent["resolution"] is None else intent["resolution"]["accepted"]
        markers = {}
        for marker, sent in expected.items():
            candidates = rows_by_marker.get(marker, [])
            recorded_id = accepted.get(marker)
            recorded_row = rows_by_id.get(recorded_id)
            candidate_count += len(candidates) + (1 if recorded_row is not None and recorded_row not in candidates else 0)
            if candidate_count > VERIFICATION_REFERENCE_LIMIT:
                fail("VERIFICATION_CANDIDATE_LIMIT_EXCEEDED")
            codes, exact = set(), False
            if not candidates:
                codes.add("OWNED_ACTIVITY_ABSENT_IN_CAPTURE")
            elif len(candidates) > 1:
                codes.add("OWNED_MARKER_DUPLICATE")
            else:
                row = candidates[0]
                comparison = {"target_account_id": sent["accountId"], "operation_date": sent["date"][:10],
                    "kind": sent["type"], "symbol": sent["symbol"], "data_source": sent["dataSource"],
                    "price_currency": sent["currency"], "quantity": remote_decimal(sent["quantity"]),
                    "unit_price": remote_decimal(sent["unitPrice"]), "fee": remote_decimal(sent["fee"])}
                financial = activity_financial_fingerprint(row) == activity_financial_fingerprint(comparison)
                context = row["active"] and row["date_context_verified"] and row["financial_context_verified"]
                if not financial:
                    codes.add("OWNED_ACTIVITY_FINANCIAL_CONFLICT")
                if not context:
                    codes.add("OWNED_ACTIVITY_CONTEXT_UNVERIFIED")
                exact = financial and context
                if exact:
                    codes.add("EXACT_POSITIVE_READBACK")
            if (recorded_row is not None and recorded_row["comment"] != marker
                    or recorded_id is not None and any(r["remote_id"] != recorded_id for r in candidates)):
                codes.add("JOURNALED_REMOTE_ID_CONFLICT")
                exact = False
            if intent["state"] == "quiescent" and marker not in accepted and candidates:
                codes.add("PRESENT_MARKER_NOT_IN_RECORDED_ACCEPTED_SET")
            for row in candidates:
                retain(row)
            if recorded_row is not None:
                retain(recorded_row)
            markers[marker] = {"candidate_ids": [r["remote_id"] for r in candidates],
                "recorded_accepted_id": recorded_id,
                "recorded_id_observed": recorded_row is not None,
                "exactly_present": exact, "codes": sorted(codes)}
        observations[digest] = {"recorded_state": intent["state"], "expected_markers": len(markers),
            "present_markers": sum(bool(v["candidate_ids"]) for v in markers.values()),
            "exact_markers": sum(v["exactly_present"] for v in markers.values()),
            "absent_markers": sum(not v["candidate_ids"] for v in markers.values()),
            "all_expected_exactly_present": all(v["exactly_present"] for v in markers.values()), "markers": markers}
    return journal, started, observations, evidence


def verify_local_intents(config_path, input_root, max_bytes):
    """Saved observations only; never settle, rewrite or replay an intent."""
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = parse_keyed_yaml(config_raw)
    if set(config) != {"schema_version", "journal", "snapshot"} or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        fail("INVALID_VERIFICATION_CONFIGURATION")
    captures, paths = {}, [Path(config_path)]
    for key in ("journal", "snapshot"):
        if not isinstance(config[key], str) or not config[key].strip():
            fail("INVALID_VERIFICATION_CONFIGURATION")
        paths.append(Path(input_root) / config[key])
        captures[key] = read_local_bytes(paths[-1], input_root, max_bytes)
    journal, started, observations, evidence = observe_retained_intents(captures, max_bytes)
    binding = journal["binding"]
    blockers = ["VERIFICATION_DOES_NOT_RESOLVE_INTENTS", "PRODUCTION_WRITES_NOT_AUTHORIZED"]
    artifact = {"schema_version": 1, "artifact_kind": "offline_intent_observation_not_resolution",
        "engine_contract": "strict-offline-intent-verification-v1", "import_ready": False,
        "binding": binding, "evaluation_started_at_utc": started,
        "input_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in {"config": config_raw, **captures}.items()},
        "intents": observations, "remote_evidence": evidence, "blockers": blockers}
    raw = yaml.safe_dump(artifact, sort_keys=False, allow_unicode=True).encode()
    if len(raw) > max_bytes:
        fail("VERIFICATION_OUTPUT_LIMIT_EXCEEDED")
    output = Path("outputs") / ("verification-" + binding["account_key"] + ".yaml")
    reject_output_input_collision(output, paths)
    private_directory("outputs")
    state = private_directory("state")
    target = hashlib.sha256(binding["target_account_id"].encode()).hexdigest()
    lock = os.open(state / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_VERIFICATION_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("VERIFICATION_TARGET_LOCKED")
        atomic_private_bytes(output, raw)
    finally:
        os.close(lock)
    return {"intents": len(observations),
        "intents_with_all_expected_exactly_present": sum(v["all_expected_exactly_present"] for v in observations.values()),
        "observed_uncertain_intents": sum(v["recorded_state"] == "uncertain" for v in observations.values()),
        "import_ready": False, "blockers": blockers}


def plan_local_compensation(config_path, input_root, max_bytes):
    """Association candidates only; no creation proof, authorization or deletion."""
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = parse_keyed_yaml(config_raw)
    if (set(config) != {"schema_version", "journal", "snapshot", "wire_sha256"}
            or type(config["schema_version"]) is not int or config["schema_version"] != 1
            or not isinstance(config["wire_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", config["wire_sha256"])):
        fail("INVALID_COMPENSATION_CONFIGURATION")
    captures, paths = {}, [Path(config_path)]
    for key in ("journal", "snapshot"):
        if not isinstance(config[key], str) or not config[key].strip():
            fail("INVALID_COMPENSATION_CONFIGURATION")
        paths.append(Path(input_root) / config[key])
        captures[key] = read_local_bytes(paths[-1], input_root, max_bytes)
    journal, started, observations, evidence = observe_retained_intents(captures, max_bytes)
    digest = config["wire_sha256"]
    if digest not in journal["intents"]:
        fail("COMPENSATION_INTENT_NOT_RECORDED")
    selected = journal["intents"][digest]
    seen = observations[digest]
    accepted = {} if selected["resolution"] is None else selected["resolution"]["accepted"]
    codes, candidates, absent, unaccepted = set(), [], [], []
    if any(i["state"] == "uncertain" for i in journal["intents"].values()):
        codes.add("ACCOUNT_WRITE_UNCERTAIN")
    associations = {}
    for other_digest, intent in journal["intents"].items():
        if intent["resolution"] is not None:
            for marker, remote_id in intent["resolution"]["accepted"].items():
                associations.setdefault(remote_id, []).append((other_digest, marker))
    rows = reviewed_wire_rows({"body": selected["body"].encode(), "sha256": digest, "import_ready": False})
    for ordinal, marker in enumerate(rows):
        observation = seen["markers"][marker]
        if marker not in accepted:
            unaccepted.append(marker)
            if selected["state"] == "quiescent" and observation["candidate_ids"]:
                codes.add("UNACCEPTED_SELECTED_MARKER_PRESENT")
            continue
        conflicts = set(observation["codes"]) - {"EXACT_POSITIVE_READBACK", "OWNED_ACTIVITY_ABSENT_IN_CAPTURE"}
        codes.update(conflicts)
        if not observation["candidate_ids"]:
            absent.append(marker)
        remote_id = accepted[marker]
        if observation["exactly_present"] and observation["candidate_ids"] == [remote_id]:
            if len(associations[remote_id]) != 1:
                codes.add("REMOTE_ID_SHARED_BY_RETAINED_INTENTS")
            row = evidence[remote_id]
            candidates.append({"marker": marker, "recorded_remote_id": remote_id,
                "wire_ordinal": ordinal, "financial_fingerprint": activity_financial_fingerprint(row),
                "observed_evidence": row})
        elif observation["candidate_ids"] and not conflicts:
            codes.add("ACCEPTED_ASSOCIATION_NOT_EXACT_IN_CAPTURE")
    candidates.sort(key=lambda c: (c["observed_evidence"]["operation_date"], c["wire_ordinal"]), reverse=True)
    if codes:
        candidates = []
    boundaries = ["CREATION_PROVENANCE_NOT_ESTABLISHED", "FRESH_REMOTE_REVALIDATION_REQUIRED",
        "EXPLICIT_DELETE_AUTHORIZATION_REQUIRED", "PROFILE_AND_DATABASE_RECOVERY_UNPROVEN",
        "PRODUCTION_WRITES_NOT_AUTHORIZED"]
    binding = journal["binding"]
    artifact = {"schema_version": 1, "artifact_kind": "offline_compensation_candidates_not_authorization",
        "engine_contract": "strict-offline-compensation-candidates-v1", "binding": binding,
        "selected_wire_sha256": digest, "selected_recorded_state": selected["state"],
        "evaluation_started_at_utc": started,
        "input_sha256": {k: hashlib.sha256(v).hexdigest() for k, v in {"config": config_raw, **captures}.items()},
        "candidate_selection_unambiguous": not codes, "selection_codes": sorted(codes),
        "accepted_absent_markers": absent, "unaccepted_markers": unaccepted,
        "candidates": candidates, "deletion_authorized": False, "import_ready": False, "boundaries": boundaries}
    raw = yaml.safe_dump(artifact, sort_keys=False, allow_unicode=True).encode()
    if len(raw) > max_bytes:
        fail("COMPENSATION_OUTPUT_LIMIT_EXCEEDED")
    output = Path("outputs") / ("rollback-plan-" + binding["account_key"] + ".yaml")
    reject_output_input_collision(output, paths)
    private_directory("outputs")
    state = private_directory("state")
    target = hashlib.sha256(binding["target_account_id"].encode()).hexdigest()
    lock = os.open(state / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_COMPENSATION_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("COMPENSATION_TARGET_LOCKED")
        atomic_private_bytes(output, raw)
    finally:
        os.close(lock)
    return {"candidates": len(candidates), "accepted_absent": len(absent), "unaccepted": len(unaccepted),
        "selection_codes": sorted(codes), "deletion_authorized": False, "import_ready": False, "boundaries": boundaries}


def validated_ghost_origin(value):
    if not isinstance(value, str) or not value.isascii() or value != value.strip() or any(c.isspace() for c in value):
        fail("INVALID_GHOST_ORIGIN")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        fail("INVALID_GHOST_ORIGIN")
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.query or parsed.fragment or "?" in value or "#" in value
            or not parsed.hostname or not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", parsed.hostname)):
        fail("INVALID_GHOST_ORIGIN")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in parsed.hostname.split(".")):
        fail("INVALID_GHOST_ORIGIN")
    canonical = "https://" + parsed.hostname + (":" + str(port) if port is not None else "")
    if value != canonical or port is not None and not 1 <= port <= 65535:
        fail("INVALID_GHOST_ORIGIN")
    return parsed.hostname, port or 443


def make_ghostfolio_request(allowed_origin, max_bytes, timeout):
    """Bounded fixed-path adapter, not execution authorization; factory never connects."""
    if type(timeout) is not int or not 1 <= timeout <= 120 or type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_GHOST_REQUEST_LIMITS")
    host, port = validated_ghost_origin(allowed_origin)
    origin = os.environ.get("GHOST_HOST")
    validated_ghost_origin(origin)
    if origin != allowed_origin:
        fail("GHOST_ORIGIN_NOT_ALLOWLISTED")
    bearer = os.environ.get("GHOST_SESSION_BEARER")
    if not isinstance(bearer, str) or len(bearer) > 16384 or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", bearer):
        fail("GHOST_SESSION_BEARER_REQUIRED")
    def request(method, path, body):
        if (method, path) == ("GET", "/api/v1/activities"):
            if body is not None:
                fail("GHOST_REQUEST_GET_BODY_REJECTED")
            expected_status = 200
        elif (method, path) == ("POST", "/api/v1/import"):
            _dispatch_json(body, max_bytes)
            rows = reviewed_wire_rows({"body": body, "sha256": hashlib.sha256(body).hexdigest(), "import_ready": False})
            if len(rows) != 1:
                fail("GHOST_REQUEST_SINGLE_ACTIVITY_REQUIRED")
            expected_status = 201
        else:
            fail("GHOST_REQUEST_PATH_REJECTED")
        connection, response_data, error_code = None, None, None
        try:
            connection = http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())
            headers = {"Authorization": "Bearer " + bearer, "Accept": "application/json", "Accept-Encoding": "identity"}
            if method == "POST":
                headers["Content-Type"] = "application/json"
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            if type(response.status) is not int:
                error_code = "GHOST_REQUEST_STATUS_REJECTED"
            elif 300 <= response.status < 400:
                error_code = "GHOST_REQUEST_REDIRECT_REJECTED"
            elif response.status != expected_status:
                error_code = "GHOST_REQUEST_STATUS_REJECTED"
            elif response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
                error_code = "GHOST_REQUEST_CONTENT_TYPE_REJECTED"
            elif response.getheader("Content-Encoding", "identity").strip().lower() != "identity":
                error_code = "GHOST_REQUEST_ENCODING_REJECTED"
            else:
                raw = response.read(max_bytes + 1)
                if type(raw) is not bytes or len(raw) > max_bytes:
                    error_code = "GHOST_REQUEST_RESPONSE_LIMIT_OR_TYPE"
                else:
                    response_data = (response.status, raw)
        except Exception:
            error_code = "GHOST_REQUEST_TRANSPORT_FAILED"
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    if error_code is None:
                        error_code = "GHOST_REQUEST_CLOSE_FAILED"
        if error_code is not None:
            fail(error_code)
        return response_data
    return request


def acquire_readonly_snapshot(config_path, input_root, max_bytes, timeout):
    """Only GET; never exchanges tokens, follows redirects, retries or imports."""
    if type(timeout) is not int or not 1 <= timeout <= 120 or type(max_bytes) is not int or max_bytes <= 0:
        fail("INVALID_SNAPSHOT_LIMITS")
    config = read_keyed_yaml(config_path, input_root, max_bytes)
    if set(config) != {"schema_version", "allowed_origin"} or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        fail("INVALID_SNAPSHOT_CONFIGURATION")
    host, port = validated_ghost_origin(config["allowed_origin"])
    origin = os.environ.get("GHOST_HOST")
    validated_ghost_origin(origin)
    if origin != config["allowed_origin"]:
        fail("GHOST_ORIGIN_NOT_ALLOWLISTED")
    # A UI Security Token is not a session JWT. Deliberately no POST auth path.
    bearer = os.environ.get("GHOST_SESSION_BEARER")
    if not isinstance(bearer, str) or len(bearer) > 16384 or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", bearer):
        fail("GHOST_SESSION_BEARER_REQUIRED")
    connection = None
    try:
        connection = http.client.HTTPSConnection(host, port, timeout=timeout, context=ssl.create_default_context())
        connection.request("GET", "/api/v1/activities", headers={"Authorization": "Bearer " + bearer,
                                                               "Accept": "application/json", "Accept-Encoding": "identity"})
        response = connection.getresponse()
        if 300 <= response.status < 400:
            fail("GHOST_REDIRECT_REJECTED")
        if response.status != 200:
            fail("GHOST_SNAPSHOT_HTTP_REJECTED")
        if response.getheader("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            fail("GHOST_SNAPSHOT_CONTENT_TYPE_REJECTED")
        if response.getheader("Content-Encoding", "identity").strip().lower() != "identity":
            fail("GHOST_SNAPSHOT_ENCODING_REJECTED")
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            fail("GHOST_SNAPSHOT_TOO_LARGE")
    except (OSError, http.client.HTTPException, ValueError):
        fail("GHOST_SNAPSHOT_TRANSPORT_FAILED")
    finally:
        if connection is not None:
            connection.close()
    normalized = parse_remote_activity_snapshot(raw)
    digest = hashlib.sha256(raw).hexdigest()
    output = Path("outputs") / ("ghostfolio-snapshot-" + digest + ".json")
    reject_output_input_collision(output, [Path(config_path)])
    private_directory("outputs")
    atomic_private_bytes(output, raw)
    return {"snapshot_activities": len(normalized), "import_ready": False,
            "blockers": ["SNAPSHOT_REVIEW_REQUIRED", "COMPLETE_ACQUISITION_HISTORY_EVIDENCE_REQUIRED"]}


def buy_simulation_config():
    """Sibling ENV and verified Yahoo YAML; scheduling is owned by entrypoint."""
    mode = os.environ.get('DRY_RUN', '1').strip().lower()
    if mode not in ('1', 'true', 'yes', 'on', '0', 'false', 'no', 'off'):
        fail('INVALID_DRY_RUN')
    source_ref = os.environ.get('BD_SOURCE_ACCOUNT_REF', '')
    if not source_ref:
        return {'source_ref': '', 'discovery_only': True}
    target = os.environ.get('GHOST_ACCOUNT_ID', '')
    if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{5,63} (?:PEA|PEA-PME)', source_ref)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', target)):
        fail('EXPLICIT_ACCOUNTS_REQUIRED')
    path = Path(os.environ.get('MAPPING_FILE', '/config/mappings.yaml'))
    try:
        document = parse_keyed_yaml(read_local_bytes(path, path.parent, 8 * 1024 * 1024))
    except OSError:
        fail('MAPPING_FILE_UNREADABLE_OR_INVALID')
    # Adapt DEGIRO's verified_mapping_document contract; this slice supports EUR.
    quotes = {}
    for isin, entry in document.items():
        if (not valid_isin(isin) or not isinstance(entry, dict) or set(entry) != {'symbol', 'currency'}
                or entry['currency'] != 'EUR' or not isinstance(entry['symbol'], str)
                or not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=_-]{0,63}', entry['symbol'])):
            fail('INVALID_EXPLICIT_MAPPING')
        quotes[isin] = dict(entry)
    return {'dry_run': mode in ('1', 'true', 'yes', 'on'), 'source_ref': source_ref, 'target': target,
            'origin': os.environ.get('GHOST_HOST', ''), 'mappings': quotes}


def instrument_candidates(items):
    """Distinct Yahoo EUR symbols only; never infer currency or venue."""
    tickers, eligible = set(), set()
    for item in items:
        if not isinstance(item, dict):
            fail('GHOSTFOLIO_LOOKUP_INVALID')
        symbol = item.get('symbol')
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=_-]{0,63}', symbol):
            continue
        tickers.add(symbol)
        if item.get('currency') == 'EUR' and item.get('dataSource') == 'YAHOO':
            eligible.add(symbol)
    return sorted(tickers), sorted(eligible)


def resolve_instrument(isin, overrides, profiles, lookup):
    """An override wins; ambiguity and provider failures remain explicit skips."""
    if isin in overrides:
        return overrides[isin]
    candidates, eligible = instrument_candidates([row for row in profiles if row.get('isin') == isin])
    source = 'existing_profile'
    reason = 'INSTRUMENT_AMBIGUOUS'
    if not eligible:
        source = 'lookup'
        try:
            candidates, eligible = instrument_candidates(lookup(isin))
            reason = 'INSTRUMENT_AMBIGUOUS' if eligible else 'INSTRUMENT_UNRESOLVED'
        except Exception:
            candidates, eligible, reason = [], [], 'INSTRUMENT_LOOKUP_FAILED'
    if len(eligible) == 1:
        return {'symbol': eligible[0], 'currency': 'EUR'}
    print(json.dumps({'code': reason, 'level': 'error', 'isin': isin, 'source': source,
        'candidate_tickers': candidates, 'eligible_eur_tickers': eligible, 'financial_writes': 0}), flush=True)
    return None


def notice_identity(note, account, occurrences):
    """Account-owned normalized source evidence, independent of ticker/capture."""
    namespace = hashlib.sha256(json.dumps([account['source_account_ref'],
        account['target_account_id']], separators=(',', ':')).encode()).hexdigest()
    fields = ('kind', 'date', 'isin', 'execution_time', 'quantity', 'unit_price',
        'brokerage', 'vat', 'debit', 'credit')
    source = {key: canonical_decimal(value) if isinstance(value, Decimal) else
        value.isoformat() if hasattr(value, 'isoformat') else value
        for key in fields if (value := note.get(key)) is not None}
    basis = json.dumps(source, sort_keys=True, separators=(',', ':'))
    rank = occurrences.get(basis, 0) + 1
    occurrences[basis] = rank
    digest = hashlib.sha256((basis + ':' + str(rank)).encode()).hexdigest()
    return 'BD#v2#' + namespace + '#' + digest


def notice_signature(activity):
    return (activity['accountId'], activity['type'], activity['date'], activity['symbol'],
        activity['dataSource'], activity['currency'],
        *(Decimal(activity[key]) for key in ('quantity', 'unitPrice', 'fee')))


def notice_legacy_row_binding(row):
    """Stable financial and inclusion context; omit mutable market metadata."""
    source = json.loads(row['stored_activity'], parse_float=Decimal)
    profile = source.get('assetProfile', source.get('SymbolProfile'))
    contexts = []
    for context in (source, source['account']):
        contexts.append(None if context is None else {
            'flags': {key: (key in context, context.get(key)) for key in ('isDraft', 'isExcluded')},
            'tags': sorted(tag['id'] for tag in context['tags'])})
    return (row['remote_id'], row['stored_date'], activity_financial_fingerprint(row),
        row['currency_origin'], row['financial_context_verified'], row['comment'], contexts,
        None if not isinstance(profile, dict) else {
            key: (key in profile, profile.get(key)) for key in ('id', 'symbol', 'dataSource', 'currency')})


def notice_approved_legacy_days(remote, grant, evidence_root):
    """Apply explicit display convention to unchanged complete manual history."""
    fields = {'snapshot_path', 'snapshot_sha256', 'account_id', 'display_timezone', 'approval_reference'}
    if (not isinstance(grant, dict) or set(grant) != fields or evidence_root is None
            or any(not isinstance(value, str) or not value.strip() for value in grant.values())
            or Path(grant['snapshot_path']).is_absolute()
            or not re.fullmatch(r'[0-9a-f]{64}', grant['snapshot_sha256'])):
        fail('NOTICE_LEGACY_BASELINE_INVALID')
    try:
        zone = ZoneInfo(grant['display_timezone'])
        raw = read_local_bytes(Path(evidence_root) / grant['snapshot_path'], evidence_root, 8 * 1024 * 1024)
        if hashlib.sha256(raw).hexdigest() != grant['snapshot_sha256']:
            fail('NOTICE_LEGACY_BASELINE_INVALID')
        baseline = parse_remote_activity_snapshot(raw, retain_stored_date=True)
    except (OSError, ValueError, KeyError, RuntimeError):
        fail('NOTICE_LEGACY_BASELINE_INVALID')
    def manual(rows):
        return {row['remote_id']: row for row in rows if row['target_account_id'] == grant['account_id']
            and not (row['comment'] or '').startswith('BD#')}
    approved, current = manual(baseline), manual(remote)
    if not approved or set(approved) != set(current):
        fail('NOTICE_LEGACY_BASELINE_MISMATCH')
    days = {}
    for key, row in current.items():
        if ('stored_activity' not in row or 'stored_date' not in row
                or notice_legacy_row_binding(row) != notice_legacy_row_binding(approved[key])):
            fail('NOTICE_LEGACY_BASELINE_MISMATCH')
        # This is the approved UI convention, never original entry-day evidence.
        days[key] = datetime.fromisoformat(row['stored_date'].replace('Z', '+00:00')).astimezone(zone).date().isoformat()
    return days


def notice_manual_day_context(remote, evidence, evidence_root=None):
    """Bind retained historical entry evidence to exact current financial rows."""
    if (not isinstance(evidence, dict) or not {'schema_version', 'activities'} <= set(evidence)
            or set(evidence) - {'schema_version', 'activities', 'approved_legacy_baseline'}
            or type(evidence['schema_version']) is not int or evidence['schema_version'] != 1
            or not isinstance(evidence['activities'], dict)):
        fail('NOTICE_DAY_CONTEXT_INVALID')
    fields = {'account_id', 'stored_date', 'financial_fingerprint', 'civil_day', 'provenance'}
    for key, entry in evidence['activities'].items():
        if (not isinstance(key, str) or not key or not isinstance(entry, dict) or set(entry) != fields
                or any(not isinstance(entry[field], str) or not entry[field].strip() for field in fields - {'provenance'})
                or not isinstance(entry['provenance'], dict)
                or set(entry['provenance']) != {'path', 'sha256'}
                or not isinstance(entry['provenance']['path'], str) or not entry['provenance']['path']
                or Path(entry['provenance']['path']).is_absolute()
                or not isinstance(entry['provenance']['sha256'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', entry['provenance']['sha256'])
                or not re.fullmatch(r'[0-9a-f]{64}', entry['financial_fingerprint'])
                or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', entry['civil_day'])):
            fail('NOTICE_DAY_CONTEXT_INVALID')
        try:
            datetime.strptime(entry['civil_day'], '%Y-%m-%d')
        except ValueError:
            fail('NOTICE_DAY_CONTEXT_INVALID')
    contexts = {}
    for key, entry in evidence['activities'].items():
        if evidence_root is None:
            continue
        try:
            raw = read_local_bytes(Path(evidence_root) / entry['provenance']['path'], evidence_root, 1024 * 1024)
            if hashlib.sha256(raw).hexdigest() != entry['provenance']['sha256']:
                continue
            context = parse_keyed_yaml(raw)
            required = {'schema_version', 'activity_id', 'account_id', 'stored_date',
                'financial_fingerprint', 'entered_day', 'entry_timezone'}
            if (set(context) != required or type(context['schema_version']) is not int
                    or context['schema_version'] != 1 or context['activity_id'] != key
                    or any(context[field] != entry[field] for field in
                        ('account_id', 'stored_date', 'financial_fingerprint'))
                    or context['entered_day'] != entry['civil_day']
                    or not isinstance(context['entry_timezone'], str)):
                continue
            instant = datetime.fromisoformat(context['stored_date'].replace('Z', '+00:00'))
            if (instant.tzinfo is None or instant.astimezone(ZoneInfo(context['entry_timezone'])).date().isoformat()
                    != context['entered_day']):
                continue
            contexts[key] = context
        except (OSError, ValueError, KeyError, RuntimeError):
            # Missing, changed or unusable retained entry context proves no day.
            continue
    legacy_days = notice_approved_legacy_days(remote, evidence['approved_legacy_baseline'], evidence_root) \
        if 'approved_legacy_baseline' in evidence else {}
    result = []
    for row in remote:
        entry = evidence['activities'].get(row['remote_id'])
        verified = bool(entry and row['remote_id'] in contexts and entry['account_id'] == row['target_account_id']
            and entry['stored_date'] == row.get('stored_date')
            and entry['financial_fingerprint'] == activity_financial_fingerprint(row))
        result.append(dict(row, manual_civil_day=entry['civil_day'] if verified else legacy_days.get(row['remote_id']),
            manual_day_provenance='verified' if verified else
                'approved_legacy_display_convention' if row['remote_id'] in legacy_days else 'unverified'))
    return result


def notice_candidate_report(proposal, row, status):
    """Report evidence only; proximity never changes matching or mapping."""
    source_day = proposal['date'][:10]
    destination_day = row.get('manual_civil_day') if 'manual_day_provenance' in row else (
        row['operation_date'] if row['date_context_verified'] else None)
    gap = ((datetime.fromisoformat(destination_day).date() - datetime.fromisoformat(source_day).date()).days
        if destination_day else None)
    source_quantity, source_price, source_fee = (Decimal(proposal[key]) for key in ('quantity', 'unitPrice', 'fee'))
    quantity, price, fee = (row[key] for key in ('quantity', 'unit_price', 'fee'))
    numbers = (source_quantity, source_price, source_fee, quantity, price, fee)
    with localcontext() as context:
        # Products and subtraction must not inherit a caller's rounded context.
        context.prec = max(28, sum(len(n.as_tuple().digits) + abs(n.as_tuple().exponent) for n in numbers) + 10)
        source_total, destination_total = source_quantity * source_price, quantity * price
        verified = row['financial_context_verified'] and row['price_currency'] == proposal['currency'] == 'EUR'
        difference = destination_total - source_total if verified else None
        fee_difference = fee - source_fee if verified else None
        percentage = difference / source_total * 100 if verified and source_total else None
    value = lambda number: canonical_decimal(number) if number is not None else 'unverified'
    return {'code': 'NOTICE_SIMILAR_ACTIVITY', 'status': status,
        'type': proposal['type'], 'symbol': proposal['symbol'],
        'source_day': source_day, 'source_day_provenance': 'notice_row',
        'destination_day': destination_day or 'unverified',
        'destination_activity_id': row['remote_id'],
        'destination_stored_date': row.get('stored_date'),
        'day_provenance': row.get('manual_day_provenance', 'owned_exact_required'),
        'day_gap': gap if gap is not None else 'unverified',
        'source_quantity': value(source_quantity), 'destination_quantity': value(quantity),
        'source_unit_price': value(source_price), 'destination_unit_price': value(price),
        'source_total': value(source_total), 'destination_total': value(destination_total),
        'source_fee': value(source_fee), 'destination_fee': value(fee),
        'total_difference_eur': value(difference), 'total_difference_percent': value(percentage),
        'fee_difference_eur': value(fee_difference),
        'financial_context': 'verified' if verified else 'unverified',
        'financial_writes': 0, 'imported': 0}, difference


def reconcile_notice_duplicates(proposals, remote, day_context=None, evidence_root=None, represented=None):
    """Consume exact owned/manual representations; ambiguity aborts the run."""
    if not proposals:
        return [], 0
    target = proposals[0]['accountId']
    namespace = proposals[0]['comment'].rsplit('#', 1)[0] + '#'
    existing, owned = [], {}
    for row in remote:
        comment = row['comment'] or ''
        if comment.startswith(namespace):
            if (row['target_account_id'] != target or comment in owned
                    or not re.fullmatch(re.escape(namespace) + r'[0-9a-f]{64}', comment)):
                fail('NOTICE_IDENTITY_OWNERSHIP_CONFLICT')
            owned[comment] = row
        if row['target_account_id'] != target or row['kind'] not in ('BUY', 'SELL', 'DIVIDEND'):
            continue
        existing.append(row)

    def signature(row):
        # A legacy timezone shift or inactive row cannot prove an exact match.
        if not (row['active'] and row['date_context_verified'] and row['financial_context_verified']):
            return None
        return (row['target_account_id'], row['kind'], row['operation_date'] + 'T00:00:00.000Z',
            row['symbol'], row['data_source'], row['price_currency'],
            row['quantity'], row['unit_price'], row['fee'])

    pending, seen, duplicates, matched_owned = [], {}, 0, set()
    for proposal in proposals:
        if proposal['accountId'] != target or not proposal['comment'].startswith(namespace):
            fail('NOTICE_IDENTITY_OWNERSHIP_CONFLICT')
        marker, expected = proposal['comment'], notice_signature(proposal)
        if marker in seen:
            fail('NOTICE_PENDING_IDENTITY_CONFLICT')
        seen[marker] = expected
        if marker in owned:
            if signature(owned[marker]) != expected:
                fail('NOTICE_OWNED_ACTIVITY_CONFLICT')
            matched_owned.add(owned[marker]['remote_id'])
            if represented is not None:
                represented[owned[marker]['remote_id']] = proposal
            duplicates += 1
        else:
            pending.append(proposal)
    context_rows = notice_manual_day_context(remote,
        day_context if day_context is not None else {'schema_version': 1, 'activities': {}}, evidence_root)
    manual = [row for row in context_rows if row['target_account_id'] == target
        and row['kind'] in ('BUY', 'SELL', 'DIVIDEND') and not (row['comment'] or '').startswith('BD#')]

    def manual_signature(row):
        if not (row['active'] and row['financial_context_verified'] and row['manual_civil_day']):
            return None
        return manual_comparison((row['target_account_id'], row['kind'], row['manual_civil_day'] + 'T00:00:00.000Z',
            row['symbol'], row['data_source'], row['price_currency'],
            row['quantity'], row['unit_price'], row['fee']))

    def manual_comparison(fields):
        if fields[1] != 'DIVIDEND':
            return fields
        quantity, price, fee = fields[-3:]
        # Multiplication must stay exact even beyond the ambient Decimal precision.
        with localcontext() as context:
            context.prec = max(28, len(quantity.as_tuple().digits) + len(price.as_tuple().digits))
            total = quantity * price
        return fields[:-3] + (total, fee)

    uncertainties = []

    def refuse(reason, **details):
        uncertainties.append({'code': 'NOTICE_MANUAL_OVERLAP_AMBIGUOUS', 'reason': reason,
            **details, 'financial_writes': 0, 'imported': 0})
    groups = {}
    for proposal in pending:
        groups.setdefault(manual_comparison(notice_signature(proposal)), []).append(proposal)
    matched, represented_markers = set(), set()
    result = []
    for expected, group in groups.items():
        matches = [row for row in manual if manual_signature(row) == expected]
        if matches:
            if len(matches) != len(group):
                refuse('multiplicity_conflict', source_count=len(group), destination_count=len(matches))
                result.extend(group)
                continue
            if represented is not None:
                # Equal financial rows are interchangeable for stock. Preserve the
                # source time multiset without attributing manual stored timestamps.
                for row, proposal in zip(matches, group):
                    represented[row['remote_id']] = proposal
            matched.update(row['remote_id'] for row in matches)
            represented_markers.update(proposal['comment'] for proposal in group)
            duplicates += len(group)
        else:
            result.extend(group)
    manual_by_id = {row['remote_id']: row for row in manual}
    for proposal in proposals:
        reports = []
        for original in existing:
            row = manual_by_id.get(original['remote_id'], original)
            if (row['kind'], row['symbol']) != (proposal['type'], proposal['symbol']):
                continue
            exact_owned = row['remote_id'] in matched_owned and row['comment'] == proposal['comment']
            exact_manual = (row['remote_id'] in matched and proposal['comment'] in represented_markers
                and manual_signature(row) == manual_comparison(notice_signature(proposal)))
            represented_elsewhere = (row['remote_id'] in matched_owned or (row['remote_id'] in matched
                and proposal['comment'] in represented_markers))
            status = ('automatic_duplicate' if exact_owned or exact_manual else
                'represented_other_notice' if represented_elsewhere else 'review_required')
            report, difference = notice_candidate_report(proposal, row, status)
            gap = report['day_gap']
            if gap != 'unverified' and abs(gap) > (4 if proposal['type'] == 'DIVIDEND' else 3):
                continue
            reports.append((difference, report))
            if represented_elsewhere or proposal not in pending:
                continue
            if gap == 'unverified':
                refuse('unverified_day_provenance')
            else:
                reason = 'fee_difference' if row['fee'] != Decimal(proposal['fee']) else 'financial_or_day_conflict'
                refuse(reason, day_provenance=report['day_provenance'],
                    source_fee=proposal['fee'], destination_fee=canonical_decimal(row['fee']))
        reports.sort(key=lambda item: (item[0] is None, item[0].copy_abs() if item[0] is not None else Decimal(0)))
        for _, report in reports:
            print(json.dumps(report), flush=True)
    if uncertainties:
        for diagnostic in uncertainties:
            print(json.dumps(diagnostic), flush=True)
        fail('NOTICE_MANUAL_OVERLAP_AMBIGUOUS')
    return result, duplicates


def reconcile_notice_holdings(proposals, remote, project_buys=True, represented=None,
                              day_context=None, evidence_root=None, progress=None):
    """Dated account/symbol stock; only source evidence establishes intraday order."""
    represented = {} if represented is None else represented
    tracked = {(p['accountId'], p['symbol']) for p in proposals if p['type'] == 'SELL'}
    first_pending_day = {}
    for proposal in proposals:
        key = (proposal['accountId'], proposal['symbol'])
        first_pending_day[key] = min(first_pending_day.get(key, proposal['date'][:10]), proposal['date'][:10])
    symbols, events = {}, []
    for proposal in [*proposals, *represented.values()]:
        key = (proposal['accountId'], proposal['symbol'])
        if key in symbols and symbols[key] != proposal['isin']:
            fail('NOTICE_SYMBOL_ISIN_CONFLICT')
        symbols[key] = proposal['isin']
    for proposal in proposals:
        key = (proposal['accountId'], proposal['symbol'])
        if key in tracked and proposal['type'] in ('BUY', 'SELL'):
            events.append({'key': key, 'day': proposal['date'][:10],
                'time': proposal.get('execution_time'), 'kind': proposal['type'],
                'quantity': Decimal(proposal['quantity']), 'proposal': proposal})
    relevant = [row for row in remote if (row['target_account_id'], row['symbol']) in tracked
        and row['active'] and row['kind'] in ('BUY', 'SELL')]
    manual = notice_manual_day_context(remote,
        day_context if day_context is not None else {'schema_version': 1, 'activities': {}}, evidence_root)
    manual_days = {row['remote_id']: row.get('manual_civil_day') for row in manual}
    for row in relevant:
        if not row['financial_context_verified'] or row['data_source'] != 'YAHOO' or row['price_currency'] != 'EUR':
            fail('NOTICE_HOLDINGS_CONTEXT_UNVERIFIED')
        source = represented.get(row['remote_id'])
        day = source['date'][:10] if source else manual_days.get(row['remote_id'])
        # An exact importer date proves a day, never an execution time.
        if not day and (row['comment'] or '').startswith('BD#') and row['date_context_verified']:
            day = row['operation_date']
        if not day:
            print(json.dumps({'code': 'NOTICE_HOLDINGS_CONTEXT_UNVERIFIED',
                'symbol': row['symbol'], 'missing_evidence': 'destination_civil_day',
                'financial_writes': 0, 'imported': 0}), flush=True)
            fail('NOTICE_HOLDINGS_CONTEXT_UNVERIFIED')
        events.append({'key': (row['target_account_id'], row['symbol']), 'day': day,
            'time': source.get('execution_time') if source else None,
            'kind': row['kind'], 'quantity': row['quantity'], 'proposal': None})
    quantities = [event['quantity'] for event in events]
    precision = max((q.adjusted() for q in quantities), default=0) - min(
        (q.as_tuple().exponent for q in quantities), default=0) + len(str(len(quantities) + 1)) + 4
    ordered = list(proposals)
    if tracked:
        ordered.sort(key=lambda p: (p['date'], p.get('execution_time') or '', p['comment']))
    with localcontext() as context:
        context.prec = max(28, precision)
        for sale in events:
            if sale['kind'] != 'SELL' or sale['day'] < first_pending_day[sale['key']]:
                continue
            preceding, available, dependencies = Decimal(0), Decimal(0), []
            for event in events:
                if event is sale or event['key'] != sale['key'] or event['day'] > sale['day']:
                    continue
                if event['kind'] == 'BUY' and event['proposal'] is not None and not project_buys:
                    continue
                quantity = event['quantity']
                if event['day'] < sale['day']:
                    preceding += quantity if event['kind'] == 'BUY' else -quantity
                    available += quantity if event['kind'] == 'BUY' else -quantity
                    continue
                proved_before = bool(event['time'] and sale['time'] and event['time'] < sale['time'])
                proved_after = bool(event['time'] and sale['time'] and event['time'] > sale['time'])
                if event['kind'] == 'BUY':
                    if proved_before:
                        available += quantity
                    elif not proved_after:
                        dependencies.append({'day': event['day'], 'quantity': canonical_decimal(quantity),
                            'source_execution_time': event['time'], 'missing_evidence': 'strict_source_execution_order'})
                elif not proved_after:
                    # Reserve stock for each sale that might precede this sale.
                    available -= quantity
            proposal = sale['proposal']
            possible = available + sum((Decimal(item['quantity']) for item in dependencies), Decimal(0))
            uncertain = available < sale['quantity'] <= possible
            diagnostic = {'code': 'NOTICE_HOLDINGS_ORDER_UNPROVED' if uncertain else
                'NOTICE_INSUFFICIENT_HOLDINGS' if available < sale['quantity'] else 'NOTICE_DATED_HOLDINGS',
                'isin': proposal['isin'] if proposal else symbols[sale['key']],
                'symbol': sale['key'][1], 'sale_day': sale['day'],
                'sale_origin': 'pending' if proposal else 'destination',
                'preceding_day_available': canonical_decimal(preceding),
                'available': canonical_decimal(available), 'sale': canonical_decimal(sale['quantity']),
                'dependent_purchases': dependencies if uncertain else [],
                **({'financial_writes': 0, 'imported': 0} if progress is None else progress)}
            print(json.dumps(diagnostic), flush=True)
            if available < sale['quantity']:
                fail(diagnostic['code'])
    return ordered


def simulate_buy_notice(document, account, mappings, resolver=None, failures=None, skipped=None, occurrences=None):
    """Simulate supported notice rows; financial failures do not hide valid rows."""
    if document['account_ref'] != account['source_account_ref']:
        fail('NOTICE_ACCOUNT_MISMATCH')
    proposals = []
    failures = [] if failures is None else failures
    skipped = [] if skipped is None else skipped
    excluded = {'DROITS DE GARDE', 'TAXE TRANSACT FINANCIERES', 'DIVISION',
        'DET DROIT DE SOUSCRIPTION', 'RETRAIT TITRES FISCALISE', 'TRANSFERT VALEUR',
        'INVESTISSEMENT ESPECES'}
    for note in document['notes']:
        operation = note.get('source_kind', note['kind'])
        supported = note['kind'] in ('BUY', 'SELL', 'COUPON')
        known = supported or operation in excluded or operation in (
            'ACHAT COMPTANT', 'ACHAT ETRANGER', 'VENTE COMPTANT', 'VENTE ETRANGER', 'COUPONS')
        # Generic excluded/no-ISIN rows also retain their observed TVA fields.
        vat = note.get('vat', Decimal(0))
        for fields in note.get('source_fields', []):
            for field in fields:
                if field.startswith('TVA'):
                    match = re.fullmatch(r'TVA\s*:\s*(.+)', field)
                    vat = parse_decimal(match[1], cash=True) if match else None
        reason = ('NOTICE_UNKNOWN_OPERATION' if not known else
            'NOTICE_CURRENCY_UNPROVED' if note.get('net_currency') != 'EUR'
                or note.get('price_currency') not in (None, 'EUR') else
            'NOTICE_NONZERO_TVA' if vat != 0 else
            'NOTICE_OUT_OF_SCOPE' if operation in excluded else
            'NOTICE_NO_ISIN' if not note.get('isin') else None)
        if reason:
            failed = reason in ('NOTICE_UNKNOWN_OPERATION', 'NOTICE_CURRENCY_UNPROVED', 'NOTICE_NONZERO_TVA')
            print(json.dumps({'code': reason, 'level': 'error', 'slot': note['slot'],
                'date': note['date'].isoformat(), 'isin': note.get('isin'), 'run_failed': failed,
                'financial_writes': 0}), flush=True)
            skipped.append(reason)
            if failed:
                failures.append(reason)
            continue
        mapping = resolver(note['isin']) if resolver is not None else mappings.get(note['isin'])
        if mapping is None:
            if resolver is None:
                fail('EXPLICIT_MAPPING_REQUIRED')
            failures.append(note['isin'])
            skipped.append('INSTRUMENT_UNRESOLVED')
            continue
        if mapping['currency'] != 'EUR':
            fail('INVALID_EXPLICIT_MAPPING')
        coupon = note['kind'] == 'COUPON'
        # The EUR debit/credit headers and exact gross/net trade arithmetic
        # establish EUR prices and brokerage, including foreign executions.
        proposal = {'type': 'DIVIDEND' if coupon else note['kind'],
            'date': note['date'].isoformat() + 'T00:00:00.000Z',
            'isin': note['isin'], 'symbol': mapping['symbol'], 'currency': 'EUR',
            'quantity': '1' if coupon else canonical_decimal(note['quantity'].copy_abs()),
            'unitPrice': canonical_decimal(note['credit'] if coupon else note['unit_price']),
            'fee': '0' if coupon else canonical_decimal(note['brokerage'])}
        if occurrences is not None:
            proposal.update(accountId=account['target_account_id'], dataSource='YAHOO',
                comment=notice_identity(note, account, occurrences), execution_time=note.get('execution_time', '00:00:00'))
        proposals.append(proposal)
    return proposals


def notice_wire(proposal):
    """Activities only; keep exact Decimal values through the JSON boundary."""
    row = {key: proposal[key] for key in ('accountId', 'comment', 'currency', 'dataSource',
        'date', 'symbol', 'type')}
    for key in ('quantity', 'unitPrice', 'fee'):
        row[key] = wire_number(Decimal(proposal[key]))
    return json.dumps({'activities': [row]}, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()


def notice_write_journal(root, config, account):
    """DEGIRO-style intent fencing, under the shared nonblocking broker lock."""
    owner = {'origin': config['origin'], 'source': account['source_account_ref'],
        'target': account['target_account_id']}
    key = hashlib.sha256(json.dumps([owner['origin'], owner['target']], separators=(',', ':')).encode()).hexdigest()
    path = root / ('notice-writes-' + key + '.yaml')
    journal = read_keyed_yaml(path, root, 8 * 1024 * 1024) if path.exists() or path.is_symlink() else {
        'schema_version': 1, 'owner': owner, 'pending': None, 'confirmed': {}}
    if (set(journal) != {'schema_version', 'owner', 'pending', 'confirmed'}
            or type(journal['schema_version']) is not int or journal['schema_version'] != 1
            or journal['owner'] != owner or not isinstance(journal['confirmed'], dict)
            or any(not isinstance(marker, str) or not isinstance(remote_id, str) or not remote_id.strip()
                for marker, remote_id in journal['confirmed'].items())
            or journal['pending'] is not None and not isinstance(journal['pending'], dict)):
        fail('NOTICE_WRITE_JOURNAL_INVALID')
    if journal['pending'] is not None:
        # Even exact positive readback requires explicit operator resolution.
        fail('NOTICE_WRITE_UNRESOLVED')
    return path, journal


def notice_exact_readback(proposal, raw, expected_id=None):
    rows = parse_remote_activity_snapshot(raw, retain_stored_date=True)
    matches = [row for row in rows if row['comment'] == proposal['comment']]
    if (len(matches) != 1 or matches[0]['stored_date'] != proposal['date']
            or expected_id is not None and matches[0]['remote_id'] != expected_id):
        fail('NOTICE_IMPORT_UNCONFIRMED')
    pending, duplicates = reconcile_notice_duplicates([proposal], rows)
    if pending or duplicates != 1:
        fail('NOTICE_IMPORT_UNCONFIRMED')
    return rows, matches[0]['remote_id']


def notice_persisted_activity_unchanged(before, after):
    """Ignore Ghostfolio's derived profile count, but preserve every stored field."""
    for key, value in before.items():
        if key != 'stored_activity':
            if after.get(key) != value:
                return False
            continue
        previous = json.loads(value, object_pairs_hook=unique_json_object)
        current = json.loads(after.get(key, '{}'), object_pairs_hook=unique_json_object)
        for activity in (previous, current):
            for profile_key in ('assetProfile', 'SymbolProfile'):
                profile = activity.get(profile_key)
                if isinstance(profile, dict):
                    profile.pop('activitiesCount', None)
        if current != previous:
            return False
    return True


def import_notice_proposals(proposals, remote, path, journal, run, request, progress,
                            represented=None, day_context=None, evidence_root=None):
    """Only readback-confirmed BUYs fund SELLs. Never replay uncertain POSTs."""
    represented = dict(represented or {})
    ordered = reconcile_notice_holdings(proposals, remote, represented=represented,
        day_context=day_context, evidence_root=evidence_root)
    # Reject precision loss anywhere before the first POST.
    wires = {p['comment']: notice_wire(p) for p in ordered}
    progress.update(financial_writes=0, imported=0)
    rejected = set()
    for ordinal, proposal in enumerate(ordered):
        if proposal['symbol'] in rejected:
            continue
        if proposal['type'] == 'SELL':
            reconcile_notice_holdings([proposal], remote, project_buys=False, progress=progress,
                represented=represented, day_context=day_context, evidence_root=evidence_root)
        body = wires[proposal['comment']]
        journal['pending'] = {'body': body.decode(), 'run_id': run.name, 'ordinal': ordinal}
        atomic_private_yaml(path, journal)
        progress['financial_writes'] += 1  # Dispatched POSTs; outcome can remain uncertain.
        try:
            status, response = request('POST', '/api/v1/import', body)
            atomic_private_bytes(run / ('import-response-' + str(ordinal) + '.json'), response)
            if status == 400:
                data = json.loads(response, object_pairs_hook=unique_json_object)
                messages = data.get('message') if isinstance(data, dict) else None
                messages = [messages] if isinstance(messages, str) else messages
                expression = r'activities\.[0-9]+\.symbol \("([^"]+)"\) cannot be resolved by the data source \("YAHOO"\)'
                if isinstance(messages, list) and len(messages) == 1 and isinstance(messages[0], str):
                    match = re.fullmatch(expression, messages[0])
                    if match and match[1] == proposal['symbol']:
                        # Sibling activities-only validation rejects before creating rows.
                        rejected.add(proposal['symbol'])
                        journal['pending'] = None
                        atomic_private_yaml(path, journal)
                        print(json.dumps({'code': 'NOTICE_SYMBOL_REJECTED', 'level': 'error',
                            'symbol': proposal['symbol'], **progress}), flush=True)
                        continue
                fail('NOTICE_IMPORT_UNCONFIRMED')
            if status != 201:
                fail('NOTICE_IMPORT_UNCONFIRMED')
            sent = json.loads(body, parse_float=Decimal, object_pairs_hook=unique_json_object)['activities'][0]
            comparison = compare_expected_import_response({sent['comment']: sent}, response)
            if comparison['status'] != 'complete':
                fail('NOTICE_IMPORT_UNCONFIRMED')
            remote_id = comparison['accepted'][sent['comment']]
            status, readback = request('GET', '/api/v1/activities', None)
            if status != 200:
                fail('NOTICE_IMPORT_UNCONFIRMED')
            atomic_private_bytes(run / ('import-readback-' + str(ordinal) + '.json'), readback)
            confirmed_remote, _ = notice_exact_readback(proposal, readback, remote_id)
            current = {row['remote_id']: row for row in confirmed_remote}
            if any(row['remote_id'] not in current or not notice_persisted_activity_unchanged(
                    row, current[row['remote_id']])
                    for row in remote):
                fail('NOTICE_IMPORT_UNCONFIRMED')
            remote = confirmed_remote
            represented[remote_id] = proposal
            journal['confirmed'][proposal['comment']] = remote_id
            journal['pending'] = None
            atomic_private_yaml(path, journal)
            progress['imported'] += 1
            print(json.dumps({'code': 'NOTICE_IMPORT_CONFIRMED',
                'comment': proposal['comment'], 'type': proposal['type'],
                'exact_response': True, 'exact_readback': True, **progress}), flush=True)
        except Exception:
            fail('NOTICE_IMPORT_UNCONFIRMED')
    return {**progress, 'rejected': sum(p['symbol'] in rejected for p in ordered)}


def sync_buy_simulation(progress=None):
    """One noninteractive notice acquisition and explicitly selected import mode."""
    progress = {} if progress is None else progress
    import subprocess
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
    import community_connect as acquisition

    os.umask(0o077)
    config = buy_simulation_config()
    root = Path('/state')
    private_directory(root)
    vault_env = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith('BW_')}
    token = os.environ.pop('GHOST_ACCESS_TOKEN', None)
    lock = None
    proxy = None
    try:
        lock = acquisition.broker_lock(root)
        acquisition.broker_login_ready(root)
        discovery = acquisition.discovery_receipt(root)
        discovery_only = config.get('discovery_only', False)
        if discovery_only and discovery is not None:
            acquisition.print_discovery(discovery, reused=True)
            return 1
        if not discovery_only:
            if discovery is not None and config['source_ref'] not in discovery['accounts']:
                fail('CONFIGURED_ACCOUNT_UNAVAILABLE')
            acquisition.ghostfolio_origin(config['origin'])
            binding_path = acquisition.account_binding_path(root, config['source_ref'])
            saved = acquisition.saved_account_binding(root, binding_path, config['source_ref'])
            account = acquisition.reconcile_binding(saved, config['origin'], config['source_ref'], config['target'])
            if account is None:
                account = {'source_account_ref': config['source_ref'], 'target_account_id': config['target'],
                           'account_key': str(uuid.uuid4())}
            journal_path, journal = notice_write_journal(root, config, account)
            destination = acquisition.ghostfolio_snapshot(config['origin'], token, include_lookup=True,
                include_import=not config['dry_run'])
            accounts, _, snapshot, lookup = destination[:4]
            import_request = destination[4] if not config['dry_run'] else None
            remote = parse_remote_activity_snapshot(snapshot, retain_stored_date=True)
            context_path = root / 'manual-day-context.yaml'
            day_context = (read_keyed_yaml(context_path, root, acquisition.MAX_BYTES) if context_path.exists()
                else {'schema_version': 1, 'activities': {}})
            # Reject malformed evidence before attempting broker access.
            notice_manual_day_context(remote, day_context, root)
            rows = json.loads(snapshot, object_pairs_hook=unique_json_object)['activities']
            profiles = [row['assetProfile'] if 'assetProfile' in row else row.get('SymbolProfile') for row in rows]
            profiles = [profile for profile in profiles if isinstance(profile, dict)]
            token = None
            acquisition.choose([{'value': row['id'], 'label': row['name']} for row in accounts],
                               'Destination', config['target'])
        private_directory(root / 'runs')
        run = root / 'runs' / str(uuid.uuid4())
        private_directory(run)
        as_of = datetime.now(ZoneInfo('Europe/Zurich')).date().isoformat()
        atomic_private_yaml(run / 'attempt.yaml', {'schema_version': 1, 'state': 'started', 'as_of': as_of})
        if discovery_only:
            atomic_private_yaml(root / 'discovery.yaml', {'schema_version': 1, 'state': 'started',
                'run_id': run.name, 'accounts': {}})
        proxy = subprocess.Popen(['/usr/bin/python3', '-I', str(acquisition.ROOT / 'collector/vault-egress.py'),
            '--broker-inspection', '--ready'], env={'PATH': '/usr/bin:/bin'},
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        acquisition.wait_proxy_ready(proxy)
        if discovery_only:
            references, _ = acquisition.acquire(run, as_of, None, '', '', vault_env, discovery_only=True)
            vault_env.clear()
            acquisition.close_proxy(proxy)
            proxy = None
            discovery = {'schema_version': 1, 'state': 'completed', 'run_id': run.name,
                'accounts': {ref: ref.split(' ', 1)[1] for ref in references}}
            atomic_private_yaml(root / 'discovery.yaml', discovery)
            acquisition.print_discovery(discovery, reused=False)
            return 1
        account, documents = acquisition.acquire(run, as_of, account, config['source_ref'], config['target'],
                                                vault_env, origin=config['origin'], binding_path=binding_path)
        vault_env.clear()
        acquisition.close_proxy(proxy)
        proxy = None
        receipt = read_keyed_yaml(run / 'qualification.yaml', root, acquisition.MAX_BYTES)
        coverage = receipt['notice_coverage']
        if (coverage['complete'] is not True or receipt['account_binding'] != account
                or coverage['window']['last_day'] != as_of or documents['complete'] is not True
                or documents['monthly_statements'] != 0):
            fail('NOTICE_WINDOW_INCOMPLETE')
        wrapper = config['source_ref'].split(' ', 1)[1]
        print(json.dumps({'code': 'NOTICE_WINDOW_COMPLETED', **coverage['window'],
            'expected_months': coverage['expected_months'], 'observed_months': coverage['observed_months'][wrapper],
            'empty_months': coverage['empty_months'][wrapper], 'selected_account_verified': True,
            'session_logged_out': receipt['session_logged_out'], 'browser_exit_verified': receipt['browser_exit_verified'],
            'monthly_statements': documents['monthly_statements'], 'contract_notes': documents['contract_notes'],
            'financial_writes': 0}), flush=True)
        proposals, skipped, failures, occurrences = [], [], [], {}
        resolved = {}

        def resolver(isin):
            if isin not in resolved:
                resolved[isin] = resolve_instrument(isin, config['mappings'], profiles, lookup)
            return resolved[isin]
        for path in sorted(run.glob('document-*.yaml')):
            metadata = read_keyed_yaml(path, root, acquisition.MAX_BYTES)
            if metadata['role'] != 'contract_note':
                continue
            raw = read_local_bytes(run / metadata['path'], root, acquisition.MAX_BYTES)
            if hashlib.sha256(raw).hexdigest() != metadata['sha256']:
                fail('NOTICE_CAPTURE_CHANGED')
            document = parse_contract_note(decode_document(raw), 16, include_coupons=True, skip_missing_isin=True, notice_sync=True)
            if document['account_ref'] != account['source_account_ref']:
                fail('NOTICE_ACCOUNT_MISMATCH')
            first = datetime.strptime(as_of, '%Y-%m-%d').date() - timedelta(days=89)
            document['notes'] = [note for note in document['notes'] if first <= note['date'] <= datetime.strptime(as_of, '%Y-%m-%d').date()]
            proposals.extend(simulate_buy_notice(document, account, config['mappings'], resolver, failures, skipped, occurrences))
        if not config['dry_run']:
            status, snapshot = import_request('GET', '/api/v1/activities', None)
            if status != 200:
                fail('GHOSTFOLIO_ACCESS_REFUSED')
            atomic_private_bytes(run / 'import-baseline.json', snapshot)
            remote = parse_remote_activity_snapshot(snapshot, retain_stored_date=True)
        progress.update(proposed=len(proposals), skipped=len(skipped), failed_rows=len(failures))
        represented = {}
        proposals, duplicates = reconcile_notice_duplicates(proposals, remote, day_context, root, represented)
        progress.update(proposed=len(proposals), duplicates=duplicates)
        proposals = reconcile_notice_holdings(proposals, remote, represented=represented,
            day_context=day_context, evidence_root=root)
        atomic_private_yaml(run / ('simulation.yaml' if config['dry_run'] else 'proposals.yaml'),
            {'schema_version': 1, 'mode': 'DRY_RUN' if config['dry_run'] else 'IMPORT',
            'proposals': proposals, 'unresolved_isins': sorted({value for value in failures if valid_isin(value)}),
            'failed_rows': len(failures), 'skipped': len(skipped), 'duplicates': duplicates,
            'financial_writes': 0, 'imported': 0})
        if not config['dry_run']:
            result = import_notice_proposals(proposals, remote, journal_path, journal, run, import_request, progress,
                represented=represented, day_context=day_context, evidence_root=root)
            progress.update(skipped=len(skipped) + result['rejected'], failed_rows=len(failures) + result['rejected'])
            print(json.dumps({'code': 'NOTICE_IMPORT_COMPLETED', 'proposed': len(proposals),
                'imported': result['imported'], 'duplicates': duplicates, 'skipped': len(skipped) + result['rejected'],
                'failed_rows': len(failures) + result['rejected'],
                'financial_writes': result['financial_writes']}, sort_keys=True), flush=True)
            return 1 if failures or result['rejected'] else 0
        for proposal in proposals:
            print(json.dumps({'code': 'DRY_RUN_PROPOSAL', **proposal}), flush=True)
        print(json.dumps({'code': 'NOTICE_SIMULATION_COMPLETED', 'proposed': len(proposals), 'imported': 0,
            'skipped': len(skipped), 'failed_rows': len(failures), 'duplicates': duplicates,
            'contract_notes': documents['contract_notes'], 'financial_writes': 0}), flush=True)
        return 1 if failures else 0
    finally:
        token = None
        vault_env.clear()
        try:
            acquisition.close_proxy(proxy)
        finally:
            if lock is not None:
                os.close(lock)


NOTIFY_WORKER_FLAG = "--notify-worker"
NOTIFY_PAYLOAD_MAX = 32 * 1024
APPRISE_URLS_MAX = 10
APPRISE_URL_MAX_LEN = 2048
APPRISE_TIMEOUT_DEFAULT = 10
APPRISE_TIMEOUT_MAX = 30
# The worker inherits only what Apprise needs to reach a destination: never the
# Bourse Direct or Ghostfolio credentials.
NOTIFY_ENV_ALLOWLIST = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
                        "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
                        "http_proxy", "https_proxy", "no_proxy")
# Worker exit code -> delivery status reported by send_notification.  Kept clear
# of the interpreter's own codes (1 uncaught error, 2 cannot open the script).
NOTIFY_EXIT_STATUS = {0: "sent", 10: "invalid_payload", 11: "unavailable", 12: "failed",
                      13: "invalid_destination"}


def load_notification_config():
    """Parse APPRISE_URLS and APPRISE_TIMEOUT; None means notifications are off.

    APPRISE_URLS is a JSON list of Apprise URL strings (blank or [] = off);
    APPRISE_TIMEOUT an integer number of seconds, 1..30 (default 10).  Never
    raises: invalid settings only disable delivery, with a fixed warning since
    the values carry destination credentials.
    """
    raw = os.environ.get("APPRISE_URLS", "")
    if not raw.strip():
        return None
    try:
        urls = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        urls = None
    raw_timeout = os.environ.get("APPRISE_TIMEOUT", "").strip()
    timeout = APPRISE_TIMEOUT_DEFAULT
    if raw_timeout:
        timeout = int(raw_timeout) if re.fullmatch(r"[0-9]{1,2}", raw_timeout) else 0
    if (not isinstance(urls, list) or len(urls) > APPRISE_URLS_MAX
            or not all(isinstance(u, str) and u.strip() and len(u) <= APPRISE_URL_MAX_LEN
                       for u in urls)
            or not 1 <= timeout <= APPRISE_TIMEOUT_MAX):
        log.warning("APPRISE_URLS or APPRISE_TIMEOUT is invalid: failure notifications disabled")
        return None
    if not urls:
        return None
    return {"urls": urls, "timeout": timeout}


def notify_worker():
    """Worker process entry: deliver one notification read from stdin.

    Never runs the sync.  Apprise is imported here only, so the sync never
    loads it.  Exit codes: see NOTIFY_EXIT_STATUS.
    """
    logging.disable(logging.CRITICAL)
    raw = sys.stdin.buffer.read(NOTIFY_PAYLOAD_MAX + 1)
    try:
        payload = json.loads(raw) if len(raw) <= NOTIFY_PAYLOAD_MAX else None
    except ValueError:
        payload = None
    if (not isinstance(payload, dict)
            or not isinstance(payload.get("urls"), list) or not payload["urls"]
            or not all(isinstance(u, str) for u in payload["urls"])
            or not isinstance(payload.get("title"), str)
            or not isinstance(payload.get("body"), str)):
        return 10
    try:
        import apprise
    except ImportError:
        return 11
    notifier = apprise.Apprise()
    # One entry may hold several space- or comma-separated URLs: bound the
    # destinations Apprise actually expanded, not the list entries
    if (not all(notifier.add(url) for url in payload["urls"])
            or len(notifier) > APPRISE_URLS_MAX):
        return 13
    try:
        sent = notifier.notify(title=payload["title"], body=payload["body"])
    except Exception:
        return 12
    return 0 if sent else 12


def _notify_worker_argv():
    # -I: ignore PYTHON* variables, user site-packages and the current directory
    return [sys.executable, "-I", os.path.abspath(__file__), NOTIFY_WORKER_FLAG]


def _stop_worker(proc):
    """Kill the worker (and anything it started) if still running, then reap it."""
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    proc.wait()


def send_notification(settings, title, body):
    """Deliver one notification through an isolated Apprise worker.

    Apprise plugins can block past any library timeout and can print their
    destination URL.  So the URLs travel on stdin, the worker gets an
    allowlisted environment and no output channel, and one deadline covers its
    whole life (import, setup, send, exit); on expiry it is killed and reaped.
    No retry: a timed-out send may still have been delivered.  Returns a fixed
    status string; SystemExit/KeyboardInterrupt propagate after the kill.
    """
    payload = json.dumps({"urls": settings["urls"], "title": title, "body": body}).encode()
    if len(payload) > NOTIFY_PAYLOAD_MAX:
        return "payload_too_large"
    # The worker re-runs this file: impossible when the script came from stdin
    if not os.path.isfile(os.path.abspath(__file__)):
        return "spawn_failed"
    env = {k: os.environ[k] for k in NOTIFY_ENV_ALLOWLIST if k in os.environ}
    try:
        proc = subprocess.Popen(_notify_worker_argv(), stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=env, close_fds=True, start_new_session=True)
    except (OSError, ValueError):
        return "spawn_failed"
    try:
        proc.communicate(payload, timeout=settings["timeout"])
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception:
        return "failed"
    finally:
        _stop_worker(proc)
    return NOTIFY_EXIT_STATUS.get(proc.returncode, "failed")


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments == [NOTIFY_WORKER_FLAG]:
        return notify_worker()
    if arguments == ['--sync']:
        progress = dict(proposed=0, imported=0, duplicates=0, skipped=0, failed_rows=0, financial_writes=0)
        result, code = 1, 'NOTICE_RUN_REFUSED'
        try:
            result = sync_buy_simulation(progress)
            code = ('SOURCE_ACCOUNT_CONFIGURATION_REQUIRED' if not os.environ.get('BD_SOURCE_ACCOUNT_REF')
                else 'NOTICE_ROWS_FAILED') if result else 'NOTICE_RUN_SUCCEEDED'
            return result
        except Exception as error:
            allowed = {'INVALID_DRY_RUN',
                'EXPLICIT_ACCOUNTS_REQUIRED', 'EXPLICIT_MAPPING_REQUIRED', 'INVALID_EXPLICIT_MAPPING',
                'MAPPING_FILE_UNREADABLE_OR_INVALID', 'INVALID_KEYED_YAML', 'YAML_DUPLICATE_KEY',
                'YAML_ALIAS_NOT_SUPPORTED', 'YAML_STRING_KEYS_REQUIRED', 'YAML_TOO_DEEP',
                'NOTICE_ACCOUNT_MISMATCH', 'NOTICE_CAPTURE_CHANGED', 'NOTICE_CURRENCY_UNPROVED',
                'NOTICE_WINDOW_INCOMPLETE',
                'CONFIGURED_ACCOUNT_UNAVAILABLE', 'ACCOUNT_BINDING_INVALID', 'ACCOUNT_BINDING_CONFLICT',
                'SOURCE_CONNECT_REFUSED', 'SOURCE_PROXY_UNAVAILABLE', 'GHOSTFOLIO_ACCESS_INVALID',
                'GHOSTFOLIO_ACCESS_REFUSED', 'GHOSTFOLIO_RESPONSE_TOO_LARGE', 'GHOSTFOLIO_ACCOUNTS_INVALID',
                'INVALID_GHOST_ORIGIN'}
            allowed.update({'NOTICE_IDENTITY_OWNERSHIP_CONFLICT', 'NOTICE_PENDING_IDENTITY_CONFLICT',
                'NOTICE_OWNED_ACTIVITY_CONFLICT', 'NOTICE_MANUAL_OVERLAP_AMBIGUOUS', 'NOTICE_DAY_CONTEXT_INVALID',
                'NOTICE_INSUFFICIENT_HOLDINGS', 'NOTICE_HOLDINGS_CONTEXT_UNVERIFIED', 'NOTICE_HOLDINGS_ORDER_UNPROVED',
                'NOTICE_SYMBOL_ISIN_CONFLICT', 'REMOTE_ACTIVITY_COUNT_MISMATCH',
                'REMOTE_NUMERIC_FIELD_INVALID_OR_REDACTED'})
            refusals = {'BROKER_RUN_LOCKED', 'BROKER_STATE_INVALID', 'BROKER_LOGIN_UNRESOLVED',
                'BROKER_DISCOVERY_UNRESOLVED', 'BROKER_DISCOVERY_INVALID', 'NOTICE_WRITE_UNRESOLVED',
                'NOTICE_WRITE_JOURNAL_INVALID'}
            allowed.update(refusals)
            allowed.update({'NOTICE_WRITE_UNRESOLVED', 'NOTICE_WRITE_JOURNAL_INVALID',
                'NOTICE_IMPORT_UNCONFIRMED', 'WIRE_NUMERIC_PRECISION_LOSS'})
            code = str(error) if str(error) in allowed else 'NOTICE_SIMULATION_REFUSED'
            print(json.dumps({'code': code, **progress,
                **({'broker_attempts': 0} if code in refusals else {})}), flush=True)
            return 1
        finally:
            summary = {'code': 'NOTICE_RUN_COMPLETED', 'status': 'failed' if result else 'succeeded',
                'error': code if result else None, **progress}
            summary['errors'] = max(1, summary['failed_rows']) if result else 0
            print(json.dumps(summary, sort_keys=True), flush=True)
            # Simulation never alerts. Only fixed codes/counts leave the process.
            if result and os.environ.get('DRY_RUN', '1').strip().lower() in ('0', 'false', 'no', 'off'):
                settings = load_notification_config()
                if settings:
                    status = send_notification(settings, 'ghostfolio-boursedirect-sync: run failed',
                        json.dumps(summary, sort_keys=True))
                    print(json.dumps({'code': 'NOTICE_FAILURE_ALERT', 'status': status}), flush=True)
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="Inspect a saved statement without network access")
    inspect.add_argument("path")
    inspect.add_argument("--input-root", required=True)
    inspect.add_argument("--max-bytes", type=int, required=True, help="Explicit local input size budget")
    inspect.add_argument("--max-depth", type=int, required=True, help="Explicit HTML nesting budget")
    inspect.add_argument("--notes", nargs="+", help="Saved daily contract-note HTML files; no URLs")
    note = subparsers.add_parser("inspect-note", help="Inspect saved operation-note fields without conversion")
    note.add_argument("path", help="Saved local HTML only")
    note.add_argument("--input-root", required=True)
    note.add_argument("--max-bytes", type=int, required=True)
    note.add_argument("--max-depth", type=int, required=True)
    note.add_argument("--include-coupons", action="store_true", help="Read coupon fields without tax or import claims")
    coupons = subparsers.add_parser("review-coupons", help="Review source net dividend cash and booking dates offline")
    coupons.add_argument("path", help="Saved monthly statement")
    coupons.add_argument("--notes", nargs="+", required=True)
    coupons.add_argument("--input-root", required=True)
    coupons.add_argument("--output", required=True, help="Private review file under outputs")
    coupons.add_argument("--max-bytes", type=int, required=True)
    coupons.add_argument("--max-depth", type=int, required=True)
    coupon_reconciliation = subparsers.add_parser("reconcile-coupons", help="Compare original coupon sources with saved history; no writes")
    coupon_reconciliation.add_argument("--config", required=True)
    coupon_reconciliation.add_argument("--input-root", required=True)
    coupon_reconciliation.add_argument("--output", required=True)
    coupon_reconciliation.add_argument("--max-bytes", type=int, required=True)
    coupon_reconciliation.add_argument("--max-depth", type=int, required=True)
    daily = subparsers.add_parser("daily-preview", help="Recompute private 90-day saved-input coverage and retain exceptions")
    daily.add_argument("--config", required=True)
    daily.add_argument("--input-root", required=True)
    daily.add_argument("--as-of", help="Broker calendar day, YYYY-MM-DD; defaults to today in Europe/Paris")
    daily.add_argument("--max-bytes", type=int, required=True)
    daily.add_argument("--max-depth", type=int, required=True)
    prepare = subparsers.add_parser("prepare", help="Prepare a private internal review plan, never an API payload")
    prepare.add_argument("--config", required=True, help="Local keyed YAML inside input root")
    prepare.add_argument("--input-root", required=True)
    prepare.add_argument("--max-bytes", type=int, required=True)
    prepare.add_argument("--max-depth", type=int, required=True)
    captures = subparsers.add_parser("qualify-captures", help="Qualify a completed local bundle into a private prepare proposal")
    captures.add_argument("--manifest", required=True)
    captures.add_argument("--config", required=True)
    captures.add_argument("--input-root", required=True)
    captures.add_argument("--output", required=True, help="New directory outside the input tree, with an existing private parent")
    captures.add_argument("--max-bytes", type=int, required=True)
    captures.add_argument("--max-depth", type=int, required=True)
    review = subparsers.add_parser("review", help="Reconcile prepared activities against saved history without network")
    review.add_argument("--config", required=True, help="Local keyed review YAML inside input root")
    review.add_argument("--input-root", required=True)
    review.add_argument("--max-bytes", type=int, required=True)
    apply = subparsers.add_parser("apply", help="Preview or explicitly qualified single-event application")
    apply.add_argument("--config", required=True)
    apply.add_argument("--review", required=True)
    apply.add_argument("--review-sha256", required=True)
    apply.add_argument("--input-root", required=True)
    apply.add_argument("--max-bytes", type=int, required=True)
    apply.add_argument("--export", help="Optional private manual proposal under outputs, not an import")
    apply.add_argument("--execute", action="store_true", help="Request execution under a separately pinned declaration; DRY_RUN overrides")
    apply.add_argument("--execution", help="Private external operator declaration inside input root")
    apply.add_argument("--execution-sha256", help="External declaration content pin, not authentication")
    apply.add_argument("--max-depth", help="Explicit HTML nesting budget for execution only")
    apply.add_argument("--timeout", help="Explicit bounded HTTPS timeout for execution only")
    check = subparsers.add_parser("check-review", help="Verify a pinned saved review offline without writing files")
    check.add_argument("--config", required=True)
    check.add_argument("--review", required=True)
    check.add_argument("--review-sha256", required=True, help="External nonsecret content pin; not approval")
    check.add_argument("--input-root", required=True)
    check.add_argument("--max-bytes", type=int, required=True)
    diagnose = subparsers.add_parser("diagnose", help="Describe saved candidates without adoption or import claims")
    diagnose.add_argument("--config", required=True)
    diagnose.add_argument("--input-root", required=True)
    diagnose.add_argument("--max-bytes", type=int, required=True)
    verify = subparsers.add_parser("verify", help="Observe retained intent evidence without resolving or sending")
    verify.add_argument("--config", required=True)
    verify.add_argument("--input-root", required=True)
    verify.add_argument("--max-bytes", type=int, required=True)
    compensation = subparsers.add_parser("rollback-plan", help="Inspect saved association candidates; no creation proof or deletion authority")
    compensation.add_argument("--config", required=True)
    compensation.add_argument("--input-root", required=True)
    compensation.add_argument("--max-bytes", type=int, required=True)
    snapshot = subparsers.add_parser("snapshot", help="Save complete activity JSON with one allowlisted HTTPS GET")
    snapshot.add_argument("--config", required=True)
    snapshot.add_argument("--input-root", required=True)
    snapshot.add_argument("--max-bytes", type=int, required=True)
    snapshot.add_argument("--timeout", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "daily-preview":
            print(json.dumps(preview_local_daily(args.config, args.input_root, args.as_of if args.as_of is not None else daily_preview_today(),
                args.max_bytes, args.max_depth), sort_keys=True))
            return 2
        if args.command == "reconcile-coupons":
            print(json.dumps(reconcile_local_coupons(args.config, args.input_root, args.output,
                args.max_bytes, args.max_depth), sort_keys=True))
            return 2
        if args.command == "review-coupons":
            print(json.dumps(review_local_coupons(args.path, args.notes, args.input_root,
                args.output, args.max_bytes, args.max_depth), sort_keys=True))
            return 2
        if args.command == "inspect-note":
            html, _ = read_document(args.path, args.input_root, args.max_bytes)
            document = parse_contract_note(html, args.max_depth, include_coupons=args.include_coupons)
            coupons = sum(n["kind"] == "COUPON" for n in document["notes"])
            unknown = sum(n["kind"] == "UNKNOWN" for n in document["notes"])
            trades = len(document["notes"]) - coupons - unknown
            blockers = ["COUPON_STATEMENT_REVIEW_REQUIRED"] if coupons else []
            if trades or not coupons:
                blockers.append("REAL_SOURCE_ACCEPTANCE_PENDING")
            if unknown:
                blockers.append("UNKNOWN_OPERATIONS")
            print(json.dumps({"notes": len(document["notes"]), "coupons": coupons,
                "trades": trades, "unknown": unknown,
                "import_ready": False, "blockers": blockers}, sort_keys=True))
            return 2
        if args.command == "qualify-captures":
            print(json.dumps(qualify_local_captures(args.manifest, args.config, args.input_root,
                                                   args.output, args.max_bytes, args.max_depth), sort_keys=True))
            return 2
        if args.command == "apply":
            dry_run = os.environ.get("DRY_RUN", "1")
            if dry_run not in ("0", "1"):
                fail("INVALID_DRY_RUN")
            if args.execute and dry_run == "0":
                if args.execution is None or args.execution_sha256 is None:
                    fail("APPLICATION_EXECUTION_GATE_REQUIRED")
                try:
                    max_depth, timeout = int(args.max_depth), int(args.timeout)
                except (TypeError, ValueError):
                    fail("APPLICATION_EXECUTION_LIMITS_REQUIRED")
                result = execute_local_application(args.config, args.review, args.review_sha256,
                    args.input_root, args.max_bytes, args.execution, args.execution_sha256,
                    max_depth, timeout, export_path=args.export)
                print(json.dumps(result, sort_keys=True))
                return 0 if result["accepted_events"] else 2
            print(json.dumps(preview_local_application(args.config, args.review, args.review_sha256,
                args.input_root, args.max_bytes, export_path=args.export, execute=args.execute), sort_keys=True))
            return 2
        if args.command == "check-review":
            print(json.dumps(check_local_frozen_review(args.config, args.review, args.review_sha256,
                                                       args.input_root, args.max_bytes), sort_keys=True))
            return 2
        if args.command == "rollback-plan":
            print(json.dumps(plan_local_compensation(args.config, args.input_root, args.max_bytes), sort_keys=True))
            return 2
        if args.command == "verify":
            print(json.dumps(verify_local_intents(args.config, args.input_root, args.max_bytes), sort_keys=True))
            return 2
        if args.command == "diagnose":
            print(json.dumps(diagnose_local_snapshot(args.config, args.input_root, args.max_bytes), sort_keys=True))
            return 2
        if args.command == "snapshot":
            print(json.dumps(acquire_readonly_snapshot(args.config, args.input_root, args.max_bytes, args.timeout), sort_keys=True))
            return 2
        if args.command == "review":
            print(json.dumps(review_local_snapshot(args.config, args.input_root, args.max_bytes), sort_keys=True))
            return 2
        if args.command == "prepare":
            summary = prepare_local_plan(args.config, args.input_root, args.max_bytes, args.max_depth)
            print(json.dumps(summary, sort_keys=True))
            return 2
        html, _ = read_document(args.path, args.input_root, args.max_bytes)
        statement = parse_statement(html, args.max_depth)
        summary = inspection_summary(statement)
        if args.notes:
            documents = []
            for path in args.notes:
                note_html, _ = read_document(path, args.input_root, args.max_bytes)
                documents.append(parse_contract_note(note_html, args.max_depth))
            result = match_trade_notes(statement, documents)
            blockers = set(summary["blockers"]) | set(result["blockers"])
            if len(result["matches"]) == sum(e["kind"] in ("BUY", "SELL") for e in statement["events"]):
                blockers.discard("CONTRACT_NOTE_ENRICHMENT_UNVERIFIED")
            summary["blockers"] = sorted(blockers)
            summary["note_matching"] = {"note_count": result["note_count"], "matched_trades": len(result["matches"]),
                                       **{k: result[k] for k in ("missing_trades", "ambiguous_trades", "unmatched_notes")}}
    except RuntimeError as error:
        log.error("Inspection failed: %s", error)
        return 1
    except (OSError, ValueError):
        log.error("Inspection failed: LOCAL_INPUT_ERROR")
        return 1
    print(json.dumps(summary, sort_keys=True))
    # 2 distinguishes a readable ledger with unresolved acceptance blockers.
    return 2


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(main())
