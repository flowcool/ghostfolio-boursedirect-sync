# Astra design review — portable disposable acceptance runner

Date: 2026-10-09. Design owner: `infra-4g8u.42`.

**Final verdict: APPROVE the amended design for implementation.** The proposed
scope and financial lifecycle are sound. The owner incorporated all four findings
below, and a second read verified their resolution before implementation began.
This is a design review, not PR review, runtime acceptance, or production
authorization. Approved plan SHA256:
`3be39dddeba799cfa804dda74ce81df2aeddd67ce46e45b825f54c94cbb8b50e`.

Reviewed: [portable runner plan](../plans/2026-10-09-portable-lab-acceptance.md),
[3.81.0 parity evidence](../design/ghostfolio-381-parity.md),
[synthetic lifecycle](../design/synthetic-import-lifecycle.md), repository rules,
the wire comparator, complete intent transition/persistence/resolution helpers,
private-file helpers, and saved-snapshot review helper. Earlier private controller
results are reported evidence; no private controller or account data was read for
this review. No Docker, HTTP, tests against services, or Beads mutation occurred.

## Findings resolved in the amended design

These findings record the initial gaps and required controls. Each is resolved at
the design level; the specified tests remain implementation acceptance evidence.

### R1 — High: isolate Docker configuration as well as the daemon address

Disposition: **resolved** by amended Gate 1.1/1.5: private Docker configuration,
allowlisted environment, no-pull enforcement, trusted executable assumption and
pinned owned-container identity/image/network/binding checks.

Evidence: Gate 1.1 fixes `--host` and ignores `DOCKER_HOST`; Gate 1.4 excludes
broker/Ghostfolio credentials. Neither specifies the complete subprocess
environment or Docker configuration directory. Gate 3 requests a hostile-config
test but does not define the corresponding isolation mechanism.

Impact: a fixed daemon flag alone is not a contract that excludes inherited
Docker context/TLS settings, client configuration, credentials, or container proxy
configuration. The promise to require cached images also needs enforcement at
creation time, beyond the earlier cache inspection.

Required revision:

- Give every Docker invocation a freshly generated private empty `--config`
  directory and the fixed local `--host`. Use a small explicit subprocess
  environment, adding only newly generated lab variables where required. Exclude
  inherited Docker/context/TLS/proxy and broker/Ghostfolio variables. Do not copy
  the caller's Docker configuration or invoke credential helpers.
- Resolve the Docker executable from a trusted installed location; document the
  trusted local daemon/executable assumption. A socket path plus labels does not
  authenticate a hostile daemon or protect against another daemon administrator.
- Enforce no pulls on each container creation (`--pull=never` or equivalent),
  retain inspected immutable image identities, and inspect the created container
  identity/image/network/bindings before relying on it.

Discriminating tests: hostile environment and Docker configuration cannot alter
the selected daemon, inject container proxies or leak credentials; an image
disappearing after preflight causes failure without a pull.

### R2 — High: make the HTTP isolation boundary explicit

Disposition: **resolved** by amended Gate 1.3–1.5/1.7: direct stdlib transport,
no inherited proxy/auth or redirects/retries, 45s timeout, 1048576-byte response
limit plus sentinel, encoding rejection, UUID path validation and pinned timezone.

Evidence: Gate 1.3 validates a loopback port and Gate 1.4 fixes methods/paths, but
the plan does not explicitly reject redirects or inherited proxy/auth settings.
The existing read-only snapshot transport already implements a direct connection,
redirect rejection, bounded reads and fixed error codes; the lab transport should
provide equally explicit guarantees while keeping its distinct HTTP lab origin.

Impact: validating the initial URL is insufficient if a client can subsequently
route through a proxy, follow redirects, or load ambient authentication. This
could move lab credentials or mutations outside the owned instance.

Required revision: use a direct numeric `127.0.0.1` connection to the port obtained
only from the exact owned container ID. Disable redirects, proxies, netrc/auth
discovery and automatic request retries by construction. Reject all 3xx responses.
Specify connect/read bounds and bounded raw response consumption before parsing,
including rejection of unexpected encoding; never trust Content-Length alone.
Generated account/activity identifiers may fill fixed path templates only after
validation as identifiers, never as URLs or arbitrary path fragments. Pin the
server timezone used by the earlier bench (`Europe/Paris`).

Discriminating tests: redirect responses never cause a second request; hostile
proxy/netrc settings are ignored; oversized/encoded responses fail safely; timeout
after a mutating send does not retry. Verify the exact owned app is running with
the expected image, network and unique binding before the mutation sequence.

### R3 — High: include attempted creations in cleanup ownership accounting

Disposition: **resolved** by amended Gate 1.2/1.7 and Gate 2.7: durable attempted
names, immutable ownership binding, explicit unknown/NotFound distinction,
independent cleanup, final absence proof and controlled interruption handling.
A timed-out creation remains a failure even after an empty interim query; this
correctly avoids claiming that a still-processing daemon cannot create it later.

