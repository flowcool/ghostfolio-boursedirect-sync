# Design

## Context

`infra-srpp` records Florent's decision and offline field/hash proof: complete 1017/1018 snapshots; archive metadata present. Remote preview copies are unavailable locally. Evidence is historical.

## Goals / Non-Goals

One explicit phase per invocation; reusable preparation/proof functions, no financial engine or automatic progression.

## Decisions

Smallest assembly: Compose/Docker inspection/build/create, tar, product recovery/sync and existing snapshot/comparison functions.

| Obligation | Existing source/test evidence | Concrete remaining gap |
| --- | --- | --- |
| Target/image binding | `compose.yaml`; `tests/test_buy_simulation.py` | ENV binds names, not fresh daemon/mount/config/image equality |
| Backup/selective restore | tar metadata; `scripts/disposable_acceptance.py:575` | Lab rollback deletes activities; no tested inventory/hash/alias-preserving deployment restore |
| One-auth recovery | `scripts/community_connect.py:72-80`; `tests/test_community_connect.py:72` | Snapshot adds accounts GET and retains bearer internally; cannot feed recovery within its one-GET envelope |
| Recovery | `boursedirect_to_ghostfolio.py:4845`; `tests/test_notice_import.py:280` | Reuse unchanged; launcher must pass child ENV securely |
| Financial phases | `entrypoint.sh`; `tests/test_notice_import.py:39` | Reuse Compose/sync; dispatch scope belongs to `infra-a3ri` |
| Preservation | `boursedirect_to_ghostfolio.py:4747`; `tests/test_notice_import.py:438` | Activity comparator exists; no complete cross-account/cash or filesystem comparison CLI |

Configuration cannot add comparisons, restoration or bearer delivery; shell glue is new code. Reuse IBKR `ghost_exchange_access_token` from `../ghostfolio-ibkr-sync/ibkr_to_ghostfolio.py:626`, product transport/comparator. Siblings lack deployment backup/restore.

Exact YAML keys: `schema_version: 1`; `target: {ssh_host,hostname,daemon_id,runtime,compose_project,service,network,volume,consumers,account_id,source_ref,account_key,mounts}`; `pins: {source_commit,build_files,files,installed_image_id}`; `protected: {paths,sha256,run_id,ordinal,remote_id}`; `deployment: {allowlist,rollback_image_id}`; `evidence_root`; keyed `phases: {approval_reference,prerequisites,expected_proof,allowed_delta}`. IDs/paths are strings; consumers/prerequisites/allowlist are lists; files/mounts/hashes are keyed maps; ordinal is an integer. Reject unknown/missing keys, unsafe paths and secrets; credentials use ENV.

## Risks / Trade-offs

Historical target evidence → fresh exact preflight. Diagnostic secrecy → fixed codes and sanitized evidence. Restoration after import → deployment-only allowlist, journals retained.

## Migration Plan

Offline delivery/tests precede amended executable-plan approval. No current deployment. Planning rollback: revert this commit.
