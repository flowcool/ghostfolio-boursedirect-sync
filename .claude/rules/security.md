# Security rules — ghostfolio-boursedirect-sync

- The importer reads saved local documents. Explicitly authorized interactive source
  collection follows `docs/design/online-source-inspection.md`; unattended scraping
  remains outside the approved design. Three failed logins lock the account: preserve
  the one-attempt authority and stop on uncertain password or OTP outcomes.
- Broker credentials, Ghostfolio tokens, OTP values, TOTP seeds, cookies and CLI
  sessions stay in the approved vault/environment delivery path. Preserve worker seed
  confinement. Never hardcode, commit or log these values or raw authentication output.
- Keep personal source captures, output, configuration and journals off Git; logs and
  public evidence contain structural codes/counts only. Off-git secret storage remains
  owned by its existing provisioning mechanism; this project stores pointers only.
- For new external HTTP/browser automation or credential handling, record main-thread
  checks of the changed security boundary and complete required exact-final-head
  CodeRabbit review before merge/use under the existing acceptance contract. Follow
  AGENTS.md for affected regressions and native proof; unchanged boundaries reuse evidence.
- Preserve exact approved origins, credential exclusivity, redirect refusal and
  one-attempt/uncertain-result fences. A blocked unrelated public resource grants no
  dispatch permission; continuation requires the existing reviewed phase-specific policy.
- Ghostfolio writes require separate explicit authority, exact account/source binding,
  private pre-request archive, confirmed acceptance and recovery controls. Inspect actual
  pinned sibling code before helper reuse; historical plan descriptions are not code proof.
