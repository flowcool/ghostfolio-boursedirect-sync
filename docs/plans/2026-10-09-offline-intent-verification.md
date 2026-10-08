# Offline retained-intent verification

Date:2026-10-09. Design owner:`infra-4g8u.45`. Astra design gate precedes coding.
Florent authorizes continuing independent implementation without waiting for PR
review; production Ghostfolio writes remain prohibited.

## Problem and scope

The approved [write-intent boundary](../design/write-intents.md) retains exact
wire bytes and uncertainty fences, but the CLI cannot inspect them against saved
readback. Add `verify` as a strictly offline observation command. It neither
resolves nor creates intents, accepts cancellation evidence, changes journal
binding/state, fetches data, exports wire bytes nor dispatches/replays requests.
Positive evidence is an observation, never a changed journal or readiness grant.

The public [owned lab](../design/disposable-acceptance.md) provides both complete
count6 and post-compensation count0 saved snapshots plus its retained confirmed
journal. That permits actual saved-data command verification without production
access. The existing full journal validator, wire validator, remote normalizer,
fingerprint, private publication and target lock mechanisms were inspected.
Runtime behavior remains tied to captured files; no atomic live snapshot claim.

## Gate1 — exact input, identity and provenance contract

Proposed CLI:`verify --config FILE --input-root DIR --max-bytes N`.
Config has exactly `schema_version: 1`, `journal`, `snapshot` path references.
Each input is captured once with the existing bounded regular-file/root/no-symlink
reader. Use captured bytes for parsing and SHA256s. Strict keyed YAML applies.
`validate_write_journal` validates every exact retained wire body/digest and
binding. Validate the whole raw activity snapshot, including count, unique IDs,
null/redaction/context contracts, before selecting rows. Malformed input fails
without output replacement. No caller-supplied engine rules or mutation option.

The command consumes one journal binding/account, including all retained intents.
An empty valid journal is valid observation: zero intents and no delivery claim.
Use a single remote comment index, preserving every row sharing a submitted
marker across **all** accounts, types and active contexts. Do not filter conflicts
before evaluation. Marker occurrence alone is insufficient; no financial
similarity, time window or manual adoption participates.

Limit total expected marker references and total materialized candidate references
independently to10000, with encoded output bounded by the explicit max-bytes
budget. Count reused historical markers and duplicate remote rows before building
each intent's candidate map; fail before the one-over reference is materialized.
Bound every normalized remote Decimal's prospective fixed-point rendering to
4096characters (or max-bytes if smaller), using its tuple/sign/digit/exponent
shape before canonical formatting or fingerprinting. Reject oversized scientific
exponents without expanding their zeroes. Bound the whole normalized snapshot,
including unrelated rows, before comparing/rendering any financial evidence.
These are initial conservative development budgets, not universal
history limits. Characterize exact boundary/one-over cases synthetically. Fail
without truncation. No all-intent × all-remote-row scan is needed.

## Gate2 — per-intent observational semantics

Preserve each recorded state (`uncertain`, `confirmed`, `quiescent`) separately
from current readback. Never relabel it. Report expected/present/exact/absent
marker counts and keyed fixed codes, with only allowlisted private evidence:
remote ID, original timestamp, normalized source day, target account, kind,
symbol/data source/currency and exact decimal strings/context flags. Do not copy
raw rows, free-text comments, wire bodies or cancellation reviewer/reference.
Include evaluation_started_at_utc because activity context is time-dependent.

For each expected marker:

1. No row: `OWNED_ACTIVITY_ABSENT_IN_CAPTURE`. This does not prove a completed
   request, cancelled work, safe replay or stale journal. Compensation can
   intentionally remove an already confirmed activity; recorded state remains.
2. Multiple rows: `OWNED_MARKER_DUPLICATE`; retain all candidate references and
   never choose one. Wrong account/nontrade/inactive rows remain visible.
3. One row: require active, verified midnight/date/financial context and exact
   full sent fingerprint before reporting `EXACT_POSITIVE_READBACK`. Any
   account/financial/date/context difference is a fixed conflict code, not
   inferred acceptance. Use exact Decimal and preserved source calendar values.
4. If the journal resolution's accepted map assigns that marker to a remote ID,
   the readback ID must equal it. A replacement row with the same marker/values
   cannot satisfy that stored-ID evidence. Report `JOURNALED_REMOTE_ID_CONFLICT`.
5. A resolved accepted remote ID appearing with a changed/missing marker is a
   journal-evidence conflict even when the expected marker is absent. Index raw
   normalized IDs and inspect resolution.accepted references independently.

An intent has `all_expected_exactly_present` only when every marker has one
exact/context-valid row and no journal-ID conflict. For uncertain intents this
is matching evidence in this saved capture, not proof of capture freshness or
permission to resolve. The existing **separate** resolution boundary has its own
source/provenance obligations;
verify does not invoke persistence or change fences. Partial/empty/conflicting
evidence stays observational. For quiescent intents, newly present markers that
were recorded absent are `PRESENT_MARKER_NOT_IN_RECORDED_ACCEPTED_SET`; do not infer old
versus later authorized request ownership. Markers may occur in more than one
historical intent, so retain per-digest observations rather than assume global
uniqueness or invent a causal story. A saved snapshot can precede journal
resolution: no code or label asserts post-resolution arrival, recent readback or
authenticated capture time. Evaluation time records when this command ran only.

## Gate3 — private publication and preservation

Artifact:`outputs/verification-<account-key>.yaml`, schema1,
`artifact_kind: offline_intent_observation_not_resolution`, engine contract,
readiness false, binding, exact config/journal/snapshot hashes, evaluation time,
per-intent observations, keyed allowlisted remote evidence, fixed overall blockers
(`VERIFICATION_DOES_NOT_RESOLVE_INTENTS`, `PRODUCTION_WRITES_NOT_AUTHORIZED`).
No output wire/resolution candidate, authorization or replay instruction.

Check resolved-path/existing-inode collision against all three captured inputs
before publication. Use existing private atomic bytes/fsync/rename under the
same target preparation lock. Outputs0600/directories0700. The command may create
its local lock/output, but no original journal or binding is replaced. Previous
output survives invalid input, lock conflict, size/budget failure and collision.
Stdout contains counts, fixed codes and readiness only, never IDs/financial values.
Readable observation exits2; invalid input or publication failure exits1.

## Gate4 — verification and delivery

Socket-forbidden tests cover complete/partial/empty/duplicate/conflicting readback,
wrong account/type/date/activity context, original accepted ID with changed marker,
same marker replacement ID, all three journal states, post-quiescence arrival,
historical marker reuse, strict whole-snapshot invalidation, exact Decimal,
captured-byte provenance, empty journal, per-input/hard-link collisions, lock/budget/
size failure, reused-marker × duplicate-row materialization limits, oversized
scientific Decimal rejection before formatting, stale snapshot without temporal
claims, private permissions/safe stdout and **unchanged journal bytes**.
Prove no call to persist_write_transition or any socket/transport occurs.

Run required full pytest and inspect semantic diff/numstat. Then run verify on
the retained **synthetic owned lab** journal with count6 and count0 snapshots:
the confirmed journal remains byte-identical and each result accurately separates
recorded acceptance from current presence. No new lab or production call needed.
Audit reachable Git history before publishing open stacked PR; leave CodeRabbit
and merge external. Do not declare root epic complete from this helper command.

Blast radius: one private observational output/local lock and versioned CLI/tests/
contract. Rollback: revert scoped implementation commit, retain original inputs,
journals and observations. No broker or Ghostfolio state changes.
