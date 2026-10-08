# Bourse Direct to Ghostfolio: manual document import proposal

Date: 2026-10-08. Author: Codex. Independent reviewer: Astra, separate session.

This is a proposal for review, not authorization to implement. Florent requested
this plan and Beads records; source characterization, prototypes, application
code, Git initialization and live writes await the gates below. Beads owns gate
status and execution order: root epic `infra-4g8u`; preparation `.1`, independent
review `.2`, Florent approval `.3`, source feasibility `.4`.

## 1. Decision and supported product boundary

The original CSV/Excel source is still unconfirmed. The supplied statement HTML
does contain dated operations with recoverable column relationships. Contract
note text supplies ISIN and explicit trade costs. These support a **candidate
manual local HTML importer**, not unattended broker synchronization. Complete
historical reconstruction is not yet proven.

Choose monthly statements as the event ledger; contract notes enrich ledger
trades and never independently create a second copy. Require user-saved HTML
files. Do not fetch Bourse Direct URLs, execute page scripts, load remote assets,
automate login, capture TOTP seeds, scrape the authenticated site or use hidden
endpoints. PDF/OCR, CSV synthesis from pasted text, positions snapshots, cron,
web UI and infrastructure deployment are outside the proposed first release.

First implementation target, conditional on G1: trustworthy BUY/SELL import from
covered monthly periods, with explicit ISIN/currency/cost evidence and a report
of every other ledger row. Dividends and standalone fees enter the target only
after representative source evidence and mapping tests. Deposits/withdrawals
are cash-reconciliation records, not fabricated BUY/SELL activities. Corporate
actions, reversals, securities transfers and unknown labels block the affected
account/period until resolved or explicitly handled outside this importer.

A partial trade importer must be labelled as such. It cannot claim full history,
complete performance or autonomous cash synchronization. G1 requires Florent to
accept its actual coverage or choose shelving; no silent scope reduction.

## 2. Evidence, authority and prerequisites

| Source | Observed fact | Limit / authority |
|---|---|---|
| `FINDINGS.md` sections 7–10 | Client history has dated trades, coupons and corporate actions; no structured export found in inspected views | Browser-agent observations relayed by Florent; not exhaustive |
| Supplied monthly HTML | Windows-1252 declaration; four parallel nested column tables; 13 aligned rows in one example; opening/closing balances and three trades | Source inspected directly; no saved byte-level file yet |
| Supplied buy contract-note text | Date, ISIN, quantity, price, gross, courtage, VAT, net EUR debit, execution time/venue | No contract-note HTML; no sell/multiple-operation sample |
| Statement listing | 21 rolling months offered; history page has no range control | Not proof of complete monthly continuity or lifetime coverage |
| Reporting détaillé | Regulatory execution-venue report, not account history | Excluded as an account source |
| Authentication | TOTP used; both SMS and TOTP enabled; three wrong passwords block account | Block duration and OTP limits unknown; importer needs neither |
| IBKR sibling source | Full 1,407-line main file read at `2d2589908a03fa0ceec65487759bdb0f1a272475` | Clean working tree at observation; not a published reusable library |
| Official Ghostfolio source | Tag 3.80.2, commit `806d83f45394bdc70e58d9b178e2ddbdf715de08`, cloned once and inspected locally | Reference version, not a newly verified production version |
| KB indexed lookup | `operations/ghostfolio/index.md` → `api-traps.md` | Relevant guards; actual destination version and behavior require G5 |

No actual account identifier, address, trade values, balance, token or raw private
document belongs in committed examples, plans, Beads or KB. User originals stay
under ignored `inputs/`; confidential reports under `outputs/`; local audit under
`state/`; task artifacts under ignored `tmp/`. These paths are already ignored.
Public/synthetic fixtures must replace personal data and financial values while
preserving row layout, multiplicity, sign, encoding and arithmetic relationships.
Private account references are local configuration, not public examples.

## 3. Numbered gates and stop conditions

