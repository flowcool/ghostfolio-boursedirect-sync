# Upstream references

## BillCollector acquisition

BillCollector owns broker login, vault access and original PDF acquisition.
The importer reads the archived originals through a read-only Paperless token.
The fork and public upstream have separate delivery and acceptance records.

For the fork daemon, start with the
[Infra runtime contract](https://github.com/flowcool/BillCollector/blob/886eba1e065b3cbb5b598aa9957364aea03aa913/doc/INFRA_RUNTIME_CONTRACT.md)
and the [Bourse Direct guide](https://github.com/flowcool/BillCollector/blob/886eba1e065b3cbb5b598aa9957364aea03aa913/doc/BOURSE_DIRECT.md).
These references describe the reviewed source snapshot of 30 October 2026.
Resolve the deployed revision from its operation record before a live action.

The daemon publishes to the global `download_dir` with an empty consumer
registry. Paperless consumes the files. Its workflow sets owner, reader rights
and the exact custom field `Source=Bourse Direct`. Verify those fields and the
original SHA-256 in Paperless. A successful collector run or a `consumed`
download row proves local publication only. Keep the database and hidden
publication journal together for recovery.

The fork supports native Download All and Download incremental on one task.
Both Bourse Direct actions read offered PDFs before revision comparison.
A known source key alone cannot establish that a notice has not changed.
Keep the exact image, recipe and mounted schema in each qualification receipt.
Provider harnesses that inject credentials do not qualify the daemon's vault
transport, scheduling or Paperless delivery.

Public upstream integrated opt-in notice identity in
[PR #41](https://github.com/s-t-e-f-a-n/BillCollector/pull/41), closed after
mirror integration at `e83c8e2`. Its
[notice contract](https://github.com/s-t-e-f-a-n/BillCollector/blob/e83c8e2031a6f96bbce9c6834bb3a8930c348c5b/doc/NOTICE_IDENTITY.md)
assigns repeat suppression to the collector. It scopes identity by task and
source, then compares a versioned PDF graph digest. Originals stay unchanged.
This integration does not resolve the separate archive-receipt interface or
prove the public Bourse Direct recipe. Read the maintainer's closing comment;
an upstream PR closed without a merge can contain an accepted contribution.

Review source changes separately from image publication and deployment.
Upstream integration alone does not qualify a changed fork image or a live run.
Retain independent financial acceptance for the importer.

## Ghostfolio release watch

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

This watch does not monitor Python package versions. Renovate and
Dependabot retain their existing dependency update roles. The watch never
changes pins, upgrades Ghostfolio, deploys a service or accesses broker accounts.

To roll back, revert the scoped release-watch PR. No service rollback or
dependency change is required.
