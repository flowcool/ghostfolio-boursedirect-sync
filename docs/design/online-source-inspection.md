# Interactive source acquisition amendment

## Authorization and retained gates

On 2026-10-08 Florent replaced manual-only source acquisition with direct online
inspection by the agent. He authorized use/start of Puppet, and opening ports or
creating a dedicated Docker network if necessary. Infrastructure inventory was
explicitly delegated to ChatGPT Terra. These instructions supersede the original
proposal's ban on broker navigation for G1 evidence collection. The reviewed
proposal remains unchanged as a historical design reference.

The importer remains an offline local-document consumer until a separately
evidenced acquisition design exists. This amendment does not authorize recurring
broker synchronization, orders, transfers, account-setting changes, Ghostfolio
production writes, or production/shared-state agent tests. Source, conversion,
identity, isolated API/recovery and delivery acceptance gates remain required.

Florent further clarified that reuse of his infrastructure is **exploration only**.
The public repository must not require Komodo, these host/container names, private
SOPS paths or the exploration bridge. Any later reusable acquisition code needs
its own configurable environment interface and provenance/license check. Do not
copy private infrastructure wiring into the public importer or treat permission
for this session as permission for an unattended service.

## Acquisition procedure

1. Identify the browser capability from pinned source and actual owning runtime.
   `infra-oh7l` owns the initial Komodo inventory; `infra-p8a4` establishes direct
   embedded Chromium/Puppeteer control through SSH stdin with a private CDP pipe.
   Its first API-only verdict was corrected: the screenshot API is insufficient,
   but the browser executable is usable without new ports. Do not reuse the shared
   Changedetection browser/session.
2. Establish an agent-owned browser context through a private control path, with
   exact startup/shutdown and rollback evidence from infra. Prefer an existing
   SSH/container-exec path. Apply the current lab ownership amendment below for
   service/network changes; do not publish an unauthenticated
   browser-control endpoint to the Internet. No broker connection occurs while
   merely characterizing infrastructure capability.
3. Establish account access. Reuse an explicitly available authenticated session
   only with clear ownership; otherwise use user-assisted authentication or
   credentials supplied exclusively through `os.environ` by an approved private
   credential bridge. Its service unlock material comes from the existing off-git
   SOPS store; the broker item remains in Bitwarden. Do not duplicate broker
   credentials into SOPS merely to accommodate the bridge. A storage pointer is
   enough for coordination. Never ask for
   passwords, OTPs, TOTP seeds or cookies in chat/Beads. This session has not found
   `BD_LOGIN` or `BD_PASSWORD` in its environment. Florent identified the requested
   Bitwarden item as `boursedirect.fr`; require an exact unique item name and verify
   its login URI against the broker origin before exposing fields to the controller.
4. Perform one deliberate authentication attempt after inspecting the actual
   login form. An incorrect password, failed OTP, challenge or uncertain submit
   outcome stops authentication work; no blind retry. Three wrong passwords lock
   the account. An OTP is never replayed after an uncertain response. Do not
   assume TOTP availability authorizes retrieving/exporting its secret.
5. Navigate only the known account-history, statement and contract-note views.
   Read account selectors and popup links; do not construct hidden endpoints,
   submit investment orders or change account/authentication preferences.
   Collect a monthly statement with its matching BUY/SELL notes and adjacent
   months/non-trade examples to establish the existing G1 coverage matrix.
6. Store originals only under ignored `inputs/` (directory 0700, files 0600),
   with neutral aliases. Source HTML/response and a serialized DOM are distinct
   evidence: record the acquisition method privately; a UTF-8 DOM serialization
   must declare UTF-8 rather than retain an incompatible legacy charset. No raw
   document, account reference, balance, URL query, screenshot, cookie or token
   belongs in routine logs, versioned examples or Beads. Derive synthetic fixtures
   and publish structural/semantic findings only.
