# Operator application delivery

Date:2026-10-09. Owner:`infra-4g8u.59`. Baseline:
`47a87a35737a4036325858cfb4996d4942b8e1ec`.
Florent asks autonomous progress toward usable project delivery, not stopping on
PR review or real-input decisions. He still prohibits production Ghostfolio
writes. Build and test the application independently; do not execute against his
instance. Astra design approval is required before each implementation package.

## Scope and evidence

Existing saved HTML preparation, strict EUR BUY/SELL conversion, identity,
adoption, full frozen review and per-event uncertainty protocol are authoritative.
The owned fixture runner proves source-to-confirmed import and repeat/compensation.
Missing application boundary: no `apply` operator path and no reusable HTTPS
request adapter. Actual source3trade legacy/adoption/history evidence remains
separate, and cannot be inferred from this development or generic user autonomy.
Reviewed source: complete application/helper/CLI chain, owned runner, existing
transport and tests; original plan I7/I8/I11. Official local source at
`806d83f45394bdc70e58d9b178e2ddbdf715de08` and established3.81.0 parity evidence
confirm fixed GET/import paths, permission guards and exact native DTO/readback.
Current TLS timeout and response byte limits remain explicit development budgets,
not global runtime deadlines. Existing session bearer support is sufficient for
interactive release; long-lived token exchange/renewal is out of this package.

## Gate0 — approved staged implementation and unchanged financial boundaries

Approve the complete design before coding. Instantiate distinct atomic packages:
A operator preview/export; B bounded transport; C future execution gate and public
application integration. A/B can ship independently; C needs a separately reviewed
exact permission/recovery contract, not an invented blanket authorization.
The plan deliberately does not turn permanent false readiness/blocker codes into
an override. Production source/security/version/display/recovery/exclusive access
proofs still need qualified evidence. No actual write authorization is implied by
code availability, a hash, a fixture callback or a local execution switch.

## Gate1 — usable default offline apply preview/export (package A)

Add `apply --config FILE --review FILE --review-sha256 HEX --input-root DIR
--max-bytes N [--export FILE] [--execute]`. Default is offline dry-run even when
DRY_RUN is unset. DRY_RUN is a strictly parsed environment switch: absent or1
means dry-run;0 permits considering explicit execution; anything else fails.
`--execute` alone cannot bypass DRY_RUN1; execute false remains dry-run even when
DRY_RUN0. No GHOST_HOST/token lookup, network callback, auth exchange or intent
creation in default path. `--execute` withDRY_RUN0 currently fails with
`APPLICATION_EXECUTION_GATE_REQUIRED` before reads/publication/transport; package C
owns any later execution behavior. This explicit interim v0 limitation is public.

Capture report/config/fourroles once through the existing bounded local reader,
require the external pin and full recomputation, and derive result only from that
validated artifact. Report new/owned/adopted counts, holdings-shortfall count,
`dry_run:true`, `import_ready:false`, current fixed blockers; no financial values,
identifiers or paths. `apply` preview is not a simulated accepted run and never
records events in a write journal. Valid diagnostic preview exits2, refusal exits1.

Optional `--export` writes the exact recomputed batch JSON as a **private manual
import proposal**, not applied data or approval. Reject shortages/unresolved
adoption, refuse null-wire export with `NO_NEW_ACTIVITIES_TO_EXPORT` (do not
fabricate empty or previously adopted activity body). Validation without export
may still report shortage diagnostics. Limit body bytes before publication.
The output must be under the repository's ignored `outputs/` resolved root;
reject leaf/ancestor path aliases escaping that root and any exact/hardlink alias
of captured config/report/roles before changing directory permissions or files.
Use existing atomic private publication0600/parent0700. Create only the outputs
root; require existing nested parents, reject symlink destination, do not create
other state. Arbitrary external output paths are rejected. Saved proposals can be
manually inspected; uploading is an operator financial action, not this command.
Document that importing a whole manual batch does not inherit our single-event
confirmation/fence protocol. Never encourage manual upload of actual blocked data.
Rollback code revert; retain private exports. Validation failures preserve prior
export and all source bytes/modes. No locks necessary: proposal publication is
atomic, read-only captured input integrity is pinned, and no intent is changed.