| Gate | Required proof | Owner / permission boundary |
|---|---|---|
| G0a: independent review | Astra issues a written verdict; blockers receive owning issues/decisions and are resolved before proceeding | `infra-4g8u.2`; review only |
| G0b: user approval | Florent approves the revised HTML-source feasibility scope and reviewed plan revision | `infra-4g8u.3`; no approval inferred from time or review |
| G1: source viability | Saved monthly and contract-note files establish layout, financial semantics, matching, historical depth and supported coverage | `infra-4g8u.4`; read-only evidence first; approve any coding probe separately |
| G2: parser bench | Approved synthetic fixtures reproduce saved-file structure; altered/missing columns fail; ledger cash controls pass | Future parser issue, created after G1 and implementation approval |
| G3: financial conversion | Every supported type has exact monetary/date/symbol semantics and a discriminating offline test | Future conversion issue |
| G4: identity and adoption | Reimports, overlap, identical trades, mapping changes and existing manual activities have demonstrated outcomes | Future identity/adoption issue |
| G5: isolated API/recovery | Disposable Ghostfolio at the selected version proves response matching, partial outcomes, account isolation and rollback effects | Future isolated-integration issue |
| G6: agreed delivery | All accepted operation types, diagnostics, second-import idempotency and recovery evidence satisfy epic acceptance | Epic owns end-to-end acceptance |
| G7: production authorization | Florent separately approves an exact target, payload and verified recovery; other writers are paused/absent | Separate future operational task; excluded from this planning authorization |

Fail a gate rather than guess missing values, fabricate holdings, ignore unknown
operations, trust a 2xx count, or continue after an uncertain write. Failure of G1
means a scoped recommendation to shelve or narrow, not premature epic closure.

## 4. G1 source characterization checklist

Acquire actual saved HTML without automated broker requests. At minimum inspect:

1. The supplied monthly layout as a real saved byte file and contract-note HTML
   for the observed buy. Check whether Chrome rewrites the declared encoding.
2. A sell and a day containing multiple operations; compare quantity, execution
   date/time, gross, explicit costs and net amount against monthly rows.
3. A dividend month and, where available, a month with cash contribution,
   withdrawal, standalone fee or corporate action. If unavailable, mark the
   corresponding type unsupported rather than synthesize broker semantics.
4. Adjacent monthly statements: date boundary, opening/closing continuity,
   statement revision behavior, month selection, available history depth and
   actual manual download burden. Do not turn 21 months into a retention promise.
5. Price/gross currency, net currency, tax/courtage inclusion, trade vs posting
   date, execution-time timezone, and any missing fields. A German venue does not
   prove a non-EUR execution. No inferred FX rate or fee from an unexplained gap.
6. PEA-PME only if it is in Florent's selected scope. An empty visible window
   does not prove an account has no historical operations.

Record a keyed coverage matrix in `docs/design/source-contract.yaml`, containing
document kinds, observed structural variants, label-to-semantic mappings,
required fields, evidence references and supported/blocked types. Keep real
private sample references in ignored local files; only synthetic/public evidence
may enter that versioned matrix. Beads records decisions and open work.

Stop if contract notes cannot provide unambiguous enrichment, currencies cannot
be established, identical trades cannot be preserved, or manual collection is
unacceptable. Agree an initial history cutoff. An empty Ghostfolio account with
sales of pre-cutoff holdings cannot be bootstrapped from these statements alone.

## 5. Implementation architecture, conditional on approval

Use one functional Python script `boursedirect_to_ghostfolio.py`, no classes or
type hints, following existing project conventions. Runtime candidates are
`requests`, `PyYAML`, and `beautifulsoup4` with the explicit stdlib `html.parser`
backend. No browser, Java, dataframe library, PDF or OCR dependency. Pin actual
direct/transitive versions after the approved parser bench; do not copy future
or unverified version pins merely because the sibling uses them. Retain license
and attribution for copied sibling code; resolve provenance of the scaffold
license before first code commit. Do not change the IBKR sibling or extract a
cross-project library as part of this project.

Proposed functions and interfaces are design contracts, not existing code:

