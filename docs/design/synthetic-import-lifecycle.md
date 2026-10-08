# Synthetic document-to-import lifecycle on Ghostfolio 3.81.0

Observed on 2026-10-09 (Europe/Zurich), under reviewed G5/G6. This joins the
existing preparation, review, exact wire and uncertainty helpers to a real
**disposable** Ghostfolio API. It adds no application transport or apply command.

## Controlled baseline

The [3.81.0 parity bench](ghostfolio-381-parity.md) owns image/source pins,
resource caps and lab isolation. A fresh uniquely owned instance started with
zero activities, two synthetic EUR accounts and no production input, credentials,
network membership or volumes. The laboratory owner seeded three exact prior
BUYs and checked returned account/date/profile/numeric fields, then captured a
complete raw GET with count3. That deliberately constructed history supplies a
truthful **lab-only** snapshot-bound acquisition declaration.

The input statement, buy note and multi-sell note were byte copies of the existing
versioned synthetic fixtures. Configuration retained their synthetic account/ISIN
references and used a newly generated account key plus the exact lab target ID.
Each invented fixture title mapped to a distinct EUR Yahoo bench profile verified
through native seed acceptance. These mappings exercise the engine; they are not
real ISIN-to-security mapping evidence. No real account history declaration was
created or modified.

## Observed complete path

| Stage | Required and observed result |
| --- | --- |
| Saved HTML preparation | Exact note matching and cash controls produced three trades: two SELLs and one BUY; one period |
| Initial saved-snapshot review | Three new activities, zero chronological holdings shortfalls, retained exact UTF-8 wire body/digest |
| Local durable intent | The retained body was persisted uncertain before dispatch; account fence true |
| Owned lab request | One POST of those exact retained bytes, HTTP201; response comparator accepted all three exact identities/financial fields |
| Complete readback | Full GET count6; exact positive resolution matched all source markers and cleared the uncertainty fence |
| Repeat preparation | Byte-identical prepared artifact and stable ledger identities |
| Second saved-snapshot review | Zero new activities, three owned activities, zero shortfalls, `wire: null`; no second source POST |
| Rollback | Six exact owned seed/source activities deleted; full GET count0 |
| Cleanup | Ownership-checked containers/anonymous volumes and exact network removed; task-label container/network lists empty |

Initial and repeated review artifacts both retain `import_ready=false`. The private
controller dispatches only to its freshly created loopback laboratory; no exposed
command accepts a production endpoint. It does not treat the remaining readiness
blockers as cleared for production. The ordinary CLI remains offline except for
its already documented optional read-only snapshot GET.

## Evidence and limits

Owning issue: `infra-4g8u.41`. It records the ignored controller/scenario/command/
event hashes. Event validation checked all six required lifecycle milestones,
accepted3/readback6, zero-new repeat, and deletion6/readback0 before reporting
success. Private input, response, snapshot, preparation, review and retained
journal files remain under the ignored owned lab directory.

This covers the exact supported synthetic fixture and a known complete owned
baseline. It does not establish real legacy fee/date adoption, completeness of
Florent's historical acquisitions, unknown source-operation support, rendered UI
dates, concurrent external writers or production cancellation. Provider availability
was observed on this run and is not a promise for an unattended workflow. Native
response equality plus complete readback is demonstrated, not a substitute for
future origin/permission/baseline/lock/security checks in an application dispatcher.

Rollback was executed on the owned lab. It compensates activity records and does
not restore asset profiles or market data. Documentation rollback: revert the
scoped report commit while retaining private uncertainty evidence. Production
Ghostfolio writes remain prohibited and the importer epic remains open.
