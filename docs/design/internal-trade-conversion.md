# Internal trade conversion contract

## Scope after the 2026-10-12 daily amendment

This document describes the existing statement-based conversion helper.
Its statement/note cross-matching, monthly cash controls and complete-period
requirements do not apply to the amended [daily product contract](daily-saved-input-preview.md).
The daily path must derive supported operations directly from their notices,
without a statement dependency. Exact financial fields, explicit currency,
account/security binding and refusal to infer missing values remain required.
No runtime behavior changes as part of this documentary amendment.

Florent accepted the strict BUY/SELL initial scope, existing Ghostfolio opening
history, explicitly configured EUR execution for his selected PEA sample, and
blocking of unsupported account periods. FINDINGS section 13 and the keyed
source matrix own the evidence and limitations; Beads owns execution gates.

`convert_matched_trades(statement, note_documents, account, mappings)` is a pure
internal helper. It consumes the strict parser results, checks the source account,
revalidates monthly cash controls, rejects unsupported non-trades and out-of-period dates,
and requires complete unambiguous exact note matching. The explicit missing-ISIN
policy excludes exactly matched operations while retaining original cash controls.
Domestic and foreign sale labels use the same strict nine-slot note and
three-column statement trade fields. `VENTE ETRANGER` does not establish currency:
explicit execution-price evidence remains mandatory, with unchanged gross, costs,
sign, VAT, date and account guards. No partial subset is
returned after a failure. It does not read configuration files, create activities
on a server, serialize a Ghostfolio payload or print financial records.

The explicit account dictionary requires `source_account_ref`, `account_key`
and `target_account_id`. The later configuration/identity layer owns stable
account-key generation, target ownership and migration. Filenames never supply
account routing authority. No account values or credentials are public defaults.

Mappings are keyed by checksum-valid source ISIN. Each entry supplies a Yahoo
`symbol`, `data_source: YAHOO`, `execution_price_currency`, `target_currency`,
`currency_evidence` and `target_security_evidence`. Evidence strings represent
operator-reviewed source/target assertions; the function does not claim to
verify market identity online. Both currencies must agree. Only EUR execution
and net EUR are currently established. Source price-currency evidence must not
conflict. Account type, venue, name and ISIN country are never currency inference.

The selected initial arithmetic is gross = abs(signed quantity) × unit price,
and BUY debit = gross + brokerage or SELL credit = gross − brokerage. Inputs
retain exact Decimal precision; no float conversion, inferred fee or rounding
tolerance exists. Source/note signed quantities agree. Nonzero VAT, foreign
currency or unknown components block until separately evidenced and scoped.

Output records contain positive quantity, type, ISIN, explicit symbol/currency,
price, gross, net, explicit brokerage/VAT/fee, source label/slot, account routing,
statement month, source calendar date and timezone-free execution clock string.
Records are private and `import_ready=false`. No durable event ID or API date is
assigned. Identity, existing-manual-activity adoption, payload number safety,
destination display dates and isolated API recovery remain later gates. Never
pass these internal records directly to a production API.

Validation uses synthetic BUY/multiple-SELL examples, mapping/currency/account
failures, mutated financial evidence, bad signs, incomplete/duplicate notes,
unknown periods and cash controls. Tests forbid network. The existing statement
and note CLI remains a counts-only inspection command.

Blast radius is local project code/tests/docs. Rollback: revert the scoped
conversion commit, leaving the earlier inspection probe and all ignored private
inputs intact. Git/local file access was verified before editing; no external
portfolio, broker, container or secret-store change is part of this contract.

Preparation explicitly enables `include_dividends=True` on the existing converter.
It validates the whole original cash ledger, matches all coupon evidence exactly,
rejects unknown operations, then combines strict trades with approved net-cash
DIVIDEND records. The default pure trade-call boundary stays strict. Dividend
mapping requires an explicit Yahoo/EUR target and security-identity assertion;
source gross price currency is not inferred. Colliding different-ISIN dividend
and trade symbol mappings refuse. No incomplete period returns a partial list.
