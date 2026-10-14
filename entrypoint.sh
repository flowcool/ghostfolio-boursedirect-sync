#!/bin/bash
set -eu

# Preserve the released inspection/preview commands for explicit operator use.
if [ "$#" -gt 0 ]; then
    if [ "$1" = "recover-notice-write" ]; then
        exec /opt/venv/bin/python /opt/app/boursedirect_to_ghostfolio.py "$@"
    fi
    exec /opt/venv/bin/python /opt/app/scripts/community_connect.py "$@"
fi
if [ -n "${CRON:-}" ]; then
    # Numeric fields only: the environment can never supply a shell command.
    if [[ ! "$CRON" =~ ^[0-9*/,-]+([[:blank:]][0-9*/,-]+){4}$ ]]; then
        echo 'Invalid CRON: expected five numeric schedule fields' >&2
        exit 1
    fi
    crontab_path="$(umask 077; mktemp)"
    # The managed scheduler needs no Sentry/HTTP client.
    unset SENTRY_DSN SENTRY_ENVIRONMENT SENTRY_RELEASE
    printf '%s /opt/venv/bin/python /opt/app/boursedirect_to_ghostfolio.py --sync\n' "$CRON" > "$crontab_path"
    if ! supercronic -test "$crontab_path" > /dev/null 2>&1; then
        echo 'Invalid CRON: schedule validation failed' >&2
        exit 1
    fi
    echo 'Running with validated cron schedule (nonoverlapping)'
    exec supercronic "$crontab_path"
fi
echo 'Running once; DRY_RUN defaults to simulation'
exec /opt/venv/bin/python /opt/app/boursedirect_to_ghostfolio.py --sync
