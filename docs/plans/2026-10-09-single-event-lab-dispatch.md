# Single-event owned-lab dispatch

Date:2026-10-09. Design owner:`infra-4g8u.49`. Astra gate before coding.
Florent authorizes autonomous progress and disposable experiments; production
Ghostfolio writes remain prohibited. No public apply command is introduced.

## Problem, inspected chain and deliverable

The portable runner currently assembles batch POST and journal operations manually.
Original I8 requires one-event sequencing and a lock spanning preflight, intent,
dispatch and readback. Existing persistence locks each transition separately;
using it around an unlocked network request is insufficient for future dispatch.
Implement `dispatch_single_lab_intent` in the functional mono-file, with a trusted
injected lab request callback. Wire/schema/journal validation, normalized complete
snapshots, pure resolution, private durability and the complete owned runner have
been inspected. Authority:[write intents](../design/write-intents.md),
[owned runner](../design/disposable-acceptance.md),
[3.81.0 parity](../design/ghostfolio-381-parity.md), original plan sections9–11.

The helper is callable by the opt-in development runner and socket-forbidden
tests only. It has no endpoint, credential, authorization-file, live production
config or CLI route. The runner's existing ownership/image/network/loopback-port
validation remains the **outer security boundary** before every HTTP call.
An injected callable is trusted code, not proof or a sandbox that can prevent a
malicious caller using another endpoint. This helper never grants production or
financial readiness; real source/adoption/security/recovery gates stay separate.

## Gate1 — exact single-event input and lock scope

Proposed function:
`dispatch_single_lab_intent(state_root, binding, reviewed, baseline_raw, max_bytes, request)`.
`reviewed` uses the existing exact body/digest/readiness-false wire contract and
must contain exactly one activity. It must match binding account ID/account key.
No wire reserialization, batching, changed event/date/fee or automatic subset.
Validate finite exact numeric fields and baseline whole-snapshot before dispatch.
Bound captured wire/baseline bytes and all normalized Decimal rendering using
the verified preformat shape guard; no scientific expansion before budget checks.
Apply equivalent bounds to fresh snapshots and response bytes. The callback must
return `(integer_status, bytes)` with bounded raw data. It receives only fixed
`GET /api/v1/activities` and `POST /api/v1/import` plus exact body; no dynamic paths.

Acquire existing target preparation lock then account namespace lock, nonblocking,
regular-file/no-symlink/private modes, and hold both until function exit. Validate
binding and full retained journal inside locks **before any callback**. Any
uncertain intent, repeated digest or previously accepted marker blocks before GET.
Extract existing locked transition/persistence calculation into an internal helper
shared by the old API and dispatch. The old API retains exact contracts/tests.
Do not reacquire flock through another FD while holding it. No caller-supplied
lock FD, simulated production authority or unlocked transition route in the CLI.

## Gate2 — fresh baseline and durable uncertainty

One GET returns200 and a whole valid snapshot. Build bounded semantic rows keyed
by unique remote ID: normalized account/marker/type/date/numeric/security/active
and context fields, augmented with the full UTC execution instant (not merely
day/midnight validity), row/account isDraft/isExcluded field presence and values,
row/account tag ID lists sorted with multiplicity retained, and asset-profile
id/symbol/dataSource/currency field presence and values. Use the authoritative
assetProfile-or-SymbolProfile branch selected by the existing parser. Preserve
unassigned-account distinction. This dedicated captured snapshot helper must not
change the normalizer/adoption/verify schema. Compare this exact semantic map,
independent of activity-list/tag ordering and unrelated runtime market metadata.
Same-day nonmidnight timestamp edits, nonreserved tag edits and profile identity
edits cannot disappear merely because normalized readiness flags remain equal.
This is a complete transition of these explicit identity/financial/context fields,
not byte equality of every market quote or arbitrary server metadata field.
Any added/deleted/changed semantic row fails **before** intent persistence/POST. This is optimistic
comparison, not exclusive access against external writers; the owned lab controls
all writers. Live concurrency remains a later operational gate.

The intended ownership marker must be absent across all baseline rows/accounts/
types/contexts. Do not infer adoption from similar economics. Neither mapping nor
history is proved by this dispatch primitive; the trusted fixture orchestration
owns preparation/review/complete synthetic history and event order.

Persist the exact reviewed intent uncertain with fsync/atomic publication under
the held locks before POST. Verify the binding/journal size and account fence as
in the existing transition. If persistence fails, no POST. Crash after this point
is conservatively fenced, including before send. No catch/finally clears it.

## Gate3 — one POST, exact response and full transition

Perform exactly one POST with retained exact bytes. Never retry on timeout,
transport exception, error status, redirect, malformed/short/oversized response,
skipped/partial/conflicting evidence or a later empty readback. Convert callback
exceptions into fixed safe codes; do not echo raw transport errors/tokens/URLs.
The trusted adapter rejects redirects/encoding and validates owned lab identity
before each call; helper status/body checks remain independent.

