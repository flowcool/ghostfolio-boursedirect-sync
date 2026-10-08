# Security rules — ghostfolio-boursedirect-sync

- No Bourse Direct API: this project reads manually saved local documents; no broker scraping or login automation.
  **3 failed logins lock the account** — never loop logins, never retry an OTP blindly; fail loud and stop.
- Credentials (`BD_LOGIN`, `BD_PASSWORD`, any OTP/TOTP seed, `GHOST_TOKEN`): only from `os.environ`,
  never hardcoded, never logged. OTP values and cookies must never be logged (picsou's sidecar redacts
  them — do the same).
- Secret storage: off-git SOPS store + pointer only (global ops rule). No secret in memory/KB/Beads.
- SMS 2FA is not automatable; do not design an unattended flow around it.
- Any new external HTTP/browser automation or credential handling → run `security-review` before merge.
- Future Ghostfolio transport must validate an exact allowlisted origin and reject redirects,
  userinfo, query and fragment; the audited IBKR sibling has no `validate_ghost_host` helper.
