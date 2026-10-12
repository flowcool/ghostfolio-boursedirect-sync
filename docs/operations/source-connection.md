# Replay the Bourse Direct connection

Resume through `scripts/source_connection.py` and the private `inputs/lab/replay.yaml` inventory before investigating acquisition or changing the lab.

## Entry sequence

Run from the project root:

```sh
.venv/bin/python scripts/source_connection.py check
.venv/bin/python scripts/source_connection.py status
```

`check` reads saved evidence and pinned helper hashes locally. `status` additionally
uses the existing private SSH/Docker adapter to verify the exact daemon, owned
container IDs, pinned images, current PIDs/network namespaces, and proxy-only
IPv4/IPv6 rules. These commands neither log into Bitwarden nor request a broker
page. The output contains fixed codes, counts and role names only.

Successful unchanged stages are reused. A historical success remains evidence
after its browser has closed; it is not a live cookie or permission to replay a
password. The current source contract distinguishes those facts explicitly.
Consult the owning Beads issue for current acceptance and external review; this
runbook contains procedure, not a second work queue.

## One project owns operational access

The community entrypoint is the ENV-configured native `bitwarden` service in
`compose.yaml`; see the [application Compose instructions](../../README.md#application-compose).
`docker compose run --rm bitwarden inspect` verifies access and closes its session.
`connect` uses the same connector but still refuses unqualified broker dispatch.
The existing dedicated lab retains `compose.lab.yaml` plus its broker overlay,
private receipts and exact-owned SSH adapter. Its historical inspection is reused
as evidence, while native image/runtime qualification is recorded separately.
Lab creation requires `BITWARDEN_CLI_IMAGE` to be the independently verified local
SHA256 image ID; there is no implicit mutable image name. The existing pinned
creation adapter supplies that ID. This input is not needed by community Compose.

| Purpose | Canonical location |
| --- | --- |
| Public command and this procedure | `scripts/source_connection.py`, this file |
| Private replay references and helper pins | `inputs/lab/replay.yaml` |
| SSH adapter, provisioning and exact-owned attestation/stop helpers | `inputs/lab/host/` |
| Mutable vault/browser receipts | `inputs/lab/host/receipt.yaml`, `inputs/lab/host/broker-runtime.yaml` |
| Access authority and receipt pointers | `inputs/source-observations/lab-access.yaml` |
| Actual request roles and expected account inventory | `inputs/source-observations/source-contract.yaml` |
| Successful vault inspection | `inputs/vault-access/inspection.yaml` |
| Public source and independently checked app body | `inputs/source-observations/` |
| Historical authentication journal and capture manifest | `state/source-auth.yaml`, `inputs/acquisition.yaml` |
| Prior exploration code, provenance only | `inputs/lab/history/` |
| Local migration and rollback evidence | `inputs/lab/migration.yaml` |

Private paths are ignored, directories0700/files0600. Credentials remain in the
existing encrypted provisioning store and Bitwarden. The project owns control
code and pointers; it does not copy broker secrets into its files. Host settings
remain private configuration. There is no infra-agent relay or browser control
port in the connection path. Former temporary controllers are archived and
cannot be treated as active commands; no lab-control command depends on `tmp/`.

## End-to-end stages and their evidence

1. **Local SSH and lab ownership.** Use `status`; reuse the same Compose lab.
   The adapter uses batch authentication, strict host-key verification and the
   exact daemon/resource receipts. Inspect current receipts before log/exec/port
   changes; container names alone never grant mutation authority.
2. **Independent vault session.** Reuse the successful inspection to establish
   exact unique item resolution, canonical broker URI, credential fields and TOTP
   profile. For actual authentication, use the source-owned CLI/provider adapter
   and existing private provisioning function. A fresh worker logs into its own
   appdata; password and session material travel through private memory/stdin.
   Inspection schemas3/5 return metadata and log out; they cannot provide collector
   credentials. Acquisition schemas1/2/4 additionally require qualified account/URI
   binding. A successful inspection does not bypass that difference.
   Native Compose receives `BW_SERVER`, `BW_CLIENTID`, `BW_CLIENTSECRET`,
   `BW_PASSWORD` and `BW_ITEM_NAME` from operator ENV. It binds item identity
   automatically; a changed principal, UUID or URI metadata remains a refusal.
3. **Sandbox and public form.** Reuse the pinned renderer/cleanup and public-source
   evidence. The body of the actual authentication application was acquired as an
   inert GET Document with scripts disabled, from a previously paused Script URL.
   Examine that saved body locally. Refresh only an invalidated dependency;
   register exact request method/type/redirect/frame evidence before enabling a
   new role. An inert Document response does not establish a Script or submit role.
4. **One deliberate password submission.** Once the current form and password
   request role are qualified, reserve the canonical acquisition journal before
   delivery/submission. Keep the earlier authenticated journal and its history.
   Submit only to the independently observed role with immutable principal
   binding. An error, challenge outside the known flow, or uncertain outcome
   stops this attempt without automatic password retry.
5. **Application TOTP challenge.** Select the observed app method. Request one
   code from the same resolved Bitwarden UUID only after the known challenge;
   submit it once. The seed stays inside the vault worker. Retain the temporary
   untrusted-device choice; no broker authentication-setting change is authorized.
6. **Authenticated account discovery.** Verify success from actual account
   navigation, enumerate every accessible account, and compare the private
   expected inventory. Distinct tax wrappers require distinct source/destination
   bindings, operation identities, coverage and deduplication. Missing or ambiguous
   bindings remain explicit; no default account substitution.
7. **Read-only acquisition and cleanup.** Navigate observed history/statement/note
   resources. A click may reuse a popup: identify its observed document, rather
   than await a new window unconditionally. Keep originals and journals private,
   verify owned browser descendants exited, and retain the durable Compose lab.
   Ghostfolio writes and recurring execution remain separate activation gates.

Historical steps4–6 succeeded on2026-10-08: one password and one application TOTP
reached account navigation. See [observed source evidence](../../FINDINGS.md) and
the private manifest/journal. That exploration used an earlier browser controller;
its success is preserved, while current collector request-role qualification is
reported separately by `check`. Source feasibility is not reopened at each resume.

## Notice-only window acquisition planning

For the amended daily contract, the existing qualified entrypoint accepts an
explicit broker calendar clock:

```sh
.venv/bin/python scripts/source_connection.py qualify-connection \
  --notice-window-as-of 2026-10-12
```

To collect only the configured source account, use the same private schema-1
`source_mode: notices` configuration as the importer:

```sh
.venv/bin/python scripts/source_connection.py qualify-connection \
  --notice-window-as-of 2026-10-12 --account-config inputs/account/daily.yaml
```

The configuration's `account` contains `source_account_ref`, persistent
`account_key` UUIDv4 and explicit `target_account_id`; see
[community account routing](../design/daily-saved-input-preview.md#community-account-routing).
The path is relative to the project root and must be a private regular file.
Only the configured stable source reference is selected, even when multiple
accounts have the same wrapper label. Missing, ambiguous or wrong references,
selected-option mismatches and unsupported wrappers refuse. Supported wrappers
remain PEA and PEA-PME. The original two-account qualification is retained when
this option is absent. This option is accepted only with notice-window
qualification; it does not change ordinary `connect` or credential delivery.

Private attempt and completion receipts retain the three-field binding and
configuration hash. The daily importer refuses a changed binding before
producing candidates, preserving the configured Ghostfolio destination. No
account references or destination IDs are printed by the connection command.
This interface has offline and disposable synthetic browser evidence; fresh
single-account broker acquisition remains unverified.

This selects the approved90day notice window and ignores the historical monthly
statement preference. It navigates the observed operation calendars for both
verified accounts (or the single configured account), follows offered notice links and interprets only the exact
source-described previous-month function. Monthly statement routes and form
submissions are not selected. The first window month is read in full so source
calendar/financial-day differences can be handled by the notice parser; daily
candidate selection still uses the actual financial booking day.

Calendar headings, selected account, source navigation arguments and explicit
empty-month messages must agree. A calendar that references the separate inert
`avis-operes.js` body waits until its exact known function has been captured;
changed, missing or ambiguous navigation refuses rather than constructing an
unqualified URL. All requests retain the existing bounded origin, exact request
role and source provenance guards. Month/year rollover uses that observed source
function, not an invented endpoint. Completion requires all window months for
all selected accounts; a verified empty calendar supplies absence evidence without
manufacturing a contract note. Qualification receipts record the selected window.

This option changes read planning only. It retains the existing one-attempt,
credential, TOTP, account, logout and browser-exit controls. It does not authorize
an automatic broker retry or activate recurring authentication. Offline replay
of saved calendars qualifies planning, not a fresh session or actual acquisition
with this option; its live qualification remains separate from existing historical
acquisition evidence. Ordinary `connect` remains guarded as described below.

## Current connection command boundary

```sh
.venv/bin/python scripts/source_connection.py connect
```

This is a deliberate refusal boundary, not an implemented credential-delivery
command. It currently returns code2 and
`SOURCE_AUTHENTICATED_REPLAY_NOT_QUALIFIED`, together with missing roles and
account-binding counts. It makes no vault/broker request. The command must become
an authenticated entrypoint only after the existing source/core/provider gates
are implemented and verified; changing the code or clearing an old journal to
make it return success is not qualification. A future session resumes from the
saved app source and named gaps instead of repeating vault/public exploration.

The credential-free form observation is available through the same entrypoint:

```sh
.venv/bin/python scripts/source_connection.py observe-public-form
```

It requires a separately pinned private `public-form.py` adapter in the project
host bundle. Without that pin it refuses before SSH access. The adapter reuses
the saved public document and authentication-app body hashes. The observed inline
loader generates a new cache timestamp per load; the opt-in profile grants only
its two named public Script/Stylesheet GETs once each with a current timestamp,
sharing the single-use budget with any identical declared asset, alongside the
two previously observed stylesheets. It blocks other requests without submitting a
form. A fresh private attempt retains original output, selector counts and owned
exit evidence. Failure stops the exact browser and retains the attempt; this
command never requests vault credentials or qualifies an authentication submit.

`characterize-password-request` uses the same owned observer with fixed dummy
markers to retain a blocked form request's URL/method/type. Every POST is denied;
it supplies no real credential and dispatches no broker authentication. It requires
an actually intercepted and successfully blocked same-frame/session JSON POST
containing both fixed dummy credential markers; requesting form submission alone
does not qualify the observation. Malformed envelopes retain request metadata and
a fixed refusal code before the attempt stops; raw sensitive headers are never
retained. The operation requires
the pinned private adapter and exact-owned runtime, and refuses prefilled or
ambiguous inputs before any mutation. The captured metadata requires independent
source inspection; it never establishes successful login. Real credential delivery
and authentication retain their separate source, runtime and security gates.

The local check reports preliminary verification and post-2FA password
finalization as separate required roles. An older six-role inventory cannot
hide those gaps or establish authentication readiness. Finalization is distinct
from app-method selection; saved application code cannot qualify its dispatch.

Inspect every denied POST separately. The current form observation produced a
preliminary verification request and a password-submit request in the same owned
frame/session. The opt-in dummy observer additionally retains each denied POST's
bounded body and Content-Type in its private envelope; other headers are excluded.
Earlier observations containing URL/method/type alone keep their missing-body
gap. Saved application source can explain payload construction, but cannot replace
actual envelope inspection. Keep these gaps explicit in the private source
contract and leave authentication roles disabled.

## Bounded recovery

Missing URI-alias metadata from an older vault inspection can be refreshed
through the same entrypoint:

```sh
.venv/bin/python scripts/source_connection.py inspect-vault-aliases
```

This requires a hash-pinned `vault_cli_binding` evidence reference whose bytes
match the successful inspection's binding hash. The historical artifact supplies
data only; no archived controller is executed. The source-owned private IPC
adapter uses the current full-ID receipt, CLI pin, egress proof and provisioning
function. SSH CLI output is consumed directly inside the worker; the supervisor's
private RPC carries only attestation/stop metadata and the final inspected
projection. Full items, seeds and CLI stdout never cross that RPC boundary.
It opens one metadata-only session, retrieves no TOTP, verifies logout
and compares every prior identity/profile field before preserving the new alias
hash in a fresh private inspection directory. No broker request or source role
activation is performed. Missing pins, changed metadata, unverified cleanup or
IPC failure refuse; a failed execution preserves intent and stops only the
receipted CLI, recording `cli_stopped_owned` for bounded recovery. Public output
contains fixed codes/counts only. Source code must be committed and pass its
exact-head external security review before this opt-in command is used.

If an exact owned browser was stopped and the receipt says
`browser_stopped_owned`:

```sh
.venv/bin/python scripts/source_connection.py restart-browser
.venv/bin/python scripts/source_connection.py status
```

The restart command saves a unique private prior receipt, records start/ACL
intents, starts the same full ID, refreshes PID/netns, reinstalls the numeric
proxy-only OUTPUT allow and IPv6 DROP, then attests. It creates no service/network
and sends no broker request. A failure stops only the receipted browser and keeps
the partial receipt. An already-running browser is inspected with `status`;
restarting it is not a prerequisite to resumption.

```sh
.venv/bin/python scripts/source_connection.py stop-browser
```

This stops the exact receipted browser only. CLI/proxies, journals and source
evidence remain intact. Ambiguous daemon/owner/PID or unreadable evidence returns
a fixed refusal. Diagnose that particular difference; preserve intents and
uncertain attempts. Rebuilding the whole stack, refreshing Chrome, relogging into
the vault or changing an authentication namespace is not a generic recovery.

## Updating a qualification

Capture a new attempt under a fresh private directory and retain failure phase,
exit code, source/runtime hashes and cleanup result before interpreting it.
Update the canonical private contract and replay references only from inspected
evidence; append public structural verification under
`docs/verification/vault-composition.yaml`. Validate and commit intended public
changes, publish under existing authority, and record current acceptance in Beads.
Successful pinned evidence is reused until its relevant input or runtime property
changes. Documentation never substitutes for an unobserved request or account.

### Interrupted vault containment

Metadata inspection reserves `inputs/lab/vault-operation.lock` before credential
provisioning. A concurrent invocation refuses; verified logout or exact owned
CLI shutdown releases the lease. Uncertain cleanup and process interruption
retain it for ownership-preserving recovery rather than opening another session.
`stop_owned_cli` revalidates the full owned ID/configuration and original running
PID. A retained `cli_stop_intent` can finish the bounded stop, or publish the
stopped receipt when that exact container is already stopped. Changed ownership,
PID or unknown receipt states refuse before mutation. This permits cleanup
reconciliation only; it never restarts the CLI or retries authentication.

## Explicit one-attempt qualification

`scripts/source_connection.py qualify-connection` is separate from ordinary
`connect`. Run it only under the scoped one-attempt authority, after offline
verification, isolated Chromium qualification and external review of the exact
committed head. It reuses the dedicated lab, independently pinned vault identity
and app source, and existing SSH/provisioning. Explicit enrollment reserves the
canonical principal namespace; existing or uncertain state refuses.

The worker keeps full vault items, seeds, session material, credentials and
authentication responses in private memory. It inspects and retains each native
request before consuming its one-use permission. It accepts one known challenge,
one application code and one separately permitted final credential request.
Unknown responses or requests stop the owned attempt without retry.

Captured account/document GETs are inert and private. Two distinct wrapper IDs
and selected-account navigation must be observed; statement/note titles and
account headers must match. When saved lists need further source inspection,
`SOURCE_READ_SELECTION_REQUIRED` retains the current browser while waiting for
a private `selection.yaml` in the current attempt directory. That record contains
`url`, `role`, `sourceSha256` and `account`; the source hash must name a captured
body and the selected account must be verified. Inspect the source before granting
the exact next read; calendar scripts are retained as inert source documents.
The original ten-minute browser lifetime and request budgets still apply. No
password or OTP retry is granted. Cleanup verifies logout or stops the exact
owned CLI, verifies browser exit or stops its exact container, and preserves
uncertainty. This qualification does not enable recurring collection.

For a specific historical statement, optionally save a private
`inputs/source-observations/statement-preference.yaml` before starting the attempt:

```yaml
schema_version: 1
statement_periods:
  PEA: '202607'
```

Only `PEA` and `PEA-PME` keys and valid `YYYYMM` strings are accepted. Invalid
configuration refuses before owned runtime access. The collector selects only
the uniquely matching French month/year label offered by the saved broker form,
using its exact observed option value and selected account. Missing or ambiguous
months refuse; no URL or option value is invented. Without this file, navigation
keeps its existing behavior. The preference narrows document selection and does
not authorize a new authentication attempt. Verify the retained statement's
actual period and financial contents separately before reconciliation.