| Function | Contract |
|---|---|
| `read_document(path, account_config)` | Local regular file → decoded HTML + document digest; enforce input-root, size and encoding policy; no network/resource loading |
| `parse_statement(html)` | Statement header + all four direct-row vectors → control rows and ledger records, preserving slots |
| `parse_contract_notes(html)` | Header + per-operation groups → enrichment candidates, never independent import events |
| `validate_ledger(statement, prior_statement)` | Exact Decimal debit/credit arithmetic, signed balances, cumulative-field semantics and cross-month continuity |
| `match_trade_notes(events, notes, resolutions)` | Unique matching or explicit ambiguity; preserve every occurrence and reject conflicting enrichment |
| `normalize_events(records, config)` | Keyed broker-independent event dicts with typed kind, provenance and Decimal strings |
| `build_activities(events, mapping, account_id)` | Strict supported-type mapping to allowlisted Ghostfolio fields; no name/ticker guessing |
| `prepare_review(inputs, config, existing)` | Deterministic review artifact with identities, coverage, blockers and baseline fingerprint |
| `apply_review(review, config)` | Exact approved artifact + fresh baseline → one-event chronological requests with durable outcomes |
| `verify_run(run, existing)` | Fresh remote listing → accepted/missing/conflicting identities; never repeat uncertain POST automatically |

### HTML parsing and money

Find the ledger by normalized headers, not table number, CSS path or logo. Use
direct-child lookup (`find_all(..., recursive=False)`) for its four nested tables
and their rows; `get_text()` only within the intended cells. Handle transparent
font tags, entities and nonbreaking spaces. Preserve blank rows while aligning
columns. Reject multiple candidate ledgers, unequal row vectors, missing control
rows, invalid dates/signs, inconsistent direction or unknown structural variants.
The supplied page has malformed surrounding markup: `html.parser` is a chosen
candidate, not presumed sufficient. If G2 finds that its repaired tree loses
relationships, stop and revise this design before adding another parser backend.

Decode declared Windows-1252 and verified UTF-8 saved variants strictly; never
use replacement characters silently in identifying or financial fields. Normalize
decimal comma/grouping and parse with `Decimal` from strings. Store Decimal values
as canonical decimal strings in YAML. Reconcile EUR displayed controls to cents;
use exact source precision for quantity/price. Characterize rounding at G1/G3,
not an unexplained blanket tolerance. Validate finite nonnegative outgoing price,
quantity and fee; signed quantities remain internal. Quantize net cash only where
the source states cents; do not round unit prices prematurely. Bound file size
and nesting at measured, configurable limits after G2; no invented defaults.

### Numeric JSON boundary (G3/G5)

Exact source Decimal values and canonical review decimal strings remain distinct
from Ghostfolio's numeric JSON fields and server Float storage. Do not send the
journal's strings as quantity, unitPrice or fee. The candidate v1 wire policy
converts only validated finite outgoing values to numeric int/float tokens and
requires each shortest emitted decimal token to round-trip to the same source
Decimal. Reject excessive precision that changes this value; never silently round.
Any explicit source-derived rounding rule must be separately approved at G3.

Serialize the allowlisted payload deterministically once; keep its exact JSON
numeric tokens and digest in the private review artifact and send those reviewed
bytes with the application/json header. Parse response numeric tokens as Decimal
(and reject booleans/nonfinite values) for comparison against the canonical values
of the submitted wire tokens, not against a separately recomputed float or an
unserialized source record. Numerically equal decimal spellings are equivalent;
a changed numeric value is a conflict, not excused by a blanket epsilon.

G3/G5 must characterize supported precision through source-to-wire-to-server-to-
read-back examples, including fractional quantities, high-precision prices,
cent-denominated fees, scientific notation and excessive precision. If the server
changes a reviewed value, halt uncertain and revise/restrict support; do not claim
binary-exact storage or universal decimal preservation. The audited sibling
accepted-value helper therefore needs adaptation, not direct reuse for Decimal
records. These tests stay owned by G3/G5, not by the proposal-correction issue.

