# Independent Astra review: manual document import proposal

Date: 2026-10-08. Reviewer: Astra, independent review session.

**Verdict: REVISE.** One blocking recovery-contract gap must be closed before
approving the proposal. The overall gate-driven approach is appropriate. This
verdict evaluates a proposal for further feasibility work; it neither proves
complete import viability nor authorizes implementation or production access.

## Reviewed baseline and method

- Plan: `docs/plans/2026-10-08-manual-document-import.md`, 481 lines, SHA-256
  `933f4411e5bba9c5c8034b156a2ef1bf8494ee3ce98ea161a8e3a073bfe579f6`.
- Read global instructions, project `CLAUDE.md`, `FINDINGS.md`, security and Python
  rules, global plan-quality rules, and the knowledge-lifecycle skill.
- Used the narrow KB path `bundle/index.md` → `operations/ghostfolio/index.md` →
  `api-traps.md`. The concept is stable and within its freshness interval; its
  API guards are applicable, with version differences checked against source.
- Read the complete 1,407-line sibling main file at verified HEAD
  `2d2589908a03fa0ceec65487759bdb0f1a272475`.
- Reused the existing official Ghostfolio checkout and verified HEAD
  `806d83f45394bdc70e58d9b178e2ddbdf715de08` (3.80.2). Checked import controller,
  duplicate detection and creation flow, activity creation/deletion, DTO and
  database model. No broker reconnaissance or private-document access repeated.
- This was source and design review only. No application code, parser prototype,
  live request, integration test, Git initialization, commit or push occurred.

## Findings

### R1 — High, blocking: absent read-back cannot clear an uncertain POST

**Evidence:** Plan lines 322–341 persist intent and forbid automatic retry, but
describe fresh read-only reconciliation on the next run without specifying the
condition that permits an absent event to be submitted again. Ghostfolio
[`import.service.ts`](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/apps/api/src/app/import/import.service.ts)
calls duplicate inspection at line 751, reads existing activities at 1029–1034,
compares their fields at 1049–1062, and creates an activity separately at 920.
[`schema.prisma`](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/prisma/schema.prisma)
lines 183–208 give `Order` a generated ID; `comment` has no unique constraint.

**Impact:** After a client timeout or process crash, the first request may still
be executing. A complete GET can truthfully show no new row while that request
is between duplicate inspection and creation. A subsequent run can make the
same observation and submit again; both requests may then create the same event.
A local lock, a fresh baseline and ownership comments do not remove this race.
The existing prohibition on automatic retries is sound but is insufficiently
defined for manual resume or a new apply process.

**Required change:** Define a durable uncertainty fence across runs. A persisted
intent without proven completion is uncertain even if no successful response was
journaled. An exact unique created row may resolve the activity outcome; multiple
or conflicting rows remain blocked. Absence alone must never clear the fence or
authorize another POST. A replay needs independent evidence that the original
request completed or was cancelled, plus an explicit reviewed resolution and
fresh baseline. If that evidence cannot be obtained, leave the account blocked.
Do not substitute an arbitrary waiting interval for proof. The mechanism for
establishing quiescence belongs to G5/G7; no new server component is required.

Add a G5 scenario in which the first request stalls after duplicate inspection,
the client times out, GET reports absence, and the client restarts. Assert that
no second POST is sent while uncertainty remains. Also cover a crash between
durable intent and outcome journaling. This issue owns the proposal correction;
the future G5 owner owns executable recovery evidence.

**Owning follow-up:** `infra-4g8u.5`, discovered from `infra-4g8u.2`.

### R2 — Medium, nonblocking refinement: define the numeric wire boundary

