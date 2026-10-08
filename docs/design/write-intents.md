# Local durable write intents and replay fences

The offline journal boundary complements [reviewed wire bytes](offline-wire.md).
It does not dispatch requests or expose apply/replay commands. Every result
remains `import_ready=false` and existing preparation/identity journals are intact.

`write_intent_transition` validates a keyed schema1 journal and adds the exact
reviewed UTF-8 body under its SHA256. Its state is immediately `uncertain`, before
any possible dispatch. One uncertain intent fences the whole target account,
including another payload digest. Known body digests are retained as tombstones;
previously accepted markers cannot be resubmitted in a differently shaped batch.
The conservative pre-dispatch crash window requires resolution even if no request
actually left the process. No timeout or empty response grants replay permission.

`persist_write_transition` is the local disk boundary. It shares preparation's
target and account-key locks, pins a separate immutable write binding, bounds the
journal size and uses existing private atomic YAML/fsync/rename persistence.
The namespace cannot change target to evade a fence. Files are0600 and directories
0700. It returns only after durable persistence; persistence failures never return
an intent for a future dispatcher. A crash after rename leaves the persisted
fence visible on the next call. A future transport must use one canonical state
root, perform all source/adoption/holdings/permission checks, hold appropriate
locks and invoke this boundary before sending the exact reviewed body.

`resolve_write_intent` requires a complete saved activity snapshot with validated
count, unique remote IDs, active account/tag context, owned marker, exact full
financial fingerprint and UTC-midnight date. All submitted markers positively
present exactly once resolve to `confirmed`. Unrelated rows are excluded only
after the whole snapshot has passed validation. A duplicate owned marker, changed
account/values or inactive record blocks resolution.

Missing rows, including an empty GET, do not clear uncertainty. An explicit
reviewed independent completion/cancellation record may resolve the request to
`quiescent`: it includes the exact wire digest, evidence reference and reviewer,
plus the saved snapshot digest and exact accepted subset. This is an explicit
operator assertion about external proof, not an automatically verified server
condition. Elapsed time, process restart, HTTP success and absence are not proof.
The isolated recovery gate must establish a truthful completion/cancellation
procedure before any actual transport can consume this path. Conflicting readback
cannot be excused by such a record. Neither resolution path dispatches or
automatically replays anything; exact known body digests stay rejected.

This disk journal assumes retained private state. It is not tamper-proof and does
not detect an operator deleting all binding/journal files. Missing historical state
requires a future recovery preflight with remote/source evidence, never a blind
fresh start. POST acceptance alone cannot settle it because full GET context and
delayed-insertion recovery remain required. Same-day ordering, chronological
holdings and actual destination/version/security validation remain later gates.

Tests use only synthetic isolated temporary directories and forbidden sockets.
They cover complete, partial, empty and conflicting readback, explicit proof,
corrupt state, account migration, oversized state, persistence failure and a crash
after durable rename. Rollback: revert the scoped code/docs/tests commit while
retaining all private journals and bindings; never remove uncertain evidence.
Blast radius: local state only. No Ghostfolio instance or shared Beads is used by
the tests.

Authority: [reviewed plan sections9/11](../plans/2026-10-08-manual-document-import.md)
and [Astra R1](../reviews/2026-10-08-manual-document-import-astra.md). Concrete
delayed-request feasibility is still an isolated API gate, not established by
these local state-transition tests.
