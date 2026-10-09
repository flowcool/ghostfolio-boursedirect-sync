# Offline preparation contract

`prepare --config FILE --input-root DIR --max-bytes N --max-depth N` reads only
bounded local files. Config must live inside the declared input root. Safe YAML
requires string mapping keys, no aliases/anchors, no duplicate keys, and bounded
composed depth. Unsupported top-level/account/document keys fail; credentials
are not part of its schema. Runtime PyYAML6.0.3 is the verified bench version.

Config is keyed: schema version 1, account binding, per-ISIN mappings and document
aliases with a monthly statement plus daily note paths. The account namespace
must be an immutable UUIDv4; source references and target IDs remain private.
All statements/notes use the existing bounded no-follow local reader, explicit
HTML charset and parser-depth budgets. Note matching/conversion enforce the
strict validated EUR/zero-VAT financial scope. Unknown periods, unverified
mappings, multiple supplied versions of a period or ambiguous notes block.

The entire input set is validated before state/output mutation. Publication
guards reject artifact, ledger or binding destinations resolving to
any captured config, statement or note path, including existing hard-link inode
aliases. `OUTPUT_INPUT_COLLISION` is reported before publication; source bytes,
previous journals and previous artifacts remain intact. This includes a common
input root containing both inputs and generated state/output directories.
Pure identity
snapshots detect rendering-equivalent statements versus financial revision.
Records receive their ledger-owned markers and are sorted for review. Decimal
values become exact strings and source dates ISO calendar strings; this is an
internal review representation, never an API serializer/date assertion.

State lives in ignored `state/`, artifacts in ignored `outputs/`. Directories
are 0700 and atomically replaced YAML files 0600. Linux nonblocking advisory locks
cover both target hash and account namespace. Locks are regular no-follow files;
concurrent local preparation fails loudly. Locks and state are local to this
working directory; this does not coordinate other hosts or production writers.

The target journal and account binding prevent silently rotating a namespace,
changing source reference or routing the same key to a different target. These
changes need a reviewed migration. Journals store normalized source fingerprints;
raw input SHA256 digests are separate artifact provenance. The journal never
claims that a Ghostfolio activity exists or that an API request succeeded.

The shared publisher pins the parent directory once with no-follow open and uses
that descriptor for temporary creation, rename, directory fsync and cleanup.
Parent-path replacement after acquisition cannot redirect these operations.
Caller collision checks and cooperative directory ownership remain required;
this does not protect against arbitrary same-user mutation before acquisition or
inside the opened directory. See the [reviewed amendment](../plans/2026-10-09-pinned-publication-directory.md).

After successful validation, the binding/revision guard is persisted before the
review artifact. Each write uses an exclusive temporary file, fsync, atomic rename
and directory fsync. There is no multi-file transaction: if artifact writing
fails after journal update, equivalent source preparation can be retried; previous
artifacts survive replacement failure. No network effect is possible. Symlink
state/output/input boundaries fail. Error diagnostics expose codes only; stdout
contains counts, readiness and gate codes.

The artifact has `artifact_kind: internal_activity_review_not_api_payload`, keyed
activities, source digests, `import_ready: false`, and explicit remote-adoption/API
blockers. No prepare run removes these blocks. Unknown operation periods are not
silently skipped. Production writes, remote existing-activity adoption and isolated
API/date/wire-number tests remain separate gates; there is no apply command.

Synthetic end-to-end tests cover reprepare/renaming, financial label revisions,
account migrations, competing locks, YAML duplicate keys/tags/aliases, path escapes,
output symlinks, configuration failures and atomic-write failure. Sockets are
forbidden. Public fixtures have invented identities/economics/evidence only.

Rollback: revert the scoped preparation commit. Move only newly generated
`outputs/prepared-<account-key>.yaml`, `state/binding-<account-key>.yaml` and
`state/ledger-<target-hash>.yaml` into a private recovery directory if discarding
local preparation state; stop other local preparers first. Retain raw inputs and
authentication journal. Existing source-revision records should not be discarded
to bypass a financial conflict. No broker, vault or Ghostfolio rollback is needed
because this command has no external-state blast radius.
