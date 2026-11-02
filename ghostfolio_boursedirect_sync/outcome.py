"""Fixed failure codes only; adapted from pinned IBKR outcome.py:49."""

FAILURE_CODES = frozenset({
    "invalid_configuration", "invalid_mapping", "paperless_auth_failed",
    "paperless_unreachable", "source_field_missing", "notice_unreadable",
    "amount_check_failed", "activities_unavailable", "unresolved_security",
    "owned_activity_conflict", "possible_duplicate", "invalid_identity",
    "sell_exceeds_holding", "share_count_change", "unknown_operation",
    "future_activity", "import_unconfirmed", "ghostfolio_auth_failed",
    "ttf_attribution_failed",
    "ghostfolio_unreachable", "unhandled_error", "review_unavailable",
})


def failure_summary(codes: set[str]) -> str:
    """Never include exception text, account identifiers, URLs or activity fields."""
    safe = {code if code in FAILURE_CODES else "unhandled_error" for code in codes}
    return "Run failed: " + ", ".join(sorted(safe or {"unhandled_error"})) + "."


# IBKR outcome.py:114,127,134; BD keeps its published failure classifications.
ACTION_INSTRUCTIONS = {
    "review_approval": "Read the exact proposal. Edit only decision to yes or reject between runs. "
                       "The related event stays held until current evidence permits it.",
    "review_evidence": "Restore the missing or conflicting source or destination proof. "
                       "Approval cannot make blocked work eligible. Independent imports can continue.",
}


def notification_summary(codes: set[str]) -> str:
    failures = codes - ACTION_INSTRUCTIONS.keys()
    parts = [failure_summary(failures)] if failures else []
    parts.extend(f"Action required: {key}. {ACTION_INSTRUCTIONS[key]}" for key in sorted(codes)
                 if key in ACTION_INSTRUCTIONS)
    return "\n".join(parts)


def log_operational_result(codes: set[str], code: int) -> None:
    import logging
    actions = codes & ACTION_INSTRUCTIONS.keys()
    result = "failure" if code else "success with user action required" if actions else "success"
    level = logging.ERROR if code else logging.WARNING if actions else logging.INFO
    log = logging.getLogger(__name__)
    log.log(level, "Cycle result: %s", result)
    for action in sorted(actions):
        log.warning("%s: %s", action, ACTION_INSTRUCTIONS[action])


RECONCILIATION_COUNTS = ("already consistent", "automatically corrected", "manually corrected",
                         "automatic work deferred", "manual review required", "rejected association",
                         "blocked", "would correct", "reference migrations", "corrected targets")
