# Design

## Source

Adopt the complete applicable IBKR v3.0.0 common core, commit
`403b4ccf13dcce076c2dc4c08633905c96c1a898`.
Review later updates separately.
Modules: `app`, `config`, `models`, `ghostfolio`, `sync`, `outcome`, `notify`.
Typed functions, data records, strict mypy, Ruff; 2 500 application lines.
No shared library/projection.

## Coverage

References bind pinned IBKR mechanisms to BD tasks. Preserve applicable tests.

| Core | Source | BD task |
| --- | --- | --- |
| ENV, URL, auth, account | `config.py:75,95`, `ghostfolio.py:116,189` | 1.1–1.2 |
| Complete read, eligibility, profiles | `ghostfolio.py:143,152,208,259` | 1.1–1.2 |
| Identity, mapping, manual/coupon match | `ghostfolio.py:64,76`, `sync.py:58,546,718` | 3.1,4.1,4.3 |
| Selection, holdings, accepted state | `app.py:234,416`, `sync.py:580,960` | 1.1,4.2,6.1 |
| Additive import, acceptance, uncertainty | `ghostfolio.py:405,466` | 6.1 |
| Outcome, isolated notification | `outcome.py:49`, `notify.py:81`, `app.py:441` | 6.1–6.2 |
| Package, image, schedule, CI | `pyproject.toml`, `Dockerfile`, `entrypoint.sh`, `.github/workflows/` | 1.1,6.2 |
| Preview evidence, release checks | `ibkr.py:127`, `scripts/check_container_runtime.sh`, `scripts/release_image.py` | 6.1; existing release work |

Python references: `ghostfolio_ibkr_sync/`.

## BD adaptations

- Use `paperless` and `notices` instead of Flex. Check labelled source accounts
  before target selection. Require one active target.
- Keep Decimal, EUR, exact matches and net coupons. BD v3 keys use broker
  reference or sorted normalized rows, then row content and identical-row rank.
  Exclude metadata, holder data and formatting; retain multiplicity.
- Use current net holdings, chronological new rows and SELL first on equal
  dates. Only confirmed imports advance real holdings. Selection stays offline.
- Accept only absent/0/1 DRY_RUN; simulation never notifies. Use UTC row dates;
  omit TZ-forced previews and bearer-expiry reminders under BD notification rules.
- After each POST, confirm through a fresh complete activity GET. On uncertainty,
  wait five seconds before that GET. Require full exact evidence, including symbol.
  Never resend; failed confirmation fences writes. No unresolved-symbol POST retry.
- Index BD identities across visible accounts before eligibility checks. Moved
  identities conflict; inactive identities stay occupied. Manual matches and
  holdings use only the selected account. Exclude Flex, cash and conversion.

Adapters: Paperless originals/search (`docs/api.md:121` at `2b00cf6`),
`pdftotext -layout`, legacy notice labels, approved ISIN lookup.

## Qualification and rollback

Adapt infra's existing empty/golden runner for BD. Isolate credentials; pin digest;
stop owned instances after checks. Build once, qualify empty/golden, publish that
exact image without rebuild. No mandatory RC channel. Publication/production
need GO. Revert commits for rollback; accepted rows remain. Unknown forms wait
for evidence. Stop on DIVISION; splits remain unverified.
