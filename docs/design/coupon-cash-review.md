# Source coupon cash review

`review-coupons` converts verified monthly coupon credits into a private source
cash review, retaining unsupported-period gates and never producing an API payload.

Florent explicitly approved net cash actually received and the Bourse Direct
booking calendar date on 2026-10-12. Existing destination activities remain
unchanged; different dates or amounts require reconciliation exceptions.

The command consumes one saved monthly statement and its saved operation notes:

```sh
python3 boursedirect_to_ghostfolio.py review-coupons inputs/statement.html \
  --notes inputs/note-1.html inputs/note-2.html --input-root inputs \
  --output outputs/coupons.yaml --max-bytes 1000000 --max-depth 256
```

Each coupon requires exactly one statement row and exactly one note, matched by
the exact source name, booking day and debit/credit fields. Ambiguous multiplicity,
missing or extra coupon notes, changed amounts, unrelated accounts and dates
outside the statement month refuse. The whole original statement cash controls
are verified before conversion; no filtered ledger is represented as complete.
The ISIN comes from the checksum-validated note, never a destination name match.

The daily/preparation missing-ISIN policy explicitly excludes coupons without
source ISIN from import candidates after exact saved-source matching; see the
[daily contract](daily-saved-input-preview.md). The strict standalone coupon
inspection still refuses missing ISIN. Subscription-right corporate actions with
valid ISIN remain exceptions: Florent excludes their resolution from the tool's
capabilities. An explicitly authorized manual reconciliation may use external
primary evidence outside the importer, retaining the original missing identity
and source movements in a private report. Such a report is not importer input,
does not qualify the affected period and cannot bypass its refusal gates.
Testing a manually prepared entry in an owned disposable lab does not add an
automatic resolution capability or authorize production writes.

The amount is the exact EUR statement credit, with `amount_basis: net_received`.
Source signed quantity, displayed unit gross/gross, commission and optional tax
credit remain distinct evidence fields. Commission is not deducted again.
Absent tax credit and explicit zero stay distinct; withholding remains unknown.
Gross-minus-credit is not relabeled as tax and displayed gross semantics are not
asserted. Source coupon quantity never becomes a sale or a holding movement.

The private YAML artifact is `source_coupon_cash_review_not_api_payload`.
It carries input byte hashes, the original account reference, keyed ledger slots,
source calendar dates and exact decimal strings. It does not carry target symbols,
target account IDs, event ownership markers or executable financial wire bytes.
Trade preparation and application cannot consume it. `import_ready` stays false.
Unsupported statement or note operations keep `UNSUPPORTED_OPERATION_PERIOD`;
this review does not authorize importing an independent subset of July.

Inputs retain the bounded inert local reader and declared charset/depth guards.
Output must live under local `outputs/`; source/output inode and path collisions
and symlinks refuse before publication. Successful output uses existing private
atomic YAML publication, mode 0600. Stdout contains only counts and gate codes.
No acquisition coverage journal or destination state is changed.

Destination symbol identity, legacy reconciliation and independent-operation
dependency proof remain separate boundaries. An actual Ghostfolio 3.83.0 check
imported seven source cash amounts on their exact source days, representing each
as DIVIDEND with quantity 1, unit price equal to net cash and fee 0. This amount
carrier avoids dividing cash by source quantities and deducting commission twice;
the signed source quantities and costs stay in the private review.
An unchanged repeat created zero new rows; all seven owned rows were removed and
the disposable containers/network were absent after cleanup. This check uses the
previously qualified artificial AIR.PA fixture profile for all seven payments.
It establishes exact API cash/date behavior, not real source-to-Yahoo identity,
complete period conversion, historical reconciliation or import readiness.
Rollback: revert this scoped implementation commit and retain private captures
and reports; no broker or production rollback is needed.

## Saved destination reconciliation

`reconcile-coupons --config FILE --input-root DIR --output outputs/FILE.yaml
--max-bytes N --max-depth N` recomputes the coupon cash review from the original
statement/notes and compares it with the entire saved destination snapshot. It
does not trust a previously generated cash report as source truth. Configuration
uses the existing schema1 account, per-ISIN mappings and keyed document aliases,
plus a `snapshot` local reference. Coupon mappings require a Yahoo symbol,
`data_source: YAHOO`, `target_currency: EUR` and a nonempty
`target_security_evidence` assertion. No execution-price currency is inferred
from a coupon's displayed gross. Missing source mappings quarantine their source
observations; invalid or colliding distinct-ISIN mappings refuse the report.

Private mapping assertions reuse the qualified exact-ISIN public Yahoo search
and existing destination profile evidence. Multiple venues can appear in that
lookup; selecting the verified existing configured symbol does not claim global
search uniqueness. A profile display name alone is not identity evidence.

Complete snapshot validation retains duplicate-ID, numeric/redaction, account,
timezone, nullable-currency and current/legacy profile precedence guards. The
comparison inspects every saved DIVIDEND for the configured account and symbol,
including inactive, cross-currency/provider and nonmidnight candidates. Such
contexts cannot disappear from the evidence merely because they cannot qualify.
The original timestamp, UTC day, quantity, unit price, fee and quantity-price
product remain visible. That product is not relabeled as net cash or issuer gross.
Product/source-cash and UTC-day/source-day differences are exact observations.

The only certain observation requires one source occurrence and one remote record
globally across all supplied periods, with exact configured Yahoo/EUR context,
the approved booking day at UTC midnight, quantity1, unit price equal to source
net cash, fee0, active context and no foreign Bourse Direct marker. Equivalent
offset spelling of UTC midnight follows the existing snapshot contract.
Identical-source or remote multiplicity quarantines all affected matches;
assignment order cannot select a winner. Same quantity-price product with a
different representation is uncertain, as are old quantities, fees and dates.

The result is `coupon_reconciliation_preview_not_api_payload`: keyed observations
and deduplicated remote evidence, not adoption state, wire bytes, new-activity
classification, holdings coverage or a write intent. A missing candidate means
only absence in this saved snapshot. Unsupported source-period blockers remain;
complete conversion, acquisition history and dividend application still gate
delivery. Existing remote records and preparation journals remain unchanged.

Each file uses the existing no-follow bounded reader. At most256 source documents,
64MiB total captured bytes, one million source/remote comparisons and a report
within max-bytes are allowed; failures preserve the previous report. Publication
uses the same outputs-only collision/symlink and private atomic-write boundary.
Stdout contains counts and fixed statuses only. Tests forbid sockets and shared
application/adoption/intent calls; original-source replay and hard-link refusal
are exercised with isolated synthetic state.

The actual 2026-10-12 check associated all seven source ISINs with the existing
configured Yahoo/EUR target profiles using seven saved exact-ISIN responses.
Two responses offered multiple venues; no global lookup uniqueness was asserted.
Original-source replay against the complete saved 1017-row destination snapshot
found five sources with legacy candidates, two without a saved candidate, and
zero certain exact net representations. An owned Ghostfolio3.83.0 lab then
imported all seven source net credits on their booking days with those verified
symbols. Exact readback, zero-new identical repeat, seven-row rollback and owned
resource cleanup passed. The comparison recognized all seven lab readback rows
as certain unique net representations while retaining the unsupported-period
gate. This establishes the positive amount/date/mapping boundary and conservative
legacy behavior; it does not resolve old dates/amounts or authorize July import.
