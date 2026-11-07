#!/bin/bash
set -e

# Generated once with pyfiglet 1.0.4, font slant. No runtime renderer.
cat <<'BANNER'
    ____  ____     _______  ___   ________
   / __ )/ __ \   / ___/\ \/ / | / / ____/
  / __  / / / /   \__ \  \  /  |/ / /
 / /_/ / /_/ /   ___/ /  / / /|  / /___
/_____/_____/   /____/  /_/_/ |_/\____/
              Bourse Direct -> Ghostfolio
BANNER

revision=${APP_REVISION:-unknown}
if [[ ! "$revision" =~ ^[0-9a-f]{40}$ ]]; then revision=unknown; fi
printf 'ghostfolio-boursedirect-sync version %s — commit %s\n' "${APP_VERSION:-dev}" "${revision:0:12}"

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
        exec python -m ghostfolio_boursedirect_sync --invalid-cron
    fi
    if ! printf '%s python -m ghostfolio_boursedirect_sync\n' "${CRON:-}" 2>/dev/null > "$crontab_path"; then
        echo 'Could not write runtime crontab' >&2
        exec python -m ghostfolio_boursedirect_sync --invalid-cron
    fi
    if ! supercronic -test "$crontab_path" > /dev/null 2>&1; then
        echo 'Invalid CRON: schedule validation failed' >&2
        exec python -m ghostfolio_boursedirect_sync --invalid-cron
    fi
    echo 'Running with validated cron schedule'
    exec supercronic -passthrough-logs -split-logs "$crontab_path"
else
    echo "Running once (no CRON schedule set)"
    exec python -m ghostfolio_boursedirect_sync
fi
