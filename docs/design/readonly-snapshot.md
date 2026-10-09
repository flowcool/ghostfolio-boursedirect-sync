# GET-only saved activity snapshot acquisition

`snapshot` is a narrowly scoped acquisition command. It sends exactly one
`GET /api/v1/activities` to an explicitly allowlisted HTTPS origin, saves the exact
validated raw JSON privately, and stays `import_ready=false`. It never POSTs an
authentication exchange, imports, deletes, updates balances or follows redirects.
No broker request is involved. No live Ghostfolio call was used for its tests.

Private local configuration:

```yaml
schema_version: 1
allowed_origin: https://YOUR_FINAL_HOST
```

Set `GHOST_HOST` to that exact canonical origin and `GHOST_SESSION_BEARER` to an
already obtained session JWT through process environment only. Never put the
credential in a command argument, configuration, file tracked by Git or logs.
The UI's long-lived Security Token is a different credential; it is deliberately
not exchanged here. Session expiry fails closed at the GET without a retry.
Legacy `GHOST_TOKEN` is not silently reused. No unattended renewal is implemented.

The origin must be ASCII canonical lowercase HTTPS, with optional explicit valid
port and no userinfo, path, query, fragment, whitespace or ambiguous spelling.
The independently reviewed config origin must match `GHOST_HOST` byte for byte.
Operator-owned allowlist configuration is a trust boundary; it is not inferred
from the token or a redirect. DNS and the system TLS trust store are used with
default certificate/hostname verification. Explicitly configured private hosts
are supported; no arbitrary URL or endpoint can be supplied to the request.

Only status200 and uncompressed `application/json` are accepted. The explicit
read budget is bounded to one extra byte for detection; timeout is an explicit
integer1–120 seconds per blocking socket operation, not a promised global wall
clock deadline. Response bytes undergo full count/identity/redaction/account/tag/
numeric/date validation before saving. Errors contain codes only, never remote
body, URL, credential or exception detail. The snapshot may cover all user
accounts; no unsupported pagination/filter assumptions are introduced.

The digest-named output `outputs/ghostfolio-snapshot-<sha256>.json` is0600 in0700
outputs, atomically fsynced. It is source evidence for the offline review command,
not proof of complete acquisition history, destination version, current profile
mapping or production write permission. Different snapshots use different names.
Configuration and snapshots stay private under repository ignore rules. Save or
copy the selected snapshot into the explicit review input root when preparing
the review configuration; bind the complete-history declaration to its raw digest.

Publication rejects resolved-path or existing inode aliases against the captured
allowlist config with `OUTPUT_INPUT_COLLISION` before changing the output directory
or replacing files. This preserves config/prior-output bytes and modes when
input-root includes outputs. The guard runs after the single read-only GET because
the destination name depends on the captured response digest; it adds no request.

Tests forbid actual sockets and replace HTTPSConnection with a verified fake.
They prove GET-only requests, TLS context, exact origin match, unsafe URLs/header
injection rejection, no redirect/retry, bounded bodies, malformed/partial JSON
blocking, safe errors and exact private raw bytes. Independent security review is
required before merge under `.claude/rules/security.md`. Actual runtime access
and credential provisioning have not been exercised. Rollback: revert scoped
code/tests/docs commit; retain private saved snapshots. No live mutation.

Authority: indexed shared auth/API knowledge, pinned official auth controller
at806d83f45394bdc70e58d9b178e2ddbdf715de08, and the reviewed transport contract.
