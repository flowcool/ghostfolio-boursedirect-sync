# Design

## Source and coverage

Continue v1. Adopt complete applicable IBKR v3.0.0 core at
`403b4ccf13dcce076c2dc4c08633905c96c1a898`; review later updates separately.
References below use `ghostfolio_ibkr_sync/`.

| Mechanism | Source | Tasks |
| --- | --- | --- |
| ENV, URL, auth, account | `config.py:75,95`; `ghostfolio.py:116,189` | 1.1–1.2 |
| Complete reads, eligibility, profiles | `ghostfolio.py:143,152,208,259` | 1.1–1.2 |
| Identity, mapping, matching | `ghostfolio.py:64,76`; `sync.py:58,546,623,718` | 3.1,4.1,4.3 |
| Selection, holdings, accepted state | `app.py:234,416`; `sync.py:580,960` | 1.1,4.2,6.1 |
| Import, exact confirmation, uncertainty | `ghostfolio.py:405,466` | 6.1 |
| Outcome, notification | `outcome.py:49`; `notify.py:81`; `app.py:441` | 6.1–6.2 |
| Package, image, schedule, CI | `pyproject.toml`; `Dockerfile`; `entrypoint.sh`; `.github/workflows/` | 1.1,6.2 |
| Preview, release | `ibkr.py:127`; `scripts/check_container_runtime.sh`; `scripts/release_image.py` | 6.1; release |

## BD adaptations

Use Paperless originals/search (`docs/api.md:121` at `2b00cf6`),
`pdftotext -layout` and observed notice labels instead of Flex.
Check source accounts before target selection. Require one active target.
Use typed functions/data records, strict mypy/Ruff and at most 2500 application
lines. No shared library/projection. Keep Decimal, EUR and UTC row dates.
Align CI/runtime; pin qualified stable digests.

BD v3 keys retain normalized source rows and multiplicity, excluding metadata.
Preserve current identities during fee correction; never derive identity from
corrected target fees. Index identities across accounts, including inactive rows.
Only eligible target rows support matching/holdings.
Manual matching maximizes exact matches, then minimizes calendar-day distance
through independent minimum-cost groups; stable dates/comments/IDs break ties.
Remove source copies and invalid/future/occupied rows before assignment.
Use chronological selection, SELL first on ties, confirmed holdings only.

Apply the spec's HALF_UP, omitted-brokerage and TTF rules. The fee-only update is the approved BD exception to additive import.
Verify the exact version's update endpoint/payload.
After every write, require complete exact readback; after uncertainty wait five
seconds before GET. Never resend. Failed confirmation stops writes.
Validate APPRISE before service access; invalid values stop without values.
Simulation never notifies. Exclude Flex, cash, conversion and retry-on-symbol.

## Qualification and rollback

Adapt the existing Infra BD adapter. Feed retained PDFs to the installed
candidate without fake Paperless. Use real lab HTTP and permanent lab authority.
Reserve instances, isolate credentials, retain evidence and verify final stop.
Qualify one image in empty/golden scenarios, including correction/idempotence.
Paperless integration remains separate. Publish only on GO.
Absent archive error cases need no new original. Regressions verify logs and
protection; they do not prove real financial observations.
Revert commits for rollback; retain accepted financial state.
