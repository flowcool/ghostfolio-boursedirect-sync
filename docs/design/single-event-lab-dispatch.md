# Single-event laboratory dispatch core

`dispatch_single_lab_intent` is a reusable lab-only orchestration helper, with a
trusted injected request callable. There is no apply CLI, production endpoint or
authorization override. The existing owned runner is the outer isolation boundary;
this helper does not sandbox arbitrary trusted Python callers or grant financial
readiness. Design authority:[plan](../plans/2026-10-09-single-event-lab-dispatch.md)
and [Astra review](../reviews/2026-10-09-single-event-lab-dispatch-astra.md).

Inputs: local state root, immutable account/target binding, canonical reviewed
single-row body/digest/readiness-false record, supplied complete baseline bytes,
positive integer byte limit and callback `(method, fixed_path, exact_body)` returning
`(integer_status, bytes)`. No credential is accepted; the trusted owned adapter
reads only its generated lab bearer from environment and validates owned resources
before each operation. No raw bodies, IDs or callback errors are logged here.

## Locking and dispatch

The helper validates exact one-row canonical wire data, binding, byte/Decimal
budgets and complete supplied baseline. It acquires private regular target and
account namespace locks and holds both continuously until return/error. Existing
binding/journal and in-memory intent transition are validated before callbacks;
uncertain accounts, known digests and accepted-marker tombstones reject before GET.
The previous persistence API shares the extracted locked transition and lock helper;
it retains the same public contract and regression coverage.

The callback receives one baseline GET. Its200 complete snapshot must match the
supplied semantic map. Marker presence anywhere in the baseline rejects dispatch.
Then exact reviewed bytes are durably journaled uncertain before one POST. Only
201 and complete exact acceptance permit one readback GET. There is no retry or
recovery GET on ambiguous acceptance. Any failure after intent publication retains
conservative evidence and stops; absent readback never allows another POST.

Readback must preserve all prior semantic rows and add exactly one new row with
the POST's independently checked ID, marker and full exact financial/context-valid
fingerprint. Extra/removed/changed rows, duplicates or different response/readback
IDs conflict. Positive resolution occurs only after that complete transition.
Success returns accepted1 and bounded private readback bytes with readiness false.

## Semantic map and budgets

The comparison augments the unchanged normalizer with full UTC instant,
row/account flag presence/value, sorted tag-ID lists retaining multiplicity and
authoritative asset-profile identity fields with presence/value. Nontrade profiles
participate. List/tag ordering and equivalent timezone spellings normalize; time,
nonreserved tags, flags even when eligibility remains false, and profile changes
cannot disappear. Unassigned context stays distinct. Runtime quotes/arbitrary
metadata are excluded; this proves a transition of explicit identity, financial
and portfolio context fields, not every server storage field.

Eligibility is recalculated by the existing normalizer. Crossing a future-date
boundary changes the map and conservatively aborts before POST or leaves an
uncertain post-intent outcome; it is never treated as unchanged evidence.
Intended future activities are rejected.

Input and callback bodies have explicit byte bounds. Strict JSON/Decimal parsing
rejects duplicate keys/nonfinite scalars and iteratively checks every numeric
token's fixed-point shape before fingerprint/DTO comparison, including irrelevant
POST metadata. The shared4096-or-smaller tuple guard does not expand exponent
zeroes. Existing whole-snapshot count/ID/redaction/context validation remains.
Statuses must be exact integers, bodies bytes. Transport exceptions are masked
with fixed codes without exception chaining; no automatic POST retry exists.

## Publication failures and verification

Intent publication failure never permits POST, including failure after rename.
Confirmation failure before replacement leaves uncertain state; failure after
replacement/directory fsync may leave a visible confirmed tombstone with uncertain
crash durability. It never reports success/proceeds/retries or rewrites the journal
back. A fresh invocation checks the retained outcome: uncertain blocks the account,
confirmed digest/accepted marker forbids repeating the event. Visibility does not
prove survival across later power loss.

Socket-forbidden tests exercise real competing lock descriptors at each callback,
strict wire/binding/fence checks, semantic drift and benign reordering, one-POST
maximum, acceptance/readback mismatch, numeric bounds, persistence before/after
publication and actual failed directory fsync. Existing persistence/verify tests
remain required. Core evidence is owned by `infra-4g8u.50`; runner integration and
actual single-event disposable execution are a separate acceptance deliverable.

Rollback: revert the scoped code/tests/docs commit; retain journals and captures.
No production changes, real broker activity, DELETE or production recovery is
covered or authorized by this helper.
