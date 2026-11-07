# Troubleshooting


| Code or symptom | Action |
| --- | --- |
| `invalid_configuration` | Read the named setting. Use exactly one source and one Ghostfolio credential; check final URLs and one active unique target. |
| `paperless_auth_failed HTTP 401` / `paperless_auth_failed HTTP 403` | Verify the token user, `view_document`, intended document visibility, `view_tag` and waiver-tag visibility. Do not grant superuser or write access. |
| `paperless_unreachable` | Check the final URL, network, TLS and response shape. Redirects are refused. |
| `source_field_missing` | Set `Source = Bourse Direct` on the intended originals yourself. |
| `notice_source_unavailable` | Restore directory readability or finish the source copy. Keep input stable during acquisition and dispatch. |
| `notice_unreadable` | Preserve the original. Privately check text extraction, account label, printed dates, known layout and all required fields. It blocks all financial writes. |
| `invalid_mapping` | Check that `MAPPING_FILE` exists, is readable by UID/GID 10001 and contains a `symbol_mapping` object. Leave it empty for automatic lookup. |
| `unresolved_security` | Verify one EUR Yahoo ticker and add the optional mapping; this is separate from unreadable-PDF recovery. |
| `review_unavailable` | Check private ownership/modes, source separation and companion files. Stop writers before editing. |
| `import_unconfirmed` | Stop writes. Preserve the journal and obtain complete exact destination readback. Never resend an uncertain request. |
| `share_count_change` / `unknown_operation` | Inspect the unsupported operation. Waive only the exact document/code after independent review; other guards remain. |

