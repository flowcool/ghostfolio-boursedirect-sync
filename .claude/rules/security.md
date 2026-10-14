# Security rules — ghostfolio-boursedirect-sync

- Secrets come only from `os.environ`: `BW_CLIENTID`, `BW_CLIENTSECRET`,
  `BW_PASSWORD`, `BW_SERVER`, `BW_ITEM_NAME` and the Ghostfolio token. Broker
  credentials come only from the vault item at run time. Never hardcode, commit or
  log a credential, a vault session, a cookie or an authentication response.
  Logs may show the activity fields of a notice row: date, type, symbol,
  quantity, price and fee. Never log the account number, the holder name, the
  address or the full text of a notice.
- Bourse Direct locks the account after three failed logins: at most one login
  attempt per run, never an automatic retry, and a scheduled run refuses while a
  failed or uncertain attempt is unresolved (see `AGENTS.md` safety invariants).
- Bourse Direct has no public API: the connector reads its website, whose pages can
  change without notice. Fail loud on an unexpected page or document shape; never
  guess a missing field.
- Send credentials only to the Bourse Direct site, the configured Ghostfolio origin
  and the configured vault server. Never send them to a URL taken from page content.
- Personal data stays off Git (`inputs/`, `outputs/`, `state/`, `tmp/`, `audit/`).
  Tests use anonymized fixtures only.
- A change to authentication, vault access, notice parsing or any new external HTTP
  call needs a security review before merge: a completed CodeRabbit review of the
  final head (the docs-only exception does not apply) and a short security note in
  the PR.
