# notice-import delta

Apply this delta with the main spec and the released manual-reconciliation
and creation-cut-off deltas. Only source selection and folder behavior change.
Existing financial rules remain applicable.

Run means `docker compose run --rm -T --no-deps -e CRON= importer` against
the configured source and an isolated destination. Read output and exit status.

## MODIFIED Requirements

### Requirement: Settings from ENV only

ENV SHALL supply `GHOST_HOST`, exactly one of `GHOST_ACCESS_TOKEN` or
`GHOST_TOKEN`, `GHOST_ACCOUNT_NAME`, and `BD_ACCOUNT_REF`.
Optional settings SHALL remain `PAPERLESS_DONE_TAG` (default `ghostfolio-done`),
`MAPPING_FILE`, `DRY_RUN`, `TZ`, `CRON`, `APPRISE_URLS`, `APPRISE_TIMEOUT`,
`LOG_LEVEL`, `ACTIVITY_REVIEW_FILE`, `ACTIVITY_RECONCILIATION`,
`NOTICE_COVERAGE`, and `IMPORT_CREATE_FROM`. Their existing rules SHALL remain.
`NOTICE_COVERAGE` SHALL accept only 0 (default) or 1; 1 selects report-only
execution regardless of `DRY_RUN`.

Nonempty `NOTICE_DIR` SHALL select folder mode and require an absolute container
directory path. Both `PAPERLESS_URL` and `PAPERLESS_TOKEN` SHALL then be absent
or empty. Absent or empty `NOTICE_DIR` SHALL select Paperless and require both
Paperless settings. Both sources, neither source, invalid settings, or a
nonunique/inactive/excluded target SHALL give `invalid_configuration`, exit 1.
Source configuration errors SHALL stop before service access. Omit secrets.

#### Scenario: Folder without Paperless
- **WHEN** Run has valid `NOTICE_DIR` and no Paperless settings
- **THEN** it reads folder notices without contacting Paperless.

#### Scenario: Conflicting or absent source
- **WHEN** Run has both source configurations or neither
- **THEN** `invalid_configuration`, no service access, exit 1.

#### Scenario: Missing Paperless token
- **WHEN** Run selects Paperless without its token
- **THEN** `invalid_configuration`, `PAPERLESS_TOKEN`, exit 1.

#### Scenario: Ambiguous Ghostfolio account
- **WHEN** Run finds colliding target names
- **THEN** `invalid_configuration`, exit 1.

### Requirement: Paperless source

In Paperless mode, read all selected original notices with `Source = Bourse
Direct`, including done-tagged notices. Paperless SHALL remain read-only.
Rejected tokens SHALL give `paperless_auth_failed`; unexpected answers,
`paperless_unreachable`. Errors SHALL show only HTTP status/code/document ID.
Omit holder/address; account references appear only in identity comments/logs.
`BourseDirect_` files without `Source = Bourse Direct` SHALL stop writes with
`source_field_missing`. Folder mode SHALL require no Paperless metadata.

#### Scenario: Wrong Paperless token
- **WHEN** Run uses a rejected Paperless token
- **THEN** `paperless_auth_failed`, exit 1.

#### Scenario: Paperless down
- **WHEN** Run cannot reach Paperless
- **THEN** `paperless_unreachable`, exit 1.

#### Scenario: Source field missing
- **WHEN** Run finds a Paperless `BourseDirect_` file without Source
- **THEN** `source_field_missing`, no writes.

### Requirement: Unreadable documents block writes

Unreadable notices/accounts or unknown field labels SHALL stop all financial
writes with `notice_unreadable`, exit 1. Simulation SHALL list readable activities.
With `IMPORT_CREATE_FROM`, an unreadable Paperless original SHALL be exempt
from this normal write block only when its document `created` is a valid
`YYYY-MM-DD` before the cut-off. Missing, invalid or current dates retain the
block. Filename and ingestion date SHALL NOT exempt a notice. Acquisition or
authorization failure SHALL remain a failure. Log the exempt document ID and
unreadable finding. Coverage SHALL still report incomplete evidence,
`notice_unreadable` and exit 1. Never infer security or financial content.

Folder originals SHALL have no metadata-based unreadable exemption. An unknown
printed trade/payment date SHALL be unreadable and held, including when other
readable rows are historical. Filename, mtime, ctime and copy date SHALL grant
no exemption. A partially readable old date SHALL NOT exempt an unreadable file.

#### Scenario: Unreadable document
- **WHEN** Run reads an unreadable PDF without an eligible Paperless exemption
- **THEN** `notice_unreadable`, no financial writes, exit 1.

#### Scenario: Historical unreadable Paperless notice
- **WHEN** Run reads an unreadable original with Paperless `created` before the cut-off
- **THEN** normal writes can continue; logs retain the finding; coverage fails as incomplete.

#### Scenario: Missing or current Paperless date
- **WHEN** Run reads an unreadable Paperless original with missing, invalid or boundary-day `created`
- **THEN** `notice_unreadable`, no financial writes, exit 1.

#### Scenario: Old-looking folder file
- **WHEN** Run has a cut-off and an unreadable folder PDF with an old filename or mtime
- **THEN** `notice_unreadable`, no financial writes, exit 1.

### Requirement: Stop on a share-count change

DIVISION SHALL give `share_count_change`; unknown operations, `unknown_operation`.
With ISIN, hold that security across notices; independent securities continue.
In Paperless mode, `PAPERLESS_DONE_TAG` SHALL waive these codes for that document
only; other rows remain eligible. The importer SHALL never apply that tag.
Folder mode SHALL have no done tag, sidecar waiver or completed-file move.
`PAPERLESS_DONE_TAG`, filenames and review `yes` SHALL NOT clear folder stops.
Existing historical cut-off rules SHALL remain applicable in both modes.

