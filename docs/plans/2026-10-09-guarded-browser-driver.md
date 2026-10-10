# Guarded browser driver: design and capability gate

This amends only held B of the supervised acquisition plan. A and offline C remain
unchanged. No broker login, real credentials, shared browser, production traffic,
or Ghostfolio writes participate in implementation qualification. The design
needs scoped Astra approval for a synthetic capability harness only. Reusable B
remains HOLD until real isolated capability proof exists and a subsequent grounded
reusable design receives exact-hash approval. Planning never replaces that proof.

## Current amendment: grounded reusable B design

The final section below is the current reusable B proposal. Earlier sections
retain the exact synthetic-harness design as historical evidence; its approval
was scoped to that experiment. The final section overrides broader OOPIF and
multi-page suggestions for reusable v0. Reusable code requires a new exact-hash
Astra approval; online enablement still requires independent source, runtime,
egress, credential and security gates. No approval is inferred from this text.

## Grounded source and runtime pins

Inspected once locally from upstream:

- [CDP schema commit8033bef](https://github.com/ChromeDevTools/devtools-protocol/blob/8033bef7599713ae32b8777386fcbd82a7e612ed/json/browser_protocol.json),
  SHA256 `d2fa8cc96c877216b2606781361e57522ecac1df3c60dd46d52273a065f49a36`.
- `puppeteer-core@24.43.1` npm archive, integrity
  `sha512-T5ScUMAsmhdNbgDR41AGESYeS6V9MSgetkSnVhhW+gXvzC42VesKCn5ld87gAZDJ6vLHL9GkRvY9WtQWSnwFbw==`.
  `lib/esm/puppeteer/revisions.js` pins Chrome for Testing148.0.7778.97;
  `ChromeLauncher.js` selects `--remote-debugging-pipe` exclusively from a port.
  Puppeteer is inspected reference material, not a runtime dependency/controller.

Candidate runtime is full Chrome for Testing148.0.7778.97 Linux64, Node20,
raw owned CDP pipe. Before the bench, obtain official distribution metadata,
record the downloaded artifact SHA256 and executable identity, and refuse a
version mismatch. Publish exact artifact/container pins in the bench evidence;
no floating browser/image is qualification evidence. The upstream schema is
source-grounding, not proof that every experimental field exists in this browser.
Missing required command/event semantics fails the capability gate.

`Target.setAutoAttach` documents recursive attachment and wait-for-debugger,
`Fetch.enable` documents paused requests until a client continues/fails them,
`Fetch.requestPaused` identifies redirect requests by `redirectedRequestId`.
`Network.requestWillBeSent` links request to loader; `Page.frameNavigated` commits
that loader and `Page.lifecycleEvent` supplies loader-bound load evidence.
`Page.loadEventFired` alone has no loader ID and is insufficient for capture.
No public Puppeteer target observer participates in the proposed ordering.

## Sole-controller startup and bounded transport

Spawn only a new non-root sandbox-capable browser, private new profile and minimal
environment, no extensions, restored session, broker URL, credentials, or debugger
port in argv. Use `--remote-debugging-pipe`, `--no-startup-window`, headless mode,
and background-networking suppression. No `--no-sandbox` or automatic fallback.
Pipe FD3 is client-to-browser and FD4 browser-to-client, NUL-delimited JSON;
The inspected package's `node/PipeTransport.js` sends NUL-delimited JSON and
`BrowserLauncher.createCdpPipeConnection` binds stdio[3] write and stdio[4] read.
The real bench must still confirm framing with the exact executable.
Browser stderr stays private bounded bytes; public errors contain fixed codes only.

A functional transport assigns monotonic IDs and routes flattened session IDs.
Limits: message1MiB, pending1000, targets32, frame bookkeeping1000,
command timeout45s, session30min, startup events1000, queued bytes8MiB and
retained stderr1MiB; count incomplete buffered messages against those budgets. Reject malformed JSON, duplicate replies,
unknown replies/sessions, oversized frames, connection loss and runtime mismatch.
No transport command is retried. Buffer startup events until the bootstrap is
armed; no target resumes while bootstrap or target initialization is pending.

First send `Browser.getVersion`; require exact product/version. Install handlers
before commands. Then await browser-level `Target.setAutoAttach` with
`autoAttach:true`, `waitForDebuggerOnStart:true`, `flatten:true`, explicit filter
excluding browser/tab only (the documented default); await discovery setup.
Reject any pre-existing page/worker/session: `--no-startup-window` compatibility
must be proved by the bench, not assumed. Create only `about:blank` targets after
these acknowledgements. An attach event may precede createTarget's reply; hold
it paused until exact returned target identity is associated with the pending
owned creation. Never infer ownership from URL/title/order alone.

## Guard initialization and request authority

For each accepted owned page attachment, require `waitingForDebugger:true`.
Install that session's event routes, then sequentially await recursive auto-attach,
`Network.enable`, `Network.setBypassServiceWorker:true`, cache disabling,
`Page.enable`, lifecycle-event enabling, install `Fetch.authRequired` routing,
and request-stage `Fetch.enable` for ALL URL/resource patterns with
`handleAuthRequests:true`. Every HTTP auth challenge receives explicit
`Fetch.continueWithAuth` with `authChallengeResponse.response: CancelAuth`,
never Default or ProvideCredentials, followed by fatal fenced stop. Cancellation
failure also stops the owned browser; no credential/default retry is permitted. Only after all acknowledgements and policy state exists
send `Runtime.runIfWaitingForDebugger`. No Promise.all includes the resume.
All initial local-frame requests share this Fetch policy. Serialize policy
decisions per principal: concurrent pauses cannot both consume the one-use permit. New OOPIF attachments
are instrumented in the same sequence before resume only when their parent frame
is already owned and their source role explicitly permits them. Unknown worker,
service/shared worker, prerender, popup or target aborts the entire session while
paused; it is never detached/resumed as a fallback. Already unpaused unexpected
attachment is a failed proof and immediate abort, not a recoverable warning.

For each request-stage pause, require exact known session/frame/epoch. Anything
outside a characterized source-contract role refuses. V0 supports exact source
URLs, methods and resource types only; no wildcard same-origin allowance. Static
assets/navigation/auth destinations must be characterized before online use.
Workers, downloads, websockets, file/data/custom schemes and unknown HTTP auth
challenges are unsupported. No page-side arbitrary evaluate input or user code.
Unexpected request aborts rather than attempting to repair the contract live.

Password/OTP/optional app-method requests consume the durable A permit exactly
once before `Fetch.continueRequest`. Compare the observed request's exact phase,
frame and page epochs, URL, method and resource type with the armed permit.
The driver's one outstanding action supplies the permit nonce; no page request
can choose its own nonce. An auth request with `redirectedRequestId` always fails,
including307/308. GET redirects also fail in v0; later compatibility needs an
explicit observed role-specific amendment. Request/response postData, headers,
cookies and full auth DOM never appear in logs/diagnostics/public artifacts.

If permit persistence/consumption fails, do not continue. Dispatch failure after
consumption leaves uncertainty fenced. Authenticate only on the separately
characterized success DOM/location observation, then persist A transition;
HTTP200 or disappearance of an input alone is not success. Clock/OTP failures
stop before permit and submit. Credentials are read only from the initial environment, kept in memory, and
passed as arguments to fixed driver-owned DOM helpers through this private pipe.
Helpers use only characterized owned-frame inputs and exact observed selectors;
no command accepts arbitrary JavaScript, selectors, URLs or page code. Credential
fill is permitted only after that action's durable uncertain state and permit are
armed, because input handlers can submit immediately. Never log CDP auth messages
or preserve credential DOM. Failure leaves the principal fenced.
No retries, OTP refresh loop, relogin/reset or
manual-browser bypass. Actual endpoint/DOM characterization belongs to the
source-contract owner; absent evidence disables the associated action.

## Fatal stop and pause-preserving teardown

Any policy/transport/timeout/overflow failure first synchronously disables all
new actions, continuations and resume commands and retains durable uncertainty.
Never detach, disable Fetch or intentionally close the pipe while the browser can
still run. Stop the exact browser process group identified at launch (new detached
owned group), wait at most5s, then SIGKILL that exact owned group if needed and
observe exit. The outer fixture controller also owns an exact dedicated container
ID and tears down that container if any descendant could survive or stop evidence
is incomplete. Container stop is bounded10s followed by exact owned-ID kill; no
shared container, name-matched process or process-list discovery is acceptable.
Only after owned-browser/resource exit is observed may intentional pipe closure
occur. Do not report complete cleanup if group/container exit cannot be verified.

Lost pipe/crash follows the same owned-group/resource stop. The disconnected
interval is not protected by CDP alone: the fixture's network-none boundary and
future separately qualified online egress boundary contain it. Bench criteria
include rejection with paused/queued requests, pipe loss, forced stop and zero
forbidden server dispatch during teardown. Production resource ownership/stop
access must be verified by its delivery owner before any online enablement.

## Capture handoff

V0 uses newly precreated guarded pages for exact observed document URLs only.
Broker-created/reused popups are rejected; their general support is deferred.
A strict decoder may accept only characterized exact popup-link syntax; it never
evaluates a site script or constructs query values. A document URL selected from
an owned frame gets a one-outstanding-action ticket before navigation.

The ticket pins private account/role/date, observed opaque link handle, frame
and page epochs, exact URL and owned target. Associate Fetch.networkId with
Network.requestWillBeSent.requestId and nonempty loaderId; reject ambiguity,
redirects, missing IDs or older navigation. Require the same target/frame/loader
at frameNavigated and lifecycle load before serialization. DOM mutation without
this exact navigation chain does not qualify. Internal opaque UUID handles map
native CDP frame/target/loader IDs privately to the offline C schema.

Capture serialization and Python filtering/parsing run once with bounded data and
minimal environment. Any active navigation, wrong account/day/month/role or extra
note date refuses. Publish files and strict complete manifest only after source
acceptance and all fsyncs; retain previous runs. Offline C then creates a new
proposal; it does not authenticate this browser proof from manifest fields alone.
Online capture freshness evidence needs its own runtime tests in the driver owner.

## Isolated capability proof and implementation phases

1. Astra reviews this exact synthetic capability-harness design. Scoped approval
   permits only that bounded experiment; reusable B remains HOLD.
2. Create a separate capability-harness/proof issue owning transport, startup,
   target/frame/worker/redirect, HTTP-auth cancellation and abort-order evidence.
   Its code is synthetic-only, has no broker CLI, source input, real credential
   environment or source-contract loading. Pure/mock checks forbid network/child
   startup; real proof remains separately opt-in. It is not reusable B delivery.
3. Opt-in newly owned Docker fixture, network none, synthetic server on loopback,
   invented origin injected into the test evaluator only. No real broker domain,
   credentials, source mounts, shared DB, Beads, browser/profile or Docker networks.
   Non-root Chrome sandbox must work; failure keeps B incomplete. Do not add
   SYS_ADMIN/privileged mode, host networking or sandbox disablement automatically.
4. Pin built image/executable/artifact digest. Verify ownership labels and exact
   ID before cleanup; containers have no volume/shared network. Record only fixed
   event kinds/counts/runtime identities, keep detailed synthetic evidence private.
5. Prove guard acknowledgements precede resume, then server counters for forbidden
   first popup/frame POST, worker request, redirected307/308 auth replay and second
   auth POST remain zero. Root's one permitted synthetic POST dispatches exactly
   once. Prove no target/request escapes during attach/create races and same-origin
   frames; unexpected-target abort has zero forbidden dispatch. Deliberately
   delay guard setup to make the negative control detect the former ordering gap.
6. Prove concurrent pauses consume at most one permit, HTTP401 challenge has no
   credential/default retry, fatal stop with queued work and pipe-loss teardown
   have zero forbidden dispatch, plus permit-fsync refusal and browser crash/restart fence,
   stale/mismatched request-loader commit/load, repeated identical fresh capture,
   wrong account/day and unsupported operations. C browser-specific evidence has
   explicit owning criteria; offline C closure is not substitute evidence.
7. Only after real evidence passes, write the final grounded reusable B design
   incorporating exact observed startup and teardown behavior and get its new
   exact-hash Astra approval. Reusable B implementation then gets its own issue
   and verification criteria. Failed or incomplete evidence leaves B HOLD.
8. Exact-head security review before merge; external PR review remains independent.
   Operational source contract, actual secret availability and repeatable sandbox
   delivery are further gates before online enablement. Production writes remain
   prohibited by Florent's instruction.

Chrome's browser-process background traffic, DNS, speculative navigation and
non-Fetch protocols cannot be called contained merely by flags. The fixture's
OS-network isolation bounds that risk. Online delivery must supply a dedicated
egress boundary with no alternate route and characterize required resources;
this is separately owned and must be reviewed before any real broker use. Driver
unit/capability completion is not online runtime authorization.

Rollback is a scoped commit revert; retain all principal enrollment/uncertainty
and captured evidence. Stop/clean only newly owned bench resources after exact-ID
and ownership verification. Runtime resources existing before the session are
never changed. If this exact Chrome cannot prove initial request suspension,
keep B held and report the failed mechanism; do not loosen the acceptance gate.

## Final grounded reusable B proposal (2026-10-09)

### Evidence and chosen scope

The integrated synthetic proof has 28 scenarios and discriminating negative
controls. The current-pinned consolidation command is:

```sh
.venv/bin/python scripts/consolidate-cdp-proof.py tmp/cdp-real-proof/integration92-exact
```

It verifies retained receipt/source/runner/evaluator consistency without starting
Chrome or Docker. Read-only `--verify-owned-absence` separately checks current
absence. Private receipts remain private; the author evidence appendix in the
existing Astra report describes observations and their limits. Integrated commit
`d321b7b` contains the reviewed proof, including stop-before-exit regressions.
Receipt hashes establish integrity, not independent source authenticity.

Reuse the proven sole-controller raw NUL-framed pipe and ordered guards, with
Chrome148.0.7778.97 and Node20.19.2 as the qualification baseline. The existing
fixture image is `sha256:11b6dc0eb079e10e625ff8de54af6018100289b51fa500e72196adfca8233df8`;
its seccomp profile SHA256 is
`cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`.
These are test identities, not a published collector image or a portable online
runtime. Future runtime changes need fresh qualification; do not accept a
matching product string as executable provenance.

Reusable v0 uses ONE root page per owned session, with same-origin in-process
frames only. No OOPIF, additional page, broker popup, worker, service/shared
worker or prerender resumes. Target discovery OR a paused attachment can reveal
an unsupported worker; either is fatal. Browser/tab discovery is tolerated only
under the bootstrap's explicit structural filter. Unexpected unpaused attachment
is fatal. Root-target ownership must match createTarget's returned ID, including
an attachment arriving before the reply. Reuse the existing one-root bootstrap;
do not generalize its ownership correlation during this delivery.

Do not support multiple precreated document pages in v0. After authentication,
resolve the exact observed document link in an owned view frame without executing
site script, then navigate the same root to that URL under a capture ticket.
Returning to a source view is a new characterized guarded navigation. If actual
broker behavior requires popup/reused-page/OOPIF support, leave that operation
disabled under source acceptance rather than widening the policy.

### Functional controller and authority boundaries

The first implementation is a callback-only reusable request controller,
without browser launcher, broker CLI, DOM evaluation, credential access or
production contract loading. It accepts trusted injected durable authority,
exact source-role tuples, owned frame/session/epoch bindings, clock, CDP send
and stop callbacks. Every output states online readiness false. The caller cannot
turn a qualification flag into permission. Synthetic fixture controllers remain
separate: no test-only alternate origin or negative-control switch enters a
public broker command.

Controller state owns one current action, bounded seen request IDs, immutable
source tuples, root/session binding and frame epochs. Clone and validate metadata
before asynchronous queuing. Serialize ALL request decisions per principal,
including navigation/assets and auth, with a bounded queue; overflow immediately
fences the session. Recheck the fence after every await and before every outbound
continuation/resume. Reject duplicate request IDs, unknown frame/session/epoch,
missing metadata, changed permit nonce or phase, redirects and unrecognized role.
No caller-supplied arbitrary CDP method, URL or JS is an operator interface.

Read-only requests need exact characterized URL/method/native resource type and
owned-frame role. No wildcard origin/path/static-asset allowance. Such roles are
absent today and disabled; this design does not infer resource compatibility
from successful synthetic navigation. Authentication uses existing
`armPermit`/`consumePermit`: durable uncertainty and permit must precede any
credential fill, permit consumption/fsync must precede continuation, and the
nonce comes only from the outstanding driver action. No permit or continuation
retry. Input-handler submission can arrive during fill and still needs the same
armed permit. Unsupported app-method flow stays disabled rather than guessing
an extra transition in the durable core.

Pass Chrome's observed method and resource type unchanged. The experiment's
JavaScript POST was `XHR`; never normalize `Fetch` to `XHR` or infer the broker's
type from that observation. Refuse EVERY redirected request, including GET and
307/308, before consuming auth authority. All HTTP authentication challenges
receive CancelAuth, never credentials or Default, then fatal stop; the event
route is installed before Fetch enablement. A second simultaneous auth pause
fences immediately; the permitted first request may have dispatched zero or one
time. Success cannot require exactly one in this race: the positive control
separately proves possible dispatch. Consumed authority remains uncertain even
when a local server or later listing sees nothing.

### Startup, fatal stop and interruption recovery

Keep the original bounded transport and sequential acknowledgement-before-resume
sequence, including recursive auto-attach, service-worker bypass/cache disable,
Page/lifecycle setup and all-request Fetch with HTTP-auth interception. Read-only
metadata event routing is distinct from auth payloads: do not retain CDP postData,
headers, cookies, credentials, unfiltered DOM or raw errors in journals or stdout.
Only explicitly selected fixed event kinds/counts/runtime hashes are public.

A fatal fence is synchronous and permanent. It blocks new actions, permit
consumption, continuations and resume, then stops the launch-owned process group,
observes exit and only then intentionally closes the pipe. Ordering must be
`fence -> stop-owned -> owned-exit -> close-pipe`; failed exit proof never closes
intentionally or reports successful cleanup. TERM5s/KILL and outer owned-container
stop10s/KILL remain bounded and use launch-time exact identities only. Pipe loss
uses the same stop sequence, but CDP alone cannot contain the disconnected interval.

Runtime delivery must persist a private keyed YAML allocation intent BEFORE
container creation, then persist/fsync a receipt binding the exact full create ID,
immutable image/runtime identities and independently checked ownership BEFORE
start or any credential transfer. An unresolved allocation intent forbids another
session. Creation/start are distinct operations; no auto-start, restart policy or
credential-bearing create environment. Kill/crash after create but before durable
receipt can leave a stopped orphan: retain the uncertain allocation, block
restart, report fixed cleanup uncertainty, and require separately authorized
operator recovery. A matching name/label or discovered ID is not removal authority.
This design deliberately makes no automatic recovery promise for that window.

With a durable exact-ID receipt, recovery checks the same daemon/resource identity
and contradictory ownership before any exact stop/removal. Incomplete or foreign
ownership refuses mutation; persisted PID alone is insufficient across restart
because of PID reuse. Lost journal, unreachable daemon, host restart and failed
fsync remain blocked until independent evidence resolves them. Do not clear an
auth principal's lock or uncertainty merely because the browser/container is absent.
The delivery owner must prove kill points before create, after create/before
receipt, after receipt/before start and during dispatch, including daemon failure.
The callback-only controller cannot prove or implement this deployment contract.

### Capture and source prerequisites

Use native Fetch.networkId -> Network requestId/nonempty loaderId -> exact frame
commit -> same-loader lifecycle load. Page.loadEventFired or DOMContentLoaded
cannot qualify. Arm ticket before navigate, reject intervening navigation and
bind root/session/frame/epochs both before and after one bounded serialization.
Fresh identical bytes remain valid with distinct observed native loader chains.
Wrong account/month/day/role, missing loader, stale commits and unknown operations
refuse. Use opaque UUIDs for private offline ticket identities, retaining native
bindings privately; never turn an offline manifest assertion into runtime proof.

Existing Python filtering/parser/publication remains authoritative. Preserve
config, source and previous-run path/inode boundaries and validate every note
operation date. The manifest is last after file/parser/digest/fsync checks; no
partial or duplicate role/date run qualifies. The synthetic marker DOM is not a
financial-document adapter and cannot certify actual selectors/account evidence.

Source owner .70 must independently characterize all enabled request roles,
account selectors, authentication observations, exact popup-link decoding and
actual financial-document shape. Existing seven disabled-role observations are
not permission or guessed URLs. Credential delivery .84 remains independent.
Dedicated egress with no alternate route must contain browser-process background,
DNS and non-Fetch traffic before online launch; flags/interception are insufficient.
No real broker request, secret export or financial write is authorized by this
reusable design or its subsequent approval.

### Acceptance ownership and implementation order

The unchanged design owner .69 closes only on pinned protocol/runtime, complete
startup/target/frame/worker/redirect/teardown design, isolated evidence plan and
new exact-hash Astra approval. It owns no inherited online acceptance.

After approval, create one atomic callback-controller owner: exact bounded request
matrix, frame/session/epoch ownership, serialized durable permits, synchronous
fencing, HTTP-auth cancellation and discriminating network/child-forbidden tests.
It must retain disabled readiness and pass full Python/Node suites. Independent
following owners cover runtime allocation/launch/crash recovery and browser/capture
composition, each with synthetic-only real isolated proof for their final code.
Those proofs are not inherited from the earlier harness. Source acceptance,
portable credentials, egress/delivery, exact-head security and external PR review
remain separate gates before an operator-commanded online session.

Rollback is `git revert <scoped-commit>` for design/code; retain auth state,
allocation intent/receipts and captures. No design or local controller rollback
undoes an attempted login. No automatic removal, production migration, image
publication, deployment or Ghostfolio write is part of this issue.

## Proposed native synthetic composition amendment (2026-10-10)

This proposal changes the internal composition design only. It requires a new
independent exact-hash Astra verdict before implementation. The previous approval
of the grounded callback-only controller is retained for its original scope.
No runtime qualification or online permission follows from this amendment.

### Verified gap and chosen seam

The existing controller validates broker-only source/read URLs. The durable core
also enforces that origin when validating source contracts and stored permits.
The old fixture substitutes broker-shaped permit URLs and synthetic handles while
the browser uses a dynamically allocated loopback port. That proves callback and
persistence behavior separately; it cannot qualify their unchanged native
composition. Retain that evidence under its historical scope.

Factor URL/source/permit validation and durable authority operations through one
internal immutable policy instance. Existing public exports retain the fixed
broker policy, signatures, principal hash, auth directory and schema-version-1
journals. They accept no policy, origin, namespace or state-root argument. No
operator command, environment flag or source file can select a synthetic policy.

Provide a development-only factory to bind the same authority implementation and
request-controller algorithm to a synthetic policy. The factory accepts only the
canonical origin returned by the newly owned fixture server: HTTP, literal
127.0.0.1, explicit integer port 1..65535, no userinfo/path/query/fragment. It
refuses every real broker origin, localhost alias, alternate IP, noncanonical
spelling and arbitrary protocol. Every enabled request URL must retain that exact
origin and the existing canonical-path/fragment/userinfo checks. Exact method and
native resource-type comparisons remain unchanged. Port allocation is allowed
only in this internal factory, never in the broker interface.

The factory creates a branded authority/controller composition, not a public
validator callback that an operator can replace with an always-true function.
Clone and freeze policy/source values at construction; both durable authority and
controller must share that exact instance. Brand handles using module-private
identity and reject foreign, forged, broker/lab or differently bound handles at
every operation. The existing trusted consume callback remains available for the
approved broker controller; the lab composition binds its real durable consumer
internally. The same controller decision algorithm handles both policies.
This is cooperation against accidental cross-use, not isolation from hostile
same-user code, which remains outside the existing filesystem trust boundary.

### Durable namespace and replay boundaries

Synthetic auth state lives under the fixture user's fixed
`~/.local/state/ghostfolio-boursedirect-sync/synthetic-cdp/auth` namespace. Use one
fixed invented principal, with a distinct domain-separated hash; do not accept a
broker login or enroll a real principal. No configurable state root, automatic
reset, stale-lock removal or journal migration is introduced. Tests may replace
HOME only in newly owned isolated processes, as existing offline tests do.

Lab journals use a distinct strict schema carrying the literal synthetic policy
identifier, exact loopback origin and fixture allocation UUID. Bind all attempts
and permits to that journal and validate the binding again on read, arm and
consume. A wrong port, allocation or policy fails closed; it never creates a fresh
attempt to bypass retained uncertainty. Broker readers reject lab journals and
lab readers reject broker journals, even if bytes are copied across directories.
Existing broker journal bytes require no rewrite. The lab factory may reopen only
its exact persisted allocation/origin for isolated crash/restart qualification.

The origin is bound before enrollment or arming. Supply observed URL, method,
resource type, session, frame and loader IDs without replacement. Only local
opaque page/frame epochs are generated by the driver, with a private mapping to
native ownership; native IDs and URLs are never translated into fixture constants
to satisfy a validator. Consumption/fsync still precedes the one continuation.
Every uncertainty and failed publication keeps the existing refusal semantics.

### Host allocation registry and pre-start authority

The host runner uses a separate fixed private namespace,
`~/.local/state/ghostfolio-boursedirect-sync/synthetic-cdp/allocations`, independent
of output directories and the container's auth journal. A private exclusive
registry lock serializes allocation/recovery. The keyed YAML registry retains all
allocation UUIDs and refuses a new allocation while any prior allocation has an
unfinished or uncertain state. It has no output-root override or stale-lock
expiry. Lost/partial/invalid registry or lock requires manual reconciliation.

Before create, persist and fsync an intent including the allocation UUID, owner
label, exact Docker endpoint and daemon ID, immutable image and seccomp digests,
runner/source digest set and complete permitted create configuration. Verify
daemon identity, image availability, control access and the approved exact-ID
cleanup procedure before create. Fixture allocation and cleanup need separately
applicable authorization. Credentials, mounts, networks, restart policies,
privileges and sandbox-disable flags are absent. Create leaves the container
stopped.

Parse one full 64-hex create ID and independently inspect that exact ID with a
successful return code. Require unchanged daemon identity, owner/allocation
labels, image, stopped state, non-root user, network-none, no mounts, no added
capabilities/privilege, pinned seccomp and the expected entrypoint/configuration.
Durably publish and fsync that independently verified receipt before archive copy
or start; recheck the receipt and resource immediately before start. A malformed
or unsuccessful create/inspect/publication retains the unresolved intent and
cannot grant start or removal authority. A create-before-receipt crash may leave
a stopped orphan; names, labels or listings never identify an authorized cleanup
target. Report fixed uncertainty and require separate operator recovery.

Recovery requires the durable receipt, the same reachable daemon and successful
exact-ID ownership/configuration inspection. Contradictory or incomplete evidence
refuses mutation, including the old runner's inspect-failure cleanup fallback.
Bounded stop/kill/remove uses only that receipt's full ID; no discovered ID or
persisted PID across process restart is authority. Verify absence using an
exact-ID daemon lookup and distinguish an explicit absent-resource response from
daemon, permission or transport failure. Fsync verified terminal absence into
the registry before a subsequent allocation can start. Retain intents, receipts
and principal uncertainty after cleanup; cleanup never authorizes authentication.

### Final-code proof and triage acceptance

Compose the sole-root bootstrap, ordered guards, bounded pipe, real controller
and lab durable authority. Keep policy, allocation and capture qualification in
the existing .94 acceptance scope; design approval alone cannot satisfy it.
Credential-runtime qualification requires this composition's acceptance evidence.
The existing plan remains the owning design artifact.

Required discrimination, beyond the unchanged existing suites:

- Broker exports refuse loopback source contracts, read tuples and copied lab
  journals; lab authority refuses broker state and cross-origin/allocation handles.
  Mutating those exclusions must fail their tests. A fresh isolated process
  refuses an unfinished or consumed synthetic attempt without resetting it.
- A positive native synthetic POST consumes the real lab permit exactly once.
  Final-code startup/target/frame/worker/redirect/HTTP-auth/second-auth and held
  callback controls retain native metadata and the approved stop ordering.
  Negative controls remain fixture-only and discriminate the safety checks.
- Capture uses a ticket armed before navigation and native Fetch.networkId,
  requestId, loader, commit and lifecycle-load correlations on the same root.
  Wrong/missing/stale loader and account/day/role/operation controls refuse;
  identical bytes with distinct fresh chains qualify. Existing synthetic marker
  checks remain a fixture adapter, not evidence of actual broker documents.
- Isolated allocation kill points cover before create, create-before-receipt,
  receipt-before-start and dispatch, plus registry/receipt fsync and daemon
  failures. Ambiguous windows never start/reallocate/clean by name. A competing
  runner cannot bypass registry exclusion by choosing another evidence directory.
- Every successful fixture ends with exact owned absence and retained private
  receipts pinned to final executable sources/runtime/evaluator. Uncertain
  ownership or cleanup leaves .94 open. Historical harness passes are not reused
  as final-code qualification. All readiness fields remain false.

Run required `bash scripts/verify-local.sh` before every scoped commit. Roll back
design/code with `git revert <scoped-commit>` while retaining all journals and
allocation evidence. This amendment allocates nothing; later fixture teardown
requires its exact receipt and separately applicable cleanup authorization.
Independent source observations, credentials, egress, security and external PR
review remain separate gates. No deployment, image publication or broker request
is part of this proposal or its approval.
