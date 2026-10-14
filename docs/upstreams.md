# Ghostfolio release watch

The destination API is monitored through official releases from
`ghostfolio/ghostfolio`. The daily workflow runs at 07:17 UTC on `main` and can
also be started manually. It uses repository-scoped `contents: read` and
`issues: write` permissions.

`.github/upstream-watch.yml` sets the first included release to `3.81.0` and
lists the API contracts to review. This is a notification baseline, not a
claim that Bourse Direct supports that version or every newer version.
The first run includes the baseline and later stable releases. Drafts and
prereleases are skipped. Each run creates at most ten notices, so subsequent
runs can drain a backlog.

Notices carry a marker based on the upstream repository and release ID.
Both open and closed issues acknowledge a release; pull requests do not.
Closing a notice prevents duplication. Release notes are linked rather than
copied. Keyword matches are review hints, not compatibility evidence.

For each notice, inspect upstream changes to activities, import validation,
deduplication, accounts, balances and Security Token authentication. Add offline
regression evidence for affected behavior before adopting the release.
The script uses bounded pagination and request deadlines, refuses redirects
and ambient proxies, and stops on a failed request without retrying a POST.

This watch does not monitor Python or npm package versions. Renovate and
Dependabot retain their existing dependency update roles. The watch never
changes pins, upgrades Ghostfolio, deploys a service or accesses broker accounts.

To roll back, revert the scoped release-watch PR. No service rollback or
dependency change is required.
