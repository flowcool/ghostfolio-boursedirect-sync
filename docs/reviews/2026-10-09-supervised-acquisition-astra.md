# Astra design review: supervised acquisition

Date: 2026-10-09. Verdict: **REVISE before implementation**.

Reviewed plan: `docs/plans/2026-10-09-supervised-acquisition.md`, SHA256
`8d1448abccacfba89488879d6ed328bcde0200625707e35d89a58fe625d59535`.
Baseline: `5a39196efb19cef6249bfaac398e6e4d0924e53a`.
This is the required independent design review, not PR review or runtime approval.

The separate JavaScript collector and existing Python document boundary are a
reasonable architecture. The plan correctly preserves unsupported-period gates,
private source handling, exact account/period checks, no Ghostfolio writes, no
seed retrieval authority, and no production tests. The blockers below concern
the implementable security and provenance contract, not the financial model.

## R1 — High: authentication fences must follow the broker login identity

**Evidence:** plan lines 53–70 and 81–82 place locks and retained attempts under
an operator-selected root and opaque account UUID. Account selection occurs
later, at lines 135–139. No durable relationship between the authentication
principal, portfolio UUID and state root is specified.

**Impact:** two portfolios accessed through the same broker login, or a new output
root used for a new collection, can obtain different locks and ignore an earlier
uncertain password attempt. An arbitrary UUID alone cannot establish the claimed
cross-command/process fence. This is an accidental-use problem even with a trusted
operator; it need not involve deliberate deletion or malicious filesystem access.

**Required amendment:** separate the stable authentication state namespace from
run/output roots and portfolio identities. Define one installed private state
root and a private immutable binding to the exact broker login principal (without
persisting the password or publishing the login). Multiple portfolios share that
principal lock. Define how first enrollment occurs and how a changed binding,
root, or missing existing state is refused or explicitly handled outside normal
acquisition. Document that this protects cooperating invocations in that namespace,
not independent machines or an operator intentionally removing state. Specify the
successful completion and manual reconciliation transitions, including a crash
after observed success but before durable success.

**Acceptance owner:** A. Synthetic separate-process tests must prove contention
and retained refusal across restarts, output-root changes and portfolio changes
for one principal, plus independent access for distinct principals. No live login.

## R2 — High: specify a phase/request matrix before enabling authentication

**Evidence:** lines 87–89 include `app-method`, month/account selection and calendar
actions; lines 107–111 permit one POST only for password/OTP form clicks. The
evidence section provides selectors and paths but no pinned authentication form
actions, redirect semantics, challenge-selection method or resource policy.

**Impact:** a form action observed in the current DOM is not by itself a reviewed
authentication endpoint. A permit bound only to action/method/phase is not bound
to the owning frame, submission or request type. Required UI transitions could
also legitimately use a currently forbidden request, causing a safe but unusable
collector. The plan does not establish that they do; that uncertainty must remain
explicit rather than being resolved by broadening permissions during execution.

**Required amendment:** add an explicit state/action/request matrix: allowed
phase, known role/path, owning page/frame generation, request resource type,
method, one-use permit lifetime, allowed redirect outcome and evidence for success.
Bind and durably arm the permit before a click; consume it before allowing the
request; reject an extra or redirected POST, including a method-preserving
redirect. Distinguish static assets from navigations and authentication requests.
Define the application-method selection and temporary untrusted-device behavior
without enabling an account-preference endpoint. Unknown methods/actions stay
disabled. A source-contract gap may be a separately owned operational prerequisite;
it must not be reported as tested live compatibility or silently fabricated in a
fixture. The strict v0 option is to omit headful authentication now, rather than
leave equivalent human-submit fencing conditional during implementation.

**Acceptance owner:** B owns driver enforcement; A owns its pure matrix evaluator.
Tests cover wrong phase/frame, arbitrary same-origin form action, extra POST,
redirected POST, failed journaling, unknown challenge and rejected/uncertain OTP.
State explicitly which component owns each criterion, without duplicating it.

## R3 — High: prove popup protection before its initial request

**Evidence:** lines 94–100 require interception on every owned page before
navigation; lines 140–143 allow both a newly created and reused broker popup.
No mechanism is specified for enforcing policy before the first request of a
site-created target. Registering a page or popup observer is not itself that proof.

**Impact:** later URL validation and safe capture do not undo an already issued
request. The initial popup, a frame or a worker must not receive a period in
which the intended application request guard is absent.

