# Daily saved-input preview

`daily-preview` recomputes an account's approved 90-day window from original saved
statements, notes and a complete saved Ghostfolio snapshot, retaining unresolved
exceptions and source coverage in private keyed YAML.

```sh
python boursedirect_to_ghostfolio.py daily-preview \
  --config inputs/daily.yaml --input-root inputs --as-of 2026-10-12 \
  --max-bytes 2000000 --max-depth 256
```

The configuration is the same schema as `reconcile-coupons`: `schema_version: 1`,
`account`, `mappings`, keyed `documents` and `snapshot`. Each document entry names
one monthly statement and its nonempty list of saved daily notes. Paths resolve
inside the explicit input root. Account and mapping rules reuse preparation and
coupon reconciliation. No assets are fetched. The command returns exit 2 for a
completed preview, including blocked previews; exit 1 indicates refusal. Standard
output contains counts and fixed codes only. Scheduling this saved-input command
does not activate unattended broker authentication or financial application.

Instead of `documents` and `current_period`, the configuration can name completed
collector directories. Keep `schema_version`, `account`, `mappings` and `snapshot`,
and add these fields:

```yaml
acquisition_runs:
  first: source-observations/qualification-example-a
  second: source-observations/qualification-example-b
index_encoding: observed_cp1252_declared_utf8
```

The command reads each `qualification.yaml` and its numbered `document-N.yaml`
receipts, then discovers account-bound monthly statements, daily notes and the
current calendar. There is no per-document list to maintain. Runs must confirm
verified accounts, completed logout and browser exit. Receipt hashes, account IDs,
wrapper, document names and observed URLs are checked against original saved
bodies. Identical captures for a role and period/day are deduplicated; different
bodies for that identity refuse before any journal replacement. Closed notes
without a statement and a missing current calendar also refuse. Historic calendars
are distinguished by their observed month navigation and URL parameters. A closed
note's calendar day can differ from its financial dates within the same month;
these differences are reported, and parsed financial dates remain unchanged.
Cross-month disagreement refuses. Current notes retain their existing exact-day
check.

The same captured bytes are used for discovery and analysis, with no second body
read. All read receipts and bodies participate in publication collision guards.
The report records run receipt hashes and capture counts. At most 16 runs and 256
capture receipts are inspected, within the aggregate 64 MiB limit. Authentication
captures and other accounts' bodies are not read. These private receipts describe
completed saved sessions; they do not establish today's acquisition cutoff.
Existing financial refusal, currency and corporate-action boundaries still apply.

The broker calendar day defines an inclusive 90-day window. `--as-of` supplies an
explicit replay day; omitting it selects today in `Europe/Paris`. This local clock
does not establish source acquisition freshness or financial date semantics. All supplied
closed periods are validated before window selection; out-of-window sources can
provide catch-up evidence. Future/current monthly statements are refused. The
report exposes `window_source_events` separately from whole-period reconciliation.
Unknown financial operations still block their period; coupon matching does not
qualify mixed trade/coupon/corporate-action periods.

An optional `current_period` adds saved current-month inventory and note
observations alongside the closed statements:

```yaml
current_period:
  period: '2026-10'
  index: saved/index.html
  index_metadata: saved/index.yaml
  index_encoding: observed_cp1252_declared_utf8
  notes:
    '2026-10-02':
      document: saved/note.html
      metadata: saved/note.yaml
```

The metadata references the collector's original per-document receipts. Each
receipt must bind the exact file hash, role, broker account ID, wrapper and saved
URL. The calendar's four navigation calls, displayed month/year and selected
account slot must agree. Every offered daily link must have exactly one retained
note, with the same captured URL/account and source day. Extra or missing notes,
duplicate days, foreign origins and future days refuse without replacing state.
An explicit no-operation calendar may have an empty `notes` mapping; that is an
inventory observation, not proof of empty history or a through-day cutoff.

