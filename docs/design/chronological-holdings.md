# Conservative offline historical sale coverage

`verify_chronological_holdings` consumes prepared strict trades, raw complete
saved activities JSON, explicit adoption resolutions and snapshot-bound history
evidence. It performs no network or state mutation and always keeps readiness
false. Full snapshot validation and adoption run first; unresolved manual matches
cannot be silently skipped or counted twice.

The operator's history evidence must explicitly assert complete acquisition
history, bind the exact snapshot SHA256 and target account, and record a reviewer
and supporting reference. This is an explicit reviewed assertion, not proof
inferred from a complete API count. Real existing acquisitions have not yet been
inspected here; Florent's prior statement that they exist does not substitute for
this snapshot-bound record. Missing acquisition history never manufactures an
opening BUY from current holdings or a statement balance.

For the prepared symbols, active existing BUY/SELL records plus only genuinely
new prepared trades form the timeline. Owned/adopted source trades appear through
their existing remote records exactly once. Other-account, draft, excluded and
future remote records cannot cover a sale. Current source future dates block.
Relevant quantity records require explicit EUR/YAHOO and verified UTC-midnight
calendar context. Unsupported active target types block; pinned enum DIVIDEND,
FEE and INTEREST do not change security quantities. No corporate-action ratio,
transfer or split is inferred. Required source security mappings remain a prior
gate; other supported securities do not contribute holdings to these symbols.

The check starts at zero on a declared complete acquisition history and groups
trades by date and symbol. Prior-day quantity must cover all sales on a day before
crediting that day's purchases. Without an independently proved execution-order
contract, same-day purchases cannot authorize sales. This is deliberately
conservative and can block legitimate intraday buy-then-sell histories. A future
extension needs reviewed chronology evidence, not a guessed order. All quantity
sums/subtractions use sufficient local Decimal precision; no current net or later
purchase can erase an earlier shortfall.

Results contain exact private ending quantities, dated shortages, reconciliation
and coverage verdict. A coverage verdict is only one gate: actual destination
version/account/security, review approval and financial/API readiness remain.
Synthetic socket-forbidden tests cover missing/future/same-day acquisitions,
owned/adopted multiplicity, manual ambiguity, context/foreign account/draft,
fractional precision and stale history evidence.

Rollback: revert scoped local code/tests/docs commit; no journal or remote mutation.
Authority: reviewed plan section7, full snapshot adoption and the pinned official
3.80.2 Type enum at806d83f45394bdc70e58d9b178e2ddbdf715de08.
