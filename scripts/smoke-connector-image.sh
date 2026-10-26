#!/usr/bin/env bash
# Adapted from pinned ibkr scripts/check_container_runtime.sh:26-40,101-112.
# Offline image checks only. No credentials, network or persistent mounts.
set -euo pipefail
test "$#" = 1
smoke_python_version=$(sed -nE 's/^FROM python:([0-9]+\.[0-9]+\.[0-9]+)-.*/\1/p' "$(dirname "$0")/../Dockerfile")
test -n "$smoke_python_version"
smoke_image_id=$(docker image inspect --format '{{.Id}}' "$1")
test "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$smoke_image_id")" = linux/amd64
smoke_run=(docker run --rm --network none --read-only --cap-drop ALL
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777)
"${smoke_run[@]}" --env "EXPECTED_PYTHON_VERSION=$smoke_python_version" --entrypoint python "$smoke_image_id" -I -c '
import _decimal
import glob
import importlib.util
import os
import shutil
import sys
from decimal import Decimal
assert Decimal is _decimal.Decimal
assert sys.version_info.releaselevel == "final", sys.version
assert ".".join(map(str, sys.version_info[:3])) == os.environ["EXPECTED_PYTHON_VERSION"], sys.version
assert os.getuid() == 10001 and os.getgid() == 10001
assert importlib.util.find_spec("pip") is None
spec = importlib.util.find_spec("ghostfolio_boursedirect_sync")
assert spec is not None and "/site-packages/" in spec.origin
assert not glob.glob("/app/*.py") and not os.path.exists("/build")
assert shutil.which("pdftotext") is not None
assert all(shutil.which(name) is None for name in
    ("node", "npm", "bw", "chromium", "google-chrome", "chrome-headless-shell"))
assert not os.path.exists("/opt/chrome-headless-shell-linux64")
print("Installed stable Python package and PDF runtime passed")
'
# Replay the real anonymized BUY layout through the installed parser.
smoke_fixture=$(realpath "$(dirname "$0")/../tests/fixtures/pdf_buy.txt")
"${smoke_run[@]}" --mount "type=bind,src=$smoke_fixture,dst=/tmp/buy.txt,readonly" \
  --entrypoint python "$smoke_image_id" -I -c '
from decimal import Decimal
from pathlib import Path
from ghostfolio_boursedirect_sync.notices import parse_text
notice = parse_text(Path("/tmp/buy.txt").read_text())
assert notice.account_ref == "TESTACCOUNT" and len(notice.trades) == 1
buy = notice.trades[0]
assert (buy.quantity, buy.unit_price, buy.fee) == (Decimal(4), Decimal("25.50"), Decimal(1))
print("Installed real anonymized BUY parser passed")
'
# Start the actual entrypoint. Missing configuration must stop before any I/O.
smoke_status=0
smoke_output=$("${smoke_run[@]}" "$smoke_image_id" 2>&1) || smoke_status=$?
printf '%s\n' "$smoke_output"
test "$smoke_status" -eq 1
[[ "$smoke_output" == *invalid_configuration* ]]
printf '%s\n' 'CONNECTOR_IMAGE_SMOKE_PASSED'
