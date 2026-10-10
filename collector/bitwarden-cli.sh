#!/bin/sh
# Fixed CLI adapter; env is cleared by the trusted caller. Secrets use stdin.
set -eu
read_value() {
    IFS= read -r encoded || exit 1
    [ -n "$encoded" ] && [ "${#encoded}" -le 5464 ] || exit 1
    printf '%s' "$encoded" | base64 -d 2>/dev/null
}
case "$1" in
    version) set -- --version ;;
    server) set -- config server "$2" ;;
    login)
        BW_CLIENTID=$(read_value)
        BW_CLIENTSECRET=$(read_value)
        export BW_CLIENTID BW_CLIENTSECRET
        set -- login --apikey
        ;;
    unlock)
        BW_PASSWORD=$(read_value)
        export BW_PASSWORD
        set -- unlock --passwordenv BW_PASSWORD --raw
        ;;
    sync|item|totp)
        operation=$1
        BW_SESSION=$(read_value)
        export BW_SESSION
        case "$operation" in
            sync) set -- sync ;;
            item) set -- get item "$2" ;;
            totp) set -- get totp "$2" ;;
        esac
        ;;
    *) exit 1 ;;
esac
exec /usr/local/bin/bw "$@"
