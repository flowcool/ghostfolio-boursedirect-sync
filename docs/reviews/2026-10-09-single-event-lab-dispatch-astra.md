# Single-event lab dispatch — independent design review

Date: 2026-10-09. Design owner: `infra-4g8u.49`.
Reviewed code: `7f1be85c8783c5c3107f736e489178aee0a6f0cc`.
Initial proposal SHA256: `d28eab44a5ba15d585e8844b45967932dec35e103d9f1e15def9b96ab377ab9a`.
Accepted amended proposal SHA256: `d9f31b0511ae21294a21b8fe1a02c38d6b5e3f8d2822d360f0d66bafb11b94ca`.

## Verdict

**GO for the two scoped laboratory implementation packages.**
R1 and R2 were incorporated into the amended plan and independently reread in
this review. No design blocker remains. Satisfy the implementation gates below;
material deviations require design reconsideration. This is
a design review, not code approval, PR review, production authorization or proof
of real-account adoption. No private input, network, Docker or Beads mutation was
used. The report is handed to the owning session for its atomic documentation commit.

The proposed single exact body, continuous target/account locks, durable uncertain
intent, one POST, independently matched accepted ID and whole transition check
are appropriate. A trusted injected adapter is honestly described as an outer
laboratory boundary, not a security sandbox. Separating core tests from the real
owned-runner bench preserves meaningful acceptance ownership.

## R1 — complete-transition comparison needs richer semantic rows

Initial blocking clarification, resolved in amended Gate2 and Gate4. `parse_remote_activity_snapshot` (lines820–885)
retains UTC calendar day and a midnight boolean, but loses the full instant.
Changing an unrelated baseline row from noon to 13:00 on the same day therefore
compares equal. `remote_active_context` collapses account/activity flags and tags
into one boolean; adding a nonreserved tag also compares equal. For nontrade rows,
profile identity is omitted. Reusing its returned dictionaries alone cannot meet
the proposed unchanged financial/date/context transition guarantee.

Use a dedicated bounded comparison map which augments the existing normalized
row with the complete normalized UTC instant and explicitly selected persistent
context: account identity, activity/account draft and exclusion flags, canonical
sorted tag IDs, and available profile symbol/dataSource/currency identity even for
nontrade rows. Distinguish absent context when necessary; document allowed
normalization (for example equivalent timezone spellings and tag order). Ignore
only explicitly enumerated runtime market metadata. Compare baseline and fresh
GET using the same map; compare preexisting rows after POST using that map too.
Do not reinterpret a priceCurrency or eligibility boolean as proof that the raw
persistent profile context is unchanged. Freeze time-dependent eligibility at one
evaluation instant, or explicitly account for the future-date boundary.

Required regressions: same-day nonmidnight timestamp drift; nonreserved tag change;
flag changes whose collapsed active boolean remains false; nontrade security
context change; harmless list/tag order and equivalent instants. Source-row
acceptance still requires active, financially verified, exact UTC-midnight context.

## R2 — distinguish confirmation failure before and after publication

Initial blocking correction, resolved in amended Gate3 and Gate4. The assertion that every confirmation persistence
failure leaves the last durable state uncertain is incompatible with
`atomic_private_bytes` (lines648–667): it replaces the journal before directory
fsync. A directory open/fsync failure can leave a visible confirmed journal.
Rewriting it back to uncertain is neither a safe rollback nor a durability proof.

Specify instead: before confirmed-journal replacement the retained intent is
uncertain; after replacement a failed durability acknowledgement may leave either
the prior uncertain state or a confirmed tombstone after recovery. Both retain the
exact digest/accepted marker and prohibit redispatch of this event. Any reported
persistence failure aborts the current sequence, returns no successful dispatch
result, and does not automatically retry or proceed to another event. Do not
promise that every fresh invocation is account-fenced after an acknowledged
failure when confirmed state may already be visible; a stronger persistent error
fence would require a separate protocol and is outside this schema-preserving plan.

Test failures before replace and after replace/before directory fsync separately,
including fresh-process rejection of the same digest and of a changed payload
reusing an accepted marker. The normal success path must await directory fsync.
The uncertainty publication path must never POST on any persistence exception,
even if its uncertain rename already succeeded.

## Mandatory implementation gates

1. Bound review and supplied baseline byte lengths before parsing, validate
   `max_bytes` as a positive integer (excluding bool), and use exact integer
   statuses and bytes-only callback bodies. Review validation reconstructs canonical
   wire bytes and verifies binary64 decimal roundtrip before dispatch. Do not
   weaken it into digest-only validation. Validate every retained journal before
   callbacks, then compute the intent transition in memory before baseline GET so
   uncertainty, digest and accepted-marker fences cannot trigger a network call.
2. Extract the proven Decimal tuple length guard before any fixed-point formatting
   or financial fingerprint, for both baseline/fresh/readback snapshots. Raw byte
   limits alone do not bound `1e999999999` expansion. POST has a different DTO from
   complete GET: reject duplicate JSON keys/nonfinite scalars and bound numeric
   shapes before the existing acceptance comparator. Mask InvalidOperation,
   malformed timestamps and transport errors with fixed codes; never leak raw
   callback exception text through exception chaining. Test tiny exponent payloads,
   negative exponents, NaN, boolean numeric values, malformed shape and oversized
   bodies, including irrelevant response metadata.
3. Extract shared lock acquisition and private persistence without reacquiring
   either flock. Close the first descriptor if second-lock acquisition or journal
   loading fails; close both on callbacks, parsing and publication errors. Verify
   existing lock files are regular and private, not merely created with0600.
   Do not unlink lock files or expose a CLI path accepting external lock handles.
   Check real competing descriptors/processes at all three callback boundaries;
   a monkeypatched flock call count alone does not establish continuous exclusion.
4. Require comparison status `complete`, exactly one accepted marker/ID, accepted
   ID absent from baseline, and final ID independently equal to that response ID.
   Full transition validation must precede the pure positive resolver: the latter
   intentionally ignores unrelated drift. No readback after ambiguous acceptance,
   no automatic quiescent resolution, no empty-readback replay permission. Tests
   must include quiescent tombstones, changed-digest accepted-marker reuse, marker
   collisions in other accounts/types, and failed confirmation boundaries.
5. Runner integration must retain the original batch as proposal evidence while
   archiving the actual one-row bodies/digests and per-event readback. Refresh the
   final saved snapshot **and its matching history evidence** before the zero-new
   second review; returning readback bytes alone does not update the current
   runner's `inputs/snapshot.json` and `history.yaml`. Assert three POSTs, three
   confirmed tombstones, count6, zero-new review, delete6/count0 and verified owned
   resource absence. Stop the sequence on any helper failure and preserve journals.

## Evidence and limits

Inspected the exact wire builder/reviewer, response comparator, complete snapshot
normalizer, fingerprints, journal validation/transition/resolution, locking and
atomic publication, bounded retained-intent observation and the runner's owned
HTTP adapter and full lifecycle. Existing tests must pass unchanged, plus the
specified synthetic socket-forbidden regressions. No implementation or real
execution was reviewed in this design-only pass.

Knowledge verdict: **Nothing durable**. A narrow Ghostfolio index lookup and the
existing import-acceptance/date concept corroborate the already-canonical retry
and date boundaries; lookup occurred after initial code reading. Findings here
belong in this project design and its tests, not a duplicate KB concept.
