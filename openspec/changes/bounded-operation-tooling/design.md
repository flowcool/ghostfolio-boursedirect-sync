# Design

## Reuse and dependencies

IBKR `docs/adr/0007-pinned-degiro-core.md` governs ownership. DEGIRO `CORE_PROVENANCE.md`/`scripts/check_core.py` provide immutable projection/reviewed pins/offline checks. No package/automatic propagation.

| Owner | Existing mechanism | Required addition/adoption |
| --- | --- | --- |
| IBKR | `ibkr_to_ghostfolio.py:ghost_exchange_access_token` and Decimal decoding | Canonical exchange through adapter transport; original-JSON Decimal/count/unique-ID validation; exact created-row comparison |
| IBKR adapter | Requests/import/cash orchestration | Adopt canonical units; retain independent cash policy |
| DEGIRO adapter | Immutable projection/uncertain-import fence | Explicit pin/regeneration/adoption; retain cash fence |
| BD adapter | `recover_notice_write` callback, exact readback, Compose | Explicit projection/adoption; dedicated AT1 transport, pre-intent `infra-a3ri` guard, receipts/native-cash preservation |

Additions are unavailable. Canonical delivery precedes each independent adoption. Never project `ghost_import_activities` into BD: reduced-batch retry conflicts with one-intent/uncertain-write fencing.

Minimal assembly fails: `scripts/community_connect.py:ghostfolio_snapshot` always adds an account GET; Compose cannot enforce pre-intent/preservation checks.

## Bindings

Private YAML schema_version=1 retains target `{ssh_host,hostname,daemon_id,runtime,project,service,network,volume,origin,account_id,source_ref,account_key,consumers,mounts}`, pins `{source_commit,build_files,files,original_image_id}`, protected `{paths,sha256,run_id,ordinal,remote_id}`, deployment `{allowlist}`, evidence_root and phases `{prerequisites,allowed_delta,grant_id,approval_reference}`. Reject unknown keys/symlinks/secrets. Grant fields apply only to mutating phases; phase keys match spec.

Types: schema_version/ordinal integers; read_only boolean; paths/allowlist/aliases/prerequisites string lists; consumers ID→state; mounts destination→`{type,source,read_only,aliases}`; build_files/files/sha256/allowed_delta/prerequisite_hashes path→hash maps; remaining leaves strings.

Existing-installation reads/preflight/pre-install bind original_image_id. Build receipt binds built_image_id to source_commit/build_files hashes before creation; post-install phases bind built_image_id. No rollback phase/digest.

`evidence_root/authority.yaml` keys grant_id to `{phase,approval_reference,config_sha256,source_commit,image_id,prerequisite_hashes,state}`. Lock/durably record started before mutation; succeeded/failed/uncertain remain consumed after crashes. Reads/analysis require no consumable grant.

## Source limits

Ghostfolio3.80.2 (`806d83f`)/3.85.0 (`ae9588b`), `portfolio.service.ts:getAccounts/getAccountsWithAggregations`, prove diagnostic paths below. Account dividend uses unordered Number addition; root uses Big. Image/source correspondence remains unproved; bind before exemptions.
