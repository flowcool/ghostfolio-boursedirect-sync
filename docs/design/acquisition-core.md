# Durable acquisition authority core (offline)

The approved A scope is implemented in `collector/core.mjs`. This is a functional
helper boundary, not a broker connector or permission to use credentials. It never
launches Chromium, sends HTTP or supplies a production enrollment CLI. Browser
integration remains under the separate capability/design gate in the
[acquisition plan](../plans/2026-10-09-supervised-acquisition.md).

`principal` maps an ASCII login to a stable case-normalized SHA256 binding. Auth
state uses the installed OS user's fixed `~/.local/state/ghostfolio-boursedirect-sync/auth`
namespace, independent of run roots and source portfolio UUIDs. An explicit offline
`enroll` call creates immutable private enrollment; later enrollment cannot reset
it. Cooperating processes share an exclusive principal lock. There is no stale-lock
removal, reset, retry, root override or uncertain-state expiry. Different hosts,
changed HOME, intentional state deletion and hostile same-user filesystem access
remain outside this cooperation boundary. No actual enrollment was run during
implementation; all tests use newly owned temporary HOME directories.

A caller acquires the principal, starts a fresh attempt and durably transitions
into password uncertainty before arming a characterized one-use request permit.
`consumePermit` rechecks phase, page/frame epoch, exact URL/method/resource type,
nonce, deadline and redirect refusal, then durably consumes before returning.
Only a later separately approved driver may continue that request after return.
Unknown/null source-contract roles stay disabled. A source-contract evidence
reference is supplied operator data, not an authenticated proof that it is true.
No actual authentication endpoint is guessed or enabled by this component.

The request controller accepts the existing `password_accepted` app-method phase
only with its own characterized role and one-use durable permit. A separately
constructed controller is required for that action; a prior controller cannot
be rearmed. It does not reuse the initial password permit or grant an unknown
intermediate request.

Password challenge and authenticated success transitions require consumed
requests; the caller still owes actual observed success evidence. Both request
and observation are trusted helper inputs here, not a browser-origin guarantee.
A crash or failed persistence retains an unfinished state and fences the next
attempt. Closed success alone permits a separate later deliberate attempt.
Locks are private mkdir entries; journal publication uses fresh exclusive temporary
files, fsync, rename and parent-directory fsync. Each newly created auth-directory
ancestor also fsyncs its parent before enrollment can succeed. Existing hard-link/symlink aliases,
wrong modes/owners and invalid schemas refuse. Partial enrollment is retained and
requires manual recovery, never automatic erasure to facilitate a retry.

Releasing a lock permanently revokes its in-memory handle before removing the
lock or synchronizing its parent. Removal, open, fsync or close failure leaves
that handle unusable for journal reads or mutations. Repeating release with the
closed handle cannot remove a subsequent owner's lock. If removal itself fails,
the retained lock remains a manual-recovery condition; the helper never retries
with stale authority or clears an uncertain journal to regain access.
A failed `closed_success` publication retains the owned lock even when rename
already exposed the success journal. Release first durably creates a private
`release-pending` guard, then removes the lock and synchronizes the directory.
Only verified release removes the guard; any release failure leaves it fenced.
Guard removal has no subsequent fallible persistence step: crash resurrection
can only conservatively refuse. Existing guards require explicit recovery;
ordinary acquisition never clears them.

`otpFromEnvironment` consumes explicit provisioned TOTP or a timestamped static
OTP, never both. It enforces integer clock, same 30-second step, age at most 20s,
not future and at least 5s remaining. TOTP is strict Base32/SHA1/30s/six digits.
The pure `totp` arithmetic helper is separately verified with RFC6238 reference
vectors; it alone is not the operational near-expiry gate. No seed was retrieved.
`diagnostic` is the sole public error shape: literal allowlisted fixed codes and readiness
false; low-level filesystem/parser errors must pass through it, not be printed.

Run `npm ci --prefix collector --ignore-scripts --no-audit --no-fund`, then
`npm test --prefix collector`. YAML 2.9.1 is pinned with integrity in the lockfile.
CI also pins setup-node's v4 commit and Node20. Tests block socket/TLS/HTTP/fetch/
WebSocket/DNS/datagram entrypoints before imports and forbid subprocess/browser
startup except one exact owned Node principal-contention fixture with isolated
HOME/minimal env and the same bootstrap. They cannot access the broker, Docker or
shared Beads. The existing socket-forbidden Python suite remains mandatory.

