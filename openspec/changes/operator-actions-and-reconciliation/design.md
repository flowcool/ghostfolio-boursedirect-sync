# Design

## Context

See proposal.md. BD already has separate modules. Keep IBKR module boundaries,
typed functions, exact Decimal transport and PDF parsing. No line-count budget,
shared library or framework.

## Decisions

Before code changes, compare delivered IBKR and BD commits, tests and retained
proof. Record requirement, both file/function/line references, evidence,
reuse/adaptation/gap, reason and acceptance command in the owning work item.
Missing evidence or contradictions block affected work.

Pin IBKR behavior at `e78bf215b1c3a4cf32e6e9bd2990ef13d38324c2` and BD at
`76a1d67e124317db2e03fd0ae3a8e41f188a62de`. IBKR main
`9d558189cf5089f90e45cb48862f4c529fad946b` adds guidance only.
Source paths below are under `ghostfolio_ibkr_sync/`.

| Part | Reused source | BD target |
| --- | --- | --- |
| Bound review | `activity_review.py:open_review`, `refresh_proposals`, `approved_proposals` | `activity_review.py`, `models.py` |
| Persistence | Same file: `safe_path`, `atomic_bytes`, `publish_review` | Review module |
| Pairing/limits | `activity_reconciliation.py:date_eligible`, `gross_within_limits`, `group_diagnosis` | `activity_reconciliation.py`, `sync.py` |
| Execution/recovery | `activity_review.py:process_review`, `validate_journal`, `recovery_read` | Review module, `app.py`, `ghostfolio.py` |
| Actions/settings | `outcome.py:record_action`, `log_operational_result`; `config.py` | Existing corresponding modules, `notify.py` |

Use schema-3 review, companion evidence/journal, locks and atomic durable writes.
Verify directory 0700/files 0600 explicitly. Retain complete raw API rows for
before/after preservation, not only BD's reduced activity index. Whitelist PUT
fields; keep Decimal encoding and exact full-field readback. Retire separate TTF
execution. Add explicit `ttf` selection/journal authority, including exact unowned
BUYs without `yes`; preserve their complete comment byte-for-byte.

Adapt `process_review`: absent TZ must not force preview or disable recovery
under profile off. Adapt `date_eligible`: PDF printed date is already a calendar
date; convert only destination instants to TZ. Write canonical midnight UTC.
Keep unchanged legacy/unowned duplicates in both modes; do not manufacture an
unresolvable migration action. Migration needs reproducible ownership.

Pass existing security holds to review selection. Validate notes with the
sibling identity reader. Omit Flex FX/residue and corporate-action execution.

## Risks and Migration

Private evidence requires a protected persistent mount. Missing/changed recovery
evidence stops writes. Qualify the exact candidate digest in existing labs,
including the one-update execution policy. Retain containers and proof.
Publication/production keep separate gates. Settle pending requests and retain
evidence before rollback: the old runtime cannot enforce the new journal.
