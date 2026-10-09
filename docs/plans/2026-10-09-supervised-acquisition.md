# Portable supervised Bourse Direct source acquisition

## Authority and product gap

Baseline: `5a39196efb19cef6249bfaac398e6e4d0924e53a`. Florent resumed
implementation autonomously on 2026-10-09 after asking how final broker collection
would work. This plan extends the [interactive acquisition amendment](../design/online-source-inspection.md).
It delivers an operator-commanded collector, not a recurring login/scraping service.
No order, transfer, broker preference change or Ghostfolio write is authorized.
The offline financial pipeline and actual history/adoption gate stay unchanged.
Astra DESIGN-only approval of this exact plan is required before implementation;
external CodeRabbit/Claude own PR review. Do not spawn PR-review agents.

## Evidence and rejected shortcuts

FINDINGS sections12/13 and private authored exploration establish:
- Fresh Puppeteer-owned context and private CDP pipe work; shared Changedetection
  context, private Komodo services and Bitwarden production session are excluded.
- Login IDs are `bd_auth_login_type_login` / `bd_auth_login_type_password`;
  a unique visible `Se connecter` control belongs to that form.
- Application challenge selection is explicit; six numeric OTP inputs may have
  digit-leading IDs. Element handles/getElementById avoid invalid CSS selectors.
  A visible `distrusted` control requests an untrusted device when present.
- Observed top-level views: `/fr/page/releves`, `/fr/page/avis-operes`,
  `/fr/page/historique-de-compte`. Observed embedded statement view
  `/priv/new/releves.php` contains `select[name=RlvCombo]` with 21 offered months.
  Contract-note view is `/priv/new/avis-operes.php`; calendar controls have exact
  titles `Mois précédent`, `Mois suivant`, `Année précédente`, `Année suivante`.
- Read-only popup documents use `/priv/new/releveCompte.php` and
  `/priv/new/releveOpe.php`. A later day may reuse the same popup. Never infer
  freshness merely from a newly observed page or a matching document path.
- Browser DOM captures must be declared UTF-8, distinguished from original
  Windows-1252 HTTP bytes. Statements and notes share significant blank slots.
- Source completeness remains limited by offered documents. Unknown operations
  still block periods. No CSV export, lifetime history, stable operation IDs or
  all-operation accounting is newly assumed.

New code is authored from these structural observations; do not copy private
exploration wiring. `puppeteer-core` 24.43.1 is compatible with installed Node20
(registry engines >=18, Apache-2.0); pin it plus lockfile. Chromium is a supplied
trusted executable, not downloaded at collection time. A separate JS collector
is justified because the importer remains a Python local-file trust boundary.

## A — durable acquisition boundary (offline first)

Create `collector/acquire.mjs` using functional helpers (no classes/type hints).
Pure helpers validate strict commands, canonical broker URLs, account aliases,
private artifact schemas, bounds, DOM metadata and TOTP; they make no requests.
Private durable data is keyed YAML where feasible; raw browser documents are bytes.
Use the existing Python private-publication/source parser boundary for bundle
qualification; do not duplicate financial conversion in JavaScript.

All filesystem roots are operator-provided, ignored/private, with no symlink in
any ancestor. Create fresh UUID run directories exclusively, directories0700,
files0600. No overwrite of a prior run, config, source, journal or evidence file.
Authentication state follows the actual login principal, independently of portfolio
and capture roots, as specified below. Exclusively create its principal lock before browser work. No automatic
stale-lock removal. Atomic write+fsync+rename+parent fsync for durable records.
Existing state must pass strict bounded schema/type checks before browser startup.

Before the password click, persist `password_uncertain`; before OTP click,
persist `otp_uncertain`. Rejection, timeout, crash, ambiguous transition, unexpected
origin, extra authentication POST, selector ambiguity or journal failure stops.
No automatic login/OTP retry across commands, sessions or process restarts.
Positive challenge may advance password state, exact authenticated navigation may
advance OTP state; arbitrary text or a hidden link does not count as success.
A failed/uncertain retained attempt fences subsequent authentication. Resolution
requires manual source/attempt evidence; no `--force`, TTL clearing or delete-and-retry
helper is supplied. A completed successful session can close normally; a later
operator-started fresh session is a separate deliberate one-attempt acquisition.
If the lock/state cannot be persisted, no authentication request is possible.