Rollback: revert the scoped implementation commit; keep real enrollment/attempt
records and locks intact. Any future manual reconciliation must establish exact
request outcome outside ordinary acquisition. No financial rollback or production
permission is supplied by this helper.

## Internal native synthetic composition

The broker exports retain their fixed origin, call signatures, principal hash,
auth namespace and schema-1 journal. A module-private policy identity factors
the same durable operations and request-controller decisions for the separate
development-only `nativeComposition(origin, allocation)` factory. It accepts
only a canonical explicit-port loopback origin and an allocation UUID. No
operator command or environment setting can select that policy.

Synthetic principal state uses the fixed `synthetic-cdp/auth` sibling namespace
and schema-2 policy/origin/allocation bindings. Handles are immutable private
identities; copied, foreign-instance, broker/lab and released handles refuse.
Copied journals, changed origins and unfinished attempts refuse reenrollment or
restart. The lab composition binds its real durable consumer internally; the
caller cannot supply a replacement consume function. Native URLs, methods,
resource types and CDP IDs are retained without broker/fixture translation.

`nativeCapture` evaluates an armed native request/Fetch-network/loader/commit/load
chain and checks active ownership/loader before and after bounded serialization.
Synthetic document markers test only the fixture adapter, not broker-document
authenticity. The pure native verdict rechecks saved observations without network
or subprocess access.

The opt-in `scripts/run-native-cdp.py` runner has no broker input or secret reader.
Its fixed private host allocation registry requires explicit first initialization,
intent fsync before create and independently inspected full-ID receipt fsync before
copy/start. Unfinished allocations exclude new runs across output directories;
failed publication retains a poisoned lock for manual recovery. Cleanup requires
the receipt, unchanged daemon and exact configuration. It preserves a private
principal archive before removal and requires exact daemon absence before terminal
registry publication. No name discovery or failed-inspection fallback grants
cleanup authority. The earlier harness remains historical proof under its own
scope, never final-code qualification of this composition.

Design authorization and final-code proof requirements are in the appended
native composition amendment of the [owning plan](../plans/2026-10-09-guarded-browser-driver.md)
and its [independent design review](../reviews/2026-10-09-guarded-browser-driver-astra.md).
Offline tests and source hashes cannot replace a fresh pinned sandboxed runtime
matrix, actual allocation kill-point observations, cleanup evidence or the
separate source/credential/egress/security gates. All readiness fields remain false.
Rollback code with a scoped revert, retaining principal journals and allocation
records; fixture cleanup requires separately applicable exact-owned authorization.

## Private vault delivery composition

`vault-worker.mjs` implements the approved fixed version/config/login/unlock/sync/
exact-item sequence. Its executable hash/version and immutable item/principal/
account reference are explicit inputs. It requests one item-ID TOTP only after
the bound challenge request, validates the supported profile privately, and
exports neither raw item nor seed. CLI errors become fixed codes. The trusted
process adapter captures bounded private output and supplies minimal child envs.

`private-channel.mjs` uses anonymous trusted stdio with bounded strict JSON,
timeouts and permanent fencing. The collector launcher constructs BD credentials
in its child's initial environment inside the container; Chromium gets a separate
credential-free environment. Container metadata, argv and Docker logs contain no
secrets. Host/daemon owners remain trusted.

The opt-in `scripts/vault_composition.py` composes two separately owned non-root,
network-none containers with fake vault commands and an actual current Chromium
headless shell. Supply the exact local image ID, resolved Chrome version, qualified
seccomp profile and a new ignored `tmp/` output directory. It retains pre-create
intents, inspected pre-start full-ID receipts and enrollment/journal evidence;
cleanup uses only receipted IDs and verifies daemon absence. Missing/uncertain
receipts remain fences. The source/account/principal records are invented fixtures.

Saved qualification results and their input hashes live in
[`../verification/vault-composition.yaml`](../verification/vault-composition.yaml).
Reuse matching successful evidence; only changed inputs or missing scenarios need
new execution. The project AGENTS policy owns current Chromium selection.
This composition proves delivery plumbing, not real vault visibility, broker
source acceptance, production egress or permission to authenticate. All readiness
flags remain false. Keep real enrollment, vault/source and external security gates.