Opening/closing balances and totals are never activities. In the supplied example
credit cumulative totals include the opening balance. Model signed opening,
operation debits/credits and signed closing explicitly, including negative-balance
fixtures. A cash deposit is not inferred from an opening balance. Statement
continuity detects omissions, but cannot prove omitted offsetting operations are
absent or validate lifetime positions.

### Event and configuration records

Local `import-config.yaml` is keyed by immutable random account keys, mapping each
source account to an explicit existing Ghostfolio account ID. Validate source
account headers against private expected references; never use a filename as
account authority. The random key is not a credential. Account-number changes
or target-account changes require reviewed migration, not a new implicit identity.
Only nonsecret metadata belongs here. `GHOST_TOKEN` comes exclusively from
`os.environ`, supplied using the established off-git SOPS store and pointer.

Event fields: `id`, `account_key`, `statement_period`, `operation_date`, optional
`execution_time`/`settlement_date`, `kind`, `source_label`, `isin`, `quantity`,
`unit_price`, `price_currency`, `gross`, `net`, `net_currency`, explicit cost/tax
components and keyed document/row provenance. Missing values are absent/unknown,
never zero by default. ISIN enrichment cannot be inferred from a truncated name.

Local keyed YAML stores document digests, semantic statement revisions, resolutions
and run audit evidence. Ghostfolio remains authoritative for remote activities;
the local journal is not a shadow portfolio or proof a timed-out request failed.
No private filenames, document text or account references in routine logs. Emit
safe document aliases, event IDs, counts and error codes; economic detail goes
only to private review artifacts. Artifacts/journal use mode 0600, containing
directories 0700; atomic replacement and local per-target locking are required.

## 6. Matching, identity and duplication

Monthly ledger events are authoritative; notes supply details only. First match
on source account, date, side, quantity and exact net/gross relationships after
confirmed currency semantics. Note ISIN and execution time enrich the match.
Display-name aliases are explicit local mappings, not fuzzy matches. Execution
vs posting differences and aggregate-vs-split-fill matches need reviewed keyed
resolutions if evidence does not establish a unique match. No inherited +/-2-day
or +/-3-day heuristic. Unmatched notes never generate an extra BUY/SELL.

Candidate identity scheme for Astra/G4 to challenge:

- Namespace `BD#v1#<immutable-account-key>#<event-digest>` in `comment`, within
  the server's comment length limit. Account key is included because reference
  Ghostfolio import duplicate detection does not compare `accountId`.
- Digest the normalized statement period, operation date, kind, stable original
  label, signed quantity, stated price and net debit/credit values plus occurrence
  ordinal among financially identical ledger rows. Do not digest filename, target
  Yahoo symbol, newly supplied note time/ISIN/fees or raw HTML file hash.
- Preserve multiplicity: two identical trades produce occurrences 1 and 2, not
  one event. Reordering unique rows or adding blank rows cannot change IDs.
  Changed multiplicity, corrected statements or normalization-version changes
  cause a review-required revision conflict, not new automatic imports.
- Raw digests track file provenance; normalized statement fingerprints distinguish
  re-rendering from financial corrections. Two conflicting versions of one account
  period block preparation until an explicit resolution.
- Month-boundary duplicates and date mismatches are reported; do not merge solely
  on economic equality or assume all financial dates lie in the statement month.

An owned remote comment with different financial values or target account is a
conflict; halt. A mapping change must not reimport owned IDs under a new symbol.
Historical securities renames, corrections and comment edits require reconciliation
and a separate migration decision. A missing journal can be rebuilt from current
remote identities and retained statement evidence; missing ownership comments or
uncertain statement identity cannot be silently guessed.

Existing manual/foreign-importer activities have no trustworthy BD ownership.
Generate candidate matches with full financial evidence and multiplicity, then
require explicit adoption resolutions; no automatic skipping on date/quantity
similarity. Adopted records stay unmodified: keyed resolutions reference their
remote IDs and validated fingerprint. Changes invalidate adoption and block apply.

## 7. Financial mapping and partial-history policy

