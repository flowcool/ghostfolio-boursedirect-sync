# Design

## Source and scope

Adopt the complete applicable IBKR v3.0.0 common core, commit
`f181c957e99836ed511a1fcdce8811beb781bf01`.
The update extracts offline selection, indexing and accepted-state functions;
financial behavior stays unchanged. Review later updates separately.
Use `app`, `config`, `models`, `ghostfolio`, `sync`, `outcome`, `notify`.
Keep typed functions, data records, strict mypy, Ruff and 2 500 application lines.
No shared library or automatic projection.

## Coverage

Paths below are relative to the pinned IBKR checkout. Each row binds the
implemented runtime/release requirements to BD tasks. Preserve applicable tests.

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

Python references above are under `ghostfolio_ibkr_sync/`.

## BD adaptations

- Use `paperless` and `notices` instead of Flex. Check labelled source accounts
  before target selection. Require one exact active target.
- Preserve Decimal, EUR, exact manual quantity/price, net coupons and BD v3
  identity with broker reference or original-PDF hash, content and identical-row rank.
- Preserve chronological sells, SELL first on equal dates; only confirmed buys
  advance real holdings. Keep selection separate from network requests.
- Accept only absent/0/1 DRY_RUN; simulation never notifies. Use UTC row dates;
  omit TZ-forced previews and bearer-expiry reminders under BD notification rules.
- Require full exact readback, including symbol; no retry on uncertain/partial
  import. Log fixed codes/status/document IDs, never response bodies.
- Exclude Flex retries, cash writes, gross dividends, historical diagnostics
  and maintenance conversion. Keep BD legacy matching and target-account scope.

Sources: Paperless `docs/api.md:121–134` at `2b00cf6` (originals/search,
view-only token); `pdftotext -layout`; parser at `legacy-wip`; approved ISIN lookup.

## Qualification and rollback

Reuse infra's existing empty/golden lab and runner protections; adapt its
IBKR-only launch/evidence for BD. Separate lab credentials; pin candidate digest;
stop owned instances after checks. Release work owns RC/stable publication.
Unverified PDF forms wait for real evidence. Revert commits for code rollback;
accepted financial rows remain. Stop on DIVISION; split holdings remain unverified.