The source-owned `bitwarden-cli.mjs` adapter connects the same worker engine to
an existing Bitwarden CLI container; it needs no new image or vault service.
`bitwarden-cli.sh` receives command-specific secrets through bounded private
stdin, and the CLI receives a cleared minimal environment. The adapter verifies
the CLI executable hash and permits only the fixed sequence for the bound UUID.
Failures or overlapping calls fence the adapter and request exact owned shutdown.
An optional SSH transport uses a trusted provisioned destination, quoted arguments
and strict host-key checking; no host or SOPS path is embedded in source code.
The trusted owner must attest the durable full-ID receipt, image/CLI pin, private
appdata, disabled logs/core dumps and qualified egress before every invocation.
Infra supplies access facts and operational wiring; this repository owns adapters
and acquisition control code. Actual vault visibility, source observations,
enrollment, profile and cleanup qualification remain separate operational gates.
Synthetic adapter evidence and reusable input hashes are retained in
[`../verification/bitwarden-cli.yaml`](../verification/bitwarden-cli.yaml).

The operator may supply the item name `boursedirect.fr` instead of a UUID.
Provider schema 2 expresses this authority with a binding containing only that
exact name and the trusted account-configuration reference. The fixed worker
uses one `list items --search boursedirect.fr` call, requires one exact live login
item, and validates its UUID, canonical broker URI, credentials and OTP profile
before delivery. It derives the principal hash from that selected login and pins
the resolved UUID for the single delayed TOTP. No whole-vault listing, fallback
after a failed pinned lookup or automatic retry is added. Schema 1 retains its
pre-pinned identity contract. Named resolution does not qualify live ownership,
egress, enrollment, account configuration or source observations.

The opt-in `scripts/qualify-bitwarden-cli.py --ssh <trusted-destination>` checks
the existing pinned CLI in one newly owned container with fresh tmpfs appdata,
no network, credentials or authentication. It retains one private pre-create
intent and inspected full-ID receipt before start, then checks binary hash,
version and the declared server read/set roundtrip. Cleanup re-reads the receipt,
verifies the daemon and configuration, removes only that full ID and retains
explicit absence evidence. Its fixed ignored evidence directory refuses a
second allocation; uncertain intents remain for manual recovery. This metadata
proof does not establish cloud API routing, vault visibility or qualified egress.

The incremental application Compose now includes a source-owned CONNECT-only
vault egress helper using the already available pinned Python image. Its exact
US-cloud destinations are grounded in official Bitwarden CLI tag
`cli-v2026.6.0`, commit `e6293ff2bc85123e9baaa998cf1543030ec5d9f0`:
`node-api.service.ts` reads lowercase `http_proxy` or `https_proxy` and constructs
`HttpsProxyAgent`; the default environment supplies identity/API cloud origins.
The CLI adapter accepts an optional attested numeric proxy endpoint and adds only
`https_proxy` to its cleared execution environment. Worker credential sequencing
and secret stdin delivery are unchanged.

The helper bounds headers, concurrent connections, DNS answers and tunnel time;
it refuses non-CONNECT requests, unrecognized authorities, ambiguous headers and
non-public/transition addresses. It validates every DNS answer before connecting
once to a literal address and does not terminate TLS or log traffic. Infra still
owns the enforced worker network-namespace IPv4/IPv6 deny policy, exact proxy IP
exception, denied embedded DNS, independent network/container receipts and
cleanup. Syntax and offline refusal tests do not prove live egress. Real routing
must be proved without secrets before independent vault access. Rollback reverts
the scoped source commit and removes only newly receipted operational resources;
never change shared services or discard authentication journals.

Provider schema 3 implements the independent vault-access milestone from the
interactive amendment. Its binding contains only the operator's exact
`boursedirect.fr` name. It reuses the same executable pin, fixed private-stdin
login/unlock/sync/search sequence and strict unique live item, URI, credential and
TOTP-profile validation. Inspection accepts a bounded list of inert item URI
aliases only when at least one exact canonical broker-origin URI is present. The
first observed canonical URI and alias counts are inspection metadata, not
acquisition URI selection; other alias values are neither exported nor executed.
Acquisition schemas 1/2 keep their single exact bound URI rule. Only private
item/principal/URI/profile metadata is
returned; no login, password, session or seed can be delivered to a collector.
The worker logs out and verifies an unauthenticated status with no retained user
or sync identity before returning. It discards its session, and both worker and
adapter refuse TOTP commands in this mode. The independently owned application
services stay available for later stages; an unverified session cleanup fences
the capability and requires exact affected-runtime shutdown. No importer config or broker enrollment is
created or inferred. Acquisition schemas 1 and 2 retain their mandatory trusted
account reference and broker gates. This separates qualification of the vault
capability from actual broker authentication without weakening either boundary.


