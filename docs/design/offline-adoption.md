# Offline existing-activity adoption contract

Florent confirms that earlier acquisitions already exist in Ghostfolio. Import
identity alone cannot prove those activities belong to this importer. The approved
plan therefore requires explicit snapshot-bound adoption rather than date/quantity
similarity skips. These pure helpers perform no HTTP request or server mutation.

`parse_remote_activity_snapshot(raw_json)` validates a complete activities response:
exact integer count equals list length, unique remote IDs, required account/type/
date/currency/comment context, nonredacted finite numeric fields and source profile.
JSON floats parse directly as Decimal; duplicate JSON keys fail. Current
`assetProfile` takes precedence; `SymbolProfile` is accepted only if the current
key is absent. Explicit nullable fields follow the
[source-proven schema compatibility contract](remote-schema-compatibility.md).
Trade profile currency must agree with activity price currency before adoption,
holdings coverage or positive write readback can be verified. No conversion rate
is inferred. BUY/SELL quantity must be positive; zero-price history is preserved
for inspection but cannot pass those financial gates.

Activity/account tags and flags determine active context. Draft/exclusion flags
must be Boolean; missing/invalid tag context fails. Reserved draft/exclusion tag
IDs come from official Ghostfolio3.80.2 config at commit806d83f45394bdc70e58d9b178e2ddbdf715de08.
Future timestamps are not treated as active holdings. Account object and accountId
must agree. A timezone is required; no timezone-free timestamp is guessed.

For this bench, the candidate source-date contract is compared only against an
exact UTC-midnight remote timestamp. Same-day nonmidnight records cannot silently
authorize adoption. This is a conservative comparison rule, not proof of the
actual display/API date contract. The isolated API/date gate remains blocking.

A financial fingerprint includes target account, calendar date, type, exact symbol,
data source, price currency, quantity, price and fee. It excludes display names,
source file bytes and ownership comment. Stable owned markers require identical
financial fingerprint, exact account and active/date context. Duplicate owned
markers or changed owned values block. Existing remote rows are never rewritten.

Manual/foreign-importer financial matches become candidates only. A keyed
resolution for each source ID must name one candidate remote ID plus the validated
financial fingerprint. Missing resolutions block; stale fingerprints/IDs fail.
One remote record cannot cover two source occurrences. Two identical activities
require two distinct remote IDs/resolutions. Another Bourse Direct ownership
marker cannot be reassigned through adoption. Extra/stale resolution keys block.

Reconciliation returns private new/owned/adopted/candidate classifications with
`import_ready=false`. `ISOLATED_API_CONTRACT_UNVERIFIED` and
`OPENING_HOLDINGS_UNVERIFIED` remain even when adoption matches. Actual immutable
remote snapshots, current target security/account validation, historical holdings,
API response/date/number/rollback proofs and production permission are later gates.
No claim is made that a live destination was read or that test fixtures prove it.

Tests are synthetic, forbid sockets, and cover incomplete/redacted lists, current
vs legacy profiles, owned conflicts, exact manual resolutions, changed/stale
financial evidence, multiplicity, cross-account separation and inactive/date
context. Blast radius is local source/tests/docs. Rollback: revert this scoped
commit; private snapshots/resolutions and earlier preparation remain untouched.

Sources: indexed KB `operations/ghostfolio/api-traps.md`, pinned official API
activities service and common config at806d83f. The IBKR sibling was inspected for
reference at54958ab1035eb97a1f67f9072b79699813ec3800; no sibling code is copied.
