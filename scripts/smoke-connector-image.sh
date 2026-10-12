#!/usr/bin/env bash
# Offline image qualification only; no credentials, broker or persistent mounts.
set -euo pipefail
test "$#" = 1
smoke_image_id=$(docker image inspect --format '{{.Id}}' "$1")
test "$(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$smoke_image_id")" = linux/amd64
smoke_run=(docker run --rm --network none --read-only --cap-drop ALL
  --security-opt no-new-privileges:true --tmpfs /tmp:rw,nosuid,nodev,size=16m
  --workdir /opt/app)
smoke_cli_version=$("${smoke_run[@]}" --env BITWARDENCLI_APPDATA_DIR=/tmp/bw \
  --entrypoint /usr/local/bin/bw "$smoke_image_id" --version)
test "$smoke_cli_version" = 2026.9.1
"${smoke_run[@]}" --entrypoint /usr/bin/python3 "$smoke_image_id" -I -c '
import runpy
runpy.run_path("/opt/app/collector/vault-egress.py", run_name="smoke_proxy")
'
"${smoke_run[@]}" --entrypoint /opt/venv/bin/python "$smoke_image_id" -I -c '
import bs4, yaml, sys, shutil, subprocess
sys.path.insert(0, "/opt/app/scripts")
import community_connect
assert all(shutil.which(name) is None for name in ("curl", "unzip", "pip", "pip3"))
packages = subprocess.check_output(["dpkg-query", "-W", "-f=${binary:Package} ${db:Status-Status}\n"], text=True)
for row in packages.splitlines():
    name, status = row.split()
    name = name.split(":")[0]
    assert status != "installed" or not (name in ("curl", "unzip", "python3-venv")
        or name.startswith("python3.") and name.endswith("-venv")), name
'
"${smoke_run[@]}" --entrypoint node "$smoke_image_id" --input-type=module -e '
import fs from "node:fs";
import {createHash} from "node:crypto";
import "./core.mjs";
import "yaml";
const pin = JSON.parse(fs.readFileSync("cli-pin.json"));
const hash = createHash("sha256").update(fs.readFileSync("/usr/local/bin/bw")).digest("hex");
if (pin.path !== "/usr/local/bin/bw" || pin.version !== "2026.9.1"
    || pin.defaultsVerified !== true || pin.sha256 !== hash) process.exit(1);
'
smoke_browser_version=$("${smoke_run[@]}" --entrypoint /opt/chrome-headless-shell-linux64/chrome-headless-shell \
  "$smoke_image_id" --version)
test "$smoke_browser_version" = 'Google Chrome for Testing 155.0.8059.39'
printf '%s\n' 'CONNECTOR_IMAGE_SMOKE_PASSED'
