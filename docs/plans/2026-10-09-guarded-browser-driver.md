# Guarded browser driver: design and capability gate

This amends only held B of the supervised acquisition plan. A and offline C remain
unchanged. No broker login, real credentials, shared browser, production traffic,
or Ghostfolio writes participate in implementation qualification. The design
needs scoped Astra approval for a synthetic capability harness only. Reusable B
remains HOLD until real isolated capability proof exists and a subsequent grounded
reusable design receives exact-hash approval. Planning never replaces that proof.

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