**Required amendment:** choose and document a supported target-initialization
mechanism that installs the guard before execution/network navigation, or constrain
v0 to a precreated owned target whose interception is already active and reject
other target creation. Unexpected targets must not be treated as ordinary pages
that are safe once inspected. Make the worker/service-worker handling explicit:
an unsupported disabling mechanism fails the prerequisite when the guarantee
depends on it. Keep the existing honest distinction from an OS/browser sandbox.

**Acceptance owner:** B. An isolated synthetic real-browser test must show zero
dispatched forbidden initial popup/frame requests and denial of a second auth
request. Mocks alone cannot prove target-startup ordering. No production domain
is used; pin the Chromium/runtime used for this evidence.

## R4 — High: bind freshness to the requested document transition

**Evidence:** lines 90–92 bind handles to generations; lines 140–144 accept a new
navigation/content generation since the triggering click. FINDINGS section 12
demonstrates actual popup reuse. Both source formats have the same four ledger
headers, as confirmed by the existing `parse_statement` and `parse_contract_note`.

**Impact:** an unrelated DOM change, a pre-existing in-flight response, or a late
response to an earlier click can advance a generic content generation while
leaving an old document eligible for capture. Matching account/month alone is
especially weak for two notes on the same day or a revised monthly document.

**Required amendment:** define a single outstanding capture ticket binding the
selected account, requested role/date, originating frame generation, clicked
observed target, exact allowed request and resulting document commit/load token.
Arm it before clicking. Reject unrelated commits, pending earlier navigations,
multiple candidates, unexpected target switches and mere DOM mutation as proof
of freshness. A same-document update requires separately characterized evidence;
otherwise v0 refuses it. Serialize and validate one immutable byte result before
publication. Validate every note group's date against the requested day and use
the existing role-specific parser, not headers alone.

**Acceptance owner:** C. Synthetic tests cover reused popup, earlier delayed
response, unrelated DOM mutation, same-day distinct documents, revised same-month
bytes, duplicate candidate targets, wrong account and one mismatched note date.
Freshly served identical bytes may be accepted when transition provenance is
proved; byte inequality is not the freshness rule.

## R5 — Medium: make isolation and component completion directly verifiable

**Evidence:** lines 173–191 require socket-forbidden mocks and an offline browser
bench, but only state that Node tests run without network. The same delivery list
contains source-contract, sandbox and security prerequisites without assigning
each a distinct acceptance owner.

**Required amendment:** state the enforcing mechanism for no-network Node unit
tests and for the opt-in browser/container bench. A test command is not a network
boundary. Use newly owned synthetic resources, temporary isolated HOME/state/
profiles and a minimal environment with no real BD/Ghostfolio/Beads credentials
or shared mounts. Browser proof should operate with OS-level outbound networking
disabled and local synthetic content; ordinary CI must not start live collection.
Add a compact component-to-criterion table, a named owner for source-contract gaps
and the required pre-merge security review. Retain root-epic end-to-end acceptance.

The Docker deliverable must retain the sandbox requirement; a sandbox failure is
a failed prerequisite, never evidence justifying `--no-sandbox` or host relaxation.

## Implementation clarifications to retain

- Define the OTP timestamp field, clock/freshness bounds and near-expiry behavior.
  A process cannot receive a refreshed environment value from its parent after
  launch. Static `BD_OTP` therefore has a bounded usability window; expired codes
  must stop, and supplying a seed remains an explicit operator choice.
- The broker's document HTML may contain more than the ledger. Define permitted
  retained content and treatment of hidden token fields, scripts and token-bearing
  links; do not claim credential-free persistence solely because the popup is a
  financial document. Any transformation needs distinct acquisition provenance.
- Apply the existing private-publication protection to qualification outputs and
  every captured config/source input, including hard-link aliases. Exclusive new
  run directories are useful but do not automatically protect a separate output
  command. The indexed KB preservation concept is directly applicable.
- Preserve the distinction between privately captured bytes, completed bundle,
  parser acceptance and import readiness. Qualification must reject duplicate or
  unreferenced manifest entries, path escapes and partial runs; completion is the
  final durable publication step after all listed files are complete.
- Codes-only diagnostics must cover stderr, startup/validation failures and child
  processes as well as the normal stdout protocol. Any subprocess Python helper
  also gets a minimal environment, not inherited broker credentials.

## Evidence, limits and disposition

