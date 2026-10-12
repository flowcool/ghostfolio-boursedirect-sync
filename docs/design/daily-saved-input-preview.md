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
fields and conservative nearby destination candidates. A note without source ISIN
is explicitly skipped and has no destination candidates or financial conversion. Source execution-price currency remains unknown;
target-profile currency never fills it. Candidates retain original timestamps,
fee differences and context flags; none is classified as certain, new or adopted.
This path does not manufacture a monthly ledger, cash controls, holding movements,
executable payload or through-day verification and never advances closed coverage.
Each note's refusal or closed-statement dependency remains in the existing private
exception journal when inputs disappear or age out. A parsed note's closed-source
dependency can resolve only when a later fully matched closed statement includes
the exact retained note hash; destination and application gates remain separate.

### Missing source ISIN policy

Operations without source ISIN are excluded from import candidates, regardless of
label. This includes standalone custody charges and cash coupons without ISIN;
the importer does not manufacture a security, fee category or corporate-action
conversion. A present but invalid ISIN still refuses. Unknown operations with a
valid ISIN retain the existing affected-period refusal.

Closed-period exclusion requires one-to-one matching of the saved note and
statement by account, month, booking day, source label and exact debit/credit.
Missing, duplicate, conflicting or ambiguous matches refuse. Skipped cash remains
in the original monthly balance controls and ledger identity. Exclusion changes
candidate selection, not the source accounting or source-revision protection.
`skipped_source_operations` exposes each excluded closed-period operation with
its source slot, date, label hash, cash and `SOURCE_ISIN_ABSENT` reason.
Ignored current notes retain only slot, date, currency, cash, reason and hash
provenance; their names and auxiliary source text remain in original private inputs.

Current notes without ISIN expose `SKIPPED_NO_ISIN`, the retained source hash and
cash, and empty destination candidates. Their original exception-journal entry
remains retained as `resolved_by_saved_evidence`; disappearance of a file cannot
clear unrelated uncertainty. This observation does not establish monthly
completeness, import readiness or destination acceptance.

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

`destination_diagnosis` explains destination refusals for every fully prepared
source activity, before window selection. It reuses the bounded
[saved-snapshot diagnosis](offline-diagnosis.md): source financial fields,
candidate IDs, differing fields, exact/similar observations and one keyed map of
original timestamps, decimal financial values and eligibility flags. A legacy
time of day remains visible even when the calendar day agrees; a fee or dividend
amount/date difference remains a discrepancy. No timestamp is normalized and
no context flag, adoption decision or exception is cleared by this evidence.
Private free-text comments are excluded. The one-million comparison and
ten-thousand candidate limits apply; a budget refusal preserves existing output.
Unsupported periods still require complete source preparation before entering
this diagnosis; their source and coupon observations remain separately visible.

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

When foreign-sale recognition upgrades a retained period, the old financial hash
must equal the exact previous UNKNOWN projection of those foreign sale rows, and
both statement and complete note hashes must be byte-identical. The new hash and
old hash remain in a resolved private parser-upgrade journal entry. Any changed
source bytes or other fingerprint discrepancy still requires revision review.
This upgrades parser classification, without clearing corporate-action refusals.

Complete supported mixed periods use raw-source preparation for all BUY, SELL and
net-cash DIVIDEND activities before marking source matching complete. Coupon
observations remain separately available for legacy amount/date reconciliation.
The existing `trade_observations` field now contains reconciliation results for
all prepared activity kinds. Destination, holdings, history and application gates
remain unresolved until their own evidence passes; complete source matching does
not grant import readiness. A malformed trade or unsupported corporate action
still prevents complete-period preparation, even when coupon review succeeds.

## Rolling-window candidate bytes

`candidate_export` previews deterministic reviewed wire for unowned, unambiguous
activities from source-complete closed periods. The entire supported prepared
set is reconciled together before selecting the inclusive 90-day source booking
window. Owned markers and certain unique adopted records are excluded; old new
activities are counted as `excluded_outside_window`. A legacy-context refusal or
unresolved automatic multiplicity produces no wire and retains a fixed
`reconciliation_code`. Invalid or unsupported source periods are listed separately.

The preview contains a private `body_utf8` and SHA256, and is explicitly
`daily_candidate_wire_not_apply_authorization` with false readiness. Its subset
can be inspected even while another source period refuses. Original whole-ledger
controls, unresolved exceptions, incomplete history, current-month cutoff and
application gates remain in the enclosing report. No caller may dispatch this
subset merely because bytes exist: it is not a frozen application review and
does not authorize a partial unsupported-period import. The existing source
replay/frozen-review/exact-wire application boundary remains mandatory.

Filtering cannot hide old malformed sources or clear prior uncertainty. A repeat
against identical captures/snapshot/day is byte-identical. This saved-input stage
still performs no broker request, Ghostfolio GET/POST or financial mutation.

For the separately qualified application path, schema3 [frozen review](offline-review-cli.md)
binds the same explicit 90-day clock and recomputes complete source/adoption evidence.
Its holdings projection includes selected new activities only: an excluded, unimported
old buy cannot cover a selected sale. Daily candidate bytes do not replace that report
or its history, current-source and external application gates.
