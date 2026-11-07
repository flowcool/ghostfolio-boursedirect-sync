# Contributing

Use [GitHub Issues](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues)
for questions, bugs and feature ideas. Search existing issues first. You do not
need access to a private tracker or infrastructure to contribute.

Include connector version/image digest, source mode, amd64/arm64, Docker/Compose
versions, Ghostfolio version and Paperless version only when used. Share the
fixed error code, exit status and a minimal sanitized reproduction. Keep original
PDFs, review files, full financial logs, tokens, account IDs and private URLs off
GitHub. Use independent synthetic examples. Report vulnerabilities through the
[private security process](.github/SECURITY.md).

Read the [README](README.md), the current
[behavior contract](openspec/specs/notice-import/spec.md) and the approved change
before changing behavior. Keep one branch and one PR per deliverable.
The current v2 importer has no broker login. v2.2 adds optional folder input.

## Development setup

Use the Python release selected in `.github/workflows/offline-tests.yml` and
`Dockerfile`. Install the package and its pinned development dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m ruff check ghostfolio_boursedirect_sync
.venv/bin/python -m mypy --strict ghostfolio_boursedirect_sync
bash scripts/verify-local.sh
```

Offline tests use anonymized notice text, mocked requests and isolated state.
They need no Node.js, browser, vault, broker credentials or Ghostfolio server.
Keep private documents, credentials and account data outside Git and GitHub.

Use Docker Engine and Compose v2 for image checks. The build needs network
access to fetch the pinned base image and dependencies:

```sh
docker build --tag ghostfolio-boursedirect-sync:local .
bash scripts/smoke-connector-image.sh ghostfolio-boursedirect-sync:local
```

The smoke check uses the installed package with network access disabled. It
checks the real anonymized BUY layout, startup, notifications and scheduling.
It creates and removes its own test containers. It does not use shared labs.

## Pull requests

Keep each PR focused. Describe the resulting behavior and the checks run.
Preserve exact Decimal values, source dates, identity, duplicate protection and
stop-on-uncertainty behavior. Follow the approved OpenSpec for behavior changes.

CI checks the typed package, the retained offline suite, documentation links,
whitespace, the native image and dependency security. Pullfrog reviews the final
code head. It is the only PR reviewer; no pre-PR review subagents are required.
Documentation-only PRs run only local-link and whitespace checks. They skip
application tests, images, dependency review and CodeQL. Code PRs retain these
checks. The required `analyze` job blocks CodeQL errors and security findings
with severity medium or higher. Changes to financial logic, identity,
deduplication, authentication, transport, writes, journal/state, major dependencies
or the base image need empty and golden lab proof on the exact PR image before
merge. Reserve shared labs and stop them after use. Every release needs the same
proof on its exact digest; reuse it when the digest is identical. See the [build guarantees](.github/BUILD.md) and the
[retained release procedure](docs/operations/releasing.md). Stable publication
and production writes require separate authorization.

## License

Contributions use the [MIT NON-AI License](LICENSE), including its additional
restrictions. This is not the standard MIT license.
