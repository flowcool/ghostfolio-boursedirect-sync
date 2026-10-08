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
        value = yaml.safe_load(contents)
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
    if path.is_symlink():
        fail("SYMLINK_PRIVATE_FILE")
    temporary = path.with_name("." + path.name + "." + uuid.uuid4().hex)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_local_plan(config_path, input_root, max_bytes, max_depth):
    config = read_keyed_yaml(config_path, input_root, max_bytes)
    if set(config) != {"schema_version", "account", "mappings", "documents"} or config["schema_version"] != 1:
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
    plans = []
    snapshots = []
    raw_digests = {}
    seen_periods = set()
    for alias, entry in entries.items():
        if not isinstance(alias, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", alias):
            fail("INVALID_DOCUMENT_ALIAS")
        if not isinstance(entry, dict) or set(entry) != {"statement", "notes"}:
            fail("INVALID_DOCUMENT_CONFIGURATION")
        if not isinstance(entry["statement"], str) or not isinstance(entry["notes"], list) or not entry["notes"] or not all(isinstance(n, str) for n in entry["notes"]):
            fail("INVALID_DOCUMENT_CONFIGURATION")
        html, digest = read_document(Path(input_root) / entry["statement"], input_root, max_bytes)
        statement = parse_statement(html, max_depth)
        if statement["period"] in seen_periods:
            fail("DUPLICATE_STATEMENT_PERIOD")
        seen_periods.add(statement["period"])
        notes = []
        note_digests = []
        for path in entry["notes"]:
            note_html, note_digest = read_document(Path(input_root) / path, input_root, max_bytes)
            notes.append(parse_contract_note(note_html, max_depth))
            note_digests.append(note_digest)
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
        raw_digests[alias] = {"statement": digest, "notes": note_digests}
    plans.sort(key=lambda a: (a["operation_date"], a["id"]))
    state = private_directory("state")
    output_root = private_directory("outputs")
    target = hashlib.sha256(account["target_account_id"].encode("utf-8")).hexdigest()
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
        journal_path = state / ("ledger-" + target + ".yaml")
        binding = {k: account[k] for k in ("source_account_ref", "account_key", "target_account_id")}
        binding_path = state / ("binding-" + account["account_key"] + ".yaml")
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
        artifact = {"schema_version": 1, "artifact_kind": "internal_activity_review_not_api_payload",
                    "import_ready": False, "blockers": ["REMOTE_ADOPTION_UNVERIFIED", "ISOLATED_API_CONTRACT_UNVERIFIED"],
                    "account_key": account["account_key"], "target_account_id": account["target_account_id"],
                    "source_digests": raw_digests, "activities": {a["id"]: a for a in plans}}
        # Persist revision guard first. Failed artifact write can be retried safely;
        # neither file is evidence that an external activity was created.
        atomic_private_yaml(binding_path, binding)
        atomic_private_yaml(journal_path, journal)
        atomic_private_yaml(output_root / ("prepared-" + account["account_key"] + ".yaml"), artifact)
        return {"prepared_activities": len(plans), "statement_periods": len(snapshots),
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


def persist_write_transition(state_root, binding, max_bytes, action, review=None,
                             digest=None, raw_snapshot=None, completion_evidence=None):
    """Locked local durability boundary only; no dispatch, response or replay API."""
    validate_write_journal({"schema_version": 1, "binding": binding, "intents": {}})
    root = private_directory(state_root)
    target = hashlib.sha256(binding["target_account_id"].encode("utf-8")).hexdigest()
    # Share preparation's target lock. Future transport must revalidate all gates.
    lock = os.open(root / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    namespace_lock = None
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_WRITE_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("WRITE_TARGET_LOCKED")
        namespace_lock = os.open(root / ("account-" + binding["account_key"] + ".lock"),
                                 os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        if not stat.S_ISREG(os.fstat(namespace_lock).st_mode):
            fail("INVALID_WRITE_LOCK")
        try:
            fcntl.flock(namespace_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("WRITE_ACCOUNT_LOCKED")
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
    finally:
        if namespace_lock is not None:
            os.close(namespace_lock)
        os.close(lock)


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


def review_local_snapshot(config_path, input_root, max_bytes):
    """Private end-to-end offline review; exact bytes, no remote calls or intent."""
    config_raw = read_local_bytes(config_path, input_root, max_bytes)
    config = parse_keyed_yaml(config_raw)
    keys = {"schema_version", "prepared", "snapshot", "resolutions", "history_evidence"}
    if set(config) != keys or type(config["schema_version"]) is not int or config["schema_version"] != 1:
        fail("INVALID_REVIEW_CONFIGURATION")
    captures = {}
    for key in ("prepared", "snapshot", "resolutions", "history_evidence"):
        if not isinstance(config[key], str) or not config[key].strip():
            fail("INVALID_REVIEW_CONFIGURATION")
        captures[key] = read_local_bytes(Path(input_root) / config[key], input_root, max_bytes)
    prepared = parse_keyed_yaml(captures["prepared"])
    expected = {"schema_version", "artifact_kind", "import_ready", "blockers", "account_key", "target_account_id", "source_digests", "activities"}
    if set(prepared) != expected or type(prepared["schema_version"]) is not int or prepared["schema_version"] != 1 or prepared["artifact_kind"] != "internal_activity_review_not_api_payload" or prepared["import_ready"] is not False:
        fail("INVALID_PREPARED_REVIEW_ARTIFACT")
    activities = prepared["activities"]
    build_wire_payload(activities)
    for activity in activities.values():
        if activity["account_key"] != prepared["account_key"] or activity["target_account_id"] != prepared["target_account_id"] or activity.get("import_ready") is not False:
            fail("PREPARED_REVIEW_BINDING_CONFLICT")
    resolutions = parse_keyed_yaml(captures["resolutions"])
    history = parse_keyed_yaml(captures["history_evidence"])
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
    output_root = private_directory("outputs")
    state = private_directory("state")
    target = hashlib.sha256(prepared["target_account_id"].encode("utf-8")).hexdigest()
    lock = os.open(state / ("prepare-" + target + ".lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(lock).st_mode):
            fail("INVALID_REVIEW_LOCK")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail("REVIEW_TARGET_LOCKED")
        atomic_private_yaml(output_root / ("review-" + prepared["account_key"] + ".yaml"), artifact)
    finally:
        os.close(lock)
    return {"new_activities": len(new), "owned_activities": len(adoption["owned"]),
            "adopted_activities": len(adoption["adopted"]), "holdings_shortfalls": len(coverage["shortages"]),
            "import_ready": False, "blockers": artifact["blockers"]}


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
    output_root = private_directory("outputs")
    atomic_private_bytes(output_root / ("ghostfolio-snapshot-" + digest + ".json"), raw)
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
    snapshot = subparsers.add_parser("snapshot", help="Save complete activity JSON with one allowlisted HTTPS GET")
    snapshot.add_argument("--config", required=True)
    snapshot.add_argument("--input-root", required=True)
    snapshot.add_argument("--max-bytes", type=int, required=True)
    snapshot.add_argument("--timeout", type=int, required=True)
    args = parser.parse_args(argv)
    try:
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
