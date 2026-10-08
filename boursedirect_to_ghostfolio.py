"""Offline source-characterization probe; does not import Ghostfolio activities."""

import argparse
import calendar
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import stat
import sys

from bs4 import BeautifulSoup, Comment


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


def read_document(path, input_root, max_bytes):
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect = subparsers.add_parser("inspect", help="Inspect a saved statement without network access")
    inspect.add_argument("path")
    inspect.add_argument("--input-root", required=True)
    inspect.add_argument("--max-bytes", type=int, required=True, help="Explicit local input size budget")
    inspect.add_argument("--max-depth", type=int, required=True, help="Explicit HTML nesting budget")
    inspect.add_argument("--notes", nargs="+", help="Saved daily contract-note HTML files; no URLs")
    args = parser.parse_args(argv)
    try:
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