Read: AGENTS.md, CLAUDE.md, security rules, acquisition amendment, original reviewed
manual-import plan, FINDINGS sections 12/13, the exact new plan and targeted parser
functions. No private financial files, credentials, browser sessions or Beads
mutations were accessed. No broker/Ghostfolio tests were run. An attempted public
Puppeteer documentation lookup failed and is not used as evidence; the browser
findings above are explicit design/proof obligations, not claims about an observed
vulnerability in a particular Puppeteer release.

KB lookup followed `bundle/index.md` to the topical indexes and
`operations/ghostfolio/saved-input-report-preservation.md` (stable, verified
2026-10-09, stale after 2026-12-31). **Knowledge verdict: Used and sufficient.**
The concept supports preservation criteria without copying its canonical details
into new KB content. Remaining findings are specific to this proposed design.

Resolve R1–R5 in the plan and submit its new exact hash for design re-review.
This report does not authorize implementation, live collection, seed export,
Ghostfolio writes or merge. Parent session owns Beads routing, commits and final
session reconciliation; only this report was authored by the reviewer.

## Re-review of amended contract

Reviewed SHA256:
`54b279c63e3b0cb9e2af78a21396a39e1c4771c0f3a7f3bd3e119d95e3dd19bb`.
Date: 2026-10-09. **Scoped verdict: APPROVE A and offline C; HOLD browser
integration B pending a separate capability/design gate.** This supersedes the
initial blanket REVISE only for the independently implementable scopes below.

The new normative R1–R5 section explicitly supersedes the earlier shorthand.
Its principal enrollment, fixed per-user state namespace, explicit migration
limits and cross-portfolio locking resolve R1 at design level. The request matrix,
separate characterized source contract and disabled-by-default unknown auth roles
resolve R2 for implementation of the pure policy. Removing headful authentication
and describing caller-owned session authority avoids implying that piped stdin
proves human presence. Actual broker compatibility remains an operational gate.

The exact request/loader-bound ticket, refusal of DOM-only mutations, all-note-date
checks and filtered DOM provenance resolve R4 at design level. The explicit
isolated environment, unit network stubs, opt-in network-none real-browser bench
and sole-criterion owner table resolve R5's acceptance ownership problem.

### Approved implementation scope

- **A:** pure validators, principal enrollment and isolated durable authentication
  records, cross-process locking, state transitions, one-use permit evaluator,
  fixed-clock OTP tests and filesystem preservation. Test state must remain under
  an isolated HOME; no live enrollment or authentication is part of acceptance.
- **Offline C:** bounded bundle schema, immutable synthetic capture-ticket
  evaluator, role-specific Python byte qualification, filtered-document helper,
  digest/account/date checks, exclusive manifest/config proposal publication and
  input preservation. Ticket events are trusted injected synthetic inputs until
  an approved B driver can supply them. Passing these tests proves the evaluator,
  not real-browser freshness or operational source compatibility.

These parts may proceed without browser integration. They must not expose a
placeholder online implementation, instantiate Chromium or accept real broker
credentials in a synthetic test. C closure may cover only its explicitly offline
criteria; any real-browser integration criterion retains its sole owner open.

### Remaining B gate: do not defer architectural viability to component close

R3 now correctly identifies the required ordering and admits that it is unproved.
However, selecting a browser-level CDP initialization mechanism while saying
"inspect the pinned implementation" and "B does not complete" still leaves a
material architecture decision until implementation. A target manager that resumes
execution before the new guard is ready cannot be repaired merely by adding a
later public target-created observer.

Before browser integration is authorized, add a distinct bounded capability/design
gate. It must identify the exact Chromium build and controller/package revision,
the sole owner of target attachment/resumption, the public supported control path,
and how the initial target, new popup, frames and workers are held or rejected
before requests. Source inspection must establish the intended ordering; an
owned synthetic network-none experiment must then discriminate it from an
unprotected first request. Permission for that isolated experiment is not
permission to use real credentials or the broker.

The parent reports that the pinned Puppeteer 24.43.1 TargetManager resumes targets
without awaiting external guards; that report supports investigation, not a claim
that this reviewer has yet inspected those bytes. A separately owned sole-client
CDP pipe controller is a possible alternative, not an approved replacement design.
Keep B implementation held until the chosen mechanism has its own evidence and
design approval. Failure must preserve this hold, not relax the network/sandbox
boundary or count a mocked driver as complete.

### Required final plan alignment

1. Replace the unconditional A/B/C sequence with A and offline C approval plus
   the separate capability/design gate before B browser integration. Preserve all
   browser-dependent criteria under open owners until their proof exists.
