# Candidate: operator actions and activity reconciliation

**Status: inactive draft.** This text is not an OpenSpec change. The active
[`pdf-notice-importer`](../changes/pdf-notice-importer/specs/notice-import/spec.md)
contract stays authoritative. Promote this draft only after that change meets
its acceptance criteria and is archived. No behavior or write authority follows
from this draft.

Source behavior: IBKR
[`clarify-operator-actions`](https://github.com/flowcool/ghostfolio-ibkr-sync/blob/e78bf215b1c3a4cf32e6e9bd2990ef13d38324c2/openspec/changes/archive/2026-10-27-clarify-operator-actions/specs/connector-runtime/spec.md)
and
[`activity-reconciliation`](https://github.com/flowcool/ghostfolio-ibkr-sync/blob/e78bf215b1c3a4cf32e6e9bd2990ef13d38324c2/openspec/specs/activity-reconciliation/spec.md).
These contracts were delivered by
[IBKR PR #322](https://github.com/flowcool/ghostfolio-ibkr-sync/pull/322) and
[IBKR PR #328](https://github.com/flowcool/ghostfolio-ibkr-sync/pull/328).
Apply these behaviors to Bourse Direct PDF evidence. Do not assume that Flex
fields or currency conversions exist in notices.

## Candidate behavior

### Required actions and notifications

A completed run reports each action that the operator must take. Examples
include an unresolved security, a notice that changes shares, a conflicting
activity, and an uncertain financial request. Each action states its reason,
effect and safe next step in private logs.

With `APPRISE_URLS`, the run sends at most one redacted summary. It sends the
summary for failed simulations and required actions in simulation too. An
unresolved action remains eligible on later runs until current evidence shows
that it is resolved. A clean run sends no success
message. A transport timeout has an unconfirmed delivery result. The run does
not retry that delivery. Notification failure does not change financial
selection or the exit code. The external message contains no account, security,
financial value, document ID, local path or secret.

### Optional activity review

The operator can select a persistent review file. The file shows each source
event, proposed destination activity, exact current and proposed values, match
evidence, blocking reason and decision. It also shows activities that already
conform. A displayed match does not authorize a write. A literal `yes` can
approve one eligible correction. A bound `reject` can exclude one false pair
without changing either activity. Unresolved and stale decisions block the
affected correction.

`ACTIVITY_RECONCILIATION` accepts `off`, `conservative`, `balanced` and
`permissive`; its default is `off`. A non-off profile requires the review file.
The profile grants only the bounded automatic corrections below. It never
creates operator approval. Simulation shows `would correct` and makes no
financial write. The existing approved BUY fee-only TTF correction retains its
current behavior unless the future spec explicitly changes it.

### One-to-one correction limits

An automatic match needs one source event and one destination activity in the
same account, of the same operation type and resolved security. A conflicting
ISIN excludes the pair. Fees do not establish identity. A competing source or
target prevents automatic selection. An exact reference takes priority over a
nearby match. No profile merges, splits or deletes activities.

BUY and SELL quantities remain exact. The source notice must pass the current
account, amount, TTF and security checks before any correction. The candidate
gross limits for EUR are those of IBKR: conservative requires exact gross,
balanced permits at most EUR 0.01 and 0.1%, and permissive permits at most
EUR 1.00 and 1%. Both absolute and relative limits must pass. Conservative
and balanced require the same local calendar day. Permissive permits two days
for BUY/SELL and three days for DIVIDEND. A threshold match is not exact
identity. A coupon correction needs separate proof that its PDF net amount
supports the proposed Ghostfolio representation.

An exact source notice may support a correction of comment, business date,
unit price or fee. It must preserve account, operation type, security, BUY/SELL
quantity and every unrelated field. A coupon correction must use its validated
net credit and fixed Ghostfolio quantity of one; it cannot infer a missing
payment from proximity. A legacy `BD#v1` or `BD#v2` comment may migrate only
when the current source account and activity establish unique ownership.
Otherwise, the affected proposal remains manual and makes no automatic write.

Each accepted update keeps an exact before/after record and requires exact
readback. An uncertain result stops further financial writes and is not sent
again automatically. Start with at most one activity update per connector run,
shared by manual approvals, automatic corrections and the existing TTF fee-only
correction. A later run uses fresh source and destination evidence.

## BD validation before promotion

- Map each current BD error and hold to the IBKR action categories. Keep
  informational custody-fee messages out of action reminders.
- Prove every eligible field from an original PDF and a complete destination
  activity read. Refuse incomplete account, security, date or amount evidence.
- Prove legacy reference ownership and collisions against the current BD
  comment generations. Refuse uncertain migration.
- Prove the EUR profile limits, exact quantities, local dates, TTF correction
  budget and coupon representation on retained originals. Keep unsupported
  shapes manual.

Keep Paperless read only, broker login outside this connector, simulation on by
default, no deletion, exact readback and no automatic resend.