**Evidence:** Plan lines 128–155 preserve exact Decimal strings and source
precision; lines 330–334 require accepted financial values to match.
[`create-order.dto.ts`](https://github.com/ghostfolio/ghostfolio/blob/806d83f45394bdc70e58d9b178e2ddbdf715de08/libs/common/src/lib/dtos/create-order.dto.ts)
requires numeric `quantity`, `unitPrice` and `fee`, while `Order` stores `Float`.
The sibling `accepted_import_subset` accepts Python `int`/`float` fields and
compares them directly. It does not define a Decimal-to-wire contract.

**Impact:** Sending the journal's decimal strings fails API validation. An
unqualified float conversion or comparison against the original Decimal values
can instead create precision loss or false uncertainty. This is already within
the broad G3/G5 boundary, so it is not a reason to reject feasibility work, but
the boundary should be made explicit before conversion implementation.

**Required change:** Distinguish exact source amounts, canonical review values,
the deterministic numeric JSON payload and accepted-value comparison. Specify
that G3/G5 must establish supported numeric precision, rejection or approved
rounding rules, and stable comparisons after wire/server conversion. Include
fractional quantity, high-precision price and excessive-precision cases. Do not
silently round source prices or introduce a broad epsilon. Keep the existing
G3/G5 acceptance owners; this follow-up owns only the proposal clarification.

**Owning follow-up:** `infra-4g8u.6`, discovered from `infra-4g8u.2`.

## Coverage of the requested review

| Area | Assessment |
|---|---|
| Identity and multiplicity | Period-scoped economic fingerprints plus occurrence count are a defensible candidate. Blank-row/file changes are excluded, corrections block, and notes cannot create independent events. G4 must still prove occurrence assignment when ledger-identical rows have distinguishable enrichment, including permutations; stable membership is insufficient if enrichment can move between IDs. Existing ambiguity and revision gates appropriately prevent claiming this solved. |
| HTML alignment | Direct rows in four parallel columns, preserved blank slots, header selection, control patterns and arithmetic are the correct response to the supplied layout. Equal row count is explicitly insufficient. Saved bytes, malformed-tree behavior and other statement layouts remain G1/G2 evidence, not proven compatibility. |
| Ledger-note matching | Strict account/date/side/quantity/money evidence and explicit resolutions are preferable to the sibling's proximity heuristics. G1/G2 must demonstrate conservation of row/note multiplicity across the whole match set, including identical or split trades. The current stop-on-ambiguity rule covers failure. |
| Currency, costs, tax and dates | No inferred EUR execution currency, missing-tax zero or invented fee is accepted. Unsupported variants are gated appropriately. R2 makes the API numeric boundary explicit. The phrase at plan line 251 about the sibling's day-based representation is imprecise: its trade datetime parser retains supplied clock time and labels it UTC; only date-only inputs/dividends become midnight. The proposed BD UTC-midnight rule must stand on G3/G5 evidence, not that sibling behavior. |
| Historical holdings and adoption | Dated existing history and explicit unmodified-record adoption are sound. No fabricated opening buy or cash overwrite is proposed. The merged timeline must be checked through existing later sales, with same-day ordering proved or blocked; later acquisitions must not fund an earlier sale. This is a characterization/acceptance obligation under the existing chronological gate. |
| Accepted outcomes and recovery | Per-event POST, exact accepted-row checks, fresh read-back and durable intent are appropriate. R1 is the remaining blocking gap. No 2xx-count or absence-only success claim is acceptable. |
| API side effects | Account permissions, global duplicate comparison, restricted views, canonical symbols, background gathering and asset-profile/market-data deletion are correctly identified. Compensation is explicitly distinguished from database restoration. G5/G7 correctly own the concrete lab/production recovery procedure. |
| Scope and maintenance | Manual HTML-only input with BUY/SELL as the conditional first target is coherent. Download burden and usefulness of partial history need Florent's G1 decision. Keep the keyed YAML state narrowly limited to provenance, explicit resolutions and recovery; do not build a portfolio database. The proposed journal is justified by recovery needs, not proven inexpensive. |
| Gates and task sizing | Review, user approval, source feasibility and live execution are separate. I1–I11 are planning packages, explicitly subject to splitting; they must not become eleven assumed one-hour implementation promises. No extra implementation tasks should be created before G1. |

## Disposition and handoff

Resolve R1 in the proposal and request a focused independent re-review of the
changed recovery contract. R2 can be resolved in the same plan revision but has
separate ownership. The minor datetime-source wording should be corrected when
editing that paragraph. Neither finding calls for application or server changes
at this stage. Review acceptance remains open until R1 is resolved and checked.
Florent's approval gate remains independent and must not be inferred from a
later reviewer approval.

The report is a new local planning artifact. Rollback is to move this report
into the existing ignored `tmp/planning-backup-2026-10-08/` directory; preserve
Beads audit history and supersede incorrect findings rather than delete them.
The plan itself was not edited. Repository initialization and commits remain
outside the current authorization.

Knowledge verdict: **Used and sufficient**. The indexed Ghostfolio concept
supplied the relevant existing local guards without broad reconstruction.
The additional review findings are consequences of the pinned public API and
this proposal; their canonical homes are this review and its owning issues, not
new portable environment knowledge.

## Final focused re-review — 2026-10-08

**Final verdict: APPROVE as a gate-driven feasibility proposal.** This supersedes
the first-pass REVISE verdict above. Both requested proposal corrections are
resolved; no blocking review finding remains. This approval does not establish
source viability, approve implementation, or replace Florent's scope decision.

Reviewed plan: 532 lines, SHA-256
`8c1ad141265a27da028fe9b54f24696374ed5f22b2f54927abbc5d1287ad5e13`.
The focused review compared the current file with the original baseline retained
at `tmp/planning-backup-2026-10-08/plan-before-R1.md`. The diff is limited to the
numeric boundary, sibling datetime clarification, durable uncertainty protocol
and corresponding recovery scenarios. No source or implementation review was
unnecessarily repeated.

| Finding | Re-review evidence | Disposition |
|---|---|---|
| R1 / `infra-4g8u.5` | Section 9 now treats every intent without proven outcome as uncertain across crashes and runs. Complete-list absence cannot clear the account fence or permit replay. Exact positive evidence is distinguishable from conflicting/duplicate evidence; replay requires independent completion/cancellation proof and explicit reviewed resolution, otherwise blocking persists. Section 11 assigns the stalled request, absent GET, restart and crash scenarios to G5. | Resolved at proposal level. Concrete recovery feasibility and execution proof remain mandatory at G5/G7. |
| R2 / `infra-4g8u.6` | Section 5 now distinguishes exact source Decimal values, deterministic reviewed numeric JSON bytes and canonical response-token comparison. Value-changing precision is rejected, server precision is explicitly characterized, no blanket tolerance is allowed, and G3/G5 retain test ownership. | Resolved at proposal level. The candidate policy still requires real isolated server round-trip evidence. |
| Datetime source wording | Section 7 correctly says that the sibling retains supplied trade clock time and labels it UTC; BD midnight representation is independently gated. | Corrected. |

The initial review covered every requested design area and retains its exact
source evidence above. The amended proposal closes the sole blocking finding
without widening authorization or promising automatic recovery. Its remaining
source, matching, ordering, numeric and API uncertainties are explicitly owned
by future gates rather than presented as successful tests.

Review issue `infra-4g8u.2` may therefore close on this report and checked plan
revision. Florent's approval issue `infra-4g8u.3`, feasibility issue
`infra-4g8u.4`, and the epic remain outside this review closure. No application
code, live request, service mutation, Git initialization, commit or push was
performed. The report remains a local uncommitted planning artifact under the
existing authorization boundary.

Knowledge verdict remains **Used and sufficient**; the focused changes do not
produce a separate environment-specific corpus contribution.
