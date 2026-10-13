#!/bin/sh
set -eu

# Preserve the released inspection/preview commands for explicit operator use.
if [ "$#" -gt 0 ]; then
    exec /opt/venv/bin/python /opt/app/scripts/community_connect.py "$@"
fi
echo 'Running once'
exec /opt/venv/bin/python /opt/app/boursedirect_to_ghostfolio.py --sync