Use fixed codes/counts/opaque handles in stdout only. Never output URLs, account
labels, selectors from private pages, document text, browser console/errors, cookies,
headers, screenshots, credential values or exception causes. Full HTML remains
private. Exit0 means requested capture succeeded, not source/import readiness;
invalid/failed session exits1, inspection-only/nonimport-ready reports exit2.

## B — supervised owned browser and credential boundary

CLI is opt-in: `node collector/acquire.mjs --supervised --root <private-root>
--account-key <opaque-uuid> --chromium <trusted-absolute-executable>`.
Read one bounded strict JSON command per line over stdin; execute sequentially,
respond with a fixed public schema, and stop on any invalid command or failure.
Commands contain no secret values and cannot supply arbitrary JS, selectors, URLs,
HTTP methods, paths, filesystem destinations or credential-provider commands.
Supported actions: inspect, login, app-method, otp, navigate known-view, select
observed-account-handle, select observed-month-handle, calendar known-direction,
open observed-document-handle, capture expected-kind/period, close.
Handles bind a specific current page/frame generation and observed role; stale,
reordered, duplicated or cross-role controls refuse before any click. Handle IDs
never encode account labels, URLs or query arguments.

Launch a new Chromium process via Puppeteer pipe and a fresh incognito context;
never attach to an external CDP URL, existing profile or user session. No public
browser endpoint, no screenshots/devtools downloads or persisted profile/cookies.
Keep sandbox enabled by default; do not silently add `--no-sandbox`. A supplied
sandbox-capable runtime is an operator prerequisite. No browser flags/user-data
paths from untrusted site/commands. Disable downloads and service workers where
supported; install interception on every owned page before navigation.

Exact HTTPS origin is `https://www.boursedirect.fr` with no userinfo/fragment,
unexpected ports or cross-origin redirect. Default block cross-origin requests;
extra essential asset origins need separately observed and reviewed evidence.
GET navigation is restricted to observed login/views/frame/document/calendar
controls; permit only exact live DOM-derived links with expected role/path.
No construction of hidden query arguments/endpoints. POST is denied by default;
a one-request authentication permit binds the exact same-origin form action,
method and phase observed before the unique password/OTP click. No global POST
allowance, order paths or preference-save actions. A site using an uncharacterized
XHR auth endpoint fails closed; characterize it separately rather than broadening
permissions on failure. GET resource loading is not evidence of complete egress
isolation; the trusted browser/site runtime may itself make requests. Interception
is an application guard, not an OS network sandbox or hostile-browser defense.

Login consumes `BD_LOGIN` / `BD_PASSWORD` exclusively from process environment.
OTP is generated on demand only after the known application challenge from an
operator-supplied `BD_TOTP_SECRET` environment value (RFC6238 SHA1, 30s, six digits),
or one explicitly timestamped fresh `BD_OTP` environment value. Strictly reject
both modes together, stale codes, malformed secrets and SMS/unknown challenge.
No seed retrieval/export or vault integration is part of the collector. Presence
of app TOTP on Florent's account does not authorize retrieving its seed; actual
infrastructure bridge stays exploration-only. Off-git SOPS plus pointer or an
operator-owned external loader supplies environment; never parse an env-file.
Missing credentials leave inspection/user-assisted authentication possible;
headful user assistance uses the same owned context and still must not mutate
preferences or bypass uncertain-submit fencing. If safe observation of human
submission cannot be established, omit headful assistance in v0 rather than
claiming equivalent fencing. Environment secrets must not be forwarded to the
Chromium child (minimal browser env; no NODE_OPTIONS/proxies or inherited secrets).
Do not claim JS strings can be securely erased; remove references after use.

## C — capture identity, bundle and importer connection

Inspect only structural fixed facts/counts, never public account names or balances.
Account selection is explicit through opaque observed handles. Verify the selected
account/document header against the operator's expected private account evidence;
never accept a path/name/label alone as account binding. Account evidence may be a
private keyed config, bounded and preserved, not a CLI argument or public output.
Capture requested month/day and type only after verifying same-origin owned popup,
new navigation/content generation since the triggering click, expected account,
period, title and four ledger headers. Register before click so reused popup and
new popup work. No freshness proof -> no capture. Validate kind/period/account
again immediately with exact captured bytes before publication. Unsupported or
mismatched documents block, not silently skipped.