For a permanently unreadable folder notice, move it outside `NOTICE_DIR` yourself
and record the file, reason and move in your private records. Preserve the original.
This hides the notice from coverage. It does not prove complete history. The
importer never moves it. Old filenames and mtimes cannot exempt unreadable folder
files. Printed dates control `IMPORT_CREATE_FROM`, including the boundary day.
Only Paperless has the narrow older-`created` unreadable exemption described in
[coverage rules](maintenance.md#available-notice-coverage).

An optional folder waiver file uses this exact UTF-8 format:

```text
sha256:<64 lowercase hexadecimal digits> share_count_change
sha256:<64 lowercase hexadecimal digits> unknown_operation
```

Replace each placeholder with `sha256sum` of the reviewed original. Use one ASCII
space, one code per line, no comments and no duplicate pairs. Blank lines are
allowed. The file must be regular, readable, outside the notice directory and
separate from all review paths. Links and inode aliases are refused. The limit
is 65,536 bytes. Append `:compose.waivers.yaml` to `COMPOSE_FILE`, set
`NOTICE_WAIVER_FILE=/notice-waivers.txt` and `NOTICE_WAIVER_PATH` to your existing
host file. Mount it read only. Malformed files fail before service access.
Unknown digests are counted and ignored. Renaming preserves a waiver; changed
bytes need a new exact entry. A waiver cannot bypass any other guard.

For support, open a [GitHub issue](https://github.com/flowcool/ghostfolio-boursedirect-sync/issues).
Share version/digest, architecture, source mode, relevant service versions, fixed
codes, exit status and a sanitized reproduction. Keep originals, holder fields,
account identifiers, review files and full logs private. Report vulnerabilities
through the [private security process](../.github/SECURITY.md).

## Required-action log symptoms

These lines come from the run's action instructions. They can accompany
`Cycle result: success with user action required` and exit code 0.

| Exact log prefix | Action |
| --- | --- |
| `review_approval: Read the exact proposal.` | Read before/after values. Edit only `decision` to `yes` or `reject` between runs. The event stays held until current evidence permits it. |
| `review_evidence: Restore the missing or conflicting source or destination proof.` | Restore that proof. Approval cannot make blocked work eligible. Independent imports can continue. |
| `coverage_gap: Compare the missing notice rows with Ghostfolio.` | Compare the rows. Use normal guarded import only after resolving the evidence. |
| `position_mismatch: Compare notice and destination movements for the reported interval.` | Resolve the unexplained quantity difference. This comparison cannot prove opening holdings. |
| `coverage_unverifiable: Inspect the named missing or conflicting evidence.` | Restore that proof before checking the affected interval. |

## Paperless tag access returns 403

`paperless_auth_failed HTTP 403` can occur after documents download successfully.
When the run reads waiver tags, the dedicated user also needs global
`documents.view_tag` and visibility of the configured tag. Document view alone
is insufficient. Give no write permission. Compare the visible source set
against your own inventory. Hidden documents remain outside this token's view.

## Folder configuration and unreadable originals

`invalid_configuration NOTICE_DIR` means the directory is not absolute or
Paperless credentials are still set. `invalid_configuration NOTICE_WAIVER_FILE`
means the waiver setting or its file is invalid. Check its format, size,
readability and separation from source/review paths. Fix it before another run.

`notice_source_unavailable` means acquisition could not complete or the source
changed. Finish copying first. Check UID/GID 10001 traversal/read access, links
and selected special files. Keep the source stable during the run.
`notice_unreadable` means a selected PDF cannot supply complete supported data.
An old filename does not exempt it. Mapping cannot repair an unreadable PDF.

`Notification result: timeout, delivery unconfirmed` means the notification can
still arrive. Do not resend automatically. A notification failure does not
change the financial result. Keep its logs with the run's exit status.

## Restart loop or repeated failure notifications

`Invalid CRON` followed by repeated startup banners means the scheduled service
keeps restarting. `restart: unless-stopped` applies to every process exit.
Each invalid-schedule run can send its own failure notification. Stop it first:

```sh
docker compose stop importer
```

Fix the five-field numeric `CRON` in `.env`. Validate the configuration without
printing secrets, then recreate the service with `docker compose up -d importer`.
Do not use `up` with empty `CRON`. It repeats the one-off run, even after exit 0.
For one run, keep the scheduled service stopped and use
`docker compose run --rm -T --no-deps -e DRY_RUN=1 -e CRON= importer`.
The one-off `--rm` command does not use the service restart policy.

## Run result lines

Use the same filter for Bourse Direct and IBKR logs:

```sh
docker compose logs --no-log-prefix | grep -E 'Cycle result:|Account evidence|Reconciliation result:|Notification result:'
```

`Cycle result` gives the financial processing result. `Account evidence` reports
`simulated proposals` or `accepted imports`, `duplicates`, `other held events`
and `deferred automatic work`. An accepted import has exact readback. A simulated
proposal is not a write. BD reports one target account without its identifier.
BD does not update cash and reports `cash=not managed`. Missing evidence is
`unavailable`, not zero. `Reconciliation result` uses the IBKR count names.
Decision counts can overlap. These lines do not prove complete notice coverage.

BD keeps its existing `Summary: ` fields and the exact `Cycle result: success`
line for scheduler compatibility. IBKR adds hold and notification fields to its
cycle line. Read BD's separate evidence and notification lines for those results.

`Notification result` is `not required`, `disabled`, `invalid configuration`,
`sent`, `failed` or `timeout, delivery unconfirmed`. Warning results include a
configuration hint. Delivery does not change the cycle result or exit code.
A timeout can still deliver. The current run does not retry it.

Required actions use a separate title from failures. Resolved groups use
`user action resolved` and include each cleared reason with count zero.
Unchanged reason/count groups stay silent until 168 hours after confirmed
sending. Failed runs send one failure summary and do not advance the last
successful grouped snapshot or certify resolution. Private per-event evidence
and financial holds remain in force.

## Foreign shares bought in EUR

Bourse Direct trades foreign shares in EUR on a European venue, for example
Deutsche Börse. Check the notice's venue and currency. Map the ISIN to the EUR
listing. Do not select the home listing in SEK or USD for an EUR trade.
Otherwise Ghostfolio reads the EUR price in the wrong currency.

For example, map SAAB B (`SE0021921269`) to the Frankfurt EUR listing `SDV1.F`:

```yaml
symbol_mapping:
  SE0021921269: SDV1.F
```

Check that the listing has price history for the holding period. An ISIN lookup
can return several listings. Use an explicit verified mapping when the lookup
is ambiguous. A mapping change does not repair existing activities. Inspect
those activities through the guarded review procedure before any correction.
