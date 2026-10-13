# v0.2 instrument mappings

Create a private `mappings.yaml` here (`chmod 600`). Compose mounts it read-only
at `/config/mappings.yaml`; `MAPPING_FILE` can select another readable path.
The file is required. Empty YAML is invalid; use `{}` for automatic resolution.
See [mappings.example.yaml](mappings.example.yaml).

Each entry uses an ISIN key and exactly `symbol` and `currency`:

```yaml
FR0000000002:
  symbol: VERIFIED.PA
  currency: EUR
```

These values are synthetic. Verify your actual Yahoo symbol and EUR currency.
YAML takes priority over Ghostfolio's existing ISIN profiles and ISIN lookup.
Automatic resolution requires one distinct eligible Yahoo EUR symbol. Several
rows for the same symbol are one candidate. Missing currency, non-EUR currency
and other data sources cannot establish an automatic mapping. Unresolved,
ambiguous or failed searches log candidate tickers, skip affected BUYs and exit
nonzero after processing resolved BUYs. Venue labels never determine tickers.

Do not publish credentials, account identifiers, mappings or broker documents.

<details>
<summary>Legacy v0.1.1 mapping format</summary>

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

</details>