2. State explicitly that multiple preserved captures for the same role/date are
   retained evidence but make qualification ambiguous. No automatic revision
   selection or silent replacement is implied by repeat capture. A qualified
   bundle needs one unambiguous source selection under the preserved evidence
   rules; if no selection mechanism exists in v0, refuse that bundle.

Neither item requires a broker test. Submit the aligned exact hash for the final
scoped verdict before coding. The knowledge verdict remains **Used and
sufficient**; these amendments concern the canonical project design, not a new
portable operational concept.

## Final exact-plan disposition

Reviewed SHA256:
`aa16144cc6f9bf4b9ed82db485004a3d3e389d33c3a40f0c96361ea2d4f78317`.
Date: 2026-10-09. **APPROVE A and offline C. HOLD B browser integration.**

The final scoped-disposition section now makes the separate B capability/design
gate an explicit dependency before reusable browser integration, records the
parent's pinned TargetManager inspection, and treats a sole-client CDP pipe
controller as a candidate requiring its own grounded design and review. That
adequately resolves the remaining plan alignment; this review does not approve
that candidate or independently certify Puppeteer's runtime behavior.

The final plan also explicitly refuses duplicate role/date entries during bundle
qualification while preserving prior captures, with no automatic revision choice.
This is a conservative, implementable policy. The offline scopes approved in the
preceding section may now be implemented sequentially, with their full owned
tests and evidence. Their approval does not include Chromium startup, live broker
collection, real credential provisioning, seed retrieval, production enrollment,
Ghostfolio writes or a claim that online collection is functional.

B remains held until its capability owner provides exact runtime/controller pins,
supported attachment/resumption ordering, isolated first-request evidence and a
new Astra-approved B design. Source-contract operational compatibility and the
pre-merge security review remain separate gates. No further design amendment is
required to begin A and offline C at this exact hash.

Review artifact only; parent owns commit, Beads and operational incident routing.
Knowledge verdict: **Used and sufficient**, unchanged from the indexed lookup.


## Exact-hash design review: portable Bitwarden delivery

Date: 2026-10-09. Initially reviewed plan SHA256:
`e5a31cd0b2886f474c9e9f977c1b7bd48a61d405cb382b537e1a7c25a56a77a6`.
**Initial verdict: REVISE the delayed-OTP timing contract.** This records the
reviewed initial bytes and two findings communicated before the author amended
the plan. The final re-review below gives the superseding exact-hash disposition.
This is independent DESIGN review, not PR review or operational authorization.

### R6 — Qualify the TOTP parameters behind the 30-second assumption

The initial amendment validated item ID, login binding, URI and TOTP availability,
then accepted six-digit output with command timestamps inside one 30-second step.
TOTP field presence and output length alone do not establish the configured
period or provider interpretation. The ordinary CLI get documentation is command
source-grounding, not evidence that these parameters match the temporal policy.

Required correction: specify supported TOTP representation/parameters at the
trusted worker boundary and reject unproved configurations/defaults. Seed or URI
parsing stays inside that worker; neither leaves it. Synthetic helper cases must
discriminate incompatible or ambiguous settings, and the pinned provider owner
must prove its interpretation of the accepted profile. No real vault access is
needed to define or test that boundary.

### R7 — Retain freshness until the intercepted request continuation

The initial amendment checked timing at receipt and immediately before arming/fill.
The existing `collector/core.mjs` authority arms a permit for up to 45 seconds,
and `consumePermit` checks that deadline rather than the OTP step. A delayed
persistence callback, input submission or request queue could therefore reach
continuation after the prior OTP check expired. One-use durable authority prevents
replay but does not itself establish freshness of the first request. This is a
contract analysis, not a reproduced live failure.

Required correction: bind the action to its OTP step/expiry, revalidate after
asynchronous work before fill and immediately before continuation, including
after durable consumption. Expiry must fence without refreshing or replaying;
already-consumed authority stays uncertain. Assign timing-result validation to
the helper owner and actual guarded fill/continuation enforcement to a separate
controller owner, with fake-clock tests crossing a held persistence callback.
The same submission rule must preserve both initial-environment and provider
modes. No local check can promise server acceptance or bound network transit.

### Source review and otherwise sound boundaries

Read the infra bridge, worker and runbook at pinned commit `ac3f584`, without
execution, and the local cache of the official Bitwarden CLI documentation for
exact-ID get, API client environment, password-environment unlock and session
environment interfaces. The sources support choosing a fresh implementation of
those interfaces and rejecting name search, repeated TOTP fetches, deployment
wiring and name-based cleanup from the exploration. They do not qualify an
installed CLI, real item visibility or an online runtime. No code was copied.

