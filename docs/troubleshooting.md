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
Only Paperless has the narrow older-`created` unreadable exemption described below.

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
