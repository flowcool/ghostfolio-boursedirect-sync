# Portable disposable acceptance runner

Date: 2026-10-09. Design owner: `infra-4g8u.42`. Astra design review is required
before executable development code. PR review remains externally managed.

## Problem, scope and rationale

The [3.81.0 parity bench](../design/ghostfolio-381-parity.md) and
[document lifecycle](../design/synthetic-import-lifecycle.md) proved useful
acceptance behavior, but their one-off controllers are ignored private artifacts.
The public v0 cannot reproduce this path from Git. Publish a small opt-in
development runner that creates its own laboratory and executes the proved
three-trade lifecycle. Do not add a production dispatcher or change financial
helpers. Keep the application functional mono-file unchanged.

Proposed artifact: `scripts/disposable_acceptance.py`, functional Python without
classes/type hints. This is a development entry point, not an application module.
It uses stdlib, installed project dependencies and existing helpers. Synthetic
input bytes come only from versioned `tests/fixtures`. No broker input, endpoint,
account ID, bearer, password or configuration path is accepted from the caller.
Do not publish recovery barrier scenarios in this iteration: their independently
proved private rehearsal stays authoritative until a separately scoped runner.

Command: `.venv/bin/python scripts/disposable_acceptance.py --run-disposable-lab`.
Missing explicit opt-in produces usage failure without Docker or network actions.
Ordinary pytest and PR CI never launch this script. No production writes are
authorized; the only API mutations belong to the freshly created synthetic lab.

## Verified prerequisites and remaining uncertainty

The existing controller, full preparation/review/wire/intent state machine and
synthetic fixture chain were inspected. On the current Linux host, cached images,
3679MiB available memory and successful owned cleanup were observed. Native
Ghostfolio3.81.0 accepted three distinct EUR Yahoo bench profiles and the exact
three-trade body; repeated review produced zero new/three owned/no wire.

Pin these cached immutable image references:

- Ghostfolio: `ghostfolio/ghostfolio@sha256:7c925671dba267cc2175195f064b42b9733f3ea170a21db488b7d2be3319e088`;
- PostgreSQL: `postgres@sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81`;
- Redis: `redis@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`.

Official application source is `920d0787541a8568920fc11f978aa01e5a52c581`.
This iteration requires preinstalled cached images; it neither pulls images nor
installs software. Yahoo availability is an external bench prerequisite, not a
guarantee. A provider failure fails the bench and still cleans owned resources;
do not replace verified response evidence with fabricated profile data.

## Gate 1 — isolation contract and Astra approval

Before implementation, review the following concrete design:

1. All Docker calls use an argument vector without shell, fixed
   `--host unix:///var/run/docker.sock`, bounded subprocess timeouts and captured
   output. Use a newly created private `--config` directory and an allowlisted
   subprocess environment: PATH plus only generated lab variables needed by
   that invocation. No inherited DOCKER_*, proxy, credential-helper, registry
   configuration or production credential variables reach Docker. Never use
   caller-selected context or inherited DOCKER_HOST. Add `--pull=never` to every
   run; cached-image inspection alone does not prevent a later automatic pull.
   Reject a
   missing/non-socket local daemon path before launching. Verify daemon access
   and all three exact cached image refs first. This is a lab-capable host
   requirement, not permission to modify another daemon's services.
2. Generate one unpredictable UUID namespace and label every created network and
   container with an exact run ownership value. Names never come from input.
   No existing resource is reused. Durably record every attempted resource name
   before its creation call, then capture returned immutable IDs and verify
   exact ID/name/label ownership. A CLI timeout/failure may follow successful
   daemon creation: inspect attempted names and adopt only exact matching owned
   resources for cleanup. Never treat an inspect/daemon failure as NotFound.
   An unresolved or timed-out create keeps a failure verdict even if an interim
   list is empty, because late creation cannot be ruled out automatically.
3. PostgreSQL and Redis use their existing tmpfs/resource caps; Ghostfolio uses
   the proved 1536 MiB/1.5 CPU cap, init and no-new-privileges. No host bind mounts,
   production volumes or production-network membership. Allow only run-owned
   containers on the private lab network. Publish only a random 127.0.0.1
   port. Validate the unique loopback port before any HTTP request and rediscover
   it if restart is ever introduced; this iteration has no restart.
4. Generate lab DB/salt/JWT credentials into the runner's process environment;
   container args reference only environment variable names. Signup and token
   exchange operate solely on that owned loopback app and put resulting lab
   access/session tokens into process environment. Use stdlib `http.client`
   directly: no proxies, netrc, redirects or HTTP retry adapter. Bound every
   response to 1048576 bytes plus one sentinel byte and use a fixed 45 s timeout;
   reject redirects, oversized bodies and malformed JSON with fixed codes.
   The size/timeout are the exercised private-controller budgets, not universal
   API limits. Reject unexpected content encoding; validate every returned ID
   used in fixed deletion paths as a UUID before constructing that path.
   Auth/signup bodies are never retained among bounded response artifacts.
   Ignore inherited broker and
   Ghostfolio credentials; never send or log them. HTTP methods/paths are fixed.
5. Use a trusted installed Docker executable (resolved once from the operator's
   trusted PATH); no project-local shim is accepted. Validate exact owned app
   ID/name/labels, pinned image, sole owned network membership and loopback
   binding before mutation, and running package version3.81.0 before
   signup or mutation. Health polling is read-only/bounded and is not an import
   retry. Mutating API calls are single-shot; a timeout fails without retry.
