# Portable owned disposable acceptance runner

This development-only runner reproduces the supported three-trade fixture chain
on an isolated local Ghostfolio3.81.0. The application CLI gains no apply command
or production readiness from this bench. Design authority:
[approved plan](../plans/2026-10-09-portable-lab-acceptance.md) and
[Astra report](../reviews/2026-10-09-portable-lab-acceptance-astra.md).
Single-event delivery follows the
[approved dispatch amendment](../plans/2026-10-09-single-event-lab-dispatch.md)
and its [Astra review](../reviews/2026-10-09-single-event-lab-dispatch-astra.md).

## Prerequisites and invocation

Use a trusted Linux lab host with `/usr/bin/docker`, an accessible local Unix
daemon socket at `/var/run/docker.sock`, the project's development environment
and all three exact immutable images cached. Image references live in the runner;
the prior [3.81.0 report](ghostfolio-381-parity.md) records their provenance and
resource caps. The runner performs no image pulls or dependency installation.
The exercised host had about3.6GiB available memory; this is an observation, not
a universal minimum. The containers' memory/CPU limits remain enforced.

```sh
.venv/bin/python scripts/disposable_acceptance.py --run-disposable-lab
```

No other input, endpoint, account or credential option exists. Omitting explicit
opt-in fails before Docker/network actions. Ordinary pytest/PR CI uses only
socket-forbidden synthetic tests and never launches the laboratory.

Docker uses a fixed local daemon, private empty client configuration and minimal
allowlisted environment. Inherited Docker/context/TLS/proxy and production
credentials are excluded. Generated lab credentials and signup/session tokens
are read from process environment; auth response bodies are not retained.
The trusted daemon/executable and operator's filesystem are prerequisites, not
an adversarial-host boundary. Yahoo provider availability is required for native
EUR bench-profile acceptance; failure never substitutes a fabricated profile.

## Checked lifecycle

The runner creates unique labeled resources and a random loopback-only app port,
validates owned IDs/image/network/binding and running3.81.0, then starts with zero
activities. It seeds three known prior synthetic acquisitions and applies the
existing saved statement/note fixture. This proves lab-only history completeness,
not a real account declaration or true ISIN mapping for the invented fixture IDs.

Initial preparation/review must yield three new trades and zero holdings shortfalls.
The original batch proposal is archived, then each chronological single-row body
is dispatched through the [continuous-lock core](single-event-lab-dispatch.md).
Each of three source POSTs has its own exact body/digest and durable uncertain
intent before dispatch, exact acceptance and complete semantic transition before
confirmation. Three confirmed tombstones and count6 are required. Per-event wire,
provenance, response and readback archives preserve what was actually transmitted.
The saved final snapshot and its matching history assertion are refreshed together.
Repeat preparation must be byte-identical; second review must show three owned,
zero new, no wire and no additional source POST. All readiness flags remain false.
Six exact owned seed/source activities are compensated with count0 readback.

Every attempted infrastructure creation is recorded durably before Docker runs.
Matching ownership plus immutable IDs controls cleanup; mismatches are never
removed. Each cleanup is attempted independently, followed by authoritative
exact-name absence queries. Unknown/timed-out creation remains a failed result
even when an intermediate list is empty. Errors, failed compensation, failed
cleanup or failed final report persistence return1; complete verified success
returns0 and prints only namespace/count-free fixed result codes/readiness.

## Retained evidence and recovery

Artifacts remain under ignored `tmp/disposable-acceptance-<namespace>/`, with
0700 directories/0600 files. The manifest records exact attempted resource names,
IDs and milestones; result.yaml is durably written after cleanup before overall
success. Separate initial/repeated preparation and review copies, baseline/full/
cleanup snapshots, exact per-event import responses and private journals survive teardown.
No raw signup/auth body is saved.

INT/TERM trigger bounded finally cleanup. SIGKILL, host loss or a daemon failure
can leave resources; no automatic daemon-wide orphan cleanup exists. Inspect the
retained manifest, then inspect **each exact named resource's ID and ownership
label** using the fixed local daemon before manual removal. A manifest alone is
not removal authority. Never prune, delete unrelated resources or discard an
uncertain journal to permit a replay. Exact cleanup mechanics remain owned by
the runner's functions and tests.

## Verification and limits

On2026-10-09 the versioned runner's first explicit owned rehearsal at `ec4565de6d08`
used one three-row source batch and passed all
lifecycle stages, deleted six activities with count0, retained both review stages
and private permissions, and confirmed empty task-label container/network lists.
Owning issue `infra-4g8u.44` records runner/result/manifest hashes and command
evidence. Full local socket-forbidden suite before that run:489 tests passed.
The subsequent explicit single-event rehearsal on2026-10-09 passed with three
source POSTs, three confirmed retained intents, count6, a zero-new repeat with no
extra source POST, compensation of six activities/count0 and empty task-label
container/network lists. Exact actual-body archives, original batch-only proposal,
initial/repeated reviews and0700/0600 permissions were verified. Owning issue
`infra-4g8u.51` records runner/result/manifest/journal hashes and command evidence.
Required full suite before this run:611 tests passed. Synthetic tests verify exact per-event archives,
pre-intent publication failure and stopping before the third event after a lost
second response; uncertain journals survive owned compensation.

This runner does not reproduce the separate delayed/lost/partial recovery barriers;
their [parity rehearsal](ghostfolio-381-parity.md) remains separate evidence.
No production data/service/credentials are used. Actual legacy dates/fees/history,
concurrent external writers, production quiescence, rendered dates, independent
security review and application delivery remain separate gates.

Rollback: ownership-checked teardown of exact newly created resources, retain
journals, revert the scoped development runner/tests/docs commit. Activity
compensation does not restore asset-profile or market-data side effects.

The runner now verifies the initial report through the shared
[frozen review validator](frozen-review-validation.md) before any source dispatch.
Its private frozen capture archive remains available for cold replay after cleanup;
the fixture-controlled hash is not human production approval.
