# Astra design review: guarded browser driver

Date: 2026-10-09. Verdict: **REVISE; reusable B remains HOLD**.

Reviewed design: `docs/plans/2026-10-09-guarded-browser-driver.md`, SHA256
`30f98214567596aac05ede1908fdc283d72d6011ddc7dbe1d6c091560812fccc`.
This is independent design review only. It is neither PR review nor browser
capability evidence. No browser, network fixture, production service, test,
process inventory, credential or shared state was accessed.

## Assessment

The sole-client raw CDP pipe is a credible candidate for a bounded isolated
capability harness. Browser-level auto-attach before creating about:blank pages,
explicit owned-target correlation, recursive attachment and acknowledged Fetch
installation before resume remove the known dependence on an external page
observer. Strict target rejection, all-request interception, redirect refusal,
durable permit consumption before continuation, and arming uncertainty before
credential fill are appropriate design choices.

The inspected protocol describes debugger waiting and request interception; it
does not establish that a popup's first navigation or every frame/worker request
is held by this exact Chrome build. In particular, pausing execution must not be
equated with suspending all initial network dispatch. The proposed positive and
negative synthetic controls are necessary. A failed mechanism keeps B held.

Loader-bound capture tickets, exact document roles and bounded immutable
publication provide a coherent continuation of offline C. Fresh identical bytes
remain valid only after the actual navigation proof. A new page or matching URL
alone cannot supply that proof.

## R1 — Preserve the capability gate before reusable B implementation

The previous exact-plan disposition requires isolated first-request evidence
before reusable B integration. New phases 1–3 instead allow reusable driver
implementation after this design review and before the capability experiment.
That changes the existing gate without resolving its architectural uncertainty.

**Required amendment:** separate the bounded throwaway/synthetic capability
harness from reusable B. After this amended harness design is approved, a distinct
issue owns the isolated executable proof and exact runtime/image pins. Only after
that evidence exists may the grounded reusable design receive its exact-hash
approval and reusable implementation begin. The design/proof-plan issue may close
only against its own planning criteria; it must not own or imply completion of
the real capability evidence. Keep source-contract, online egress, secret delivery
and pre-merge security review as separately owned gates.

## R2 — Define abort ordering without releasing paused targets

The design repeatedly says to abort while a target is paused, but does not define
transport and browser teardown ordering. Closing or detaching CDP must not be
treated as a safe way to fail paused requests: it may remove the very pause or
interception on which the guard relies. This is an unproved failure-path property,
not a runtime finding from this review.

**Required amendment:** on fatal policy/transport failure, synchronously fence all
new actions and outbound continuation/resume commands, retain durable uncertainty,
and terminate the newly owned browser process tree using its launch-time ownership
handle before intentionally closing its pipe. Never detach targets or disable
Fetch as cleanup. Define a bounded force-stop fallback and observe process exit;
do not discover ownership through broad process listings. Connection loss/crash
must trigger the same owned-resource stop without claiming that CDP alone protects
the interval after disconnection. The network-none fixture and the separate online
egress gate remain the containing boundaries for that interval.

**Capability owner evidence:** trigger rejection with requests paused and work
queued, then verify zero forbidden server dispatch through teardown. Exercise
transport failure and the bounded stop path separately. Only synthetic resources
belonging to the harness may be stopped.

## R3 — Arm HTTP authentication challenge interception explicitly

The schema makes `Fetch.enable.handleAuthRequests` optional. The design rejects
unknown HTTP authentication challenges but only specifies request-stage patterns;
those patterns alone do not establish challenge cancellation behavior.

**Required amendment:** install the `Fetch.authRequired` route before enabling
Fetch with `handleAuthRequests:true` on every supported session. No challenge may
receive credentials or default handling. Cancel the challenge and enter the fatal
fenced stop path; failed cancellation still requires owned-browser termination.
Add a synthetic HTTP-auth challenge criterion proving no credentials/default
retry dispatch. Broker form password/OTP permits remain separate from HTTP auth.

## Proof scope and bounds to retain

The capability owner must retain all proposed first-popup/frame POST, worker,
same-origin-frame, attachment race, second-auth, redirect307/308, permit persistence,
restart fence and real-loader capture criteria. Include each supported target
class in evidence; an unsupported OOPIF command is a failed prerequisite, not a
reason to resume it without the guard. A deliberately unguarded negative control
must actually increment its forbidden counter so a zero count is discriminating.

The transport limits are workable fail-closed limits for a synthetic capability
bench. They are not yet evidence of broker-document compatibility. Bound startup
event buffers, stderr storage and queued bytes as well as completed messages;
timeout or overflow follows R2. Sequential policy decisions must prevent two
simultaneous pauses from both consuming a permit. The A durable one-use primitive
remains authoritative; the harness must exercise concurrent request arrival.

Record the exact full Chrome artifact, image, Node version and launch flags.
The supplied Chrome148.0.7778.97 reference pin is a candidate, not a qualified
installed runtime. Network-none, non-root sandbox operation and no shared mounts,
profiles, credentials or state remain mandatory. Failure must not authorize
privileged mode, SYS_ADMIN, host networking or sandbox disablement.

## Evidence and disposition

Read the repository AGENTS.md, the supervised acquisition plan and its scoped
review, and the exact B design. Inspected the local pinned CDP JSON definitions
for Target auto-attach/create/attachment, Fetch enable/request pause, and frame
navigation. Inspected extracted pinned Puppeteer launcher/revision reference
files for pipe wiring and the Chrome revision. No claim about initial-request
suspension is inferred from those sources.

