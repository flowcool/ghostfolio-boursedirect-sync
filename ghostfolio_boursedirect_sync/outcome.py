"""Fixed failure codes only; adapted from pinned IBKR outcome.py:49."""

import re

FAILURE_CODES = frozenset({
    "invalid_configuration", "invalid_mapping", "paperless_auth_failed",
    "paperless_unreachable", "source_field_missing", "notice_unreadable",
    "amount_check_failed", "activities_unavailable", "unresolved_security",
    "owned_activity_conflict", "possible_duplicate", "invalid_identity",
    "sell_exceeds_holding", "share_count_change", "unknown_operation",
    "future_activity", "import_unconfirmed", "ghostfolio_auth_failed",
    "ttf_attribution_failed", "notice_source_unavailable",
    "ghostfolio_unreachable", "unhandled_error", "review_unavailable",
})


# IBKR f9a2b11 notify.redacted_source_failure: diagnostic boundary.
# BD deliberately permits only fixed code/field/HTTP classes, never free text.
FAILURE_CONTEXT = frozenset({
    "CRON", "LOG_LEVEL", "IMPORT_CREATE_FROM", "NOTICE_COVERAGE", "DRY_RUN",
    "GHOST_TOKEN or GHOST_ACCESS_TOKEN", "Ghostfolio token", "BD_ACCOUNT_REF",
    "PAPERLESS_DONE_TAG", "ACTIVITY_RECONCILIATION", "ACTIVITY_REVIEW_FILE", "TZ",
    "NOTICE_DIR", "NOTICE_WAIVER_FILE", "PAPERLESS_URL", "PAPERLESS_TOKEN",
    "GHOST_HOST", "GHOST_ACCOUNT_NAME", "APPRISE_URLS", "APPRISE_TIMEOUT",
    "Ghostfolio authentication", "Ghostfolio accounts", "correction in simulation",
})


def redacted_failure(exc: Exception) -> str:
    """Keep a fixed failure class and allowlisted context, without exception text."""
    if not isinstance(exc, RuntimeError):
        return "unhandled_error"
    code, _, context = str(exc).partition(" ")
    if code not in FAILURE_CODES:
        return "unhandled_error"
    if (code == "invalid_configuration" and context in FAILURE_CONTEXT
            or re.fullmatch(r"HTTP [1-5][0-9]{2}", context)):
        return f"{code} {context}"
    return code


def failure_summary(codes: set[str]) -> str:
    """Never include exception text, account identifiers, URLs or activity fields."""
    safe = {code if code in FAILURE_CODES else "unhandled_error" for code in codes}
    return "Run failed: " + ", ".join(sorted(safe or {"unhandled_error"})) + "."


# IBKR outcome.py:114,127,134; BD keeps its published failure classifications.
ACTION_INSTRUCTIONS = {
    "coverage_gap": "Compare the missing notice rows with Ghostfolio. Use normal guarded import only after resolving the evidence.",
    "position_mismatch": "Compare notice and destination movements for the reported interval. Resolve the unexplained quantity difference.",
    "coverage_unverifiable": "Inspect the named missing or conflicting evidence. Restore that proof before checking the affected interval.",
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


# IBKR v4.3.4 outcome.py:149-163. BD has one target and does not manage cash.
def log_account_evidence(*, simulated: bool | None, accepted: int | None,
                         duplicates: int | None, held: int | None,
                         reconciliation: dict[str, int]) -> None:
    """Report observed counts only; keep unavailable evidence distinct from zero."""
    import logging

    log = logging.getLogger(__name__)
    log.info("Account evidence: %s=%s; duplicates=%s; other held events=%s; "
             "deferred automatic work=%s; cash=not managed",
             "imports" if accepted is None else "simulated proposals" if simulated else "accepted imports",
             accepted if accepted is not None else "unavailable",
             duplicates if duplicates is not None else "unavailable",
             held if held is not None else "unavailable",
             reconciliation.get("automatic work deferred", "unavailable"))
    log.info("Reconciliation result: %s", "; ".join(
        f"{name}={reconciliation.get(name, 0)}" for name in RECONCILIATION_COUNTS
    ) + "; decision counts can overlap" if reconciliation else "unavailable")
