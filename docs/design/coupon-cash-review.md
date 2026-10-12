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

Destination symbol identity, dividend representation, exact API acceptance,
legacy reconciliation and independent-operation dependency proof remain separate
boundaries. An isolated amount/date check with artificial lab symbols establishes
only API cash/date behavior, not real source-to-Yahoo identity or import readiness.
Rollback: revert this scoped implementation commit and retain private captures
and reports; no broker or production rollback is needed.