Bound command5120 bytes, config/state1MiB, HTML4MiB, controls1000, frames/pages32,
steps1000, operation timeout45s, whole supervised session30min, captures256 and
aggregate source64MiB. These are explicit conservative v0 limits, not broker
limits; exact/one-over behavior must be tested. No silent truncation of inventories
or documents. Bound DOM serialization in browser before transfer to the parent;
metadata/hash/account/date qualification precedes publication. Financial document
validation is delegated to the existing parser, not a regexp account/title alone.

A private manifest records schema, run ID, opaque account key, document role/period,
neutral filename, captured SHA256, acquisition method `browser_dom_utf8`, capture
sequence and completion state. Do not persist cookies/login body/seed or auth
response. Original HTML contains personal data; publication exclusion is mandatory.
DOM serialization charset must say UTF-8. Repeat capture preserves earlier bytes;
no automatic cache-by-month that would hide revisions. Stable importer ledger
rules remain authoritative when source bytes change.

Provide an offline qualification command that consumes a completed private bundle,
checks every digest/role/account/period/byte limit and all statement/note layouts,
then proposes a private prepare configuration using explicitly supplied existing
account/mappings. No invented financial mapping/currency/history/adoption acceptance.
A bundle does not assert complete account history or remove non-trade period blockers.
Existing prepare/review/check-review/default apply preview are then directly usable.
No automatic prepare, import, destination auth/POST or overwrite of existing config.

## Sequential delivery gates and acceptance ownership

1. A: durable core/strict commands/auth fence and pure helpers with synthetic tests.
2. B: driver/secret-minimal owned Chromium protocol. Socket-forbidden mocks test
   lifecycle and every pre-submit refusal; ordinary Python tests never launch a
   browser. Node tests run `node --test collector/tests/*.test.mjs` without network.
3. C: private bundles and importer connection with synthetic realistic iframe,
   month/calendar, reused-popup and duplicate-date documents. Owned offline browser
   integration uses locally supplied synthetic content with outbound networking
   blocked; never a broker canary or shared profile. No production login test.
4. Operator/Docker runbook and CI: fresh non-root sandbox-capable container, pipe,
   no published ports, private bind for outputs/state, `restart: no`, explicit
   supervised run only. No production Bitwarden/Komodo dependency. Container proof
   uses newly owned local resources only; failure does not change live infra.
5. Actual acquisition is a later operational activity with checked credentials and
   exact private account evidence, not implementation acceptance. Missing seed or
   sandbox/network/selector evidence is reported honestly; do not test against the
   real broker to fill gaps. Root epic retains full end-to-end delivery acceptance,
   existing-history adoption and G7 production permission ownership.

Astra must challenge the auth phase/origin/POST permit, restart fences/lock cleanup,
secret forwarding, stale-popup/account/period binding, test isolation, operational
viability and whether any unresolved prerequisite makes this falsely functional.
Only approved gates become atomic sequential Beads issues, each roughly one hour;
no end-to-end criteria copied into component issues.

## Rollback and remaining risk

Close owned pages/context/browser on normal close, EOF, timeout, malformed command,
SIGINT/SIGTERM or failure; never stop a shared browser/container. Keep uncertain
journal and partial source manifest after failure. SIGKILL/host loss may leave an
owned browser/lock; the private run manifest supports manual identity-checked
cleanup, not broad process killing or automatic lock deletion. Close failures are
failures and do not clear fences. Revert scoped versioned changes; retain private
evidence. Git commits/pushes/open PRs are authorized; merging requires actual
external review plus applicable security gates. No live Ghostfolio rollback is
needed because the collector cannot communicate with Ghostfolio.

The broker UI is fragile and may change. A fixture proves behavior under the
observed contract, not current broker compatibility, lifetime history or an
unattended product. The original CSV/manual-import proposal remains historical;
this supervised acquisition amendment does not expand financial coverage.


## Required implementation contract after Astra R1–R5

This section is normative and supersedes ambiguous earlier shorthand.

