# Daily saved-input preview

`daily-preview` recomputes an account's approved 90-day window from original saved
statements, notes and a complete saved Ghostfolio snapshot, retaining unresolved
exceptions and source coverage in private keyed YAML.

```sh
python boursedirect_to_ghostfolio.py daily-preview \
  --config inputs/daily.yaml --input-root inputs --as-of 2026-10-12 \
  --max-bytes 2000000 --max-depth 256
```

The configuration is the same schema as `reconcile-coupons`: `schema_version: 1`,
`account`, `mappings`, keyed `documents` and `snapshot`. Each document entry names
one monthly statement and its nonempty list of saved daily notes. Paths resolve
inside the explicit input root. Account and mapping rules reuse preparation and
coupon reconciliation. No assets are fetched. The command returns exit 2 for a
completed preview, including blocked previews; exit 1 indicates refusal. Standard
output contains counts and fixed codes only. Scheduling this saved-input command
does not activate unattended broker authentication or financial application.

The explicit broker calendar day defines an inclusive 90-day window. All supplied
closed periods are validated before window selection; out-of-window sources can
provide catch-up evidence. Future/current monthly statements are refused. The
report exposes `window_source_events` separately from whole-period reconciliation.
Unknown financial operations still block their period; coupon matching does not
qualify mixed trade/coupon/corporate-action periods.

Current-month operation indices and standalone daily notes are a separate source
boundary; this command currently consumes neither without a closed statement.
The acquired calendar's offered links can be matched to account-bound saved notes,
but that inventory does not prove a through-day cutoff or monthly cash controls.
The observed calendar bytes declare UTF-8 yet fail strict UTF-8 decoding. Retain
the original bytes and that discrepancy; a separate manual inspection projection
does not qualify the index for the strict financial-document reader.
A future current-month observation path must verify the captured account, month,
offered-link inventory and note hashes, preserve refused notes as exceptions, and
keep closed-period coverage unchanged. A matching destination trade with an
unverified timestamp or execution-price currency cannot become a certain match.

An unsupported or malformed daily note records its fixed refusal code as an
unresolved source exception for that period, with the original source digests
retained. It cannot mark source matching complete, clear prior destination
uncertainty, or prevent other valid months from being reviewed. A parsed note
whose account differs from the configured source still refuses the whole command.

Coverage advances only when a saved closed statement passes exact full-period
source matching, either strict trade conversion or an exclusively matched coupon
period. `last_completed_acquisition_period` is the latest such observed period,
not a contiguous-history assertion or an invocation timestamp. Missing or
unqualified months are listed separately from the first required window month
retained by the journal.
Report fields distinguish missing statements from observed periods whose exact
source matching remains unqualified; acquiring a document does not resolve its
financial interpretation. No current-month index absence proves a through-day
cutoff: `current_period_through_day_verified` remains false. If a required gap
falls entirely before the current window month, `resume_requires_catchup` is true
and `DAILY_RESUME_CATCHUP_REQUIRED` blocks resumption. Saved catch-up evidence can
clear the gap; there is no automatic acknowledgement or expiry mechanism.

Strict trades reuse preparation and conservative destination reconciliation.
Source matching and destination certainty are separate. Holdings and financial
application remain unqualified in this preview. Dividends reuse original-source
cash review and global snapshot comparison, with net received cash and broker
booking date. Existing destination activities are never rewritten, adopted or
deleted; absent candidates never authorize creation.

`state/daily-<target-sha256>.yaml` owns observed period fingerprints and keyed
exceptions. `outputs/daily-<account-uuid>.yaml` publishes the current preview.
Existing `state/binding-<account-uuid>.yaml` and preparation ledger bindings are
checked. The existing target preparation lock and account lock prevent concurrent
writers; acquisition or deployment is not controlled by those local locks.
Different account UUIDs cannot reuse a target journal. Binding changes require
explicit migration. Financial statement revisions are refused rather than
silently replacing retained evidence; presentation slots are excluded from the
financial fingerprint, but economic multiplicity and cash controls are retained.

Exceptions remain unresolved when their source disappears or ages out of the
window. Only a fresh matching saved-source/snapshot comparison can resolve an
observed exception. Resolved evidence remains in the journal. Coupon identities
use booking date, ISIN, exact net cash, currency and occurrence; source slots and
file names do not define their durable identity.

All mutable destinations, including lock files, reject input path/inode aliases
before publication. Private directories use 0700; journals, bindings and reports
use 0600 and atomic replacement. Journal publication precedes report publication,
so an interrupted report can be regenerated with the same saved inputs. Neither
file proves a remote write. Input, aggregate, document-count, retained-state and
report-size limits apply. A malformed journal, reversed calendar day, source
account mismatch or occupied lock refuses rather than resetting progress.

Rollback: stop local preview writers and revert the scoped runtime change.
Retain original documents, snapshot, binding and journal. If a newly created
journal must be removed from active use, verify its binding and move it to private
recovery storage; do not delete it or reset uncertain history. There is no service
deployment, broker attempt or production financial mutation to roll back.
