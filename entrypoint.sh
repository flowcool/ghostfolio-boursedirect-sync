#!/bin/sh
set -eu
exec python -m ghostfolio_boursedirect_sync "$@"