6. Derive project/fixture root from the installed script path, never caller cwd.
   Work artifacts live under ignored project-local `tmp/disposable-acceptance-
   <UUID>/`, exclusively created (`exist_ok=False`) with no symlink ancestry,
   directories0700/files0600. Every helper's relative outputs/state runs with cwd
   exclusively inside this owned run root. Record private journals, bounded raw
   snapshots/responses and report. Archive initial and repeated preparation and
   review bytes before a subsequent helper overwrites its normal destination.
   No live configuration/inputs are read. Final report persistence failure is a
   failed bench and still executes cleanup; stdout success follows durable report.
7. Errors/stdout contain fixed lab codes, counts, namespace and version only.
   Never print subprocess stderr, exception paths, tokens, full API rows or HTTP
   error bodies. Record cleanup failure explicitly and return nonzero even if
   the financial scenarios succeeded. Use explicit runtime checks/errors, not
   Python asserts removable by optimization. Do not print a successful result early.
   Set the proved server `TZ=Europe/Paris`. INT/TERM raise a controlled interruption
   so bounded finally cleanup runs; SIGKILL/power loss cannot promise cleanup.
   Retained attempted-resource manifest supplies exact ownership-checked manual
   recovery, never daemon-wide cleanup or automatic speculative replay.

Security design blockers are resolved before coding. This review is Astra design
review, not a PR-review subagent or substitute for external CodeRabbit.

## Gate 2 — exact lifecycle and ownership cleanup

Implement the already observed lifecycle with explicit assertions:

1. Owned startup: new network/database/cache/app, exact running version, new
   synthetic user and EUR account, complete activity list count 0.
2. Seed exactly three prior synthetic BUYs; assert exact returned account,
   timestamp, EUR Yahoo profile and numeric fields. The artificial fixture ISINs
   deliberately map to distinct AIR.PA/OR.PA/MC.PA bench profiles, as documented
   in the prior run; they are not source-security mapping claims. Complete saved
   GET count3 proves the controlled baseline, not real history completeness.
3. Copy the three saved synthetic document fixtures, generate a new account key
   and configuration, and truthfully bind the controlled acquisition declaration
   to the exact raw snapshot digest. Run existing preparation and review helpers.
   Assert three trades, three new activities, no holdings shortfall, readiness
   false and retained exact body/digest. Keep all artifacts private.
4. Persist the exact retained body as uncertain before one lab POST. Match every
   accepted row using `compare_import_response`; a complete raw GET count 6 plus
   exact ownership/financial context positively resolves the intent. No response
   status/count alone grants acceptance. Any failure retains the journal.
5. Repeat preparation and review with the fresh saved snapshot/declaration:
   assert byte-identical preparation, three owned/zero new/no wire, zero
   shortfalls, readiness false and no second source POST.
6. Compensate only exact known seed/source marker and account IDs, assert count 0.
   Never delete a row outside that known set. If activity compensation fails,
   still attempt owned infrastructure teardown and retain evidence.
7. In finally, inspect exact ID/name/ownership labels for every attempted container before
   removing it and its anonymous volumes; inspect network ownership before its
   removal. Do not stop/remove on ownership mismatch. Attempt each owned cleanup
   independently; report failure rather than hiding it behind earlier success.
   Distinguish explicit NotFound from inspection/daemon failure; successful
   exact-name final listing must prove absence of each attempted container and
   network after teardown. A previously absent owned resource is already clean
   only when creation was known not to remain in flight; unknown resource/state
   cannot be treated as success. No daemon-wide prune, wildcard delete or image
   removal. Retain private journals after teardown.

The controller supplies orchestration only. All financial decisions remain in
the application helpers. Its sole owned environment permits deliberate synthetic
dispatch despite production readiness remaining false; it must not be an
endpoint-configurable bypass usable with real accounts.

## Gate 3 — tests before an owned real rehearsal

Socket-forbidden unit tests mock subprocess/HTTP boundaries. They discriminate:
opt-in omission, fixed daemon selection despite hostile inherited Docker config,
missing image/daemon, private Docker config/minimal env/no-pull enforcement,
ownership mismatches, timeout-after-create/inspection failure and final absence,
non-loopback/multiple port bindings,
wrong app version, inherited credential non-use, single-shot mutation/no retry,
response limit, safe error output, cleanup continuation and failure exit. Tests
must not connect to Docker, a real socket, production or shared Beads.

Run the complete required pytest suite and inspect semantic diff/numstat before
the real bench. Then explicitly run only the new owned acceptance runner on the
lab host. Exact final counts, zero-new repeat, retained uncertainty evidence and
absence of its exact owned containers/network are acceptance criteria. If this
fails, capture the failed gate; do not call the deliverable verified.

## Gate 4 — publication and scope boundaries

Document prerequisites, single opt-in invocation, network/provider dependency,
failure/cleanup behavior and private artifact locations. Run the established
bounded whole-history privacy audit, diff checks and public synthetic CI. Commit
the scoped artifacts, push an open stacked PR under current authorization, and
leave CodeRabbit/merge to Florent's external workflow. Review is not a blocker to
later independent work; unresolved security findings remain owning issues.

Blast radius: exact newly owned lab resources and ignored run artifacts only.
Rollback: exact ownership-checked resource teardown/count 0 where reachable;
revert the runner/tests/docs commit without deleting retained journals. No
financial production rollback is claimed. The root epic cannot close on this
bench: actual history/adoption and application delivery are separate obligations.
