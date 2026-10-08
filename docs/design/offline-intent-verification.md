# Saved retained-intent observation command

`verify` compares a retained write journal with a saved complete activity snapshot.
It is entirely offline and does not create/resolve intents, change fences or
journal state, fetch a snapshot, export wire bytes or send/replay requests.
Design authority: [approved plan](../plans/2026-10-09-offline-intent-verification.md)
and [Astra review](../reviews/2026-10-09-offline-intent-verification-astra.md).

```yaml
schema_version: 1
journal: retained-journal.yaml
snapshot: captured-activities.json
```

```sh
.venv/bin/python boursedirect_to_ghostfolio.py verify \
  --config inputs/verify.yaml --input-root inputs --max-bytes 1048576
```

Both references are relative to the explicit input root. The config and each
input are captured once as bounded regular local bytes. Strict keyed YAML, exact
retained body/digest/binding validation and whole-snapshot count/ID/context checks
apply before selecting rows. Captured-byte SHA256s bind the output provenance.
No supplied cancellation reference or readiness flag grants additional behavior.

## Meaning of the report

Private `outputs/verification-<account-key>.yaml` retains each recorded state
separately from presence in the supplied capture. It reports marker counts and
fixed evidence codes. All rows participate in ownership lookup, including wrong
accounts, nontrades, inactive rows and repeated markers. Exact numeric/fingerprint
and UTC-midnight/context evidence is required for `EXACT_POSITIVE_READBACK`.
Accepted remote IDs stored in a resolution are checked independently: replacement
IDs and changed/missing markers cannot silently satisfy the old recorded identity.

| Code | Observation only |
| --- | --- |
| `OWNED_ACTIVITY_ABSENT_IN_CAPTURE` | No row with the expected marker in these bytes |
| `OWNED_MARKER_DUPLICATE` | Multiple rows share the expected marker; none selected |
| `OWNED_ACTIVITY_FINANCIAL_CONFLICT` | A single marked row differs from the retained sent fingerprint |
| `OWNED_ACTIVITY_CONTEXT_UNVERIFIED` | A marked row lacks active/date/financial readiness context |
| `JOURNALED_REMOTE_ID_CONFLICT` | Stored accepted ID and marked row identity disagree |
| `PRESENT_MARKER_NOT_IN_RECORDED_ACCEPTED_SET` | A quiescent record did not accept this marker, but the supplied capture contains it |

A confirmed intent can be absent after deliberate compensation. An uncertain
intent can have all expected exact rows in a supplied capture. Neither observation
changes the journal or proves capture freshness, cancellation, safe replay or
production readiness. A saved snapshot may predate journal settlement; evaluation
time is only when this command ran. No code asserts a post-settlement arrival.

Evidence is keyed and allowlisted: IDs, financial fields with exact Decimal
strings, original timestamp and normalized context flags. Raw row/comment/body
and completion reviewer/reference are excluded. Output readiness is always false,
with fixed non-resolution and no-production-write blockers. Stdout contains only
counts/codes/readiness; readable observation exits2, invalid input/publication1.

## Budgets, persistence and preservation

Expected marker references and materialized candidate references each have an
initial10000 cap. Reused historical markers and duplicate rows count per intent
before materialization. Remote Decimal fixed-point expansion is bounded to4096
characters or the smaller explicit byte budget using tuple shape before formatting
or fingerprinting; this includes unrelated rows. Scientific exponent overflow and
oversized output fail without truncation. These are development policy budgets,
not universal API/history limits.

The artifact is privately published with atomic write/fsync/rename under the
existing target preparation lock. Config/journal/snapshot path and existing inode
aliases against the output are rejected before publication. Invalid inputs,
conflicting locks and budget failures preserve previous output and journal bytes.
Directories0700/files0600; original journal and binding are never replaced.

## Evidence and limits

Socket-forbidden tests cover all journal states and complete/partial/empty
captures, ID/marker/financial/context conflicts, provenance after external file
change, whole-snapshot redaction, exact decimal budget boundaries, scientific
expansion, reused-marker candidate budgets, collisions/locks and safe output.
They prohibit journal persistence and demonstrate no resolution call.

On2026-10-09 the retained synthetic owned lab journal was observed against its
pre-compensation count6 and post-compensation count0 captures. The recorded state
remained confirmed in both, while expected source presence changed from3 to0.
Original journal SHA256 remained identical. No new Docker/network or production
request was needed; exact evidence belongs to `infra-4g8u.46`.

Rollback: revert the scoped CLI/tests/docs commit; retain all private input,
journal and observational files. No broker or Ghostfolio rollback applies.
