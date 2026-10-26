#!/bin/bash
set -e

echo "ghostfolio-boursedirect-sync version ${APP_VERSION:-dev}"

if [ -n "${CRON:-}" ]; then
    # Five numeric cron fields only; never interpolate an environment command.
    if [[ ! "${CRON:-}" =~ ^[0-9*/,-]+([[:blank:]][0-9*/,-]+){4}$ ]]; then
        echo 'Invalid CRON: expected five numeric schedule fields' >&2
        exec python -m ghostfolio_boursedirect_sync --invalid-cron
    fi
    if ! crontab_path=$(
        umask 077
        mktemp "${TMPDIR:-/tmp}/bd-crontab.XXXXXX" 2>/dev/null
    ); then
        echo 'Could not create runtime crontab' >&2
        exit 1
    fi
    printf '%s python -m ghostfolio_boursedirect_sync\n' "${CRON:-}" > "$crontab_path"
    if ! supercronic -test "$crontab_path" > /dev/null 2>&1; then
        echo 'Invalid CRON: schedule validation failed' >&2
        exec python -m ghostfolio_boursedirect_sync --invalid-cron
    fi
    echo 'Running with validated cron schedule'
    exec supercronic "$crontab_path"
else
    echo "Running once (no CRON schedule set)"
    exec python -m ghostfolio_boursedirect_sync
fi
