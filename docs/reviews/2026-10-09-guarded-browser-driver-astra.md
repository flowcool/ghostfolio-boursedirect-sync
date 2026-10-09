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