BUY/SELL: positive Ghostfolio `quantity`, explicit type, validated price currency,
explicit total eligible costs, mapped Yahoo symbol and source trade date. Net
cash direction must agree with side. Never take `abs()` of an inconsistent sign
to manufacture a valid activity. Gross/quantity/price/net relationships must match
the approved source semantics. Unknown FX or tax treatment blocks the event.

DIVIDEND, only after source evidence: prefer explicit gross and withholding;
quantity 1 and unitPrice gross are a candidate when paid-share count is absent.
Do not invent zero withholding for a net-only coupon. A net-dividend-only mode
requires Florent's explicit semantic acceptance, revised scope and tests.

Standalone FEE, only after G3: Ghostfolio has the enum, but API source presence
alone does not establish the correct importer payload/accounting behavior. Validate
noninvestment MANUAL symbol requirements and monetary interpretation in isolation.
Deposits/withdrawals remain ledger controls in v1; the inspected activity enum
has no deposit/withdrawal type. No manufactured trades to represent them.

Date-only activity candidate is the source calendar date at UTC midnight; this
must stand on G3/G5 source/display evidence. The sibling trade parser preserves
supplied clock time and labels it UTC; only date-only inputs/dividends become
midnight, so it is not evidence of a uniform day-based convention. Preserve
source execution time for matching;
do not interpret timezone-free times as UTC. Validate displayed date behavior in
the destination timezone and draft rules before selecting the final contract.
Settlement date is optional evidence, not a replacement for trade date by default.

Require explicit ISIN → Yahoo ticker mappings and verify target security/currency.
No fallback from truncated statement names. For non-EUR or minor-unit prices,
require verified conversion of every monetary field; defer unsupported variants.
Do not carry IBKR-specific inferred market scaling into Bourse Direct by default.

Adoption must state whether holdings before the available history already exist
in the target. Chronological holdings checks use validated existing history plus
accepted new events at the event date, not future acquisitions or today's net
holdings. Missing acquisition/cost basis blocks a historical sale. Never invent
an opening BUY from current positions; operator-provided history is separate
evidence. Any narrowed backfill must disclose its performance limitations.

## 8. Reuse of the IBKR core

Vendor selected audited helper logic at the recorded revision into this single
script, with source attribution and ported discriminating tests. No runtime
import from a mutable sibling checkout; no wholesale file copy or broker-shaped
fake IBKR dictionaries.

| Sibling helper | Reuse boundary |
|---|---|
| `ghost_headers`, HTTP timeouts | Retain token-header construction; add a single validated transport and redacted errors |
| `activity_is_active`, `activity_date_is_current` | Retain draft/exclusion and valid-date guards; verify tag/version assumptions at G5 |
| `ghost_get_existing_orders` | Retain single-list count/redaction/profile checks; replace IBKR/dividend namespaces and indexing with account-scoped BD identities |
| `accepted_import_subset`, `mark_import_uncertain` | Retain exact accepted-row validation, canonical returned symbol and fail-closed uncertainty; persist recovery evidence across runs |
| `ghost_import_activities` | Retain activities-only payload and accepted-outcome discipline; remove automatic symbol drop/retry in v1 |
| `load_mapping`, `resolve_symbol` | Reuse YAML validation approach; require complete explicit mapping and eliminate raw-symbol fallback |
| `ghost_update_cash_balance` | Excluded: a dated statement balance must not overwrite today's cash |
| Flex fetch/parsers, converters, holdings/manual matching, `process_account` | Excluded: broker IDs, sign conventions, accrual semantics and approximate matches are IBKR-specific |

Reconnaissance mentioned `validate_ghost_host`; no such function exists in the
inspected sibling main file. Implement the missing transport validation deliberately,
not as assumed reuse. Existing raw HTTP behavior is not a complete security boundary.

## 9. CLI, review and apply protocol

Proposed CLI (commands below do not exist yet):

```bash
.venv/bin/python boursedirect_to_ghostfolio.py inspect --input-root inputs/ --config import-config.yaml
.venv/bin/python boursedirect_to_ghostfolio.py prepare --input-root inputs/ --config import-config.yaml --output outputs/review.yaml
.venv/bin/python boursedirect_to_ghostfolio.py apply --review outputs/review.yaml --review-digest <approved-sha256>
.venv/bin/python boursedirect_to_ghostfolio.py verify --run <run-id>
.venv/bin/python boursedirect_to_ghostfolio.py rollback-plan --run <run-id> --output outputs/rollback.yaml
```