7. Close agent-owned pages/context and stop a container started for this task
   when the handed-over infra procedure requires it. Do not delete an existing
   user's session/profile or stop unrelated writers. Source acceptance is owned
   by `infra-4g8u.4`; infrastructure capability alone does not satisfy G1.

## Incremental application Compose decision

On 2026-10-10 Florent clarified that vault access is a reusable project capability
to establish first, rather than a one-off workaround for this exploration. The
implementation starts from the future application's project-owned Docker Compose
configuration, using the existing `archivage-bitwarden-cli` artifact as its first
brick. The same Compose grows incrementally to include the browser and collector;
subsequent stages reuse the established services, configuration and qualified
evidence instead of recreating a separate exploration stack each time. This
repository owns the Compose integration and acquisition code; infra supplies
host, image availability, network and secret-provisioning wiring. Reuse the
existing artifact and CLI adapter instead of building another worker or image.

The vault-access milestone is one independent session resolving the unique live
`boursedirect.fr` item, verifying its broker URI and required fields, with exact
owned lifecycle and cleanup evidence. This milestone does not require tearing
down and rebuilding the application stack for every later stage. Broker
authentication and Ghostfolio account binding retain their separate gates.
Application Compose ownership does not authorize reuse of BillCollector's live
session/appdata or an unattended broker schedule. The concrete network and
secret-provisioning wiring must satisfy the existing requirements before access.

See the [domain vocabulary](../../GLOSSARY.md) and the
[source-owned delivery contract](acquisition-core.md).

## Direct lab ownership and connection replay amendment

On 2026-10-11 Florent authorized this project's agent to operate its dedicated
lab directly through local SSH, including owned container lifecycle, logs,
networks and necessary ports, without an infra-agent relay. This supersedes the
earlier requirement to route every lab change through an infra issue. Shared or
production services, destructive operations and financial writes retain their
separate authority gates. A private SSH/container-exec control path remains the
default; any required port must have a bounded purpose and exposure.

The [canonical connection procedure](../operations/source-connection.md) owns
resumption, exact-resource attestation and bounded recovery. Its source-owned
entrypoint reads one private project inventory. Active private control code and
mutable receipts live under `inputs/lab/`; prior exploration controllers are
archived there as provenance. Infra remains the authority for host/secret/network
facts, while this project owns its lab operation and connection control. Public
code must remain independent of private host names and provisioning paths.

Reuse successful unchanged source, vault and runtime evidence before investigating
the first unqualified stage. The successful password/application-TOTP exploration
of 2026-10-08 remains evidence; it does not establish a live session or qualify the
current collector's unobserved requests. Account discovery must include the
declared PEA and PEA-PME and establish distinct verified bindings; personal
identifiers remain private. The replay command explicitly refuses authentication
while its request roles and credential-delivery gates are unqualified.

## Credential-free public bootstrap qualification

The saved 2026-10-11 public document contains an inline loader using `Date.now()`
for the cache version of `/apps/auth/production/auth.js` and `auth.css`.
An exact historical full URL therefore cannot replay this public bootstrap.
The opt-in public observation profile permits each of those two files once,
after the sole public document, in its exact owned session/frame, with GET and
the matching Script/Stylesheet type, no redirect, and only a thirteen-digit
`version` timestamp generated within the current bounded observation. No other
query key, path or origin is accepted. The ordinary exact-URL policy and inert
document mode remain unchanged; the latter cannot select this profile.

The private operator must pin the actual loader evidence before selecting the
profile. This amendment qualifies only credential-free public assets. Password,
application-method, OTP, account and financial-resource requests remain disabled
until their separate observations and delivery gates pass.

### Blocked form request characterization

The opt-in source observation can exercise the independently observed login form
using two fixed dummy markers. It refuses prefilled, foreign, duplicate, disabled
or mismatched-form inputs before any mutation. Only the two known input controls
and their associated form can be exercised; no operator JavaScript, URL, selector,
password or OTP is accepted. The same public-only policy denies every POST and
every uncharacterized GET before network dispatch. This is source request-shape
observation, with no vault access, principal enrollment or broker authentication.