### R1: principal enrollment and cooperating-process boundary (owner A)

Production auth state is fixed at `~/.local/state/ghostfolio-boursedirect-sync/auth`;
HOME represents one installed OS user (Docker uses a fixed user/HOME with this
exact directory on a separately persistent private volume). No run-root/account-key
or CLI auth-root override exists. Tests inject isolated HOME before process launch.
No independent-host, malicious administrator, changed HOME or deleted-state safety
claim is made. The deployment runbook owns the one-installation/one-state-volume
contract; changing it is a migration, never a retry recovery.

Before any password attempt require an explicit OFFLINE `enroll` action. The
principal is SHA256 of `BD-AUTH-v1\n` plus the canonical login: trim is forbidden,
ASCII login grammar `[A-Za-z0-9._@-]{1,128}`, uppercase for binding (the original
login is submitted). This deliberately prevents case-only cooperating bypass.
Create its immutable enrollment and private principal directory exclusively;
existing enrollment never resets an attempt. A missing enrollment is not silently
recreated during login. Login drift routes to another unenrolled principal and
refuses. A manual enrollment for another actual principal is an explicit distinct
operation; multiple source accounts share the existing same-principal lock/state.
Private records contain principal hash/installation UUID, never login/password.

One exclusive mkdir lock per principal spans session authentication; no stale lock
removal. Journal stores immutable principal binding, schema and keyed attempt UUIDs.
Transitions are `password_uncertain -> password_accepted -> otp_uncertain ->
authenticated -> closed_success`; any rejection/uncertainty is terminal blocked.
A crash after observed success before persistence retains its prior uncertain
state. Browser startup/inventory-only can occur without credential use; login
requires enrolled principal/lock and no unfinished/blocked historical attempt.
No automatic resume of password_accepted from an earlier process. Close failure
retains unfinished state and causes failure. Only closed_success enables a later
separate operator-started attempt. Ordinary commands cannot remove attempts,
change binding, clear blocked state or enroll over an existing principal.

A owns strict records, atomic publication, actual-principal derivation, locking,
transition logic and separate-process restart/root/portfolio contention tests.
No auth request callback occurs unless the prior durable transition completes.

### R2: evaluated request permits and grounded compatibility (A pure, B driver)

A private source-contract input has strict schema1, exact broker origin and keyed
roles. Authentication role paths MUST be supplied from previously observed
private form/network evidence; placeholders/absent roles keep authentication
DISABLED. The plan does not know actual auth endpoints or app-method transport.
A separate source-contract owner must qualify these against real observation
before actual collection; synthetic paths are explicitly invented test data.
No credential retrieval or login is required to implement the disabled boundary.

Request matrix:
- inventory/closed: no auth POST; only explicit initial GET `/fr/login` and
  characterized same-origin static asset paths. Unknown resources fail.
- password_prepared: one exact contract-bound path/method/resourceType and owned
  page+frame epoch; top-level DOM form action must equal that contract. Permit
  must exist durably before click and be consumed durably before dispatch.
- password_accepted/app-method: only the separately characterized choice action;
  GET-only or one dedicated bounded POST as its exact contract says. Unknown
  choice transport refuses. No preference-save path is permitted.
- otp_prepared: one contract-bound request matching owned page/frame epoch, same
  checks/one-use durable permit as password. A distrusted control is permitted
  only within this characterized challenge form and no settings-save request.
- authenticated: GET-only known views/frames/calendar/selected document plus exact
  static assets. No arbitrary page/form/API request or POST.
- blocked/failed/closing: no network except close; all permits revoked locally.

A permit includes phase, attempt UUID, page/frame epoch, exact canonical request
URL/path (private only), method, resourceType, nonce and deadline (max45s); scope
includes the query from actual observed action. Form/query changes invalidate it.
Document auth and XHR auth are different contracts, never interchangeable.
Consume before request.continue; persistence failure aborts request and session.
Reject second request, wrong frame/type/body phase and EVERY POST redirect.
Any auth redirect after the one allowed POST is permitted only as GET to an exact
characterized success/challenge path, at most one redirect, with explicit phase
proof; method-preserving/auth-replay/cross-origin redirects abort.
GET view/document redirects likewise require characterized same-role targets;
unknown redirect causes refusal, not follow-and-validate-afterward.

