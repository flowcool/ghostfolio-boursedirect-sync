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
import sys
import uuid
from urllib.parse import urlsplit

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
        kind = "SELL" if label.startswith("VTE CPT ") else "BUY" if label.startswith("ACH CPT ") else "UNKNOWN"
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


def parse_contract_note(html, max_depth):
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
    candidates = []
    for table in soup.find_all("table"):
        first = table.find("tr", recursive=False)
        if first is None:
            body = table.find("tbody", recursive=False)
            first = body.find("tr", recursive=False) if body else None
        if first and tuple(text(c) for c in cells(first)) == HEADERS:
            candidates.append(table)
    if len(candidates) != 1:
        fail("LEDGER_MISSING_OR_AMBIGUOUS")
    rows = direct_rows(candidates[0])
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
    if not count or count % 9:
        fail("UNSUPPORTED_NOTE_GROUP_LENGTH")
    groups = []
    labels = {"ACHAT COMPTANT": "BUY", "ACHAT ETRANGER": "BUY", "VENTE COMPTANT": "SELL"}
    for start in range(0, count, 9):
        slots = []
        for offset in range(9):
            parts = [cells(v[start + offset]) for v in vectors]
            if any(len(c) != 1 for c in parts):
                fail("UNSUPPORTED_NOTE_SLOT")
            if any(c[0].find("table") for i, c in enumerate(parts) if i != 1):
                fail("UNSUPPORTED_NOTE_SLOT")
            if offset in (0, 2, 6, 8):
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
        if header[0] not in labels:
            fail("UNSUPPORTED_NOTE_OPERATION")
        if not valid_isin(header[1]) or not header[2]:
            fail("INVALID_NOTE_SECURITY")
        kind = labels[header[0]]
        note = {"slot": start + 1, "kind": kind, "isin": header[1], "name": header[2],
                "date": parse_date(text(slots[1][0][0])), "net_currency": "EUR",
                "price_currency": None}
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
        if min(note[k] for k in ("gross", "brokerage", "vat", "debit", "credit")) < 0:
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
    if len({n["date"] for n in groups}) != 1:
        fail("NOTE_MULTIPLE_DATES")
    return {"account_ref": accounts[0], "notes": groups, "slot_count": count}


def match_trade_notes(statement, documents):
    if any(d["account_ref"] != statement["account_ref"] for d in documents):
        fail("NOTE_ACCOUNT_MISMATCH")
    notes = [n for d in documents for n in d["notes"]]
    trades = [e for e in statement["events"] if e["kind"] in ("BUY", "SELL")]
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


def convert_matched_trades(statement, documents, account, mappings):
    """Return private internal records only; identity and API contracts are separate."""
    if not isinstance(account, dict) or not isinstance(mappings, dict):
        fail("INVALID_CONVERSION_CONFIGURATION")
    for key in ("source_account_ref", "account_key", "target_account_id"):
        if not isinstance(account.get(key), str) or not account[key].strip():
            fail("ACCOUNT_CONFIGURATION_MISSING")
    if statement["account_ref"] != account["source_account_ref"]:
        fail("SOURCE_ACCOUNT_MISMATCH")
    if any(e["kind"] not in ("BUY", "SELL") for e in statement["events"]):
        fail("UNSUPPORTED_OPERATION_PERIOD")
    if any(e["date"].strftime("%Y-%m") != statement["period"] for e in statement["events"]):
        fail("OPERATION_OUTSIDE_STATEMENT_MONTH")
    validate_ledger(statement["controls"], statement["events"])
    result = match_trade_notes(statement, documents)
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
    return records


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
    if any(e["kind"] not in ("BUY", "SELL") for e in statement["events"]):
        fail("UNSUPPORTED_OPERATION_PERIOD")
    if any(e["date"].strftime("%Y-%m") != statement["period"] for e in statement["events"]):
        fail("OPERATION_OUTSIDE_STATEMENT_MONTH")
    validate_ledger(statement["controls"], statement["events"])
    occurrences = {}
    events = []
    normalized = []
    for event in statement["events"]:
        facts = ["v1", statement["period"], event["date"].isoformat(), event["kind"],
                 event["label"], *[canonical_decimal(event[k]) for k in
                                   ("quantity", "unit_price", "debit", "credit")]]
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
        notes = [parse_contract_note(decode_document(raw), max_depth) for raw in capture["notes"]]
        activities = convert_matched_trades(statement, notes, account, config["mappings"])
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
    if type(prepared_raw) is not bytes or len(prepared_raw) > max_bytes:
        fail("PREPARATION_INPUT_LIMIT_EXCEEDED")
    result = compute_prepared_sources(config_raw, documents, max_bytes, max_depth)
    observed = parse_keyed_yaml(prepared_raw)
    expected = result["artifact"]
    if yaml.safe_dump(observed, sort_keys=True, allow_unicode=True) != yaml.safe_dump(expected, sort_keys=True, allow_unicode=True):
        fail("PREPARED_SOURCE_CONTENT_CONFLICT")
    return expected


