# Design

## Context

Historical counts1017/1018; six accounts. Account-dividend Decimal delta differs; binary serialization matches, derivation unproved.

## Decisions

Minimal assembly: Docker/Compose, tar and product commands.

| Obligation | Reuse/evidence | Missing boundary |
| --- | --- | --- |
| Target/image | `compose.yaml`; `tests/test_buy_simulation.py` | Fresh exact target/pins comparison |
| Backup/restore | tar; `scripts/disposable_acceptance.py:575` | Inventory/hash/alias-preserving deployment-only restoration |
| Recovery/auth | `scripts/community_connect.py:43`; `tests/test_community_connect.py:72` | Extra account GET; hidden bearer |
| Product recovery | `boursedirect_to_ghostfolio.py:4845`; `tests/test_notice_import.py:280` | Stdin-to-child-ENV launcher |
| Finance | `entrypoint.sh`; `tests/test_notice_import.py:39` | Delegate unchanged; `infra-a3ri` owns dispatch scope |
| Preservation | `boursedirect_to_ghostfolio.py:4747`; `tests/test_notice_import.py:438` | Complete account/cash/aggregate/filesystem comparison |

Reuse sibling `ghost_exchange_access_token` (`../ghostfolio-ibkr-sync/ibkr_to_ghostfolio.py`); configuration/siblings lack these boundaries. Historical helper used `compose run -e`; versioned stdin launcher sets child `GHOST_SESSION_BEARER` only.

Exact schema (all keys required):

```text
schema_version: integer=1
target: {ssh_host,hostname,daemon_id,runtime,project,service,network,volume,origin,account_id,source_ref,account_key,consumers,mounts}
pins: {source_commit,build_files,files,original_image_id}
protected: {paths,sha256,run_id,ordinal,remote_id}
deployment: {allowlist,rollback_image_id}
evidence_root: string
phases: {PHASE:{grant_id,approval_reference,prerequisites,allowed_delta}}
```

PHASE keys match the spec. Consumers map IDs to states; mounts map destinations to `{type,source,read_only,aliases}`. Build_files/files/sha256/allowed_delta map paths to expected-value hashes. Paths/allowlist/aliases/prerequisites are string lists; read_only boolean; ordinal integer; remaining leaves strings. Reject unknown keys/symlinks/secrets.

Private `evidence_root/authority.yaml`, keyed by grant_id: `{phase,approval_reference,config_sha256,source_commit,image_id,prerequisite_hashes,state}`. Hash-map prerequisite_hashes; enum state=`started|succeeded|failed|uncertain`; other leaves strings. Consume atomically under lock; retain across crashes/rollback.

Preflight/pre-install require original_image_id. Build receipt `{built_image_id,source_commit,build_files}` binds actual built digest to source/build hashes before creation; IDs are strings, build_files a hash map. Subsequent phases require built_image_id. Rollback requires built_image_id before, original_image_id after; rollback_image_id equals original_image_id.

## Migration Plan

Offline delivery precedes separately validated executable plan. Rollback changes deployment only; retain journals/evidence.
