# Contributing

This page is for source contributors. Operators who want to run the released
connector should start with the [README](README.md). Changes are welcome through
GitHub pull requests; read the [documentation map](docs/README.md) and the
relevant [design contract](docs/design/index.md) before changing behavior. The
release is an AMD64-only, one-shot acquisition and dry-run preview; a change
must preserve the stated account, financial, credential, and transport
boundaries.

## Development setup

Use a Linux AMD64 host with Python 3.13, Node.js 20, Docker Engine and Docker
Compose v2. The public synthetic checks need Python and Node.js dependencies;
they do not require Docker, broker credentials, a vault, or a Ghostfolio server.
The container image build itself requires Docker and network access to fetch its
pinned base image and dependencies.

Clone the source repository, then install and run the offline checks:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix collector --ignore-scripts --no-audit --no-fund
.venv/bin/python scripts/check-docs.py
.venv/bin/python -m pytest tests -q
npm test --prefix collector
```

Checks use synthetic inputs and isolated state. Do not put broker documents,
credentials, account identifiers, or private acquisition receipts in GitHub
issues, pull requests, or fixtures. Never point a test or disposable lab at a
production Ghostfolio instance.

To build the container locally, use the source-only override:

```sh
docker compose -f compose.yaml -f compose.build.yaml build bitwarden
docker compose -f compose.yaml -f compose.build.yaml run --rm bitwarden connect
```

The published user archive contains Compose files and documentation, not the
application source, `Dockerfile`, or build override. Use a source checkout for
development. Keep both Compose files on the `run` command so it uses the local
image produced by the build. `compose.yaml` on its own always uses the pinned
release image.

## Pull requests

Keep each pull request focused and describe the user-visible result, relevant
security or financial implications, and the checks run. Preserve exact date,
Decimal, currency and fee handling; source-to-note matching; persistent account
bindings; and the stop-on-uncertainty behavior. A preview is not a financial
write or permission to add one. Changes to acquisition, credentials, financial
conversion or recovery need the owning design contract and boundary-specific
synthetic evidence.

GitHub Actions runs documentation/link checks, the Python and Node.js offline
test suites, whitespace checks, container builds and vulnerability scans. Changes
to the release workflow or packaging must also preserve the release contents,
checksums and final manual publication gate documented in
[the release procedure](docs/operations/releasing.md).