The calendar uses `index_encoding: declared` for normal strict decoding. The
separately characterized `observed_cp1252_declared_utf8` profile requires a UTF-8
declaration, bytes that fail strict UTF-8, no BOM/NUL and strict cp1252 decoding.
It applies only to this nonfinancial index. Financial notes still use the unchanged
strict declared-encoding reader; original index and note bytes remain untouched.

`current_period_observations` exposes the inventory, byte hashes, parsed source
fields and conservative nearby destination candidates. A missing-ISIN note retains
its refusal and is not converted. Source execution-price currency remains unknown;
target-profile currency never fills it. Candidates retain original timestamps,
fee differences and context flags; none is classified as certain, new or adopted.
This path does not manufacture a monthly ledger, cash controls, holding movements,
executable payload or through-day verification and never advances closed coverage.
Each note's refusal or closed-statement dependency remains in the existing private
exception journal when inputs disappear or age out. A parsed note's closed-source
dependency can resolve only when a later fully matched closed statement includes
the exact retained note hash; destination and application gates remain separate.

### Standalone custody-fee boundary

Daily preview recognizes only the observed standalone three-slot custody-note
shape: one booking day, `DROITS DE GARDE`, an empty security slot, a
`CONSERV ETG YYYYTn` reference (year and quarter), and a strictly
positive debit with empty credit and blank surrounding slots. Exact ledger
headers establish EUR. The report retains `custody_fee_observation` with no ISIN,
no financial conversion and nearby account-bound FEE candidates marked uncertain.
The original parser refusal remains unresolved; recognition does not enable
financial preparation or clear monthly controls.

Standalone custody debits remain unsupported importer inputs. An owned disposable
Ghostfolio 3.83.0 qualification establishes a native representation for a separately
reviewed fee: `type: FEE`, `dataSource: MANUAL`, a stable category UUID as `symbol`,
`quantity: 1`, `unitPrice: 0` and the exact positive source cash debit as `fee`.
The category UUID identifies the fee category, not a security or an inferred ISIN.
Currency and booking day need their own source evidence. Midnight UTC is a wire
representation of a reviewed booking day, not evidence of the source execution time.

The qualified native import preserves the explicit account, MANUAL profile, date,
currency and fee on readback. Replaying identical bytes creates zero new activities;
account balances remain unchanged and owned activity deletion restores the empty
lab. A free-text description as an explicit MANUAL symbol is rejected. These
observations qualify destination behavior, not automatic source conversion,
current-period completeness or production application.

Native duplicate detection can suppress an otherwise identical activity in another
account. Future fee preparation must therefore use an account-bound source marker
and reconcile the exact returned account and stored activity; HTTP success or an
empty created-activity list cannot establish cross-account acceptance. Reuse the
[reviewed-wire and acceptance boundary](offline-wire.md) rather than dispatching
directly from the current-period observation. An unidentified cash debit still
retains its refusal; it must not be classified as a fee just to remove an exception.

An unsupported or malformed daily note records its fixed refusal code as an
unresolved source exception for that period, with the original source digests
retained. It cannot mark source matching complete, clear prior destination
uncertainty, or prevent other valid months from being reviewed. A parsed note
whose account differs from the configured source still refuses the whole command.

Coverage advances only when a saved closed statement passes exact full-period
source matching, either strict trade conversion or an exclusively matched coupon
period. `last_completed_acquisition_period` is the latest such observed period,
not a contiguous-history assertion or an invocation timestamp. Missing or
unqualified months are listed separately from the first required window month
retained by the journal.
Report fields distinguish missing statements from observed periods whose exact
source matching remains unqualified; acquiring a document does not resolve its
financial interpretation. No current-month index absence proves a through-day
cutoff: `current_period_through_day_verified` remains false. If a required gap
falls entirely before the current window month, `resume_requires_catchup` is true
and `DAILY_RESUME_CATCHUP_REQUIRED` blocks resumption. Saved catch-up evidence can
clear the gap; there is no automatic acknowledgement or expiry mechanism.

