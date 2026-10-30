# Design

## Context

See proposal.md. This is a proposed contract, not approval to change financial
behavior. BD already uses a Python package with separate modules. There is no
line-count budget. Preserve these boundaries and extend them as IBKR does.

## Goals / Non-Goals

Reuse qualified IBKR functions and typed records. Keep the PDF parser, EUR
Decimal arithmetic and existing transport. Add no shared library or framework.

## Decisions

Pin sibling `ghostfolio-ibkr-sync` at
`e78bf215b1c3a4cf32e6e9bd2990ef13d38324c2`. All source paths below are
inside `ghostfolio_ibkr_sync/`.

| Part | Source mechanism | BD target |
| --- | --- | --- |
| Review and bound decisions | `activity_review.py:open_review`, `refresh_proposals`, `approved_proposals` | `activity_review.py`, `models.py` |
| Safe persistence | `safe_path`, `atomic_bytes`, `publish_review` in that file | Same review module |
| Association and limits | `activity_reconciliation.py:date_eligible`, `gross_within_limits`, `group_diagnosis` | `activity_reconciliation.py`, existing `sync.py` |
| Single update and recovery | `activity_review.py:process_review`, `validate_journal`, `recovery_read` | Review module; existing `app.py`, `ghostfolio.py` |
| Required actions | `outcome.py:record_action`, `log_operational_result` | Existing `outcome.py`, `notify.py` |
| Settings | `config.py` review/profile settings | Existing `config.py` |

Use schema-3 review and companion evidence/journal files, owner-only directory
0700 and files 0600, verified explicitly. Reuse lock, atomic replacement,
durable pre-write journal and evidence-bound choices. Preserve full before/after
values. Reuse BD's Decimal payload/readback functions through one whitelisted
update path; retire the separate TTF executor.

Adapt source events to validated PDF rows. Keep canonical UTC midnight;
local-date matching requires explicit TZ. Omit Flex currency conversion,
floating-point residue allowances and corporate-action execution. Legacy
hash inputs can be absent; hold these cases instead of inventing ownership.

## Risks / Trade-offs

Source divergence → preserve applicable sibling modules and typed function
boundaries; adapt only the documented PDF/EUR differences. Review source drift
separately. Do not combine responsibilities to reduce line count.
Permission or evidence drift → refuse writes. Recovery files contain private
financial evidence → mount outside Git and protect their complete directory.

## Migration Plan

Keep profiles off by default. Document the newly required TTF persistence.
Qualify exact candidate in the existing lab. Publication and production remain
separate gates. Before runtime rollback, settle every pending request with exact
readback and retain evidence; the old runtime cannot enforce the new journal.