## Credential-free public document observation

The explicit `compose.broker-inspection.yaml` overlay grows the preserved laboratory
stack with a separately owned broker-only proxy/network. `compose.lab.yaml` retains
`network_mode: none`; the overlay cannot grant Bitwarden destinations to the
browser or broker destinations to the CLI. The CONNECT helper's default policy
remains vault-only; `--broker-inspection` selects the fixed canonical broker host
on port443. Infra must install and attest proxy-only IPv4/IPv6 namespace routing,
including direct/DNS denial, before any browser execution. Restart alone does not
restore authority. No control ports or secrets are added to Compose.

`collector/lab/public-login-observation.mjs` is an opt-in one-document source
inspection, not an authentication entrypoint. It accepts a numeric proxy and
private routing-receipt hash on stdin under a minimal secret-free environment.
It verifies the pinned sandboxed Chrome version and renderer OS protections,
uses guarded target attachment and Fetch interception before page release,
disables page scripts, and grants exactly one GET Document to the previously
observed public login URL. Redirects, assets, frames, XHR and every POST are
blocked. Their bounded private request metadata records observation without
enabling a role. No credentials, OTP provider, enrollment or broker auth journal
is accessed. Unknown endpoint roles remain disabled.

Stdout is a private bounded evidence envelope for an owning supervisor to capture
exclusively under ignored `inputs/` (0700 directory, 0600 file), not a routine log.
It retains request/response metadata and the CDP response-body representation;
this is not a claim of original wire bytes. Failures retain a partial private
envelope plus fixed stderr codes/counts, and the supervisor must stop the exact
owned browser container if process cleanup or output qualification fails. Source
publication contains only hashes, codes and structural counts. Rollback removes
the explicit overlay and restores the received network-none browser; existing
vault services, auth journals and prior observations are preserved. A public
login GET cannot establish authenticated account or password/app-method/OTP
roles, and all readiness flags remain false.


A later explicitly selected public-page observation may accept up to32 immutable
asset tuples (`observed_assets`: exact canonical URL plus Script/Stylesheet/Image/
Font type) and `reference_evidence_sha256` alongside the route receipt. The
private owning supervisor verifies those tuples against the retained public HTML
references or previously paused metadata before supplying them. In this mode,
page scripts can execute only after interception is installed; the initial public
Document and each known asset GET are admitted once, in the owning session/frame,
without redirects. XHR/Fetch, every POST, unknown assets and foreign targets remain
blocked. Bounded target metadata, responses and a separately marked UTF8 DOM
serialization retain source-discovery evidence. Authentication remains disabled;
this is not recurring collection or permission to fill credentials. The default
two-field input still grants only the public Document with scripts disabled.

### Explicit immutable alias binding

Provider schema4 adds a pinned-UUID acquisition mode. Its binding retains the
schema1 item UUID, expected name, selected canonical broker URI, principal hash
and account-configuration reference, adding `uriAliasesSha256`. The worker hashes
the ordered URI/match metadata privately after strict bounded validation; omitted
and null match modes have the same representation. Every alias and match mode is
pinned. Adding, removing, reordering or changing metadata refuses delivery.
The selected URI must appear exactly once. Other aliases never supply a command,
navigation destination or fallback. Credentials/profile then pass the existing
strict UUID/name/principal/TOTP checks. The CLI uses `get item UUID`, and delayed
one-use TOTP uses that same UUID. Schemas1/2 retain their single-URI requirements.

Metadata-only inspection now includes this hash, without exporting extra URI
strings, credentials, a seed or a code, and retains logout/status verification.
The earlier successful inspection remains valid for its original fields; its
missing alias hash cannot be invented from alias counts. Schema4 requires a
fresh privately verified metadata hash and explicit configuration before use.
Synthetic worker/CLI verification proves the new mode's logic, not a real vault
session or broker readiness. Source/account, enrollment, runtime, egress and
external security-review gates remain required; no real schema4 configuration or
credential delivery is activated by this amendment.

## Native community CLI integration