The exact selected UUID, returned item/principal/URI checks, expected importer
binding and prior enrollment give an implementable account boundary. Provider
mode's one-use private descriptor and nonces correlate an already trusted
supervisor; they do not authenticate an arbitrary service. Mutual exclusion with
initial OTP/seed inputs must reject partial or malformed competing inputs too,
before credential actions; failure must never fall back to the other mode.

Two separately owned runtimes, private post-start pipes, collector-child-only
initial credential environment and no secret Docker create/exec environment
metadata are coherent. The browser process gets no credential environment or
vault state. Disabled log collection, bounded fixed-code errors, no tracing/dumps
and private worker appdata address accidental disclosure while explicitly trusting
the parent, host and daemon. Runtime evidence must prove those properties in final
code; the exploration's behavior cannot be inherited as qualification.

The canonical persistent principal root and each resource's pre-create intent /
pre-start exact-ID receipt preserve the existing guarded recovery contract.
Missing state, unresolved allocation, contradictory ownership or failed cleanup
remain blockers. A discovered name or label cannot authorize resource removal.
The stopped-orphan gap remains explicit and requires separate operator recovery.

## Final exact-hash re-review: portable Bitwarden helper decomposition

Date: 2026-10-09. Reviewed amended plan SHA256:
`a6f12b414f4f7d2cc9e4310763abd079f4ba67d383b39c76412c114aad992e2e`.
**APPROVE the scoped pure-helper design and its three-owner decomposition.**
R6 and R7 are resolved at design level; no blocking design finding remains for
that scope. This supersedes the initial REVISE above only for the amended
portable-delivery proposal, without changing earlier component approvals.

R6 is resolved by private worker qualification of the strict Base32 and
SHA1/30-second/six-digit profile. Explicit URI parameters must match; omitted
parameters need pinned documented defaults and provider verification. HOTP,
unsupported settings, malformed representations and unproved defaults disable
TOTP. The downstream supported-profile assertion remains trusted input, not
cryptographic attestation; the seed and raw URI stay within the worker. Strict
URI parsing must reject ambiguous or duplicate parameters rather than choose a
value. Pure fixtures and the following pinned-provider proof retain distinct
acceptance obligations.

R7 is resolved by binding the action to its observed step and absolute expiry,
checking the same timing rules after transition/arm waits before fill and before
consumption, then checking again after fsync immediately before continuation.
The generic 45-second permit cannot override the stricter OTP bound. Clock
reversal/skew, rollover and insufficient remaining time stop without refresh,
replacement or retry. The corrected retention rule leaves password_accepted
before the OTP transition and otp_uncertain plus any consumed permit afterward;
there is no backward transition or claim to recall an earlier continuation.

The decomposition now explicitly assigns three linked implementation owners:

1. Pure exact-item/profile/binding and bounded one-use delayed-OTP helpers, with
   network/child-forbidden synthetic validation and unchanged initial-env mode.
2. Guarded-controller OTP step/expiry enforcement, including held-consumption
   clock crossings and immediate post-await checks for both credential modes.
3. Portable supervisor/worker and lifecycle composition, with final-code isolated
   fake-vault/browser proof, exact runtime pins, secret-transfer/logging checks,
   pre-start interruption windows and exact-resource cleanup evidence.

The planning owner .84 may close only after these owners are linked with their
acceptance boundaries; the controller timing change must precede composition.
Do not describe pure-helper completion as delivered Bitwarden integration.
Actual vault visibility, source compatibility, shared-clock/provider behavior,
dedicated egress, portable runtime and exact-head security/external PR review
remain their separately owned gates. This review authorizes no vault operation,
seed export, container launch, broker login, production change or Ghostfolio write.

No network, vault, credentials, Docker/browser runtime, production service or
shared Beads operation was accessed during either pass. The reviewer read only
local sources/contracts and the public-document cache, then appended these
sections while preserving every earlier report byte. Parent owns Beads, commits
and terminal reconciliation. Local source inspection is not runtime evidence.

Knowledge lookup followed the corpus/topical indexes, including secret rotation
and Docker's Bitwarden Host-header concept. That concept is stable/fresh but
its bw-serve condition is absent in the chosen CLI-only architecture; it supplies
no new delivery requirement. The previously checked input-preservation concept
remains applicable to configuration and retained evidence. **Knowledge verdict:
Used and sufficient.** No retrieval escalation or new portable operational
finding arose; these design corrections belong in their canonical project records.
