# Qualified operator application

The `apply` command defaults to offline preview/export. Remote application exists
only when both `DRY_RUN=0` and `--execute` are explicit, and a separately reviewed,
externally pinned declaration matches the exact source/report/account/baseline.
No production run has been performed or authorized for this project session.

## Authority and source qualification

The declaration schema is illustrated by `examples/execution-declaration.yaml`.
Its placeholders and false confirmations deliberately prevent execution. It is
an unsigned record of operator responsibility, not authenticated approval. Its
external SHA256 binds bytes; it proves neither reviewer identity nor the truth or
freshness of security, recovery, version, rendered dates or exclusive access.
Those facts require real independent evidence before an operator runs it.

The controller fully recomputes the frozen review and current preparation from
bounded local HTML/configuration bytes. It refuses unresolved adoption, holdings
shortfalls, unsupported operations, changed raw documents and financially different
mappings. The current preparation config must match the declaration's own byte
pin. Older preparation artifacts omit historical config hashes and mapping
evidence references: replay cannot prove those references never changed. The
current declaration must qualify them; nonempty strings alone prove nothing.
Supported destination scope is characterized 3.81.0 with Europe/Paris or
Europe/Zurich display review. No server-version detection or universal timezone
policy is claimed. Per-symbol execution/target currency must be explicit EUR.

## Public workflow

Run from the repository root so `inputs/`, `outputs/` and `state/` remain ignored.
Keep source documents/configuration/output/journals private and out of Git/Beads.
Supply credentials through environment only; never put them in YAML or arguments.

1. Save original monthly statement and all daily note HTML. `inspect` verifies
   controls/matching; `prepare` creates internal activities and revision guards.
   See `offline-preparation.md`. Unsupported rows block their entire period.
2. Capture a complete saved destination activity list with GET-only `snapshot`,
   using verified HTTPS `allowed_origin`, exact matching `GHOST_HOST` and existing
   session JWT `GHOST_SESSION_BEARER`. No Security Token exchange/renewal exists.
3. Review complete acquisition history, actual legacy dates/fees and explicit
   manual-activity adoption. Do not infer completeness from current positions or
   from the statement's rolling availability. `diagnose` helps examine candidates;
   it cannot establish acceptance. Actual account acceptance remains unresolved.
4. `review` computes the saved reconciliation. `check-review` verifies its external
   report pin against original captures. `apply` previews counts by default or
   writes an exact private manual proposal with `--export outputs/proposal.json`.
   Report/proposal generation is not permission to send it.
5. Only after actual source/history/adoption and external destination/security/
   recovery/exclusivity reviews, prepare a private execution declaration. Obtain
   exact explicit operator write permission for that report and account. Record
   declaration/report/current-config pins externally. Do not simply change every
   example confirmation to true; each record must correspond to real evidence.
6. A later authorized invocation uses the following command shape. The example
   pins are placeholders and this document grants no permission to run it:

```sh
DRY_RUN=0 .venv/bin/python boursedirect_to_ghostfolio.py apply \
  --config inputs/review-config.yaml --review inputs/review-report.yaml \
  --review-sha256 EXTERNALLY_REVIEWED_REPORT_SHA256 \
  --execution inputs/execution.yaml \
  --execution-sha256 EXTERNALLY_REVIEWED_DECLARATION_SHA256 \
  --input-root inputs --max-bytes 1048576 --max-depth 32 --timeout 30 \
  --execute
```

Paths on command line follow the current directory; all configuration references,
including the declaration's relative `prepare_config`, follow input-root.
The byte/depth/timeout values above are example budgets, not broker guarantees.
`DRY_RUN` absent or1 overrides execute and ignores execution-only files/options/
credentials. `DRY_RUN=0` without execute still previews. Other values fail.
Effective execution rejects `--export`; preview still permits it under override.
A null wire needs no credentials, requests, archive or state changes; it is a saved
diagnostic, not a fresh remote observation or fence clearance.

## Dispatch, evidence and failure

Before credentials or local mutation, the public route verifies source/frozen/
declaration consistency, financial readiness and every writable path's aliases.
Before any request, a new ignored private `outputs/application-<UUID>/` archive
retains the manifest, exact declaration/external pin, report/external pin, review
config/four input roles (including original baseline), current preparation config/
pin and ordered raw statement/notes. Generated role filenames cannot inherit
source path traversal. Files are0600, directories0700; manifest/files and parent
entries are fsynced before dispatch. Initialization failure sends no request.
Partial failed archives remain. No bearer, authentication body or password is saved.
Manifest role hashes and aliases reconstruct the complete validation bundle for
cold replay without original paths; retained limits identify the run's budgets.
Archive hashes establish consistency, never authenticated permission.

Every chronological event has one canonical numeric body. The shared protocol core
holds target and namespace locks, rejects account fences/tombstones before GET,
checks full baseline equality, durably persists uncertainty before exactly one
POST, validates complete acceptance and full readback transition, then durably
confirms the event. A post-confirmation observer retains its exact body, previous/
new hashes and raw new readback in that archive. Observer failure stops immediately
with the confirmed tombstone retained. Later timeout/persistence failure retains
the confirmed prefix and uncertainty; there is no batch, retry or auto-resume.
Local per-event locks provide neither cross-host exclusivity nor a transaction.

Exit0 requires at least one positively confirmed event and completion of the
whole requested sequence. Exit2 is preview or qualified zero-new diagnostic.
Exit1 is refusal/failure; partial remote effects may exist. Stdout contains only
counts/fixed codes and false readiness, never IDs, money, endpoints or secrets.
Frozen readiness/blockers remain unchanged: external run qualification is distinct
from universal financial readiness. HTTP201 alone never produces success.

After any failure, preserve inputs, archives and journals; stop other writers and
inspect saved evidence. Do not rerun blindly or remove a fence. Capture a fresh
complete snapshot via the separate GET-only command if independently authorized;
`verify` observes retained intents without resolving them. `rollback-plan` reports
exact recorded associations but supplies no creation/deletion authority. There
is no application DELETE or automatic compensation. Use the independently reviewed
recovery procedure and reestablish permission before any intervention.
Reverting code does not undo remote effects. Retain all evidence through rollback.

## Verification boundary

`validate_qualified_application` is pure. `dispatch_qualified_application` repeats
its own full preflight for trusted owned/test callbacks; a callback does not prove
transport-origin identity. The public route alone creates the fixed bounded HTTPS
adapter from the environment after preflight. Ordinary pytest forbids sockets and
exercises exact mocked HTTPS, partial outcomes, aliases and archive cold replay.
The opt-in runner uses explicitly synthetic declarations and newly owned local
Docker HTTP callbacks. Its three imports/repeat/compensation do not prove live
HTTPS, actual source acceptance or production recovery/security.
Design authority: `../plans/2026-10-09-qualified-application.md` and exact Astra
approval in `../reviews/2026-10-09-qualified-application-astra.md`.