Require exact201 and existing complete single-row acceptance with full sent
identity/Decimal/date/profile matching. Its accepted ID must not exist in the
baseline. On any defect, leave the durable journal uncertain and return/raise a
fixed error; no automatic recovery GET or resolution from an ambiguous response.

Then one GET200 whole snapshot must equal the semantic baseline map plus exactly one new
row: the accepted response ID, expected marker and full exact/context-valid sent
fingerprint. Require the ID from POST and snapshot agree independently. Changed
pre-existing rows, additional new rows, missing baseline rows, duplicate ownership,
wrong returned ID, inactive/date/context/numeric conflict block with uncertainty
retained. Never resolve based only on source presence while baseline drift exists.

Only after complete exact transition may the same locked persistence helper
resolve positively and fsync the confirmed journal. A failure before journal
replacement leaves uncertain state. A failure after os.replace, including parent
directory fsync, may leave a valid confirmed tombstone visible with uncertain
crash durability: never promise the old state survives. Either outcome aborts the
sequence, never reports success or sends the next event. A fresh process validates
whatever retained state exists: uncertain fences, confirmed digest/marker tombstones
forbid retransmitting the same event. A later power-loss outcome cannot be inferred
from current filesystem visibility; retain evidence for operator recovery.
Return counts/false
readiness plus the bounded readback bytes to the private lab caller for its next
baseline, not stdout. No token, response dump or body printed. Confirmation proves
this observed laboratory transition, not authenticated production creation or
complete restoration. No new journal schema/creation-authority field is added.

## Gate4 — adversarial socket-forbidden tests

Tests inject fake callbacks, prohibit sockets, and use isolated temporary state.
Assert continuous target/account locks during GET/POST/GET and conservative state
on interruptions at each boundary. Cover exact byte dispatch, one-activity rejection,
binding mismatch, every fence/tombstone conflict before any request, baseline
list-order equivalence and financial/marker/account/context/add/remove changes,
marker already present elsewhere, persistence failure before POST, and one-POST
maximum on timeout/error/malformed/skipped/partial acceptance.

Readback tests discriminate exact source presence from complete transition: extra/
removed/changed unrelated rows, accepted-ID mismatch/replacement, duplicate marker,
changed financial/context/date, empty snapshot and post-intent GET failure retain
uncertain state. Test confirmation persistence failures before rename (uncertain)
and after rename/directory fsync (possibly confirmed visible tombstone), with no
overall success/next event and byte-preserved safe evidence. A new process refuses a second
POST. Bound malformed callback shape/status/body, whole-snapshot redaction,
scientific expansion and input/output sizes; safe errors exclude raw secret text.
Snapshot scalar shapes are bounded before formatting/equality. POST response uses
strict JSON/Decimal parsing, duplicate-key rejection and iterative Decimal tuple
shape checking before the existing DTO comparison; it is not falsely passed to
the activity-list normalizer. Decimal exponent overflow becomes a fixed safe code.
Timestamp/tag/profile semantic augmentation gets separate same-day and nonreserved
tag/profile-change tests; activity/tag ordering alone remains equivalent.
Existing persistence and verify tests must pass unchanged.

## Gate5 — owned runner integration and real evidence

Replace only the runner's source batch POST/journal assembly with chronological
single-event helper calls. Existing seed setup remains owned lab infrastructure.
Build deterministic source order by source date then original wire ordinal; this
is fixture order, not a promise for unresolved real same-day holdings. Generate
each exact one-row body through the existing wire builder from prepared new
activities and retain per-event provenance. Pass latest exact readback as the next
baseline. The original reviewed batch remains a private proposal/archive, not
mislabelled as transmitted bytes. Archive each actual single-body digest and
readback privately; no reuse of a batch digest for individual requests.

Expect three source POSTs, three confirmed tombstones, full count6, byte-stable
source identities, zero-new second review/no extra source POST, owned delete6,
count0 and verified infrastructure absence. Existing private synthetic archives
and old batch benches remain historical evidence, not rewritten. Ordinary CI never
starts Docker; real run is explicit opt-in with existing rollback/access guards.

Split atomic work: first core+fake transport tests, then runner integration+actual
bench. No implementation/review concurrency. Full pytest/diff/privacy audit before
each commit; open stacked PRs and leave external review/merge deferred. No root
completion or actual adoption/history proof is inferred from this bench.

Blast radius: reusable lab dispatch core/local owned state plus development runner
and newly owned disposable resources only. Rollback: revert scoped commits; retain
uncertain journals and evidence. Runner's independently validated resource-ID
cleanup and final absence checks remain unchanged. No production rollback applies.
