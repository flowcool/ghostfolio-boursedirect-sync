# Optional security mappings

Create a private `mappings.yaml` in this directory. Compose mounts the directory
read-only at `/config`; the one-shot `connect` command reads `/config/mappings.yaml`.
This file is ignored by Git. A missing mapping appears in the dry-run report and
does not cause the connector to guess a security, symbol, or currency.

Use the security's ISIN as the YAML key. Each entry supplies the Ghostfolio
symbol, supported data source, execution-price currency, destination currency,
and the evidence used to verify the mapping. The following values are synthetic
and illustrate the fields in `tests/fixtures/import-config-synthetic.yaml` only;
they are not real securities or recommendations to reuse a mapping:

```yaml
FR0000000036:
  symbol: SYNTHG.PA
  data_source: YAHOO
  execution_price_currency: EUR
  target_currency: EUR
  currency_evidence: Synthetic operator evidence only
  target_security_evidence: Synthetic target profile only
```

`data_source` must be `YAHOO`. For supported buys and sells, both currencies
must be explicitly verified as `EUR`; the connector does not convert another
currency. Keep the evidence descriptions specific to your own verification.
Do not put account documents, credentials, or personal financial data in this
directory.

Source and destination accounts are configured through the Compose environment
fields or selected during `connect`. The selected pair is retained in the private
persistent state volume. A configured value that conflicts with retained state
stops the run instead of silently changing the route.