`inspect` is completely offline. `prepare` parses locally and, when configured,
uses only GET on a selected isolated target to inspect baseline/security/symbol
context. It never POSTs a server dry run. Offline preparation can produce a
diagnostic artifact; an applyable artifact requires a verified destination baseline.
No token is required for offline inspection. Any nonzero blocker prevents apply.

Review artifact contains schema/engine/source-contract versions, config/mapping/
input semantic digests, destination origin and account ID, baseline fingerprint,
coverage, adopted IDs, every event disposition and exact proposed payloads. Hash
the canonical review content; reject changed inputs, mapping, target, baseline
or artifact at apply. Digest approval pins content, not user identity; explicit
write authorization remains a separate operator action.

`apply` alone permits activity POSTs; default behavior never writes. `DRY_RUN=1`
overrides apply and prohibits all mutations. The CLI must not expose the token
in arguments. Validate exact allowed scheme/hostname/port and origin using URL
parsing; reject userinfo, query/fragment and redirects. Construct fixed API paths;
no arbitrary URL from an HTML document, config record or server error. Default
test target is the disposable lab; production requires G7, not a test flag.

Obtain a local lock, re-fetch the complete baseline, and ensure no concurrent
external writer on the target. A local lock cannot enforce other users' behavior;
exclusive target access is an operational prerequisite. Process one account and
one event at a time in approved chronological order. Persist `prepared` intent
before POST; then persist returned created ID and exact acceptance evidence.
Do not treat `dry_run` simulated rows as accepted or journal remote creation.

Use `POST /api/v1/import` with only `{"activities": [activity]}`. Server responses
may skip rows or return a canonical symbol. Validate actual accepted identity,
date, type, quantity, unitPrice, fee, currency, data source and active context.
After each write, read back and compare the expected baseline transition before
the next event. Any short/ambiguous response must be reconciled against the
complete listing, not marked successful because the server returned 2xx.

No automatic POST retry after timeout, network failure, 5xx, uncertain 400 or
malformed success. Maintain a durable account-level uncertainty fence across
processes and runs. Every persisted intent without a proven accepted/rejected
outcome is uncertain, including a crash after intent and before send or outcome
journaling. A new process must check this fence before any account mutation.

Read-only verification can resolve a unique exact owned row positively; multiple
or financially conflicting matches remain blocked. An absent event in a complete
listing never clears the fence or authorizes another POST: the original request
may still be running after its duplicate check and before creation. Ghostfolio
has no unique ownership-comment constraint. Neither a local lock, baseline hash,
manual rerun nor arbitrary elapsed wait proves the old request ended.

Re-POST after absence requires independent evidence that the original request
completed without creation or was cancelled before creation, plus an explicit
reviewed resolution linked to the original intent and a fresh baseline. Define
and verify the actual completion/quiescence evidence procedure at G5/G7. If such
proof cannot be obtained, keep the account blocked; provide diagnostics and an
operator decision path rather than an automatic recovery promise. No new server
component or idempotency guarantee is assumed. A known unresolved-symbol validation
error also stops v1 rather than importing a reduced silently incomplete portfolio.
Partial successful runs are explicit and resumable by owned identity; they are
not server transactions and do not claim atomic financial rollback.

Reference API details verified in source: import requires `createActivity` **and**
`createAccount` permission even for existing accounts; `/activities` has read-scope
guards; import response uses `assetProfile`; import creates activities with
`updateAccountBalance: false`; server duplicate comparison omits `accountId`.
Preflight account ID, currency, permissions, response redaction and active context
in the chosen version before lab apply. No new accounts/platforms/tags/market-data
objects are supplied in v1 payloads. Imports can still create asset profiles and
trigger background market-data gathering; activities-only is not side-effect-free.