Knowledge lookup followed the corpus index and Ghostfolio index to
`operations/ghostfolio/saved-input-report-preservation.md` (stable, verified
2026-10-09, stale after 2026-12-31). Its preservation boundary remains applicable
to capture publication. **Knowledge verdict: Used and sufficient.** These new
findings belong to the canonical project design; no portable runtime result was
discovered or published.

The bounded harness approach is acceptable in principle. Amend R1–R3 and submit
the new exact hash for scoped approval before harness work. Reusable B remains
held until real capability evidence and the subsequent grounded design approval.
This review grants no real broker access, seed retrieval, production writes,
Ghostfolio writes, merge or online enablement. Parent owns Beads, commits and
terminal reconciliation; the reviewer authored only this report.

## Exact-hash re-review: synthetic harness only

Date: 2026-10-09. Reviewed amended plan SHA256:
`8b9ee147f644fa6ea1ef3879ef2e2eecf7559f3df1257439d1f6d8ec30c45fa5`.
**APPROVE the bounded isolated synthetic capability-harness design;
HOLD reusable B.** This supersedes the initial REVISE only for the scoped harness
design and experiment defined in the amended phases.

R1 is resolved: the synthetic-only harness has a separate proof owner, cannot
load broker sources/contracts or real credential environments, and must produce
actual isolated evidence before a subsequent exact-hash reusable-design approval.
The planning issue does not substitute for that evidence or authorize reusable B.

R2 is resolved at design level: a synchronous fatal fence prevents further
continuations and resumes, preserves uncertainty, and terminates the launch-owned
process group before intentional pipe closure. Bounded escalation and an exact
owned-container fallback cover incomplete descendant-exit evidence. Lost-pipe
containment is correctly attributed to the OS boundary, not CDP. The real proof
still must establish the claimed zero forbidden dispatch during teardown; this
review does not assert that the experiment will pass.

R3 is resolved: HTTP-auth routing precedes Fetch enablement with
`handleAuthRequests:true`, challenges receive CancelAuth without credentials or
Default handling, and cancellation failure follows fatal stop. The synthetic401
criterion explicitly covers retry behavior. Concurrent permit decisions are
serialized, and startup events, queued/incomplete bytes and retained stderr now
have explicit bounds.

The full Chrome candidate remains unqualified until exact artifact/image/runtime
pins and sandboxed network-none evidence exist. The first-request negative control
must demonstrably dispatch its forbidden request; failure to observe that signal
makes the corresponding zero-dispatch result inconclusive. Every required proof
criterion must retain its owner until met, including frames/workers, redirects,
HTTP auth, crash/restart fencing and actual capture-loader freshness.

No browser, fixture, test, process inventory, credential, network or shared-state
access occurred during this re-review. Only the amended design and its exact hash
were read, and this report was appended. A/offline C approval is unchanged;
source acceptance, online egress/delivery, real secret provisioning, security
review and production authorization remain separate. No broker or Ghostfolio
production write is authorized. Knowledge verdict: **Used and sufficient**,
unchanged from the narrow indexed lookup above. Parent owns commit and Beads.

## Playwright candidate evidence (2026-10-09, author follow-up)