The complete private envelope retains paused request metadata and the explicit
synthetic-action marker. Metadata from a blocked request can characterize its
URL/method/type, but proves no server acceptance, account ownership or successful
authentication. The source owner still owes independent inspection and a separately
bound real credential attempt. No role becomes enabled from a counter alone.

The canonical characterization command requires the pinned project-owned adapter
and verified owned runtime. The fixed helper and POST-denial composition are
qualified with synthetic DOM objects and socket-forbidden tests. This observation
remains inside the authorized read-only source scope; it does not activate real
credential delivery. Actual authentication, merge and financial activation retain
their separate external review and authorization gates.

## Automatic service target decision

On 2026-10-10 Florent confirmed the architecture after a grilling interview. The
canonical keyed target policy is `source-contract.yaml` under `target_service`.
The product is an independent Bourse Direct service in the incremental application
Compose: daily unattended acquisition and import, plus an operator trigger,
revisiting the latest 90 days each run. A coverage gap outside that window blocks
both daily and manual resumption until explicit resolution: verified catch-up
where the source supports it, or an operator acknowledgment of the missing period.
Acquisition coverage derives from the last completed period; pending exceptions
remain in the durable journal beyond the window. This supersedes the earlier manual-only
**product target**; recurring broker execution is not activated by this decision.
The currently implemented collector remains guarded by the acquisition procedure
and actual source qualification above. Production Ghostfolio writes remain a
separate concrete activation gate.

Certain unique existing financial matches prevent duplicate imports; existing
financial values are neither corrected nor deleted automatically. IBKR provides
reuse evidence for deployment and reconciliation concepts, not permission to
copy its looser quantity/date-only matching. Unknown operations, demonstrated
dependents and conflicting existing records become private exceptions, while
independently qualified operations continue. The present period-blocking and
operator-resolution implementation stays unchanged until reviewed dependency and
automatic reconciliation behavior exists; this target is not runtime evidence.
Authentication uncertainty always stops without an automatic retry.

Commands/infrastructure jobs and private exception artifacts are the operator
interface. Existing infrastructure notifications report intervention-required
codes/counts only. Deduplication journals and acquired source documents outlive
the rolling collection window in private persistent storage with verified backup
and restore. The deployment adapter remains replaceable; Komodo, host names and
private secret paths are infrastructure configuration, not public runtime
requirements. The same stack grows to include browser and collector services.

## Verification and rollback

`infra-jnvj` records the existing Archivage Bitwarden CLI mechanism. Recreate its
reader access with independent appdata and private connectivity rather than
attaching Puppet to the production BillCollector vault API. Never borrow its
live `BW_SESSION`, list the whole vault, or print credentials/TOTP. An exact-name
lookup must stop on absence or ambiguity. Password and TOTP must stay in memory;
request the TOTP only when the known authentication challenge requires it. The
API's required Host header and secret injection are supplied by the owning infra
contract, not guessed from a successful TCP connection.

The public Bourse Direct homepage was reached with a fresh Puppet browser context
on 2026-10-08; it exposed `/fr/login`. This proves basic browser egress only, not
account access. That context was closed and the task-started container stopped.

This phase gathers real evidence, not a broker canary or a production importer
test. Validation of the parser and future import behavior uses synthetic files
and a disposable Ghostfolio instance. Characterize operation matching, ISIN,
currencies, explicit costs/taxes, calendar semantics and history completeness
before building activities; no values inferred from names or net-price gaps.

The scope change affects documentation and project Beads. Documentation rollback
is a new revert of the amendment commit, retaining the user's decision in Beads.
Runtime rollback must be verified against the current exact-owned receipts and
canonical connection procedure before startup or network changes. Authentication
cannot be rolled back by deleting local files;
prevent unsafe attempts instead. No financial operation is part of this phase.
