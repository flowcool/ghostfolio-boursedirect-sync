# Offline statement inspection contract

## Authority and scope

Florent authorized implementation with “Carte blanche” on 2026-10-08 after
Astra approved plan revision SHA256
`8c1ad141265a27da028fe9b54f24696374ed5f22b2f54927abbc5d1287ad5e13`.
This permits the plan's separately approved G1 coding probe. It does not supply
the missing source evidence or authorize live financial writes. The reviewed
proposal remains immutable; this document describes the narrower executable
probe rather than silently treating G1 as satisfied. Beads `.3` owns approval,
`.4` owns real-source acceptance, `.7` owns probe behavior.

## Implemented behavior

`inspect` reads a bounded regular file within an explicit input root; final-path
symlinks and paths outside that root are rejected. Linux nonblocking/no-follow
open and descriptor inspection prevent reading a FIFO/device as a document.
Private paths and document contents are absent from operational diagnostics.

Only explicit Windows-1252/UTF-8 declarations are supported. Decoding is strict;
ambiguous/absent declarations, invalid bytes and replacement characters fail.
Beautiful Soup uses `html.parser` explicitly; no script, link, PDF renderer or
remote-resource loader is present. Explicit byte/depth budgets cap input scope;
the parsed-tree depth check does not claim to sandbox the parser itself.

Find one ledger by its four direct header cells. Require four direct nested
column tables, equal row counts and supported direct cell counts. Keep every
blank slot before alignment. Transparent fonts within cells and tbody wrappers
are supported. Multiple ledgers, orphan dates/amounts, nested slot tables and
unsupported layouts fail. Two financially identical rows remain two records;
the probe does not yet assign durable event ownership identities.

Control rows consist of opening balance, cumulative amounts and closing balance,
in that order. The opening date is the previous month's last day; closing is
month-end. Every operation lies between opening and cumulative controls.
Verify opening + credits − debits = closing, and cumulative debit/credit columns
include the corresponding opening column. This is the single observed control
variant; do not generalize it to unseen statement versions. Use exact Decimal
arithmetic with locally sufficient precision and reject non-cent cash values.
Control totals never become activities.

`VTE CPT` and `ACH CPT` trade labels require quantity, price and net direction
consistent with SELL/BUY. Other labels are retained as UNKNOWN and block import.
Dates outside the statement month are reported as a blocker. No security,
currency, gross, fee or withholding value is inferred from names or net amounts.

The returned internal statement contains private source evidence and must not
be logged or committed. CLI output exposes only a synthetic alias, slot count,
operation counts, reconciliation result and blocker codes. A parsed ledger exits
2 because source acceptance and note enrichment remain unresolved. Failures exit
1; no activity creation, export payload, preparation, apply or rollback command
exists. Account-header presence is checked; configured expected-account matching
belongs to a later source/configuration stage, so this is not import authorization.

## Verification and limitations

`tests/fixtures/statement-synthetic.html` is entirely synthetic, including account
reference, names, dates, quantities and financial values. It mirrors the observed
malformed surrounding markup and thirteen parallel row slots; its ASCII entities
and encoding declaration are not evidence of the broker's original saved bytes.
All tests run offline with sockets disabled and temp files under the environment's
TMPDIR. Dependencies are pinned to installed versions exercised by this bench.

The test suite discriminates structural ambiguity, altered cash controls, sign
errors, invalid dates, duplicate multiplicity, negative balances, encoding,
precision, file boundaries and safe diagnostics. These prove the probe contract,
not real-source completeness, rounding semantics, note matching, Ghostfolio
idempotency, recovery or performance accuracy. Real contract-note HTML and
representative adjacent/non-trade monthly statements remain necessary.

## Provenance and rollback

The inherited LICENSE is byte-identical to `../ghostfolio-ibkr-sync/LICENSE`,
including the porana attribution. Retain it verbatim. No sibling application
code is copied; parser and tests are original, based on the supplied layout.

Changes affect local project files, a private development virtualenv and project
Beads only. No services or external portfolio state are touched. Before the first
commit, scaffold backups remain under ignored `tmp/planning-backup-2026-10-08/`.
The pre-probe scaffold versions and a recovery script are in ignored
`tmp/implementation-backup-2026-10-08/`. To roll back this probe, run
`python3 tmp/implementation-backup-2026-10-08/restore_probe.py`; it moves new files
to `recovered-probe/` and restores the saved scaffold, without touching private
inputs. Review `git diff`, stage tracked changes with `git add -u`, and create a
new rollback commit. The script refuses to overwrite an existing recovery
directory. Backup access and script syntax were checked; rollback was not run.
Do not rewrite Git history or revert the root commit indiscriminately.