Authenticated evidence requires absence of password/challenge and unique visible
known account-navigation links on the owned root; challenge success additionally
requires the characterized destination and input/control structure. Both require
private observation ticket/time and durable transition. Piped stdin is NOT proof
of a human's presence: --supervised declares caller-owned external authority for
this one session. There is no timer/restart loop/cron entrypoint. Omit headful
human authentication in v0; it cannot bypass request/journal controls.

B owns mocked driver enforcement tests; A owns matrix/permit semantics tests.
Source-contract operational owner owns actual endpoint/transport compatibility.
A missing contract is an honest disabled capability, not a successful live test.

### R3: target-startup proof before enabling the browser driver (owner B)

Use a browser-level CDP target initialization mechanism: auto-attach targets with
`waitForDebuggerOnStart` BEFORE creating/navigating any controlled page, enable
request-stage Fetch interception before resuming each supported page/frame, and
block unsupported workers/service-workers. A target observer followed by normal
page.setRequestInterception is explicitly INSUFFICIENT. Do not assume Puppeteer's
internal resume ordering is safe: inspect the pinned implementation and prove
ordering with the actual chosen Chromium. If the public API/runtime cannot retain
the pause until this guard is active, B does not complete and no real credentials
or broker navigation may be enabled. This is a proof gate, not a claim that the
mechanism has already been observed.

Prefer precreated instrumented pages for direct observed document targets. A
strict decoder may extract an exact URI literal from characterized popup-link
syntax without evaluating site JavaScript or synthesizing query values; unknown
syntax refuses. Precreated owned target navigation uses that exact observed URL.
If a broker-created/reused popup is supported, ALL targets still need the same
first-request guard. Unexpected targets are rejected while paused, not after
possibly dispatching. Frame navigation requests share the request-stage policy;
a same-origin subframe is not exempt. No arbitrary nested-target or worker gap.

B completion requires the opt-in OS-network-isolated REAL Chromium fixture bench:
forbidden initial popup/frame/method-preserving redirected POST, worker requests
and a second auth POST dispatch zero requests to the simulated target. Test
instrumentation observes request.continue/response counters and local server;
mock tests alone do not satisfy B. Retain exact Chromium/package identities.
No --no-sandbox fallback, shared Puppeteer profile or production broker origin.

### R4: immutable exact capture ticket (owner C)

A single outstanding ticket binds source account reference (private config),
requested document role/date, origin frame epoch, current visible observed link
handle and exact resulting request URL, instrumented target identity and expected
navigation loader ID. Ensure there is no outstanding prior navigation before
arming. Record current commits; arm before the controlled request/click, consume
exactly its request and accept only that request's corresponding document commit
and load event. Reject unrelated/earlier commits, multiple candidate responses,
DOM-only mutation, target switch, wrong date/account/type and a stale handle.
Same-document updates remain unsupported without separately characterized proof.
Identical bytes from a proven fresh load are valid; inequality is not freshness.

Serialize once into bounded UTF-8. Delegate exact captured bytes to role-specific
Python parse_statement/parse_contract_note, check account_ref and requested period;
EVERY note group's operation date must equal the requested day. The parser validates
all slot/financial structures, even when the document ultimately has unsupported
operations. Do not grant import readiness from capture/parser acceptance.

Publication retains `browser_dom_utf8_filtered` evidence: strip scripts, base,
forms/inputs, iframes, navigation links and event attributes from the retained
financial-document DOM; never store hidden auth token fields or token-bearing
links. Record this explicit filtering provenance; it is NOT original HTTP bytes
or source-authenticity proof. Preserve ledger text/table/blank slots and metadata;
if filtering alters parser acceptance, refuse. Source-contract owner must still
inspect actual financial popup shape before calling it compatible. If credential
text appears outside recognizable fields/scripts, account-document acceptance
must refuse; no general guarantee against arbitrary secret-encoded text is made.

