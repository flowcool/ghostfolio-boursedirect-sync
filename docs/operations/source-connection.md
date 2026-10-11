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
   Inspection schema3 returns metadata and logs out; it cannot provide collector
   credentials. Acquisition schemas1/2 additionally require qualified account/URI
   binding. A successful inspection does not bypass that difference.
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
the saved public document and authentication-app body hashes, grants only their
observed Script/Stylesheet GETs, and blocks other requests without submitting a
form. A fresh private attempt retains original output, selector counts and owned
exit evidence. Failure stops the exact browser and retains the attempt; this
command never requests vault credentials or qualifies an authentication submit.

## Bounded recovery

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