Evidence: Gate 1.2 says to track successfully created resources. Gate 2.7 cleans
created resources in `finally`. A creation may reach Docker before the CLI times
out or fails to return its resource ID.

Impact: a partial startup can leave a running owned resource outside the tracked
list. Killing the client does not prove the daemon never created the resource.
An inspect failure is also not proof of absence. The same uncertainty applies to
a timed-out removal. Ordinary `finally` does not provide a SIGKILL cleanup promise.

Required revision:

- Durably record the namespace and every intended exact resource name before
  each create call. Separate creation from startup where practical; bind names
  to inspected immutable IDs and exact ownership labels as soon as available.
- On failed/ambiguous creation, inspect only that attempted exact name and adopt
  it for teardown only after exact label verification. Use immutable IDs for
  subsequent mutation/cleanup. A collision or mismatch must never be removed.
- Establish absence through a successful authoritative query; daemon errors or
  malformed output remain unknown and force a failed cleanup result. Reconcile
  removal timeouts through bounded read-only checks, and perform a final
  exact-namespace resource query before declaring cleanup complete.
- Attempt each owned cleanup independently. Handle ordinary interruption and
  termination through bounded cleanup; document that forced process/host loss
  leaves the durable manifest for manual, ownership-checked recovery. Do not add
  broad automatic orphan cleanup or treat a manifest alone as removal authority.

Discriminating tests: timeout after successful create, failure between create and
start, missing ID response, label mismatch, inspect transport failure, removal
timeout, and one failed cleanup followed by successful independent cleanups.
The final success code must require confirmed resource absence.

### R4 — Medium: bind helper working directories and retain both lifecycle stages

Disposition: **resolved** by amended Gate 1.4/1.6/1.7: script-derived root,
exclusive run directory with checked ancestry, isolated helper cwd/state,
archived initial/repeated artifacts, no retained authentication bodies and
durable reporting before stdout success.

Evidence: Gate 1.6 promises a unique private run directory. The inspected
`review_local_snapshot` writes `outputs/review-<account_key>.yaml` and uses `state/`
relative to the process working directory. Its second invocation replaces the
same review path. Private-directory helpers reject a symlink at the immediate
path, but do not establish the proposed runner's complete ancestor boundary.

Impact: calling helpers from the repository root could use ordinary project
state/output directories rather than the promised isolated run root. Retaining
only the second review would lose the original three-new review even if its exact
wire body survives in the intent journal.

Required revision: derive the repository/fixture root from the script location;
validate the project-local temporary parent, reject symlink escape and create the
UUID run directory exclusively before any Docker mutation. Run all existing
helpers with cwd and state rooted inside that private run directory. Use the
existing durable `persist_write_transition` boundary before the source POST and
send precisely its retained body. Keep separate immutable copies of the initial
and repeated preparation/review, raw baseline/readback/cleanup snapshots and
bounded import response. Never persist auth/signup response bodies containing
credentials. Record sanitized resource and milestone evidence durably; final
report persistence failure must not become success or prevent teardown.

Discriminating tests: invocation from another cwd, unsafe temporary ancestor,
pre-dispatch persistence failure, preservation of both review stages, no writes
outside the unique run root, and report-write failure followed by cleanup. The
caller must never supply an alternate state root, input, endpoint or account.

## Acceptance boundary retained

The existing plan correctly requires the complete chain: initial count0, exact
three-seed acceptance/count3, three-new preparation and review, durable uncertain
intent before one exact-body POST, exact response matching and complete count6
readback, positive intent resolution, byte-identical repeat preparation,
three-owned/zero-new/no-wire review, exact six-row compensation/count0, and verified
owned resource removal. Preserve `import_ready=false` throughout.

Use explicit runtime failure checks for these gates, including under optimized
Python; do not rely on removable Python `assert` statements for safety or final
acceptance. No stage may publish overall success before financial checks, cleanup
and durable final reporting all finish. A failed scenario remains failed even if
cleanup succeeds. Compensation never resolves an uncertain intent by inference;
failed-run evidence stays available after infrastructure destruction.

The runner may depend on Yahoo availability and the trusted local Docker host;
that is a documented lab limitation. It must not fabricate profiles to recover
from provider failures, accept external endpoints, clear production readiness
gates, or claim the deferred recovery scenarios were reproduced by this runner.
No new recovery framework, production dispatcher or application module is needed.

## Review completion and knowledge

The amended plan passes the narrow recheck; there are no unresolved design
blockers. Implement the controls and discriminating tests above. Unit and real
owned-lab evidence remain implementation acceptance, not evidence supplied by
this design review. External PR review and merge remain with Florent's workflow.

Knowledge verdict: **Used and sufficient**. The narrow Ghostfolio index lookup
reached the current import-acceptance/date and saved-input-preservation concepts;
they agree with the canonical helper/report boundaries inspected here. The new
findings concern this proposed runner and belong in its design/review artifacts;
no new cross-project operational observation was produced.