Strict trades reuse preparation and conservative destination reconciliation.
Source matching and destination certainty are separate. Holdings and financial
application remain unqualified in this preview. Dividends reuse original-source
cash review and global snapshot comparison, with net received cash and broker
booking date. Existing destination activities are never rewritten, adopted or
deleted; absent candidates never authorize creation.

`state/daily-<target-sha256>.yaml` owns observed period fingerprints and keyed
exceptions. `outputs/daily-<account-uuid>.yaml` publishes the current preview.
Existing `state/binding-<account-uuid>.yaml` and preparation ledger bindings are
checked. The existing target preparation lock and account lock prevent concurrent
writers; acquisition or deployment is not controlled by those local locks.
Different account UUIDs cannot reuse a target journal. Binding changes require
explicit migration. Financial statement revisions are refused rather than
silently replacing retained evidence; presentation slots are excluded from the
financial fingerprint, but economic multiplicity and cash controls are retained.

Exceptions remain unresolved when their source disappears or ages out of the
window. Only a fresh matching saved-source/snapshot comparison can resolve an
observed exception. Resolved evidence remains in the journal. Coupon identities
use booking date, ISIN, exact net cash, currency and occurrence; source slots and
file names do not define their durable identity.

All mutable destinations, including lock files, reject input path/inode aliases
before publication. Private directories use 0700; journals, bindings and reports
use 0600 and atomic replacement. Journal publication precedes report publication,
so an interrupted report can be regenerated with the same saved inputs. Neither
file proves a remote write. Input, aggregate, document-count, retained-state and
report-size limits apply. A malformed journal, reversed calendar day, source
account mismatch or occupied lock refuses rather than resetting progress.

## Compose execution

`Dockerfile.daily` packages the same Python 3.13 program and pinned runtime
requirements. `compose.daily.yaml` runs it without a vault session, credentials
or network access. It does not start broker authentication, fetch a destination
snapshot or apply activities. Existing collector Compose remains separately
invoked; this addition delivers the saved-acquisition analysis stage.

Prepare an existing private input tree with an acquisition-directory configuration
and complete saved snapshot, plus a private persistent work directory owned by
UID/GID 1000:

```sh
install -d -m 700 tmp/daily-compose
docker compose -f compose.daily.yaml build preview
DAILY_CONFIG=account/daily.yaml docker compose -f compose.daily.yaml run --rm preview
```

`DAILY_INPUT_DIR` selects the original input tree (default `./inputs`), mounted
read-only at `/inputs`. `DAILY_WORK_DIR` selects the retained private work tree
(default `./tmp/daily-compose`), mounted at `/work`. Neither directory is silently
created by Compose. Its `state/` journals, bindings and locks and `outputs/`
reports survive container removal and repeated scheduled invocations. Use separate
work trees for environments; never mount production runtime state into a lab.
`BOURSEDIRECT_DAILY_IMAGE` optionally selects a built, pinned daily image.
No host environment or credentials are forwarded to the runtime. The container
runs without root, Linux capabilities, network or writable image filesystem.
Do not change the saved document/snapshot inputs while a preview is running.

An infrastructure-owned daily job may invoke the same command; it evaluates
Europe/Paris's current day without editing the config. No scheduler or production
service is installed by this repository change. Historical replay overrides the
command with the same flags plus `--as-of YYYY-MM-DD`. Exit 2 means a completed
preview, including retained blockers; it is not financial readiness. Exit 1 means
refusal. Persist private journals and inspect the fixed counts/codes before
retrying a refused preview; original documents remain read-only.

Rollback: stop local preview writers and revert the scoped runtime change.
Retain original documents, snapshot, binding and journal. If a newly created
journal must be removed from active use, verify its binding and move it to private
recovery storage; do not delete it or reset uncertain history. There is no service
deployment, broker attempt or production financial mutation to roll back.
