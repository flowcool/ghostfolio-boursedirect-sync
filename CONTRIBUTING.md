# Contributing

Read the [README](README.md) and the active OpenSpec change under
`openspec/changes/` before changing behavior. The v1 candidate reads PDF notices
from Paperless. BillCollector owns broker acquisition.

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
code head. See the [build guarantees](.github/BUILD.md) and the
[retained release procedure](docs/operations/releasing.md). Stable publication
and production writes require separate authorization.