## 10. Recovery, rollback and blast radius

Planning changes affect this directory and project-routed Beads only. Before
editing guidance, copies were saved to `tmp/planning-backup-2026-10-08/`. Current
rollback is to copy those exact files back, and move the new plan into the backup
directory. Preserve Beads history; cancel/supersede records with an explanation
instead of deleting them. No broker session or service is affected.

Implementation commits must be atomic after authorization. Restore code through
`git revert <implementation-commit>` once the actual commit is known; reverting
code does not undo remote financial writes. Originals and review artifacts are
never deleted automatically. Recovery state must survive process crashes and a
lost local journal; remote listing and retained source documents are required.

Financial rollback candidate: `rollback-plan` lists only exact created IDs from
the run, ordered in reverse import order. Immediately re-read each ID and verify
account, ownership comment and financial fingerprint before proposing
`DELETE /api/v1/activities/{id}`. Never use bulk DELETE, wildcard/account-wide
deletion, or delete adopted/existing records. Stop if any record has changed.
Actual deletion requires separate explicit Florent authorization.

Important source limit: deleting an activity may also delete its now-unused
asset profile and market data. Thus activity deletion is compensation, not a
complete database restoration. G5 must rehearse on a disposable instance with
pre-existing profile fixtures and newly created profile fixtures, and prove the
chosen restoration procedure. Keep a full isolated database snapshot plus
verified restoration access before the test. Record exact commands/paths/image
digest when the lab is selected; placeholders are not execution-ready rollback.

G7 is blocked until an exact production recovery procedure is verified with its
owner, including cache/background data effects and impact on unrelated users.
Any whole-database restore has a wider blast radius and cannot be the routine
rollback of this importer without explicit maintenance scope. Do not test or
rehearse against production, shared mutable state, or the live Beads database.

## 11. Verification and sequential work packages

Use `.venv/bin/python -m pytest -q` for meaningful offline logic tests once code
exists. Block unexpected network at the test boundary; mock requests. Sanitized
fixtures cover the following properties, rather than copying implementation:

- Exact ledger association through blank/nested rows, malformed variants,
  byte encodings, monetary signs, decimal grouping and negative balances.
- Missing/reordered columns, broken controls and unknown labels stop; totals
  cannot become cash flows and a zero-net securities withdrawal is not cash.
- Note/statement overlap, repeated saves, renamed files, two identical trades,
  changed multiplicity, statement correction, date-boundary ambiguity and lost
  state never silently drop or duplicate an event.
- Mapping changes preserve ownership identity; manual adoption and wrong-account
  input are explicit; two source accounts with identical trades remain distinct.
- Net-only dividends, fee/tax ambiguity, currency/GBp mismatch and corporate
  actions block until supported semantics exist; missing historical buys block
  sales. Future holdings cannot back an earlier historical sale.
- No token/private document leakage, redirect/userinfo host bypass or mutation
  in inspect/prepare/DRY_RUN; review and baseline changes invalidate apply.
- Returned canonical symbol, redaction/count mismatch, 2xx skipped rows, 400,
  partial writes, process crash and timeout have independently checked outcomes.
- G5 stalls the first import after duplicate inspection but before insertion;
  the client times out, GET reports absence, and the client restarts. No second
  POST is sent while the durable fence remains. Cover crash after intent/before
  send and after send/before outcome persistence, exact positive reconciliation,
  duplicate/conflicting evidence, and absent-outcome operator resolution.

After G1 approval, instantiate atomic implementation issues, each roughly one
hour, splitting any larger package before claiming. Proposed sequence:

| Package | Deliverable / owning acceptance |
|---|---|
| I1 | Instruction/input privacy bootstrap, source-contract fixtures and local CLI/config validation |
| I2 | Monthly ledger extraction and cash-control tests: G2 statement ownership |
| I3 | Contract-note extraction and deterministic matching tests: G2 enrichment ownership |
| I4 | Strict mapping, currency/date/money conversion and supported-type tests: G3 |
| I5 | Statement revision, occurrence identity and manual adoption tests: G4 |
| I6 | Private deterministic review artifacts, stale-artifact rejection and offline diagnostics |
| I7 | Audited Ghostfolio read transport and guards, with ported/adapted tests |
| I8 | Single-event apply, durable intent/outcome journal and uncertainty reconciliation |
| I9 | Rollback-plan output and bounded ownership/conflict verification |
| I10 | Disposable API contract/idempotency/recovery tests: G5; split fixture setup from rehearsal |
| I11 | Operator acquisition/review/recovery documentation and security/code review fixes |

