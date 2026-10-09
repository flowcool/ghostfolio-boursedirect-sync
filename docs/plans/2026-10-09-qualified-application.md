# Qualified operator application execution

Date:2026-10-09. Design owner:`infra-4g8u.62`. Baseline:
`04f492526aae` (resolve full pin in review). This is separately reviewed packageC
from the approved operator application plan. Florent authorizes autonomous coding,
publication and newly owned isolated tests; **no production Ghostfolio writes**.
Code may enable a later operator-approved run, never execute one in this session.
Actual legacy/history/fee owner25 stays open and cannot be invented away.

## Gate0 — source truth and permission are separate

Read the complete preparation, frozen, exact numeric/wire, intent/core/sequence,
transport, CLI and runner chain. Existing frozen validation proves consistency
with preparation bytes, not that today's raw HTML/config/mappings still produce
those bytes. Production execution also requires independently qualified version,
security, display, recovery/exclusivity and explicit operator write permission.
The controller checks a strict externally pinned declaration linking these proofs;
it cannot authenticate reviewer identity, prove truth of free-text references or
enforce exclusive access across hosts. Never call it an authenticated approval or
an automated verification of external recovery/security. A bare --execute switch
or a matching hash alone is insufficient. Document those exact operational gates.
No authPOST/renewal or broker request is added. No unsupported source type/date/
fee is resolved by the declaration. Existing financial helper refusals remain.

## Gate1 — pure source preparation replay (atomic packageC1)

Extract the current pre-persistence preparation computation into
`compute_prepared_sources(config_raw, documents, max_bytes, max_depth)`.
Documents keyed by configured alias contain exactly statement bytes and ordered
note bytes; all bounded before HTML parsing. Reject wrong/extra/missing aliases,
nonbytes, exact-int positive limits, unknown config/doc/account schema or wrong
schema scalar type. Retain existing encoding, matching, currency/mapping,
chronological order, stable identity and source hashes unchanged. Return keyed
`artifact` and `snapshots` for the existing preparation publisher; source hashes
remain raw document hashes. No files/locks/time/network/state in computation.
Existing CLI captures config/documents once and passes them to that helper before
its unchanged revision guards/publication. Preservation guard sees all original
captured paths; do not weaken ledger/binding migration behavior.

Add `validate_prepared_sources(prepared_raw, config_raw, documents, max_bytes,
max_depth)` which computes expectedartifact then strict full typed-YAML compares
with preparedraw. Config is externally pinned at execution via its own SHA256;
rawsource changes fail against prepared source hashes; financially/identity-relevant
mapping changes fail full artifact replay. This qualifies the **current** externally
pinned preparation configuration for this run: the old prepared artifact has no
config SHA and omits currency/security evidence references. A change solely to
those nonfinancial evidence strings cannot be detected as a historical change by
artifact comparison. It may be accepted only under the newly reviewed declaration
pinning the current config bytes and its source_acceptance record. Do not claim
historical config/reference immutability or that nonempty references prove facts.
Any mismatch against the current declaration's config pin fails, including benign
formatting/path/reference changes after that review. Unsupported rows, altered
multiplicity/date/fees and prepared provenance/identity still fail replay.
No persistence or correction/adoption override occurs. Existing preparation
schema/blockers remain, no source authenticator is claimed. Sourcebytes supplied
by trusted caller remain sourcebytes, not broker-issued cryptographic evidence.

## Gate2 — strict pinned execution declaration (atomic packageC2)

CLI extends apply with `--execution FILE --execution-sha256 HEX --max-depth N
--timeout N`. Needed only when DRY_RUN0 and --execute are both explicit. Other
truth-table cases retainA behavior and do not inspect executionfile/credentials
or any new rawsource input. Execute+export is rejected before side effects only
in the effective DRY_RUN0 plus --execute branch;
no mixture of manualproposal and remote application. Missing declaration refuses
at the existing executiongate before network/state. All declaration/review/config/
prepared/snapshot/adoption/history/prepareconfig/rawHTML captured once with bounded
local reader inside inputroot. Pin every raw declaration/review and prepareconfig.

Declaration schema exactly:
- schema_version integer1, artifact_kind `operator_execution_declaration_not_authenticated_approval`;
- review_sha256, prepare_config and prepare_config_sha256;
- allowed_origin canonicalHTTPS, account_key, target_account_id,
  snapshot_sha256 exact captured snapshot pin;
- destination_version exactly `3.81.0` (the characterized version);
- display_timezone exactly `Europe/Paris` or `Europe/Zurich` (characterized display
  scope; not automatic UI detection or a universal date policy);
- confirmations keyed exactly `source_acceptance`, `destination_validation`,
  `security_review`, `recovery_procedure`, `exclusive_access`, `write_authorization`.
  Each is exactly `{confirmed:true,confirmed_by:nonemptystring,reference:nonemptystring}`.

Whole declaration SHA must match externally supplied lowercase64hex pin. Match
report/account/snapshot and replay actual preparation sources against captured
preparedartifact under its pinned config. Missing/false/wrongtyped/additional
confirmations or fields fail. A reference is the operator's review record, not
machine evidence of actual truth, contemporaneous exclusivity or human identity.
The explicit invocation requests the run under that independently reviewed record;
creating a synthetic record in this session never authorizes production. Required
premerge security review remains external, and must be real before production.
Version is operator evidence tied to the declaration; initial activityGET checks
baseline, not serverversion/UI/recovery truth. Do not claim otherwise.

