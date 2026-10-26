"""Fixed failure codes only; adapted from pinned IBKR outcome.py:49."""

FAILURE_CODES = frozenset({
    "invalid_configuration", "invalid_mapping", "paperless_auth_failed",
    "paperless_unreachable", "source_field_missing", "notice_unreadable",
    "amount_check_failed", "activities_unavailable", "unresolved_security",
    "owned_activity_conflict", "possible_duplicate", "invalid_identity",
    "sell_exceeds_holding", "share_count_change", "unknown_operation",
    "future_activity", "import_unconfirmed", "ghostfolio_auth_failed",
    "ghostfolio_unreachable", "unhandled_error",
})


def failure_summary(codes: set[str]) -> str:
    """Never include exception text, account identifiers, URLs or activity fields."""
    safe = {code if code in FAILURE_CODES else "unhandled_error" for code in codes}
    return "Run failed: " + ", ".join(sorted(safe or {"unhandled_error"})) + "."
