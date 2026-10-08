# Ledger identity and revision contract

The reviewed plan's v1 identity candidate is implemented as pure offline helpers.
`ledger_identity(statement, account_key)` requires a canonical lowercase UUIDv4
namespace supplied by private account configuration. It does not generate or
rotate account keys. Later configuration must persist one immutable key per
source/target binding; never use a broker account number as an ownership marker.

For each supported ledger trade, digest normalization version, statement month,
source calendar date, type, stable original label, signed quantity, stated price,
net debit and net credit, plus ordinal among identical ledger occurrences.
The marker is `BD#v1#<account-key>#<SHA256>` (107 characters). Event names are not
fuzzy-normalized. Decimal values normalize without rounding; negative zero becomes
zero. Raw file hash/name, row slot, ISIN, execution time, fees and target symbol
are excluded. These enrichment/configuration changes cannot create new identities.

Blank-row changes and reorder of unique trades preserve IDs. Two identical
trades receive occurrences 1 and 2, retaining multiplicity; the helper does not
claim to distinguish which original trade changed if a statement is corrected.
All unknown or outside-period operations block. Cash controls are revalidated.

A separate normalized statement fingerprint includes the unordered multiset of
ledger facts and dated opening/cumulative/closing control values. It ignores blank
slots and rendering order, but includes changed money, quantity, labels, dates
and multiplicity. Raw hashes remain separate acquisition/provenance evidence.

`register_statement_snapshot(journal, snapshot)` returns a new keyed in-memory
journal with schema version 1. Accounts are keyed by immutable namespace and
periods by YYYY-MM. An equivalent snapshot is a reimport; a changed fingerprint
or normalization version for the same account-period raises
`STATEMENT_REVISION_CONFLICT`. It never picks a newer file as the winner or
mutates the caller's journal. A reviewed resolution/migration is still needed.

These functions do not persist a journal, link activity records to server IDs,
query Ghostfolio or adopt existing manual activities. Private atomic persistence,
per-target locking, destination comment limits, ownership conflicts, mapping
change detection and existing-activity adoption remain separate work. No marker
from this bench authorizes a remote write. The displayed API date contract is
also unresolved; source dates stay calendar dates internally.

Tests use invented financial documents and namespaces. They demonstrate stable
normalization, account separation, enrichment independence, preserved identical
occurrences, equivalent reimports and changed-period conflicts. Sockets are
forbidden. Rollback is a new revert of the scoped identity commit; source and
conversion helpers plus private inputs remain intact. No external-state blast
radius or secret read is part of this change.