Florent confirmed the native ENV contract on2026-10-11 through the grilling
workflow: a reproducible community CLI image, operator-supplied vault ENV,
automatic named item/identity binding and one session per execution with verified
logout. This explicitly supersedes the earlier ban on container ENV secret
injection for this native entrypoint. The private operational lab adapter retains
its existing stdin contract and historical qualification evidence.

`compose.yaml` now owns the native `bitwarden` service. The preserved
`compose.lab.yaml` owns the former dedicated lab services. The native image uses
the official architecture-specific CLI release archive with fixed checksum;
no private image, host provisioning or remote Docker executor is required.
Only the worker receives vault ENV. It clears those fields from its process
environment after reading them and supplies a minimal environment per CLI call.
Docker administrators remain trusted because Compose stores initial ENV in
container metadata. Tmpfs appdata is independent per execution and never mounted
from another application's session. Default native HTTPS egress is ordinary
container connectivity, not evidence of the lab's proxy-only confinement.

Provider schema5 is metadata-only inspection for an explicitly configured exact
item name. Schemas1–4 retain their prior binding rules. After unique live item,
broker URI, credential and TOTP-profile validation, inspection logs out and
verifies unauthenticated status. It exposes no credentials or OTP capability.
The immutable private native binding retains vault origin, configured name, UUID,
principal, selected URI, full alias hash and profile. Exclusive locking and
durable publication preserve partial/uncertain binding files as refusal gates;
changed identities never cause automatic rebinding. The public `inspect` command
reports fixed codes/counts only.

`nativeVaultExecution` composes the same worker with local CLI subprocesses.
A trusted source-qualified in-process consumer uses schema4 and receives only
the bound credential projection plus the single delayed same-UUID code method.
Every completed or failed execution attempts verified logout once after a login
was reserved. A failed executable verification never invokes the unverified
binary during cleanup. Uncertain logout refuses without retry; owned one-shot
container exit discards private tmpfs. Closing while an operation is pending
refuses instead of issuing overlapping CLI commands.

The public `connect` command currently runs native vault inspection and retains
the identity binding, then refuses broker authentication with exit2. Its future
guarded source driver must consume this same connector; no vault success is
converted into source permission or a claim of authenticated acquisition.
Existing broker journal, actual request-role/account/resource qualification,
external security review and financial activation gates remain separate.

Rollback reverts the native source/Compose commit, retaining the private binding
and all historical broker journals. Native ENV configuration contains no
credential export, alternate executable or arbitrary command interface.

## Native source-request envelope inspection

`inspectSourceRequest` is an offline boundary for the authorized bounded
qualification profile. The trusted owner supplies an exact source-pinned
candidate and a native paused request from its owned page/frame/session.
It verifies exact URL/method/type, unambiguous JSON Content-Type, bounded
unique-key payload and the current in-memory principal/password or delayed code.
TOTP requests require `trusted_device=false`; login requests require a null
redirect. GET roles cannot carry a credential projection. Its private result
contains structural keys and source/native metadata only, with dispatch and
readiness false. It returns no body, header, credential-derived hash or secret.
Source hashes supplied by the caller are provenance references, not proof of
independent source qualification; the trusted supervisor still verifies them.

This helper never arms a role, consumes a permit, sends a request or launches
a browser. The guarded runtime must combine inspection with actual source
observation, durable one-use consumption, independent response/success evidence
and exact owned cleanup under the online acquisition amendment.

The existing CLI adapter now supports verified logout/status after acquisition
with or without an OTP request. Closing before the code permanently skips its
slot; logout failure fences the adapter and stops only its attested container.
This closes the delivery session rather than retaining it for another attempt.

The source-owned metadata worker uses `sshCliTransport` directly for CLI stdout.
Its Python supervisor provides private initial provisioning and attestation/stop
callbacks, then receives the final metadata projection after verified logout.
The supervisor never relays full items, seeds or CLI response bodies. Synthetic
IPC coverage stands in for SSH inside the worker process and asserts that the
supervisor observes only control metadata, while logout failure still fences
the exact owned CLI.

## Separate post-2FA credential finalization

Source schema2 adds a separately qualified nullable `finalize` role. The owner
selects `post-2fa-finalization` when starting the attempt, before credentials or
permits. This protocol is retained in the existing principal journal and cannot
be downgraded by swapping in a schema1 source. Historical schema1 journals and
the synthetic two-request protocol remain compatible; no namespace is changed.