## Gate3 — qualified execution controller and no retry

Refactor existing callable sequence into shared non-public computational sequencing
with two adapters: unchanged trusted lab wrapper and a qualified application
controller. Keep lab authority distinct; do not merely rename it production-ready.
The controller accepts already captured preflight bundle, declaration and a trusted
request callback. The public apply branch constructs only the fixed HTTPS adapter
**after** complete pinned/source/financial/binding/declaration preflight. The
controller must also preflight itself before any supplied callback/state, so test
or owned adapters cannot accidentally bypass gates. Readiness staysfalse and named
external conditions remain visible in results; no permanent frozenblocker deletion
or free-form bypass is added. Qualification authorizes only the exact supplied run
under external operator responsibility, not generic financial readiness.

Prebuild all single-row chronological bodies, rejectshortfalls/unresolved adoption,
use initial capturedbaseline and per-event exact confirmed readback. Existing
fences/tombstones, per-event locks, initialGET, durable uncertainbeforePOST,
complete acceptance and transition check stay unchanged. No batch/retry/autoresume/
DELETE/cash/API accountcreation/profiledata payload is introduced. No-op/null wire
returns counts without tokenfactory/network/state/observer; it does not clear a
journal fence or assert a fresh remote capture. With newactivities, state_root is
fixed private `state/` for publicCLI. Before any local state mutation, reject all
captured file aliases against target/account lock, writebinding and writejournal
paths; rejectsymlink state ancestors/root, preserve unsafe inputs. Source replay
never updates ledgerjournals, and existing preparation revisions remain guarded
by preparation plus fresh full source comparison; not rewritten at application.

For a nonempty run, after pure preflight and destination preservation checks,
create a newly owned private UUID archive. Before the first callback or write
intent, fsync an ownership manifest and the complete exact captured bundle:
declaration and external pin; review and external pin; review config and all four
roles (including initial raw baseline); prepare config and its pin; every ordered
statement/note byte capture keyed by configured aliases. Use generated role-based
filenames, never source paths as output destinations. Manifest binds those role
hashes and the run identity. No credentials are archived. Initialization failure
means zero callbacks and no write intent; partial archives remain for diagnosis.
Cold replay must work entirely from retained bytes after originals change.

After each durable confirmation, controller's observer writes exact wire,
previous/newreadback hashes and new raw readback under a newly UUIDnamed private
`outputs/application-<UUID>/`. Record archive ownership before use; validateoutput
root/ancestors/no aliases before mkdir/chmod. No inputs/output/journals are deleted.
Observerfailure immediately stops withconfirmedtombstone retained, no nextevent or
automaticcompensation. Archive is evidence, never approval. Confirmed partial state
survives later transport/persistence faults. Publicstdout only counts/fixedcodes,
`dry_run:false`, `accepted_events`, readinessfalse; no IDs/financialvalues/tokens/
origin/path. Success remote execution exit0, no-opdiagnostic exit2, refusal exit1.
HTTPstatus alone never produces exit0. Logsneverinclude remote/exceptiondetails.

## Gate4 — discriminating evidence and delivery

C1: all existing preparation/source/identity tests unchanged, source replay pure
filesystem/socket/lock forbidden; byte/type/config/docs/mapping/digest/tamper/
unsupported/multiplicity bounds and input preservation; fullpytest beforecommit.
C2: strict pinned declaration false/missing/extra/bool/int/source/config/binding/
version/timezone/confirmations/limits; all failures before credential/request/state;
DRY_RUN overrides even malformed executioninputs. PublicCLI mockedHTTPS happy3
singlePOST/exactfullreadback, timeoutaftercreation fencing and rerunrefusal,
observerfailure confirmedtombstone/no nextPOST, stalebaseline and zero-new no-op.
Archive initialization persistence failure gives zero callbacks; first-confirmed/
second-timeout retains complete qualification and first event evidence. Revalidate
source, frozen review and declaration from archived bytes after originals change.
Source change must fail before anycallback despite fresh correct declarationhash.
State/output pathsalias input hardlinks/symlinks failbeforemutation. No privacy
leak/freeform blocker override/sourcehistory assertion fabricated.

Adapt owned runner to invoke qualifiedcontroller with **explicit synthetic**
declaration using originalprepareconfig/docbytes and fixtureownership evidence,
keeping prior exact archives/repeat/compensation; callable trustedHTTPfixture
remains localowned transport, not production adapter. Required newlyowned pinned
3.81.0 run:3POST/3confirmed/count6/repeatzero/compensation6/count0/resourceabsence,
plus whole frozen/source archive coldreplay unchanged. No productionrequest or
synthetic declaration for real private actual inputs. Real HTTPSadapter is verified
through mockedconnections; do not call that ownedHTTPS runtime proof.

Run fullsuite/diff/numstat/privacy, atomiccommit/push/openPR and leave externalreview
untouched. Publicexample declaration contains only obvious placeholders/false
confirmations and no credential/actual account; no turnkey fabricated approval.
Document complete prepare→snapshot→review→applypreview→qualifiedfutureexecution→
verify/rollback-plan workflow, actual25gates and operational no-retry procedure.
The project is technically usable once controller arrives, but root G6/G7 real
acceptance stays open until independently proven, without stopping other coding.
Rollback eachscopedcodecommit; retaincaptures/archive/journals. Code rollback never
compensates remoteeffects; no application DELETE option added. Per-event locks
are not a transaction, distributedlock or recovery guarantee.
