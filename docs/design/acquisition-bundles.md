# Offline acquisition bundle qualification

`qualify-captures` checks one completed saved acquisition bundle and writes a
private preparation proposal. It sends no requests, changes no source files or
ledger journals, and grants no authentication, source freshness, historical
completeness, or import readiness. Browser integration remains a separate gate.

The input bundle contains exactly `manifest.yaml` and `sources/`. The latter
contains exactly the manifest's neutral `capture-<UUIDv4>.html` files. A strict
keyed YAML manifest has `schema_version: 1`, `artifact_kind: acquisition_bundle`,
`status: complete`, a UUIDv4 `run_id`, explicit `account_key` and
`source_account_ref`, and keyed `files`. Every file entry has exactly `role`
(`statement` or `note`), `period` (month or day), lowercase SHA256 `sha256`,
`provenance: browser_dom_utf8_filtered`, and `ticket`.

Ticket fields are `account_ref`, `role`, `period`, UUIDv4 opaque
`origin_frame_epoch`, `link_handle`, `target_id`, `loader_id`,
`commit_loader_id`, `load_loader_id`, an exact broker-origin `request_url`, and
integer `sequence` (1–1000, unique within the bundle). The three loader handles
must agree. These are offline consistency checks of trusted supplied evidence;
they do not prove a request occurred, a target was guarded, or a capture was fresh.
Browser-specific ticket construction and observation are not implemented here.

The filtering helper strips scripts, styles, forms, input controls, frames,
assets, comments, links and all attributes except table span attributes. It
unwraps navigation links and retains ledger text and blank table slots. It emits
UTF-8 metadata and checks the same complete financial parser result before and
after filtering. Qualification requires already filtered bytes, not an arbitrary
provenance label. This does not detect arbitrary secrets encoded in visible text;
actual source-document compatibility is still an operational acceptance gate.

Each document must match its explicit source account and month/day. Every note
group must belong to the selected day. Duplicate role/date entries are refused;
there is no newest-revision selection. Missing notes, orphan note months,
unreferenced files, aliases/duplicate YAML keys, digest conflicts, symlink paths,
unsupported financial operations, and missing explicit mappings refuse output.
The existing preparation computation validates all financial matches before any
publication. Files are at most 4 MiB, manifest/config at most 1 MiB, a bundle at
most 256 captures and 64 MiB, and the explicit nesting limit at most 256.

Use an existing strict preparation configuration for account and security
mappings. Its previous document paths are replaced by the exact qualified source
absolute local paths in the private proposal; no existing configuration is overwritten or automatically adopted.

```sh
mkdir -m 700 outputs
.venv/bin/python boursedirect_to_ghostfolio.py qualify-captures \
  --manifest inputs/run/manifest.yaml --config inputs/import-config.yaml \
  --input-root inputs --output outputs/capture-proposal \
  --max-bytes 1048576 --max-depth 64
```

Exit 2 means a saved proposal with unresolved readiness gates; exit 1 means refusal.
Stdout contains counts and false readiness flags only. The new output directory
must have an existing private parent and be outside the input tree. Every input
path/inode is checked against the destination before mutation. Publication uses
an exclusive directory (0700) and atomic files (0600); `qualification.yaml` is
published last. On publication failure, retain the incomplete directory and use
a new output name after investigating. There is no automatic cleanup or overwrite.

The report projects each capture to its neutral filename, role, period, SHA256
and ticket sequence. Raw account references, request URLs and full tickets remain
only in the authoritative private input manifest, whose digest the report pins.
This minimizes duplication; both reports and input manifests remain private.

Inspect both output files before using `prepare-proposal.yaml` with the existing
`prepare` command. Give `prepare` an explicit common input root that contains both
this saved proposal and its referenced source files (the project root in the
example). The proposal preserves the explicit mappings and references original
captured bytes. It does not run `prepare` or change the identity journal itself.

Rollback: revert the scoped code/document commit. Preserve source bundles,
configurations, proposals, and auth uncertainty records. Tests use invented
financial data and forbidden sockets, never a browser, broker or Ghostfolio.
