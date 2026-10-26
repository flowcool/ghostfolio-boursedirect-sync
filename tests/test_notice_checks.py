"""Notice-check regressions use anonymized text from retained real notices.

BUY uses the retained PDF text. SELL/coupon amount blocks transcribe the
existing note-foreign-sell-anonymized-real.html and note-coupon-anonymized-real.html
fixtures to the field layout observed in the retained PDF corpus. No financial
values are invented for the baseline. Deliberate alterations exercise rejection.
These checks do not claim SELL/coupon dispatch or real-service acceptance.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from ghostfolio_boursedirect_sync import notices

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("change", [
    "unknown-label", "renamed-label", "numeric-suffix", "numeric-prefix",
    "duplicate-field", "non-eur", "missing-currency",
])
def test_unexpected_buy_fields_are_rejected(change):
    text = (FIXTURES / "pdf_buy.txt").read_text()
    if change == "unknown-label":
        text += "\n                        TAXE : 0.01\n"
    elif change == "renamed-label":
        text = text.replace("COURS :", "NOUVEAU COURS :")
    elif change == "numeric-suffix":
        text = text.replace("BRUT : 102.00", "BRUT : 102.00oops")
    elif change == "numeric-prefix":
        text = text.replace("BRUT : 102.00", "BRUT : oops102.00")
    elif change == "duplicate-field":
        text += "\n                        BRUT : 102.00\n"
    elif change == "non-eur":
        text = text.replace("EUR PEA", "USD PEA")
    else:
        text = text.replace("EUR PEA", "PEA")
    code = "notice_unreadable"
    with pytest.raises(RuntimeError, match=f"^{code}$"):
        notices.parse_text(text)


def test_real_sell_amounts_use_absolute_quantity():
    # Retained real SELL text. Identifiers, time and amounts are anonymized.
    fields = notices.checked_amounts(
        "SELL", (FIXTURES / "pdf_sell_amounts.txt").read_text(), Decimal("1123.30"), "EUR"
    )
    assert fields["QUANTITE"] == Decimal("-47")


@pytest.mark.parametrize("old,new", [
    ("BRUT : +1 128,94", "BRUT : +1 128,95"),
    ("COURTAGE : +5,64", "COURTAGE : +5,65"),
    ("TVA : +0,00", "TVA : +0,01"),
])
def test_altered_real_sell_amount_fails(old, new):
    text = (FIXTURES / "pdf_sell_amounts.txt").read_text()
    assert old in text
    with pytest.raises(RuntimeError, match="^amount_check_failed$"):
        notices.checked_amounts("SELL", text.replace(old, new), Decimal("1123.30"), "EUR")


def test_real_coupon_uses_positive_net_credit_without_recomputing_gross():
    # This retained coupon has gross 5.72 and net credit 4.86.
    notices.checked_amounts(
        "DIVIDEND", (FIXTURES / "pdf_coupon_amounts.txt").read_text(), Decimal("4.86"), "EUR"
    )


@pytest.mark.parametrize("credit", ["0", "-4.86"])
def test_coupon_requires_a_positive_credit(credit):
    with pytest.raises(RuntimeError, match="^amount_check_failed$"):
        notices.checked_amounts(
            "DIVIDEND", (FIXTURES / "pdf_coupon_amounts.txt").read_text(), Decimal(credit), "EUR"
        )


@pytest.mark.parametrize("kind,fixture,net", [
    ("BUY", "pdf_buy.txt", "103.00"),
    ("SELL", "pdf_sell_amounts.txt", "1123.30"),
    ("DIVIDEND", "pdf_coupon_amounts.txt", "4.86"),
])
def test_all_amount_types_require_eur(kind, fixture, net):
    text = (FIXTURES / fixture).read_text()
    if kind == "BUY":
        text = text.split("QUANTITE", 1)[1]
        text = "QUANTITE" + text
    with pytest.raises(RuntimeError, match="^amount_check_failed$"):
        notices.checked_amounts(kind, text, Decimal(net), "USD")


def test_buy_equality_does_not_round_under_a_small_decimal_context():
    from decimal import localcontext

    text = (FIXTURES / "pdf_buy.txt").read_text()
    text = text.replace("25.50", "25.50000000000000000000000000001")
    text = text.replace("102.00", "102.00000000000000000000000000004")
    text = text.replace("103.00", "103.00000000000000000000000000004")
    with localcontext() as context:
        context.prec = 6
        notice = notices.parse_text(text)
        assert notice.trades[0].unit_price == Decimal("25.50000000000000000000000000001")
        with pytest.raises(RuntimeError, match="^amount_check_failed$"):
            notices.parse_text(text.replace("103.00000000000000000000000000004", "103.00"))


def test_non_pdf_bytes_are_unreadable():
    with pytest.raises(RuntimeError, match="^notice_unreadable$"):
        notices.extract_text(b"This is not a PDF.")


@pytest.mark.parametrize("kind,old,new,net", [
    ("BUY", "QUANTITE : 4", "QUANTITE : -4", "103.00"),
    ("SELL", "QUANTITE : -47", "QUANTITE : +47", "1123.30"),
])
def test_quantity_sign_must_match_the_operation(kind, old, new, net):
    name = "pdf_buy.txt" if kind == "BUY" else "pdf_sell_amounts.txt"
    text = (FIXTURES / name).read_text().replace(old, new)
    with pytest.raises(RuntimeError, match="^amount_check_failed$"):
        if kind == "BUY":
            notices.parse_text(text)
        else:
            notices.checked_amounts(kind, text, Decimal(net), "EUR")


@pytest.mark.parametrize("old,new", [
    ("QUANTITE : 4", "QUANTITE : 0 4"),
    ("BRUT : 102.00", "BRUT : 10 2.00"),
    ("BRUT : 102.00", "BRUT : 0 102.00"),
    ("103.00", "1 03.00"),
])
def test_malformed_digit_grouping_is_not_silently_removed(old, new):
    text = (FIXTURES / "pdf_buy.txt").read_text().replace(old, new)
    with pytest.raises(RuntimeError, match="^notice_unreadable$"):
        notices.parse_text(text)


def test_unknown_field_without_a_colon_is_unreadable():
    text = (FIXTURES / "pdf_buy.txt").read_text() + "\nTAXE 0.01\n"
    with pytest.raises(RuntimeError, match="^notice_unreadable$"):
        notices.parse_text(text)
