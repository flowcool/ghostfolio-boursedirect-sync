# Design

## Context

See [proposal](proposal.md) and [delta](specs/notice-import/spec.md).
BD runtime `e49001c` already implements v2 review. Its completed change was
archived with `openspec archive operator-actions-and-reconciliation --yes`.
That synchronized the released main spec. It did not approve this delta.

## Goals / Non-Goals

Extend existing modules. Keep one review file, one journal and v2's one-update
budget. Latest IBKR permits more updates; that later policy is not adopted here.

## Decisions

References below use IBKR commit
`e18d8475944078adb5e176a77a8d173b80aa60b6`, under `ghostfolio_ibkr_sync/`.
The existing BD implementations are the integration points.

| Part | Sibling reference | BD integration |
| --- | --- | --- |
| Discovery/review | `activity_review.py:651,762` | `activity_review.py:candidate_reason,refresh_proposals`; `sync.py` |
| File/evidence | `activity_review.py:290,369` | Existing compact review and private state |
| Apply/recovery | `activity_review.py:1086,1175` | Existing journal, whitelist PUT and exact readback |
| Quantity diagnosis | `activity_reconciliation.py:146` | Existing exact arithmetic; interval quantity report |
| Action alerts | `outcome.py:116` | `outcome.py`, `notify.py`, `app.py` |

Add fee-only proposals before fee-blind duplicate suppression. Retain whole
comments. Add manual-only coupon discovery at ±31 UTC calendar days. The
25-day APAM difference rules out reusing the three-day limit. Uniqueness is
necessary; operator approval confirms the payment. Preserve old/proposed
currency explicitly. SAAB requires activity EUR while its market profile stays
SEK. Qualify that exact API behavior; never edit the profile or infer FX.

Coverage reuses `paperless.py:document_ids,_object_ids`, the notice parser and
current matching evidence. The report-only ENV switch and complete-notice
comparison are approved BD adaptations. No identical sibling mode exists.
Do not reuse the creation count as absence proof. Local logs hold detailed rows;
existing Apprise sends only redacted counts/actions. No second report store.

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
