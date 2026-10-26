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
# Pinned IBKR check_container_runtime.sh:101+: keep one-off and scheduled checks.
[[ "$smoke_output" == *'Running once'* ]]
for smoke_cron in bad '60 * * * *' '* * * * * *' '* * * * *; id' '@daily'; do
  smoke_status=0
  smoke_output=$("${smoke_run[@]}" --env "CRON=$smoke_cron" "$smoke_image_id" 2>&1) || smoke_status=$?
  test "$smoke_status" -eq 1
  [[ "$smoke_output" == *'Invalid CRON'* ]]
  [[ "$smoke_output" == *'invalid_configuration CRON'* ]]
  [[ "$smoke_output" == *'Summary: simulated=0'* ]]
  [[ "$smoke_output" != *'Failure notification'* ]]
done
# The real isolated worker must dispatch without loading settings or starting a run.
smoke_status=0
smoke_output=$(printf 'invalid payload' | "${smoke_run[@]}" -i --entrypoint python \
  "$smoke_image_id" -I -m ghostfolio_boursedirect_sync --notify-worker 2>&1) || smoke_status=$?
test "$smoke_status" -eq 10
test -z "$smoke_output"
# Real Apprise delivery stays inside this network-isolated container.
"${smoke_run[@]}" --entrypoint python "$smoke_image_id" -I -c '
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from ghostfolio_boursedirect_sync import notify, outcome
received = []
class Sink(BaseHTTPRequestHandler):
    def do_POST(self):
        received.append(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass
server = HTTPServer(("127.0.0.1", 0), Sink)
server.timeout = 15
thread = threading.Thread(target=server.handle_request, daemon=True)
thread.start()
status = notify.send_notification(
    {"urls": [f"json://127.0.0.1:{server.server_port}/hook"], "timeout": 10},
    notify.NOTIFY_TITLE, outcome.failure_summary({"unresolved_security"}))
assert status == "sent", status
thread.join(timeout=2)
assert len(received) == 1 and b"unresolved_security" in received[0]
print("Installed isolated Apprise delivery passed")
for cron in ("bad", "60 * * * *"):
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    result = subprocess.run(["/app/entrypoint.sh"], capture_output=True, timeout=20,
        env={**os.environ, "CRON": cron, "DRY_RUN": "0",
             "APPRISE_URLS": json.dumps([f"json://127.0.0.1:{server.server_port}/hook"])})
    thread.join(timeout=2)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert b"Invalid CRON" in output and b"Failure notification sent" in output, output
    assert output.count(b"Summary:") == 1, output
assert len(received) == 3
assert all(b"invalid_configuration" in body for body in received[1:])
server.server_close()
print("Installed invalid CRON finalization and notification passed")
'
# A real minute tick must reach the installed program's configuration gate.
# Stop only this owned offline container. Retain its logs before removal.
smoke_scheduled_id=''
cleanup_schedule() {
  if [ -n "$smoke_scheduled_id" ]; then
    docker stop --time 10 "$smoke_scheduled_id" >/dev/null
    test "$(docker inspect --format '{{.State.Running}}' "$smoke_scheduled_id")" = false
    docker rm "$smoke_scheduled_id" >/dev/null
  fi
}
trap cleanup_schedule EXIT
smoke_scheduled_id=$(docker run -d --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,noexec,nosuid,size=16m,mode=1777 \
  --env 'CRON=* * * * *' "$smoke_image_id")
smoke_ticked=0
for smoke_attempt in {1..75}; do
  smoke_output=$(docker logs "$smoke_scheduled_id" 2>&1)
  if [[ "$smoke_output" == *invalid_configuration* ]]; then
    smoke_ticked=1
    break
  fi
  test "$(docker inspect --format '{{.State.Running}}' "$smoke_scheduled_id")" = true
  sleep 1
done
printf '%s\n' "$smoke_output"
test "$smoke_ticked" -eq 1
printf '%s\n' 'Installed worker, invalid CRON and scheduled tick passed'
printf '%s\n' 'CONNECTOR_IMAGE_SMOKE_PASSED'