C owns all ticket/freshness/date/account/filtered-byte/source-publication tests and
full bundle qualification. Complete manifest is last durable publication after
all files fsync and parser/digest checks; partial manifests refuse qualification.
Strict paths, every digest, no duplicate role/date entries or unreferenced files,
exclusive new output, and all config/source output-path/inode collisions (including
hard links) are checked before output mutation. All errors/child stderr are fixed
codes; Python helper receives a minimal env and no BD/Ghostfolio/Beads secrets.

### R5: isolation, secret timing and criterion ownership

Node unit-test bootstrap replaces net/tls/http/https/fetch/WebSocket connection
entrypoints with failure stubs before imports, and forbids child_process/browser
startup in ordinary tests. Pure helpers and trusted injected fake callbacks only.
Python tests retain their socket forbidden fixtures. Real-browser bench is opt-in
only: newly owned Docker container `--network none`, local loopback synthetic
server/content, isolated temporary HOME/auth/root/profile, no real credential env,
no shared mutable DB/Beads/session or private-source mounts; minimal synthetic env.
Ordinary CI runs only unit tests, never live browser/container acquisition.
The fixture server uses a test-only explicitly injected origin evaluator; public
CLI has no alternate broker-origin flag. Sandbox failure is a bench failure.

BD_OTP is read once from initial process env along with BD_OTP_ISSUED_AT (integer
UTC epoch seconds); require issue<=now, age<=20s and at least5s remaining in its
30s step. No parent-env refresh claim. Near rollover or old code stops BEFORE
OTP permit/submission; do not wait and reuse. BD_TOTP_SECRET (strict Base32,
SHA1/30s/6digits) is optional explicit operator provisioning, never retrieved;
generate only after challenge preflight with >=5s remaining, otherwise refuse
pre-submit. Fixed-clock RFC6238 vectors and malformed-clock/key/mode tests own A.

| Owner | Sole acceptance ownership |
|---|---|
| A durable core | Principal enrollment/lock/attempt/permit records, pure request evaluator, OTP validation, persistence refusal and multi-process fences |
| B browser driver | Owned minimal-env browser lifecycle, first-request/redirect/request matrix enforcement and real isolated startup-order proof |
| C bundle connection | Exact ticket/account/date/parser/filtering/publication/digest/source-manifest and prepare-proposal preservation |
| Source-contract operations | Observed broker auth/choice/document-link/resource compatibility and actual credential availability; no implementation canary |
| Operator/container delivery | Non-root sandbox-capable repeatable runtime, persistent canonical auth root/private outputs and cleanup instructions |
| Pre-merge security review | Exact-head acquisition/network/secret implementation security findings resolved before merge; external PR review stays independent |
| Root epic | Full accepted source-to-review/second-import/recovery delivery and production permission; not copied into components |

Instantiate A/B/C sequentially only after exact amended plan approval. Component
closure needs ALL its owned evidence, not a successor note. If the browser proof
or actual source contract is unavailable, keep that owner open and complete
other independently approved reversible work without claiming an online sync.


## Scoped design disposition and B capability dependency

A and offline C are implementation candidates after exact Astra approval. B browser
integration is HOLD until a separately owned pinned-runtime capability/design
step establishes a supported first-request mechanism. Inspection of
puppeteer-core24.43.1 TargetManager.js shows its automatic resume path issues
Target.setAutoAttach, network setup and Runtime.runIfWaitingForDebugger in
Promise.all after an internal Ready event. A public target-created listener does
not establish the required guard ordering. Do not implement B by assuming the
independent CDP client can prevent that resume. A raw owned CDP-pipe controller
without Puppeteer's automatic TargetManager is one candidate for that capability
step, not an approved implementation or a proven mechanism in this plan.

The capability owner will pin its protocol/runtime, demonstrate startup/request
ordering on OS-network-isolated synthetic content, write the grounded B design,
and obtain its Astra review before reusable B code. This is a design dependency,
not a component left secretly incomplete after closure. No production broker
login or sandbox disablement participates in capability characterization.
A/offline C have no dependency on a browser executable and retain all their own
acceptance obligations; no online acquisition claim follows from their delivery.

Repeat captures preserve every earlier run/byte result. In a single qualification
bundle, duplicate role/date entries are deliberately refused as ambiguous;
there is NO automatic newest-revision selection. An operator can later qualify
one exact completed run or separately review a revision-selection policy.
Public documentation must state this conservative limitation.
