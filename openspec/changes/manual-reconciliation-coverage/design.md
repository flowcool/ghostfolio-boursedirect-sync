# Design

## Context

See [proposal](proposal.md) and [delta](specs/notice-import/spec.md).
BD runtime `e49001c` already implements v2 review. Its completed change was
archived with `openspec archive operator-actions-and-reconciliation --yes`.
That synchronized the released main spec. It did not approve this delta.

## Goals / Non-Goals

Extend existing modules. Keep one review file and one journal. Adopt current
IBKR's qualified sequential correction budget and grouped notification delivery.

## Decisions

References below use IBKR commit
`23cb7624014d95e3604583e04cd2f91c0e9f0596` (fetched `origin/main`), under `ghostfolio_ibkr_sync/`.
The existing BD implementations are the integration points.

| Part | Sibling reference | BD integration |
| --- | --- | --- |
| Discovery/review | `activity_review.py:651,762` | `activity_review.py:candidate_reason,refresh_proposals`; `sync.py` |
| File/evidence | `activity_review.py:290,369` | Existing compact review and private state |
| Apply/recovery | `activity_review.py:1086,1174` | Existing journal, whitelist PUT and exact readback |
| Quantity diagnosis | `activity_reconciliation.py:146` | Existing exact arithmetic; interval quantity report |
| Action alerts | `action_notifications.py:22,54`; `outcome.py:116` | `outcome.py`, `notify.py`, `app.py`; private delivery state beside review state |
| Date rules | `activity_reconciliation.py:37`; `activity-reconciliation` spec | Configured `TZ` local-day comparison; preserve compatible stored instants |

Add fee-only proposals before fee-blind duplicate suppression. Retain whole
comments. Add manual-only coupon discovery at ±31 calendar days in configured `TZ`. The
25-day APAM difference rules out reusing the three-day limit. Uniqueness is
necessary; operator approval confirms the payment. Preserve old/proposed
currency explicitly. SAAB requires activity EUR while its market profile stays
SEK. Qualify that exact API behavior; never edit the profile or infer FX.

Coverage reuses `paperless.py:document_ids,_object_ids`, the notice parser and
current matching evidence. The report-only ENV switch and complete-notice
comparison are approved BD adaptations. No identical sibling mode exists.
Do not reuse the creation count as absence proof. Local logs hold detailed rows;
Apprise sends one redacted grouped summary per run. Group by sorted reason/count
pairs. Notify on first, changed or cleared groups, and unchanged groups after
168 hours since confirmed delivery. Failures notify each run. Keep only the
IBKR-style private delivery state; no second report store. Failed or uncertain
delivery cannot advance that state.

Apply all eligible manual, profile and comment corrections in stable order.
Use fixed D=120 seconds after each confirmed correction before the next PUT.
Exact readback precedes each next PUT. First uncertainty stops all later
financial writes. Restart reads the journal and never resends. Qualify D on
the exact BD candidate in the integrated empty/golden lab acceptance. A new
release raises D when the lab margin no longer passes. D=120 replaces D=28
after the measured 69.230-second chain failed the previous qualification.

For manual notice proposals, compare canonical source and stored dates by
calendar day in configured `TZ`. Keep existing profile date rules.
Use the printed coupon payment day at 00:00 UTC. Preserve a stored instant on
the same local day; do not propose a date change for its intraday difference.

Statements are unavailable to this parser: `notices.py:parse_notice` accepts
notice rows, not statement schemas. Retained statement analysis is external
private evidence. Report interval quantity differences only; absolute positions
remain unverified. Adding a statement parser would be a separate scope.

## Risks / Trade-offs

Partial history or split normalization can resemble a gap. Report unknowns
explicitly. Preserve source and review input paths and permissions.

## Migration Plan

Replay retained before/after captures and existing labs after implementation.
Rollback this spec PR by revert. Runtime rollback must retain journals and settle
pending writes first; it cannot undo financial changes. Align stale guidance
with the approved contract during implementation, before enabling writes.
