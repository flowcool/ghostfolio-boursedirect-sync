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