def capture_preparation_sources(config_raw, input_root, max_bytes, max_depth):
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
    config = preparation_configuration(config_raw, max_bytes, max_depth)
    documents, document_paths = capture_preparation_sources(config_raw, input_root, max_bytes, max_depth)
    input_paths = [Path(config_path), *document_paths]
    computed = compute_prepared_sources(config_raw, documents, max_bytes, max_depth)
    artifact = computed["artifact"]
    snapshots = computed["snapshots"]
    account = config["account"]
    state = Path("state")
    output_root = Path("outputs")
    target = hashlib.sha256(account["target_account_id"].encode("utf-8")).hexdigest()
    journal_path = state / ("ledger-" + target + ".yaml")
    binding_path = state / ("binding-" + account["account_key"] + ".yaml")
    artifact_path = output_root / ("prepared-" + account["account_key"] + ".yaml")
    for destination in (journal_path, binding_path, artifact_path):
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
    inactive = unassigned
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


def parse_remote_activity_snapshot(raw):
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


def legacy_duplicate_candidate(activity, row):
    """Bounded similarity for rejection/diagnosis only, never adoption."""
    identity = ("target_account_id", "symbol", "data_source", "kind")
    if row["kind"] not in ("BUY", "SELL") or any(row[k] != activity[k] for k in identity):
        return False
    day = activity["operation_date"]
    source_day = datetime.fromisoformat(day.isoformat() if hasattr(day, "isoformat") else day).date()
    return (row["quantity"] == Decimal(activity["quantity"])
            and row["unit_price"] == Decimal(activity["unit_price"])
            and abs((datetime.fromisoformat(row["operation_date"]).date() - source_day).days) <= 1)


def reconcile_existing_activities(prepared, remote, resolutions):
    """Private offline adoption proposal; never changes remote records or readiness."""
    if not isinstance(prepared, dict) or not isinstance(resolutions, dict):
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
        candidates = [r for r in remote if r["kind"] in ("BUY", "SELL") and r["target_account_id"] == activity["target_account_id"]
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
        if activity.get("kind") not in ("BUY", "SELL") or activity.get("data_source") != "YAHOO" or activity.get("price_currency") != "EUR":
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
    expected = reviewed_wire_rows(review)
    result = {"status": "conflicting", "accepted": {}, "missing": sorted(expected),
              "import_ready": False, "blockers": ["COMPLETE_READBACK_REQUIRED", "UNCERTAIN_WRITE_RECOVERY_UNVERIFIED"]}
    try:
        data = json.loads(raw, parse_float=Decimal, object_pairs_hook=unique_json_object)
        if not isinstance(data, dict) or not isinstance(data.get("activities"), list):
            fail("INVALID_IMPORT_RESPONSE")
        seen_ids = set()
        for row in data["activities"]:
            if not isinstance(row, dict):
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


def verify_chronological_holdings(prepared, raw_snapshot, resolutions, history_evidence):
    """Pure conservative coverage proof; never invent opening acquisitions."""
    build_wire_payload(prepared)
    remote = parse_remote_activity_snapshot(raw_snapshot)
    adoption = reconcile_existing_activities(prepared, remote, resolutions)
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
    symbols = {a["symbol"] for a in prepared.values()}
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
    for marker in adoption["new"]:
        activity = prepared[marker]
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
    return {"snapshot_sha256": snapshot_digest, "coverage_verified": not shortages,
            "shortages": shortages, "ending_quantities": {k: canonical_decimal(v) for k, v in sorted(balances.items())},
            "adoption": adoption, "import_ready": False,
            "blockers": ["DESTINATION_VALIDATION_REQUIRED", "SECURITY_REVIEW_REQUIRED"] + (["CHRONOLOGICAL_HOLDINGS_SHORTFALL"] if shortages else [])}


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
    activities = prepared["activities"]
    if len(activities) * len(remote) > 1000000:
        fail("DIAGNOSIS_COMPARISON_LIMIT_EXCEEDED")
    original = json.loads(captures["snapshot"], parse_float=Decimal, object_pairs_hook=unique_json_object)
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
    if (set(config) != {"schema_version", *roles} or type(config["schema_version"]) is not int
            or config["schema_version"] != 1
            or any(not isinstance(config[k], str) or not config[k].strip() for k in roles)):
        fail("INVALID_REVIEW_CONFIGURATION")
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
    review_capture_configuration(config_raw)
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
    coverage = verify_chronological_holdings(activities, captures["snapshot"], resolutions, history)
    adoption = coverage["adoption"]
    new = {marker: activities[marker] for marker in adoption["new"]}
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
    return {"review_verified": True, "new_activities": len(artifact["adoption"]["new"]),
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
    if declaration["destination_version"] != "3.81.0" or declaration["display_timezone"] not in ("Europe/Paris", "Europe/Zurich"):
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
    return {"new_activities": len(artifact["adoption"]["new"]), "owned_activities": len(artifact["adoption"]["owned"]),
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="Inspect a saved statement without network access")
    inspect.add_argument("path")
    inspect.add_argument("--input-root", required=True)
    inspect.add_argument("--max-bytes", type=int, required=True, help="Explicit local input size budget")
    inspect.add_argument("--max-depth", type=int, required=True, help="Explicit HTML nesting budget")
    inspect.add_argument("--notes", nargs="+", help="Saved daily contract-note HTML files; no URLs")
    prepare = subparsers.add_parser("prepare", help="Prepare a private internal review plan, never an API payload")
    prepare.add_argument("--config", required=True, help="Local keyed YAML inside input root")
    prepare.add_argument("--input-root", required=True)
    prepare.add_argument("--max-bytes", type=int, required=True)
    prepare.add_argument("--max-depth", type=int, required=True)
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