Execution dependencies follow the gates and required inputs, not parallel issue
claims. G3/G4 decisions feed apply; do not start integration while identity is
unresolved. The epic alone owns G6 end-to-end coverage, zero-new-record second
import and recovery evidence; child issues own their listed component acceptance.
No estimate claims a complete prototype fits one hour; reassess/split after review.
No implementation issues are created prematurely while these designs are pending.

The isolated acceptance run uses a dedicated Ghostfolio/database/Redis setup,
lab-only credentials and no mounted production volumes. Pin the tested server
version and image digest; fixture accounts/data are synthetic. Do not inherit
the sibling's production `DRY_RUN` recipe: live/shared-state testing is prohibited
by the global agreement. Container packaging is optional after local CLI acceptance;
supercronic and deployment are not needed for manual-file ingestion.

## 12. Astra cold-review handoff

Read this plan, `FINDINGS.md`, `CLAUDE.md`, `.claude/rules/security.md`,
`.claude/rules/python-conventions.md`, global plan-quality rules and the KB
Ghostfolio index. Read the sibling core at the recorded revision; challenge
reuse against source, not the sibling's potentially stale narrative docs.
The temporary official-source checkout is optional; use the pinned source URLs
below if unavailable. Do not inspect private raw documents from other sessions.

Review only before any implementation. Save an English review report to
`docs/reviews/2026-10-08-manual-document-import-astra.md`, link it in
`infra-4g8u.2`, and state approve/revise/reject with numbered severity, evidence,
impact and required decision/test for every finding. Use Beads for actionable
findings, linked `discovered-from` to the review issue. Do not close the review
gate with unresolved blocking acceptance or infer Florent approval.

Priority questions: can occurrence identity survive the observed source variants;
can contract notes uniquely enrich without double counting; is the supported
coverage genuinely useful given download/history limits; can partial-history
adoption and date semantics be proven; are API side effects/recovery accounted
for; does YAML journal complexity pay for its maintenance; are the packages
appropriately split? Reject guessed tax/currency/fee semantics. Propose a simpler
boundary if it provides the same evidence and recovery guarantees.

## 13. Source references

- Local sibling: `../ghostfolio-ibkr-sync/ibkr_to_ghostfolio.py`, commit
  `2d2589908a03fa0ceec65487759bdb0f1a272475`; full main file read, relevant
  `tests/test_ghostfolio.py` and orchestration cases inspected, not executed.
- [Ghostfolio import controller](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/apps/api/src/app/import/import.controller.ts)
- [Ghostfolio import service](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/apps/api/src/app/import/import.service.ts), especially `import` and `extendActivitiesWithErrors`.
- [Activity DTO](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/libs/common/src/lib/dtos/create-order.dto.ts)
- [Activity controller](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/apps/api/src/app/activities/activities.controller.ts)
- [Activity service](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/apps/api/src/app/activities/activities.service.ts), especially `createActivity` and `deleteActivity`.
- [Data-provider validation](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/apps/api/src/services/data-provider/data-provider.service.ts)
- [Activity enum](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/prisma/schema.prisma)
- [Beautiful Soup documentation](https://www.crummy.com/software/BeautifulSoup/bs4/doc/): explicit parser selection, direct-child searches and text extraction; fetched successfully via ordinary HTTP after browser-tool access failed.
- [Python Decimal documentation](https://docs.python.org/3/library/decimal.html): decimal strings and exact monetary arithmetic; fetched successfully.

Reference sources establish design constraints, not runtime acceptance. No live
Bourse Direct or Ghostfolio request, agent canary or shared mutable test was run.
