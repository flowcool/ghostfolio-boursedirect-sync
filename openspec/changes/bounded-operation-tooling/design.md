# Design

## Context

Historical hashes/counts match (1017/1018); six accounts/metadata present, previews absent. Account-dividend Decimal delta differs; binary-serialized addition matches, derivation unproved.

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

Configuration lacks these boundaries; glue requires code. Reuse `ghost_exchange_access_token` in `../ghostfolio-ibkr-sync/ibkr_to_ghostfolio.py`; siblings lack deployment restoration. Historical `phase2-at1-recovery-preview.py:446` used `compose run -e`. A versioned launcher receives stdin, sets child `GHOST_SESSION_BEARER`, invokes recovery.

Exact schema (all keys required):

```text
schema_version: integer=1
target: {ssh_host,hostname,daemon_id,runtime,project,service,network,volume,origin,account_id,source_ref,account_key,consumers,mounts}
pins: {source_commit,build_files,files,installed_image_id}
protected: {paths,sha256,run_id,ordinal,remote_id}
deployment: {allowlist,rollback_image_id}
evidence_root: string
phases: {PHASE:{grant_id,approval_reference,prerequisites,allowed_delta}}
```

PHASE keys are the nine spec phases. Consumers map IDs to states; mounts map destinations to `{type,source,read_only,aliases}`. Build_files/files/sha256/allowed_delta map paths to hashes of exact expected values. Paths/allowlist/aliases/prerequisites are string lists; read_only is boolean; ordinal is integer; other leaves are strings. Reject unknown keys, symlinks and secrets.

Private `evidence_root/authority.yaml`, keyed by grant_id, stores `{phase,approval_reference,config_sha256,source_commit,image_id,prerequisite_hashes,state}`. Prerequisite_hashes is a hash map; state is `started|succeeded|failed|uncertain`; other fields are strings. Consume atomically under lock before dispatch; retain across crashes/rollback.

## Migration Plan

Offline delivery precedes separately validated executable plan. Rollback changes deployment only; retain journals/evidence.