#### Scenario: Division and coupon in one notice
- **WHEN** Run reads an unwaived current DIVISION with a coupon for the same security
- **THEN** `share_count_change`, coupon held.

#### Scenario: Stop cleared
- **WHEN** Run reads a Paperless notice with the configured waiver tag
- **THEN** its stop is waived and the coupon remains subject to all other checks.

#### Scenario: Renamed folder stop
- **WHEN** Run reads the same folder DIVISION under a done-like name with review `yes`
- **THEN** the security stays held; no file is changed or moved.

## ADDED Requirements

### Requirement: Safe read-only folder acquisition

The folder SHALL be mounted read-only. The importer SHALL never modify originals,
create markers, move files or write review state inside the source directory.
It SHALL select immediate regular files with case-insensitive `.pdf` extension.
It SHALL NOT recurse. Other entries SHALL be ignored and counted as ignored.
Each selected PDF SHALL contain 1 through 20,971,520 bytes (20 MiB).
Selected PDF symlinks, non-regular PDF entries, links in the configured directory
path, empty or oversized PDFs SHALL give `notice_unreadable`, exit 1, and block
all financial writes. Links SHALL NOT be followed.

A missing, unreadable or unlistable directory, or incomplete/changed acquisition
before dispatch SHALL give `notice_source_unavailable`, exit 1, and block all
financial writes. A selected file that cannot be read SHALL give
`notice_unreadable` with the same block. Readable previews can remain available;
coverage SHALL state incomplete evidence. The new code SHALL use the existing
redacted failure-notification rules. Notifications SHALL omit paths and names.

#### Scenario: Uppercase PDF and other entries
- **WHEN** Run reads one valid `.PDF`, a text file and a nested directory
- **THEN** only the PDF supplies rows; the other entries are counted as ignored.

#### Scenario: Unsafe PDF entry
- **WHEN** Run selects a PDF symlink, special file, empty file or file above 20 MiB
- **THEN** `notice_unreadable`, no financial writes, exit 1.

#### Scenario: Incomplete folder acquisition
- **WHEN** Run cannot enumerate the directory or a selected file changes during acquisition
- **THEN** `notice_source_unavailable`, no financial writes, exit 1; coverage is incomplete.

### Requirement: Content identity without duplicate creation

A folder document SHALL use `sha256:<digest of original PDF bytes>` as its
document identity. Its path, name, directory order and timestamps SHALL NOT
define identity. Identical copies SHALL share one document identity. Report
source-file and distinct-document counts separately. Preserve existing
source-copy counting for historical exclusions.

Financial activity identity SHALL remain `BD#v3` under the existing row rules.
Neither the content hash nor source mode SHALL change it. Equal logical events
in byte-different regenerated PDFs SHALL retain existing duplicate checks.
Renaming, moving to another configured folder, copying, or switching sources
SHALL NOT create an already represented activity. Confirmed destination evidence,
not a file marker, SHALL prove completion. Every run SHALL read selected PDFs again.

#### Scenario: Copy and repeat
- **WHEN** Run follows a confirmed import with renamed and duplicate copies of its original
- **THEN** repeated events are duplicates, zero creations, and originals remain unchanged.

#### Scenario: Regenerated or switched source
- **WHEN** Run finds an already represented event through a regenerated PDF or the other source
- **THEN** its financial identity is unchanged and no replacement activity is created.

### Requirement: Folder dates and source-independent review

In folder mode, `IMPORT_CREATE_FROM` SHALL compare each row's printed trade or
payment date from the PDF. Never use file metadata. Earlier rows SHALL remain
available for review and coverage but SHALL NOT become creations or simulated
holdings. The boundary day SHALL remain eligible. Existing historical-stop
rules and correction authority SHALL remain unchanged.

`ACTIVITY_REVIEW_FILE` SHALL provide the same proposals, holds, approvals,
recovery and exact readback in both modes. Source and review paths SHALL remain
separate; unsafe overlap SHALL give `review_unavailable` before financial writes.
A rename of unchanged bytes SHALL NOT change source evidence. Changed content,
association or destination evidence SHALL invalidate consent under existing rules.
Switching sources SHALL NOT itself authorize corrections or settle pending work.

#### Scenario: Printed date wins
- **WHEN** Run reads old and boundary-day folder rows whose filenames and mtimes suggest opposite dates
- **THEN** only the boundary-day row can become a creation; historical review remains available.

#### Scenario: Rename versus changed evidence
- **WHEN** Run refreshes review after a rename, then after a content change
- **THEN** the rename retains unchanged evidence; changed evidence clears stale consent.

### Requirement: Folder coverage parity

`NOTICE_COVERAGE=1` SHALL read all selected folder originals. On the same supported
originals and destination, both sources SHALL produce the same logical findings
and exact values. Acquisition counts and source identifiers can differ.
Existing conforming, correction, unresolved, absent, unsupported, unreadable and
position findings SHALL remain available. No source mode SHALL claim complete
broker history. Paperless tag waivers SHALL NOT transfer to folder mode.
Unreadable or incomplete acquisition SHALL retain its failure and incomplete status.
Coverage SHALL send no financial POST/PUT/DELETE, open or settle no review journal,
and change no review decision, including with `DRY_RUN=0`, `yes` or pending work.

#### Scenario: Same originals through both sources
- **WHEN** Run reports coverage through each source on the same supported originals and destination
- **THEN** logical findings and values agree; review decisions and journals stay unchanged.

#### Scenario: Coverage with approvals and an unreadable file
- **WHEN** Run uses folder coverage with `DRY_RUN=0`, approvals, pending work and an unreadable PDF
- **THEN** no financial writes or journal settlement; `notice_unreadable`, incomplete coverage, exit 1.
