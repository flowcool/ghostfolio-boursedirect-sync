# Security rules — ghostfolio-boursedirect-sync

- Secrets come only from `os.environ`: the Ghostfolio token and the Paperless
  token. The importer has no broker credential and no vault access. Never
  hardcode, commit or log a credential, a cookie or an authentication response.
  Logs may show the activity fields of a notice row: date, type, symbol,
  quantity, price, fee and the activity comment. The Bourse Direct account
  number appears only in the activity comment (`BD#v3#<account>:...`) and in
  that log line, never in an error, a notification or a test fixture. Never
  log the holder name, the address or the full text of a notice.
- The Bourse Direct login, its lock rule and the vault belong to BillCollector,
  not to this importer.
- Bourse Direct notices can change without notice. Fail loud on an unexpected
  document shape; never guess a missing field.
- Send each token only to its configured origin (Ghostfolio or Paperless). Never
  send a token to a URL taken from document or response content.
- Use Paperless read only, with a user that has view permission only.
- Personal data stays off Git (`inputs/`, `outputs/`, `state/`, `tmp/`, `audit/`).
  Tests use anonymized fixtures only.
- A code change to authentication, notice parsing or any new external HTTP
  call needs a security review before merge: a completed CodeRabbit review of the
  final head (the docs-only exception does not apply) and a short security note in
  the PR. A change of this file or of spec text only is a docs-only PR
  (Florent, 2026-10-15).
