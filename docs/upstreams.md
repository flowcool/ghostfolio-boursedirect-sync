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

## Checksummed binary release watch

The separate `dependency-release-watch.yml` workflow runs daily at 07:29 UTC
on `main`, or manually. It reads the Bitwarden CLI and Chrome headless-shell
download versions from the Dockerfile. It never reads Python or npm manifests.
Renovate owns ordinary package updates; Dependabot owns security fixes.

Bitwarden notices use stable `cli-v` releases from `bitwarden/clients`, excluding
drafts, prereleases and releases of other clients. Chrome notices use the
[official Chrome for Testing catalog](https://github.com/GoogleChromeLabs/chrome-for-testing#json-api-endpoints),
restricted to available `chrome-headless-shell` builds for `linux64`. The catalog
includes several release channels. A notice reports availability, not approval
of the Stable channel; review the channel before adopting a version.

Each newer version gets a notice with the current pin, version-change level,
official release metadata link and manual checksum-update checklist. Markers
identify component and version, including equivalent trailing-zero spellings.
Open and closed notices prevent duplicates; pull requests do not. Each run
creates at most ten issues, with remaining notices deferred to the next run.

The workflow uses `contents: read` and `issues: write`, with serialized runs.
GitHub requests reuse the Ghostfolio watch's bounded client. Chrome catalog
requests have a 30-second deadline and a 16 MiB response limit, refuse redirects
and ambient proxies, and never receive the GitHub token. An upstream failure
stops the run before issue creation. No container, broker login or Ghostfolio
write is needed. This watch does not change Dockerfile pins, checksums, builds
or deployments. Revert its scoped PR to remove it.