## Gate2 — exact-origin bounded reusable HTTPS adapter (package B)

Add `make_ghostfolio_request(allowed_origin,max_bytes,timeout)` returning the fixed
callback signature `request(method,path,body)`. Factory validates canonical HTTPS
allowlist via existing validator, exactGHOST_HOST match and existing environment
GHOST_SESSION_BEARER syntax/bounds. It captures credentials privately once, without
connection or logging. No GHOST_TOKEN fallback, renewal or anonymous authPOST.
Each call permits only GET`/api/v1/activities` withNonebody or POST`/api/v1/import`
with boundedbytesbody. Canonical one-event body is validated before connection;
reject DELETE/PUT/extra paths, URL injection and multi-eventPOST. This adapter is
not itself authorization: only a qualified application controller may call it.
It does not connect from preview or ordinary tests. No new endpoint CLI exists.

Use http.client.HTTPSConnection with default verifiedTLS and explicit timeout,
new connection per call, exact bearer/json/identity headers, no proxy/netrc,
redirect, retry or error-body logging. AcceptGET200/POST201 only, uncompressed
application/json, bounded read(max_bytes+1). Return tuple(status,rawbytes) for
existing core validation; TLS/transport/error status raises fixed safe code with
no underlying exception disclosure. Always close on every outcome; close failure
must not leak exception text or trigger a retry. Network creation, send, headers,
read and close faults are separately characterized. The core has persisted
uncertainty before POST, so failure remains fenced and no automatic replay occurs.
Keep current `snapshot` behavior unchanged initially to avoid unrelated error
contract/publication changes. Duplicated narrow header validation can be factored
later only with evidence, not as a prerequisite.

## Gate3 — qualified application execution (package C, not approved by this plan)

A later exact design must establish operator execution authority and qualified
source/target/version/security/display/recovery/exclusivity evidence matching the
captured report and prepared inputs. Define what an artifact can assert vs what
must be an operational permission action. The existing frozen lab helper is not
production authority; do not silently rename it or drop permanent blockers.
Tie any public execution to one exact target/namespace/report/wire/baseline and
preserve DRY_RUN override, single-event protocol, partial progress evidence,
no-retry and durable fences. Current session may implement later approved code
but cannot run it against production. Independent new owned rehearsals only.
Unattended broker acquisition remains outside scope; manual saved-source input
is the v0 default. Interactive Bourse Direct inspection remains separately allowed.

## Gate4 — acceptance and publication

A: socket/credential/intent-forbidden tests for all dry-run switch combinations,
pin/provenance tamper, actual reference capture once, new/null-wire/shortfall counts,
exact private JSON proposal, destination escapes/symlinks/input alias/hardlinks,
prior output/source/state preservation, size/budget failure and count-only logs.
Exercise preview/export on a private mirror of a retained owned frozen bundle,
compare exact wirehash, preserve original archive and never upload the export.
B: socket-forbidden fakeHTTPS tests verify factory no connection, strictmethod/
path/body/allowlist/bearer/limits, TLS/header/JSONbudget, eachfault/error/redirect
single-shot/close behavior and secret-free fixed exceptions. Exercise the adapter
through the actual existing single-event core with fake responses, including lost
POST response fencing. No need live production or public internet.

Run required fullpytest for each atomic package, semanticdiff/numstat/privacy
beforecommit, authorizedpush parent-before-child and leave PRsOPEN for external
review. Optional real HTTPS lab requires a separate ownedTLSfixture plan and
permission, not weakening certificate verification. A/B completion is interim
operator delivery, not complete project or Gate6/7 acceptance. Beads keeps actual
source and application-execution owners open. Knowledge lookup used fresh indexed
acceptance/date/auth concepts checked against project contracts/pinned source;
no new corpus concept is needed merely for these interfaces.