Florent clarified that the suggested reuse candidate was Playwright. A bounded
Luna primary-source lookup found that [context routing](https://playwright.dev/docs/api/class-browsercontext#browser-context-route)
can cover popup initial requests, whereas page routing cannot. Context routing
has a documented service-worker bypass; blocking service workers is an explicit
option. Context redirect behavior remains unverified in this lookup.

The inspected historical source sample is Playwright v1.56.1 at
`54c711571a37de525377e6f3d3608c3e029b1829`, not a current-version claim.
[Page initialization](https://github.com/microsoft/playwright/blob/54c711571a37de525377e6f3d3608c3e029b1829/packages/playwright-core/src/server/chromium/crPage.ts#L527-L564)
collects network initialization and `Runtime.runIfWaitingForDebugger` in the same
`Promise.all`.
[Network session initialization](https://github.com/microsoft/playwright/blob/54c711571a37de525377e6f3d3608c3e029b1829/packages/playwright-core/src/server/chromium/crNetworkManager.ts#L87-L93)
also awaits enablement and interception together. This sample does not establish
a sequential interception-acknowledgement-before-resume guarantee; it is not
proof of a runtime escape or a defect in current Playwright.

The official [launch option](https://playwright.dev/docs/api/class-browsertype#browser-type-launch-option-chromium-sandbox)
defaults Chromium sandboxing to false. The [Docker guide](https://playwright.dev/docs/docker#crawling-and-scraping)
recommends a separate user and seccomp policy for untrusted crawling. Runtime
qualification remains separately owned by infra; these sources authorize no
host-security change or sandbox fallback.

The existing synthetic raw-CDP capability experiment remains approved; reusable
B remains held. This author evidence note does not change the Astra verdict or
the reviewed plan, approve a Playwright driver, or substitute for real ordered
guard tests. Beads `.71` records exact lookup findings and unresolved limits.

## Synthetic ordering experiment (author implementation evidence)

`collector/capability-ordering.mjs` is the first mock-only part of the approved
capability experiment. It imports no browser, network, child-process or source
loader. Injected callbacks model route installation, sequential guard
acknowledgements, resume, owned exit confirmation and pipe closure. The retained
result explicitly states `browser_proven=false`. It is not a browser driver,
bounded CDP pipe implementation, full target/request policy or runtime authority.

Network/child-forbidden tests hold each guard acknowledgement independently,
then observe whether resume is attempted. The deliberately parallel negative
control must record one forbidden dispatch while the held interception remains
unacknowledged; that counter is a simulated signal, not a browser server count.
Other scenarios reject unpaused attachments, stop pending initialization,
refuse pipe closure without positive owned-exit confirmation, and cancel HTTP
auth explicitly before stopping, including cancellation failure and wrong session.

This mock verifies the ordering primitive and the negative-control detector.
The real sandboxed positive/negative experiment, bounded transport, unexpected
popup/frame/worker handling, durable concurrent permits and loader freshness
remain required under the owning issue. The existing sandbox runtime blocker
and reusable B HOLD are unchanged. Subagent execution evidence is recorded on
`.71`; it is not an independent design/PR review or real Chrome qualification.

## Composed offline capability evidence (author implementation)

The same approved experiment now includes callback-only NUL-framed transport,
startup ownership binding, and fixed invented request/capture fixtures. Transport
tests enforce strict UTF-8, exact command/session replies, bounded pending work,
input/output/startup queues, command/session deadlines and synchronous event
routing. Fatal transport failures compose with the ordering fence; owned exit
confirmation precedes intentional pipe closure. Startup holds an early paused
attachment until the exact create-target reply binds ownership, and rejects
pre-existing, unpaused, second-page, worker and iframe targets. Aborting releases
an attachment wait without initialization.

The fixed fixture serializes concurrent authentication requests and requires
successful durable consumption before its one continuation. Redirects, stale
epochs and foreign targets cannot consume or continue. Isolated composition
tests use the existing offline authority core with a private owned temporary
directory, fsync failure injection and controller restart: persistence failure
prevents continuation and uncertain delivery remains fenced after reacquisition.
Capture requires matching request, frame commit and loader-load events plus the
ticket account/day/epochs; DOM markers alone cannot satisfy it.

These tests dispatch no real request and launch no browser. Invented fixtures and
simulated protocol frames do not establish Chrome's initial request suspension,
real worker/frame interception, server counters, process crash recovery or actual
loader freshness. Every returned qualification remains `browser_proven=false`.
The real sandbox prerequisite, real positive/negative controls and all browser
acceptance remain open; the reviewed plan and Astra verdict are unchanged.

## Initial real dispatch evidence (author experiment, 2026-10-09)

Infra runtime owner `infra-66vf` qualified the existing exact Chrome image using
the pinned Playwright crawling seccomp profile. The paired opt-in probe retains
the default-profile sandbox failure as a negative control; `chrome://sandbox`
reports the namespace layer, PID/network namespaces and Seccomp-BPF/TSYNC active
under that profile. AppArmor, nonroot identity and network-none isolation remain
in place. Infra commit `fbe0d1d` owns the reproducible sandbox probe; the source
issue records exact runtime/profile pins and private cleanup receipts.

The opt-in `scripts/run-cdp-first-request.py` copies only four synthetic modules
into newly owned network-none containers without mounts or real credentials.
`collector/lab/first-request.mjs` uses actual Node20.19.2, Chrome148.0.7778.97,
NUL-framed CDP, acknowledged bootstrap guards and a loopback HTTP counter.
The five initial scenarios passed with positively observed browser exit and
exact container removal:

- A permitted root POST reaches the server exactly once; forbidden count zero.
- A forbidden root POST is intercepted before dispatch; server count zero.
- Omitting Fetch installation in the negative control dispatches that POST once.
- A form POST popup actually creates a second paused attachment, is rejected,
  and does not reach the forbidden endpoint.
- The popup negative control deliberately resumes the second attachment without
  guards and dispatches the forbidden POST once. Popup blocking is disabled in
  both controls so an absent popup cannot masquerade as containment.

Initial exploration omitted extension suppression and correctly failed when
Chrome announced a component service worker. The retained fixture suppresses
extensions/component extensions per the existing design; no target rejection
policy was weakened. Private prototype receipts remain diagnostic evidence.

This is a partial executable proof, not a new Astra verdict or independent PR
review. Every report retains `browser_proven=false`. The fixture's in-memory
one-use counter does not establish the real durable-principal integration gate.
Frames/workers, redirects307/308, HTTP-auth cancellation, concurrent durable
permits/fsync failures, process crash/restart, pipe loss/forced-stop dispatch and
actual loader/account/date freshness still retain acceptance ownership in `.71`.
The qualified runtime removes the previous sandbox blocker; reusable B stays
HOLD until complete proof and subsequent exact-hash design approval. No broker
or Ghostfolio request was sent, and ordinary pytest/npm tests never start this
opt-in Docker fixture.

## Expanded real capability evidence (author experiment, 2026-10-09)

The same opt-in harness now runs 28 fixed scenarios under the qualified image
and seccomp pins. This is author implementation evidence, not a new Astra verdict
or an independent security/PR review. The reviewed plan remains byte-identical.
The runner copies the synthetic modules, existing durable authority core and
installed pinned `yaml@2.9.1`; it records each copied file's SHA256 and its own
SHA256. No source configuration, credentials, volumes or shared database enter
the container. The core's invented role metadata is never a browser destination;
only the exact invented loopback request is mapped to that offline authority.

Guarded root and same-origin child-frame POSTs, popup POSTs, worker/shared-worker/
service-worker requests, 307/308 replay and the second authentication POST have
zero forbidden server dispatch. Corresponding unguarded controls actually reach
the server; the second-auth and concurrent controls dispatch twice. Worker
rejection can occur on discovery or on a paused attachment, depending on the
observed ordering. The proof accepts either exact worker-type rejection signal,
without resuming it. Cross-origin/OOPIF support is not delivered by this fixture.
The late-installation negative control resumes before installing Fetch, waits
500 ms, and observes one forbidden dispatch before installing the guard.

In this exact runtime `Fetch.requestPaused` reports the fixture's JavaScript
`fetch()` POST as `XHR`. The synthetic contract pins that observed value and
passes the native method/resource type into durable consumption. Concurrent
pauses consume exactly one durable permit and dispatch at most once: fatal
rejection of the second pause can stop the browser before even the first request
reaches the server. Separate permitted-root evidence proves positive dispatch.
Injected fsync failure has no continuation or server POST. A Chrome group crash
after durable consumption and before continuation also has no POST. A fresh Node
process reads the fixture's journal and refuses a new attempt in all three
durable cases. This uses only the newly owned principal, never shared state.

Pipe-loss and forced-stop scenarios wait until two forbidden requests are
actually paused. The former destroys the read pipe as explicit failure injection;
the latter stops the process group so TERM cannot succeed, exercising bounded
KILL escalation. Both retain zero forbidden server dispatch. The trace confirms
synchronous fencing before owned stop and observed browser exit before deliberate
teardown pipe closure. The outer runner verifies and removes the exact labelled
container, covering any remaining descendants independently of browser exit.

`collector/lab/capture-document.mjs` arms the capture experiment before navigation,
binds native session/frame ownership, correlates Fetch.networkId with the actual
Network request ID and loader, and requires ordered frame commit and loader-bound
load. A fixed driver-owned DOM expression serializes invented markers/body; frame
and loader checks bracket serialization. Two identical documents have distinct
native request/loader IDs. Four additional real documents exercise wrong account,
day, role and unknown-operation markers. A real replacement navigation invalidates
the second capture's loader. Adversarial replays derived from these native events
reject the previous commit/load, missing loader, wrong identity/epoch and a
DOMContentLoaded event used in place of load. These derived cases are identified
as policy replays, not fabricated additional browser events or real financial
document/source-acceptance evidence.

Private receipts remain under ignored `tmp/cdp-real-proof/`; ordinary pytest/npm
tests still forbid networking and do not invoke Docker or Chrome. Every runtime
report retains `browser_proven=false`: local capability evidence does not approve
reusable B, source roles, online egress or broker access. Exact publication evidence
and the subsequent grounded reusable-design approval remain separate gates.

Verification for this increment: all 28 scenarios in `final-matrix-9` passed;
the subsequent capture-only change (arm before navigation and explicit native
event-order check) passed in `final-capture-10`. All corresponding exact container
IDs were independently absent after cleanup. The required Python suite passed
993 tests in 80.31 seconds; the network-forbidden collector suite passed 155
tests with zero failures in 2535.969294 ms. Beads `.71` retains the private receipt
locations, commit anchors and publication acceptance ownership.

## Bench regression and consolidation follow-up (author implementation)

The browser experiment now imports a pure `fixtureVerdict` evaluator and a
single keyed `collector/lab/scenarios.yaml` catalogue shared with the Python
runner. Offline tests exercise each scenario, historical expectation mistakes,
missing stimuli, cancellation/authority failures, capture evidence and teardown
order. They start no browser or Docker resource. Live reports also contain fixed
verdict failure codes; containment policy and the approved plan are unchanged.

`scripts/consolidate-cdp-proof.py` rechecks full coverage, current source and
runner hashes, runtime pins, ownership/removal receipts and every observation
through that same evaluator. It reads receipts and runs only the fixed pure Node
evaluator. Docker absence inspection is explicitly opt-in and read-only:

```sh
.venv/bin/python scripts/consolidate-cdp-proof.py tmp/cdp-real-proof/<matrix>
.venv/bin/python scripts/consolidate-cdp-proof.py tmp/cdp-real-proof/<matrix> --verify-owned-absence
```

An explicit `--replace-capture <directory>` accepts exactly one capture receipt
with the same inventory, runner and common source pins; only the capture module
hash may change. Both original and replacement must pass, all other modes must
retain the original common pins, and the final capture must match current files.
The summary retains selected receipt hashes, the superseded capture hash and
validator hashes. This checks provenance consistency, not source authenticity or
independent browser attestation. Original receipts are never rewritten; historic
receipts from a different runner revision cannot qualify the current tool.

PR39 review findings are addressed with explicit Python runtime checks that
remain active under `-O`. Cleanup records the full create ID before inspection,
attempts its removal even when inspection is temporarily unavailable, records
cleanup failures, publishes a receipt and preserves the original execution
exception. Explicit contradictory ownership blocks removal and qualification;
the review suggestion to remove even a foreign-labelled resource is not adopted.
Synthetic response-injection tests cover these distinctions without touching
Docker or shared state. The reader-boundary "Major" finding is a false positive:
the test fixture changes into `tmp_path`, so `inputs/` is beneath the accepted
root; all six exact-boundary cases pass unchanged. Agent-helper installation is
documented, and shared infrastructure routing distinguishes destination epic
from source issue; sibling-copy alignment is handed off separately.

These changes harden the same approved synthetic experiment. Reusable B,
actual source/credential/egress gates and independent external review remain
separate; every report retains `browser_proven=false`.


### Current-head teardown review correction (author evidence)

The subsequent CodeRabbit and Claude reviews of `6e211bf` identified a valid
ordering gap in the pure fixture verdict: a fenced `stop-owned` recorded after
`owned-exit` could qualify when pipe closure was correctly ordered. The evaluator
now requires `stop-owned < owned-exit < close-pipe`, with the first stop fenced
and pipe closure reporting exit. A focused regression independently rejects late,
missing and unfenced stops; removing the stop-before-exit guard makes it fail.

Python regressions now reject reused container IDs both across selected matrix
receipts and across an explicit replacement and its superseded capture receipt.
Removing the identity guard makes both tests fail because no error is raised.
A nonzero inspection return cannot establish ownership even with plausible JSON.
Malformed create output retains a durable failed receipt and cleanup uncertainty;
it never grants authority to remove an unvalidated ID or a discovered resource.
That improbable case remains unqualified rather than broadening removal authority.

These are author corrections within the existing synthetic proof contract, not a
new Astra verdict or production-browser qualification. Exact-current private
receipts must be regenerated after the evaluator pin changes. Existing reader
root feedback remains disproved; shared sibling routing is owned by `infra-d4cl`.


## Exact-hash re-review: grounded reusable B design

Date: 2026-10-09. Reviewed plan SHA256:
`6d9d0448907b80df6b5a4a02989bdaa2b65310d6bcc6b83a39436a80b56c55ef`.
**APPROVE the grounded design and its first callback-only controller delivery.**
No blocking design finding remains for that scope. This supersedes reusable B's
previous design HOLD only for the implementation sequence in the final grounded
section; it does not qualify an online driver or grant broker access. The final
section is normative over the historical multi-page/OOPIF suggestions.

This is independent DESIGN review, not PR review, an implementation security
approval, or independent observation of a running browser. The controller may
accept trusted injected authority and metadata, but has no launcher, operator
broker command, source loader, DOM evaluator or credential reader. Its readiness
remains false. Trusted callback inputs prove policy behavior only; subsequent
composition must prove that native events, durable authority and the runtime
actually supply those inputs. The plan makes this distinction sufficiently
explicit and assigns separate acceptance owners rather than inheriting harness
success as reusable-code qualification.

### Assessment of the requested safety boundaries

- **Startup and target ownership:** acknowledge browser auto-attach/discovery
  before creating the sole blank root; associate an early attachment only with
  createTarget's exact returned identity; require debugger waiting; install and
  acknowledge every guard before resume. The inspected one-root bootstrap is
  consistent with this restricted model. Only same-origin in-process frames are
  supported. OOPIFs, other pages/popups, workers and prerenders remain fatal on
  discovery or attachment, never a compatibility fallback. Browser/tab structural
  discovery is not permission to accept another usable target. New runtime code
  must retain bounds and fatal handling through startup, including queued events.
- **Request authority and redirects:** immutable exact URL/method/native-type
  tuples, explicit owned frame/session/epochs and one current driver action avoid
  implicit same-origin or resource allowances. Native `XHR` in the experiment
  cannot establish actual broker transport or justify coercing `Fetch`. All
  redirects, including GET and method-preserving auth redirects, are refused
  before auth consumption. Absent observed source roles remain disabled. The
  stricter final redirect rule supersedes the earlier acquisition proposal's
  conditional redirect allowance.
- **Durable permits and concurrency:** arming uncertainty before fill and durable
  consumption before continuation preserve the existing authority core. Metadata
  is copied/validated before queuing, decisions are bounded and serialized, and
  the fence is checked after each await before an outbound action. A second
  simultaneous auth pause must fence at ingress rather than wait for the first
  pending callback to finish. The permitted first request may dispatch zero or
  one times; neither zero server count nor resource absence clears uncertainty.
  Unsupported app-method transitions remain disabled; no extension to the core's
  transition semantics is implied by accepting role metadata.
- **HTTP challenges and fatal stop:** CancelAuth is mandatory, with no Default or
  credential response. The synchronous-fence rule applies when the challenge is
  received, before awaiting its cancellation acknowledgement; cancellation must
  not leave other continuations/resumes enabled. This is an implementation
  obligation under the current fatal-stop contract, not approval to copy the
  experiment's `cancelHttpAuth` unchanged: that helper calls abort in `finally`.
  An already-fenced cancellation/stop path must remain bounded and cannot reopen
  authority. All fatal paths retain `fence -> stop-owned -> owned-exit ->
  close-pipe`; failed exit evidence must not become successful cleanup. Physical
  pipe loss still needs an independent egress boundary.
- **Pre-start allocation and recovery:** a durable intent before create and an
  independently checked exact-ID receipt before start/credential transfer close
  the unsafe assumption that an in-memory create result survives a crash. The
  create-before-receipt gap can leave a stopped orphan, but the explicit blocked
  allocation and manual recovery boundary make no automatic cleanup claim.
  Names/labels discovered later cannot grant removal authority. Exact-ID recovery
  still checks daemon/resource identity and refuses contradictory or incomplete
  ownership; a persisted PID alone is insufficient. Runtime kill-point and daemon
  failure evidence remains mandatory under its following owner. The controller
  neither implements nor proves that deployment contract.
- **Capture:** same-root navigation avoids claiming support for unproved popup
  ownership. Exact native request/loader/commit/load chains and epoch checks
  bracketing bounded serialization preserve freshness even for identical bytes.
  Existing parser/filter/publication checks remain authoritative for financial
  shape, every note date and config/source/previous-run preservation. Offline
  manifest agreement and synthetic marker DOM are explicitly insufficient to
  establish runtime or actual broker-document authenticity.

### Evidence, limits and acceptance handoff

Read repository guidance, the acquisition/core/bundle contracts, the historical
review and current grounded proposal. Inspected the synthetic bootstrap,
ordering/request helpers, scenario catalogue, durable permit boundary and the
receipt-consolidation code. The existing synthetic helper implementation is
reference/evidence for the design, not the approved reusable implementation.

Independently ran only this read-only consolidation:

```sh
.venv/bin/python -B scripts/consolidate-cdp-proof.py tmp/cdp-real-proof/integration92-exact
```

It returned `passed=true`, `modes=28`, `receipts=28`,
`current_pins_verified=true`, `capture_replaced=false`,
`live_absence_verified=false`, and `browser_proven=false`. Validator SHA256 was
`425768d24f16065e962bea99abaa0d0f755cd55ba48dab28640389f0803a2090`;
the pure observation evaluator SHA256 was
`c2d749c52ab3580c4d16b87f2abde52f205a1a788c86a68e192b09b087157a19`.
This confirms consistency of the retained 28-scenario evidence and current source
pins; it does not authenticate receipt authorship or rerun Chrome. The parent's
separate current absence check is author evidence, not a check performed by this
reviewer. No browser, Docker command, network request, credential, private broker
HTML, production service or shared Beads state was accessed by this review.

The first controller owner must supply discriminating network/child-forbidden
checks, including held callbacks crossed by a fatal event, duplicate IDs,
immutable queued metadata, bounded queues, simultaneous auth requests, HTTP-auth
cancellation and persistence refusal. Complete Python/Node verification remains
required. Later launch/recovery and capture-composition owners must prove their
final code in separately isolated real fixtures; the earlier harness is not that
proof. Source characterization, portable credential delivery, dedicated egress,
exact-head security and external PR review retain their independent gates. No
real login, secret export, production change or Ghostfolio write is authorized.

Knowledge lookup followed the corpus and topical indexes to the stable
`saved-input-report-preservation` concept, verified 2026-10-09 and fresh through
2026-12-31, then checked its boundary against the owning acquisition-bundle
contract. **Knowledge verdict: Used and sufficient.** No retrieval escalation or
new portable runtime finding arose; design decisions stay in their canonical
project artifacts. The reviewer appended only this section, preserving every
prior report byte. Parent owns Beads, commits and terminal reconciliation.


## Exact-hash design review: native synthetic composition amendment

Date: 2026-10-10. Review owner: `infra-4g8u.99`.
Reviewed the complete plan at commit
`dc1c393b80177a599d452ded81ebd2900de28c77`, SHA256
`49ddae6d63e66a4741e4e2c37df75ed4d72491b6a165eefafe6fd8e7306be66e`.
The working plan was byte-identical to that committed object.

**APPROVE the native synthetic composition DESIGN.** No blocking design finding
or further plan amendment is required for this scoped implementation. The
2026-10-10 amendment governs the internal synthetic composition; earlier approvals
retain their original scopes. This verdict is neither PR review, final-code
acceptance, runtime qualification nor permission to allocate a fixture or access
the broker. Implementation and all final-code proof remain owned by `.94`.

### Grounding and safety assessment

The seam addresses an actual gap. `core.mjs` applies `brokerUrl` in source and
stored-permit validation; `request-controller.mjs` imports those fixed validators
and validates read URLs separately. The old `lab/first-request.mjs` consumes a
broker-shaped saved request while Chrome requests a loopback URL, and
`lab/capture-document.mjs` replaces session/frame/URL values with `FIXTURE`
constants after native correlation. Those experiments cannot establish the new
unchanged native composition, even where their individual controls passed.

A module-private immutable policy shared by the real authority and controller is
an appropriate internal seam. Keep the public broker signatures, origin, principal
hash, fixed namespace and schema-1 journal format unchanged. The lab factory's
literal canonical loopback origin, fixed invented principal, separate namespace,
strict policy/origin/allocation journal binding and private handle identity make
cross-use fail closed without exposing a configurable broker validator. This is
a cooperation boundary under the existing same-user filesystem assumptions.
Source cloning/freezing must cover nested values, and neither caller mutation nor
an object with copied fields can acquire another instance's authority.

Native URL/method/resource/session/frame/request/loader identities must pass
through without fixture substitution. Local opaque epochs remain legitimate
ownership metadata; they are not substitutes for CDP identities. The existing
controller's exact event/action comparisons allow its consumer to use the already
compared action tuple, but the composition must demonstrate that the tuple equals
the native event. Do not fork the authority or decision algorithm into a permissive
lab copy. Keep durable consumption before continuation and permanent fencing after
fatal ingress, including a concurrent second authentication request or HTTP-auth
challenge. The existing controller's synchronous `authRequired` fence is the
required path; the older ordering helper's cancellation-then-abort behavior is
not sufficient as the composition's sole challenge handler.

The fixed host registry closes the alternate-output-directory bypass. Exclusive
allocation/recovery, fsynced intent before create, independently verified full-ID
receipt before copy/start, and immediate pre-start reinspection are a coherent
fail-closed ordering. Registry/receipt loss, partial publication, daemon mismatch
or uncertain ownership cannot become a fresh allocation or cleanup authority.
The create-before-receipt window deliberately permits only a stopped orphan and
manual reconciliation. Names, labels and later discovery never confer cleanup
identity. A retained lock after a crash also requires manual reconciliation; no
stale-lock expiry is implied by recovery support.

The current runner is not compliant with that new contract: it retains the ID in
memory, publishes its receipt after execution, can remove after failed inspection,
and checks final absence by name. These are required replacement points under
`.94`, not reasons to approve the old runner unchanged. Exact-ID absence must be
a positive daemon observation, never a generic inspection failure. Cleanup does
not clear authentication uncertainty. Failed terminal-absence fsync blocks the
next allocation even after a resource is physically gone.

Capture must arm its native ticket before navigation and correlate Fetch network
ID, Network request/loader, commit and loader-bound load on the owned root. Keep
ownership/epoch and active-loader checks around bounded serialization, including
an intervening navigation with identical content. Synthetic account/day/role and
operation markers test the fixture adapter only. The existing acquisition-bundle
parser and publication-preservation contract remain the financial/source boundary.

### Final-code acceptance handoff

The `.94` owner must produce the amendment's evidence against its final executable
sources; none is satisfied by this design verdict or historical harness receipts:

- Discriminating broker/lab exclusion, forged/cross-instance handle, nested source
  mutation, copied-journal and wrong-origin/allocation tests; unchanged broker
  schema-1 compatibility; a fresh isolated process that refuses retained synthetic
  uncertainty without reset or implicit reenrollment.
- One positive native POST using the same durable consumer/controller algorithm,
  with exactly one durable consumption before dispatch. Startup, unsupported
  target/frame/worker, redirects, held callbacks, HTTP auth and concurrent/second
  auth must prove ingress fencing and the original bounded stop ordering. The
  race may dispatch zero or one times; the separate positive control proves one.
- Native capture controls for missing/wrong/stale chains, changed ownership or
  epoch, wrong markers and intervening navigation, plus identical bytes with
  distinct fresh chains. Evidence must distinguish real events from derived
  adversarial replays.
- Isolated allocation kill points and fsync/daemon failures at intent, create,
  receipt, start/dispatch and terminal absence. A competing process selecting a
  different output directory must still be excluded. Missing/contradictory
  ownership must produce no start, reallocation or removal; a verified receipt
  permits only its exact-ID recovery under applicable authorization.
- Final source/runtime/evaluator pins, retained private receipts and exact owned
  absence for successful fixtures, plus the required complete local verification.
  Uncertain cleanup keeps `.94` open. All readiness fields remain false.

### Evidence and limits

Read project guidance, the scoped review brief, the full owning plan, acquisition
core/bundle contracts, the existing report, actual core/controller, sole-root
bootstrap, ordered guards, bounded pipe, native capture helper, fixture runner,
and relevant controller/core/composition/runner regression code. Hash/committed
object comparison and initial Git status were read-only and successful. The
parent reports `bash scripts/verify-local.sh` exit 0 with 1031 Python and 285 Node
tests before this review; that is author evidence for existing code, not an
independently rerun suite or evidence of the proposed implementation.

No browser, Docker command, network request, credential, real broker document,
production resource or shared-state test was used. This review makes no new
vendor/runtime claim. Source characterization, credential delivery, isolated
runtime authorization, egress, security and external PR review retain their
separate gates. Rollback of this appended report is a scoped commit revert;
retain every authentication journal, allocation record and private capture.

Knowledge lookup followed corpus and Ghostfolio indexes to the stable
`saved-input-report-preservation` concept (verified 2026-10-09, fresh through
2026-12-31), checked against the owning acquisition-bundle contract. Lookup outcome:
applicable. **Knowledge verdict: Used and sufficient.** The indexed path needed
no retrieval escalation; these design decisions already belong in the canonical
project plan/report and add no separate portable operational lesson. Only this
section was appended, preserving all preceding report bytes. Parent owns Beads
updates, complete verification, the scoped commit and terminal reconciliation.


## Exact-hash design delta review: cached fixture recovery identity

Date: 2026-10-10. Independent design delta review under `infra-4g8u.99`.
Final owning plan SHA256:
`e275a5ec951cc092d1b7582524a3b19a189cb0f31c787d654f1ae409142cd7ad`.
**APPROVE the cached fixture recovery identity amendment only.** Its final text
matches the reviewed substitution; no blocking design finding remains. Earlier
scope restrictions and acceptance obligations continue to apply.

Approved replacement of the development-only exact image-index pin:

- Historical index:
  `sha256:11b6dc0eb079e10e625ff8de54af6018100289b51fa500e72196adfca8233df8`.
- Recovered index:
  `sha256:05f2836ccd6a6b66a18e21e9d940e36336b7d40e353a3e97b05b01df0654f721`.
- Identical original/recovered runtime manifest:
  `sha256:480e30540a19482a31a70f345a97c769491d677a62b43eb2232f4fcfbe08c625`.
- Identical original/recovered configuration:
  `sha256:0665422bcb24981c0ed8a4dd885167958273a4210e410be84322465fa6ed9b9f`.

The retained original and recovery build logs show unchanged runtime identities,
cached filesystem/configuration steps and different attestation/index digests.
The saved recovered-image inspection agrees with the new index, non-root user and
fixture label. Recovery log SHA256 is
`b80ab4faed9bc8a7d3779c2dc7225a72a6df5a090cc609b53fa7675f0bfab918`;
inspection SHA256 is
`bf8b34a41fd6598a83f0163ec4d6f74f55dae804a22f7b871089298cc319b4af`.
These are independently read saved records, not a live daemon inspection or
independent observation of the build/runtime.

Chrome148.0.7778.97, Node20.19.2, artifact/profile/label pins, fixed registry,
sandbox and exact full-ID controls remain mandatory. No tag fallback, runtime
override, registry reset or rewriting old receipts is approved. Any incompatible
retained allocation remains blocked for separate reconciliation. The final
32-mode runtime proof under `.94` remains outstanding and must run from scratch
against final sources and the recovered exact index with new private receipts;
no historical receipt qualifies it. All readiness fields remain false. This is
not PR review, runtime acceptance, production authorization or broker permission.

Only this review section was appended; previous report bytes were preserved.
No Docker/browser/network operation or Beads mutation was performed. Parent owns
required local verification, the scoped commit and `.99` closure before runtime.
**Knowledge verdict: Nothing durable.** This narrow identity delta belongs in
its canonical plan, review and retained build records; it adds no portable lesson.


## Exact-hash design delta review: supervised allocation interruption proof

Date: 2026-10-10. Independent DESIGN review of the final owning plan SHA256
`d5724ac0126b4eee2c1f737c1563b2c21079c3cf9fc9370e5d964061c5a1eb55`.
**APPROVE the narrowly supervised laboratory interruption-proof design.**
The earlier scoped HOLD is resolved: the worker now checks its exact private
`output/home` and current parent PID against the invoking supervisor before
accessing the registry, and the plan explicitly bounds the test-only recovery
exception. This is cooperation against accidental cross-use, not a security
boundary against hostile same-user code.

Inspected the corrected `prove-native-allocation.py`, the relevant runner and
allocation operations, and the native verdict's permitted-dispatch condition.
The supervisor observes its same-invocation child exit by SIGKILL before retaining
the old lock, acquiring fresh exclusion and reconciling that same allocation.
The unreceipted full create ID comes from the fsynced checkpoint of that controlled
create call; independent exact-ID inspection and durable receipt publication
precede ordinary cleanup. Names, labels, discovered resources, expired locks or
reconstructed authority after supervisor loss are not acceptable substitutes.
Before-create intent remains retained and refuses another allocation. No restart,
new allocation or ordinary runner recovery capability follows from this exception.

The corrected dispatch checkpoint follows completion and validation of the native
permitted run, then kills the worker before the ordinary runner receives and
publishes its result. It therefore tests interruption after completed dispatch
and before ordinary result publication, not a kill synchronized with a packet or
an in-flight request. Preserve native observations, killed-state evidence,
principal uncertainty and reconciliation receipts separately; do not present the
supervisor's additional checkpoint authority as ordinary crash recovery evidence.

This approval supplies design permission only. Final helper verification, a
scoped commit before launch, applicable fixture authorization and observed runtime
proof remain required under `.94`. The 32-mode matrix and interruption evidence
retain distinct source pins and must not inherit historical receipts. All
readiness flags remain false; no production, broker, deployment or financial
permission is added. No runtime, Docker, network or shared-state operation was
performed by this review. Only this section was appended, preserving every prior
report byte. Parent owns verification, Beads and commit reconciliation.

**Knowledge verdict: Nothing durable.** The bounded experiment and its evidence
limits are recorded in the canonical project plan/report; no portable operational
lesson or corpus change is introduced.


## Exact-hash design delta review: retained allocation registry capacity

Date: 2026-10-10. Final owning plan SHA256:
`eb3f6516ec1bab5cebf9535e249a22358c07c83d88fd471d4a94a53386e84ad9`.
**APPROVE this bounded registry-capacity and supervised lock-reconciliation
design delta.** No blocking design finding remains. Raising serialized registry
capacity from 1MiB to 32MiB retains the independent 1000-allocation,
1000-source-entry, depth-16, strict-schema and private-file controls. These are
maximum bounds, not a promise that every permitted combination fits. Future
capacity exhaustion must still refuse without pruning receipts or resetting state.

Inspected the exact plan appendix and the allocation diff, schema validation,
publication and poisoned-handle ordering. `_publish` checks serialized length
before creating its temporary file; `_save` already poisons the handle, and
`begin_allocation` must succeed before the runner reaches create. This supports
the reported failure mechanism. The reported 32 terminal rows and 1,019,046-byte
live registry are parent evidence; this reviewer did not inspect or mutate it.

The narrow same-session exception requires verified complete terminal-absence
rows, proof that this failed attempt published no new intent and reached no
create, and proof that no current/competing owner remains. Retain the original
lock separately and preserve registry bytes; never infer recovery authority from
lock age, successful test results or terminal rows alone. Unknown publication or
resource outcome remains blocked. This approves neither a general lock-clearing
command nor automatic recovery.

Before reconciliation or launch, the owner must add discriminating finite-limit
regression evidence, run complete local verification and commit the scoped change.
The `.94` owner must rerun all 32 runtime modes with fresh receipts against the
changed allocation-source digest; previous matrix passes cannot qualify it.
All readiness flags remain false and existing resource/authorization boundaries
remain unchanged. This is DESIGN review only, with no runtime, Docker, network,
registry mutation or PR review performed. Only this section was appended and all
prior report bytes were preserved. Parent owns evidence, Beads and commit closure.

**Knowledge verdict: Nothing durable.** The bound and its qualified local failure
mechanism belong in the canonical project plan/report and acceptance evidence.