For this protocol, a consumed OTP request can advance only to `otp_accepted`.
The owner then records `finalization_uncertain`, arms a distinct exact finalization
permit and consumes it durably before the one credential-bearing continuation.
Only that consumed request plus separately verified broker success may advance
to `authenticated`. The controller accepts finalization with its usual owned
frame/epoch binding, duplicate reservation and failure fencing. It does not
reuse the OTP permit or retrieve a second code.

Interruptions in either new state retain the principal fence. Unconsumed
requests, failed durable publication, duplicates and failed continuation cannot
declare success or restart an attempt. Authentication still requires observed
success; these callable offline helpers neither implement nor activate a browser.

### Method qualification before OTP

The first schema2 password permit durably snapshots whether a network app-method
role is required, together with the initial page/frame epochs. A required role
must consume its own permit before entering `otp_uncertain`; later source changes
cannot replace it with a local selection. With no network role, the observed
frontend's local TOTP selection instead needs `confirmLocalAppMethod`: a separate
durable receipt asserting independently checked native DOM, exact initial epochs,
owned session/frame, pinned source hash, TOTP selection and an untrusted device.
Missing, duplicate, foreign-frame or failed-publication evidence refuses OTP.
No synthetic network request or permit is invented for a local DOM action.
Historical legacy attempts retain their prior behavior. Existing post-2FA records
are still readable; missing method qualification cannot authorize new progress.

### Paused authentication qualification gate

`brokerAuthenticationComposition` binds one cooperating authority and its handles
to `source-authentication-gate.mjs`. The bounded gate accepts only the three
source-described POST/XHR destinations for initial credentials, TOTP and final
credentials. The trusted owner separately proves current source bytes, runtime
ownership and actual response outcomes. The gate compares the native body in
memory, retains structural evidence, arms the exact durable permit and consumes
it before continuation. It binds credential requests to the journal principal,
clones inputs before awaiting and reserves each phase at ingress. Duplicate or
HTTP-auth events fence held actions; HTTP authentication is cancelled without
credentials. Retention, fsync, timing or continuation failures stop the owner.
The gate never advances authentication state or declares successful connection.

The bounded qualification profile permits inspecting an already paused expected
request before arming its exact permit. Ordinary operational controllers keep
their previously qualified before-fill gate. Synthetic runtime qualification
uses an internally registered loopback policy and separate synthetic namespace;
the broker factory exposes no operator-selectable origin or state-root override.

### Native qualification building blocks

`source-native-session.mjs` composes the pinned private CDP pipe with existing
startup guards and request/response interception. Native default realms are
bound by their unique context ID; foreign frames, HTTP redirects and new targets
fence the session. Response interception permits durable protocol publication
before frontend callbacks issue the next native step. HTTP authentication is
cancelled. The stop callback verifies owned exit before closing the pipe; final
close separately drains handlers to avoid a handler waiting for itself.

The dedicated `lab/source-browser-pipe.mjs` launches only the fixed attested
Chromium with a numeric owned proxy and credential-free environment. It pins
process start identities, checks renderer sandbox state and bounds the lifetime.
Renderer command lines can be flattened by Chromium; classification recognizes
both space and NUL separators. Native bytes remain on private stdio. Only fixed
process/sandbox/exit codes and counts go to the private control stderr channel.

`source-authentication-dom.mjs` restricts credential fill to the two observed
blank login controls in one form. Local TOTP requires the observed heading,
exact six ordered empty numeric inputs and the explicit distrust control. The
source's multi-character handler receives the code once; no additional button
click or second fill is performed. Results expose only structural proof.
`source-authentication-response.mjs` decodes bounded native UTF8/base64 bodies
internally and projects known challenge, OTP acceptance and one same-origin
final source-page destination; no response body, token or header is exported.

`source-read-gate.mjs` permits only source-pinned preliminary/state/systems/config
reads or independently qualified document GETs. Each request's structural evidence
and distinct consumed grant precede continuation. A trusted owner must prove
actual candidate provenance and publish grants atomically; a source hash alone
is not lookup authority. Duplicate grants, failure or fencing refuse.

The network-none `lab/source-authentication-runtime.mjs` exercises these primitives
with an invented proxy site and fixed synthetic credentials. Its isolated
synthetic namespace, native IDs, original request URLs, renderer sandbox and
exact exit proof are retained. It does not select a broker origin, use a real
vault or enable an operational connection command. The operational caller still
owes independently bound credentials, current source bytes and both-account
source evidence.
