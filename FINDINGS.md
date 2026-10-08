# FINDINGS — ghostfolio-boursedirect-sync (reconnaissance)

**Status:** Reconnaissance and source evidence with an offline inspection probe. Initial handoff by Claude
(Opus 4.8), followed by dated Codex checkpoints. Initial sections retain their historical context;
later checkpoints supersede pending evidence. See the [gated proposal](docs/plans/2026-10-08-manual-document-import.md).

**Initial reconnaissance verdict (historical; see later checkpoints):** This is the **hard case**. Bourse Direct has **no API** and no PSD2 coverage for
the securities account. Every existing building block gives **positions only** — a snapshot, not the
dated activity feed Ghostfolio needs (buys/sells/dividends). The only plausible dated-activity source
is a **manual CSV export** whose existence must be verified on the account. **Do not start building
until the data-source question (§1) is answered** — a positions-only sync produces a photo, not a
tracked portfolio (no history, no performance).

---

## 1. THE decisive question: is there a CSV export of dated operations?

- A third-party source ([Hub Finance](https://hub-finance.fr/comment-suivre-vos-performances-avec-bourse-directe-mon-compte/))
  claims the client area has an **"Historique des mouvements"** section downloadable as **CSV** (dates,
  amounts, operation types: buys, sells, dividends, transfers). **Not officially confirmed.**
- The official [compte-titres FAQ](https://www.boursedirect.fr/fr/support/faq/compte-titres) only
  mentions a monthly statement, with no stated format.
- **Action for Florent / next agent:** log into Bourse Direct and check whether "Historique des
  mouvements" (or equivalent) exports CSV/Excel with dated operations.
  - **If yes →** build a CSV adapter (parse CSV → internal activity list → Ghostfolio core). Same clean
    design as IBKR/DEGIRO-backfill. No scraping. This is the target.
  - **If no →** only positions scraping remains → snapshot only, no history. Treat as last resort and
    accept the limitation, or drop the project.

---

## 2. Existing building blocks — all positions-only (verified)

### picsou `bourse-direct-auth` (`Cloeille/picsou-finance`, read in full)

- Python + **Playwright**. Drives the interactive login + **OTP (6-digit) MFA**, then reads the
  portfolio via the modern Socket.IO stream (`/backend/portfolio`) or the legacy
  `streaming/compteTempsReelCK.php`.
- Output model (`AccountPayload`/`PositionPayload`): account balance, cash, and **positions only**
  (isin, symbol, quantity, buyingPrice, currentValue, pnl). **No transactions, no dividends, no dated
  activities.**
- Auth is interactive OTP; the session is a cookie blob (`CAPITOL`) stored by picsou's Java backend. No
  stored OTP secret here either → re-auth needs a fresh OTP when the cookie expires. **Not cron-able
  unattended** on its own.
- License: Apache-2.0 **+ additional restrictions** (non-commercial). Reference only.
- Value: a worked, currently-maintained (last commit 2026-10-03) reference for the Bourse Direct
  login/MFA flow and the portfolio stream shapes, including the brittle DOM navigation (collapsed
  account menu, "Portefeuille temps réel", iframe reloads). Expect xpath/selector churn when the site
  changes.

### Other references

- `wadael/BourDirConnect` — Java/Playwright scraper of "Portefeuille Temps Réel". Positions only, needs
  a valid 2FA code, author warns all xpaths break on site redesign. Non-commercial license.
- `carldeg/BourseDirect` — order placement, not reading. Out of scope.
- `Export-To-Ghostfolio` — **no Bourse Direct converter** (verified: not in `src/converters/`). Would
  only help if a CSV source existed and someone wrote a converter for it.

---

## 3. Hard constraints for any automation

- **Account lockout after 3 failed logins.** A daily cron that mis-handles its OTP three times locks the
  account. This alone makes naive scraping risky.
- **2FA type matters.** Bourse Direct offers SMS or an authenticator app. **SMS is not automatable.**
  Only an app-based TOTP could be automated — and only if the secret can be captured (same problem as
  DEGIRO). Confirm which 2FA the account uses.
- Private, JS-heavy, iframe-based site → scraping is fragile and high-maintenance by design.

---

## 4. What to reuse from `../ghostfolio-ibkr-sync`

The Ghostfolio-side core is reusable **if** a dated-activity source exists (CSV path):
- `ghost_*` import/cash/dedup functions, `load_mapping`/`resolve_symbol` (ISIN→Yahoo),
  `convert_*_to_activity`, `DRY_RUN`, cleanup scripts. See the DEGIRO repo's `FINDINGS.md` §3 for the
  exact function list — it is identical here.
- Runtime harness (`Dockerfile`/`entrypoint.sh`) reusable **only** for the CSV/API path. The
  Playwright path needs a different base image (browser deps) and is not a cron-friendly shape.

If the project ends up positions-only via scraping, almost none of the IBKR core applies (no activities
to import) — it would instead push a holdings snapshot, a fundamentally different integration.

---

## 5. Next agent — suggested first steps

1. **Answer §1 first** (CSV export existence) — it decides whether this is a project at all.
2. Confirm §3 (2FA type, lockout policy) with Florent.
3. Only then scope + plan (plan-quality rules apply).
4. Create the Beads epic after scoping (metadata `project=ghostfolio-boursedirect-sync`).
5. `git init` + first atomic commit once scope is agreed.

## References

- picsou-finance (reference only): https://github.com/Cloeille/picsou-finance
- Hub Finance (CSV claim, unverified): https://hub-finance.fr/comment-suivre-vos-performances-avec-bourse-directe-mon-compte/
- Bourse Direct compte-titres FAQ: https://www.boursedirect.fr/fr/support/faq/compte-titres
- IBKR sibling repo: `../ghostfolio-ibkr-sync`
- DEGIRO sibling repo: `../ghostfolio-degiro-sync` (shares the Ghostfolio core reuse map)


---

## 6. Phase 0 gate — 2026-10-08 (Codex)

**Verdict: UNDETERMINED — implementation gate remains closed.** This is not a
negative viability verdict: the decisive account-side evidence is unavailable in
this session. No implementation, authenticated request, login attempt, or OTP
retry was performed. The prior reconnaissance above remains the evidence base;
its investigation was not repeated.

### Evidence and remaining verification

| Check | Evidence available | Gate status |
|---|---|---|
| Dated-operation CSV/Excel export exists | Section 1 records a third-party claim, explicitly unconfirmed; no account observation or sample supplied | Await Florent's account-side check |
| Export is sufficient to reconstruct activities | No headers or representative rows available | Await format, columns, date range, and operation coverage |
| Account's configured 2FA | Florent confirmed app-based TOTP in this session (2026-10-08); no secret requested or received | Confirmed by account owner |
| Account lockout policy | Section 3 and `.claude/rules/security.md` impose a three-failure safety boundary; no account-specific confirmation supplied | Preserve boundary; await confirmation |

Florent was asked to check the export format, column names, accessible date
range, and coverage of buys, sells, dividends, fees, deposits and withdrawals,
as well as the configured 2FA and lockout policy. Credentials, OTP values,
cookies and TOTP seeds are not needed for this gate and must not be supplied.
An anonymized representative export, if available later, must retain parsing
structure and consistent identifiers without personal account information.

### Decision boundary

- If a dated-operation export exists, inspect its actual schema and coverage
  before agreeing the CSV adapter scope. Missing required values or limited
  history must become explicit limitations or unresolved gates, never invented
  activities. The target remains manual export ingestion, without site scraping.
- Manual export ingestion requires no Bourse Direct credentials, OTP automation,
  or TOTP seed in the program. Account-side authentication remains Florent's
  responsibility when obtaining the file; Ghostfolio credentials remain subject
  to the off-git SOPS and environment-only rules.
- If only positions are available, recommend shelving the dated-activity sync.
  Any snapshot-only alternative requires Florent's separate scope decision and
  must explicitly exclude historical activity/performance reconstruction.
- After positive export evidence, prepare a phased, gated plan grounded in the
  actual export and sibling core. Obtain Florent's approval before coding;
  create the scoped Beads epic only once viability and scope are established.
  Initialize Git and make the first commit only after scope agreement. Push
  requires Florent's explicit request.

No additional project guidance or implementation plan was initialized during
this gate: the existing scaffold already expresses the constraints. The narrow
KB lookup reached `operations/ghostfolio/index.md` and `api-traps.md`; these are
applicable to a future Ghostfolio integration, but do not resolve export
availability. No new portable operational knowledge was established here.


---

## 7. Phase 0 — browser reconnaissance report (2026-10-08)

**Current verdict: dated-operation CSV/Excel route UNCONFIRMED; no-go for
implementation pending additional evidence.** Dated activities do exist in the
client UI. Therefore the evidence does not support a positions-only verdict or
a conclusion that no usable source exists. Do not implement authenticated HTML
scraping. A document-based adapter would be a scope change requiring Florent's
agreement after inspecting the documents.

Source: browser-agent report supplied by Florent in this session. The following
are reported UI observations, not independently reproduced by Codex. No file
was downloaded or inspected during that reconnaissance. Section 6 preserves
the earlier checkpoint; this section supersedes its pending-evidence assessment.

### Observed sources

- `Mes comptes > Historique de compte` (`/fr/page/historique-de-compte`): HTML
  table `HISTORIQUE DE COMPTE`; account selector and `OK` only. No export or
  date-range control found on this page. Headers, in order: `Date opération`,
  `Date affectation`, `Libellé`, `Opération`, `Qté`, `Cours`, `Montant net`.
  The selected PEA showed 16 rows from 2026-07-08 through 2026-10-02. This is an
  observed window, not proof of a three-month retention limit. PEA-PME was not
  checked. Display uses dd/mm/yyyy, decimal comma, space grouping, trailing EUR
  sign; no file encoding or delimiter is known.
- `Avis d'opérés`: daily calendar with year/month navigation. No note opened.
- `Relevés`: UI states `Les relevés sont disponibles sur 21 mois glissant`.
  Monthly `Relevé de Compte` opens a popup; file type and contents unverified.
  Other categories include liquidation, portfolio valuation, securities-lending
  remuneration, and annual fees. An annual-fees route was observed; this does
  not establish a general transaction API and was not investigated.
- `Documents en ligne`: `Reporting détaillé` entries for 2017–2022, not opened;
  format and operation coverage unknown. The visible years do not establish
  continuous history or completeness.
- `Fiscalité du compte`: aggregate gains/income, not an operation ledger.
- Unchecked: liquidation account page, scheduled investments, PEA-PME. Login
  activity history is not a financial-operation source.

### Operation coverage and limitations

Observed labels: `ACHAT COMPTANT`, `ACHAT ETRANGER`, `VENTE COMPTANT` (negative
quantity), `COUPONS` (net amount only), `CONSERV ETG 2026T3` (no quantity/price),
`DIVISION` (negative/positive pair), `DETACH. DROITS SOUSCRIPT.`, and
`RETRAIT TITRES FISCALISE` (nominal price, zero amount; securities withdrawal,
not cash withdrawal). One row had distinct operation and settlement dates.

No explicit ISIN/ticker, currency column, gross amount, brokerage fee, tax, or
unique operation ID was visible. Cash deposits/withdrawals, incoming securities
transfers, duplicates, cancellations, corrections and totals were not observed;
their coverage remains unknown. A trade's net amount differed from quantity
multiplied by price, but the difference is not sufficient evidence of a
separately identifiable fee: currency conversion, tax and other charges must
not be conflated. In particular, `ACHAT ETRANGER` and EUR display do not prove
the execution currency. Do not reconstruct missing fees or withholding tax
without documented semantics and supporting values.

### Authentication evidence

`Authentification renforcée` (`/fr/double-authentification`) reportedly shows
`2 / 2 méthodes enregistrées`, with SMS and application TOTP both `ACTIVÉE`.
Florent separately confirmed using TOTP. No security settings were changed.
The security page (`/fr/infos/securite`) states that three incorrect password
entries block the account. This confirms the password lockout boundary, not an
OTP-attempt policy. Block duration, recovery procedure and OTP limits remain
unknown. No automated login is needed for the proposed manual-file route.

### Next bounded evidence pass

Ask the browser agent, in the existing authenticated session, to inspect one
monthly account statement, one detailed report, and one trade-day contract
note, using Florent's consent for private-document access/downloads. Return
format, exact headers, field semantics and coverage only, with no personal or
financial values. Check explicit history controls and PEA-PME; report observed
limits without guessing. Do not repeat authentication, explore hidden endpoints,
or probe undocumented APIs.

If a structured export is found, inspect a representative anonymized file
before planning. If only PDF/printable documents provide sufficient activities,
report feasibility and maintenance limits and ask Florent whether to scope a
manual document importer instead. If neither is sufficient, recommend shelving
the activity sync. No code, Beads epic, Git initialization or commit is
introduced by this evidence update.


---

## 8. Phase 0 — document follow-up (2026-10-08)

**Verdict: CSV/Excel route remains UNCONFIRMED. Manual contract-note/document
import is a plausible alternative, not yet proven viable for a complete activity
history and not authorized for implementation.** This checkpoint supersedes
section 7's pending document assessment. No original PDF file has been inspected
by Codex: evidence consists of Florent's supplied browser-agent report and
copied contract-note text. Personal/account identifiers and actual trade values
from that paste are deliberately excluded from this document.

### Sources resolved or excluded

- `Reporting détaillé 2021` is a public annual execution-venue regulatory report
  (`Reporting annuel 2021 - Top 5 des plates-formes d'exécution`), not an account
  ledger. The inspected HTML has selectable text, tables and a PDF-download
  control, but no account-operation fields. Remove this source from backfill
  candidates. Other listed years must not be interpreted as account history.
- The selected PEA-PME history reports `Aucun mouvement dans ce compte`, with
  the same controls and no export. This does not prove the account has never
  had activity; its statements and contract notes remain unchecked.
- No additional control to extend the visible PEA history or export CSV/Excel
  was found. Absence remains scoped to inspected views.
- The monthly PEA `Relevé de Compte` remains unresolved: its popup was not
  accessible to the browser agent. The page offers January 2025 through
  September 2026 and describes statements as all account operations; actual
  completeness and contents remain unverified.

### Contract-note evidence

Florent supplied copied text from the popup for the previously selected trade
day. The browser agent reports a selectable-text PDF titled `Avis d'Opération`.
The popup also exposes `Format PDF` and `Imprimer cette page`; the actual
PDF bytes/layout remain unavailable to Codex.

Observed structure: date; operation label `ACHAT ETRANGER`; ISIN; security name;
`QUANTITE`, `COURS`, `BRUT`, `COURTAGE`, `TVA`, `Heure Execution`, `Lieu`;
and a net debit under `Débit (€)` (paired with a `Crédit (€)` column).
Numbers use explicit plus signs and decimal commas. On the supplied buy, net
debit equals gross plus brokerage plus VAT. This verifies that example only,
not a universal formula. The footer states debit/credit amounts include VAT.

No unique operation reference, separate settlement date, explicit execution
currency or exchange rate is visible. The displayed debit is explicitly EUR;
the denomination of price/gross must still be established before mapping them.
Foreign execution venue alone does not imply foreign execution currency.
VAT must not be conflated with dividend withholding or other transaction taxes.
A selectable copy does not prove stable table extraction from PDF files.

### Feasibility boundaries

- A missing broker operation ID is not by itself a reason to abandon a file
  importer. A candidate deduplication method must be validated against repeated
  imports, overlapping monthly/daily sources, and genuinely identical trades.
  Date/time/ISIN/quantity/price alone must not silently collapse distinct fills.
- Absence of settlement date does not alone determine feasibility. The chosen
  activity date and actual sibling/Ghostfolio requirements must be verified
  before implementation rather than assumed from the browser report.
- Do not demand an FX rate when all relevant monetary values are explicitly and
  consistently denominated in EUR. Conversely, do not infer price currency from
  an EUR net debit. Validate document semantics and the mapping on actual files.
- One observed buy proves neither sells nor dividends, cash flows, corporate
  actions, tax coverage, multi-operation notes or historical depth. A trade-only
  importer would have a materially narrower scope than complete portfolio
  history and requires Florent's explicit agreement.

### Remaining decisive checks

1. Inspect a monthly statement: actual file format, selectable text, exact
   headers, ISIN/amount currency, operation coverage, and whether net/gross/fees
   are individually represented. Check deposits/withdrawals, dividends, fees,
   securities transfers and corporate actions without assuming completeness.
2. Inspect a sell note or a multi-trade day; establish calendar history depth.
3. If document ingestion is selected, inspect original anonymized PDF files to
   validate extraction and ambiguous values. Keep raw private documents off Git;
   preserve relevant parsing layout and arithmetic when preparing safe samples.
4. Present the supported scope, gaps, manual download burden and a phased plan
   to Florent before coding or creating the project epic. PDF/document import is
   a change from the initially specified CSV adapter, not an automatic fallback.

No implementation, authenticated automation, Git initialization, commit or
Beads epic was introduced. The source observations belong in this project's
viability findings; no new cross-project operational lesson was established.


---

## 9. Phase 0 — monthly account statement (2026-10-08)

**Verdict: the requested CSV/Excel adapter cannot currently be scoped on verified
source evidence. A manual saved-document importer is a candidate requiring a
separate scope agreement and an offline file feasibility gate. Complete dated
activity reconstruction remains unproven.** This supersedes the pending monthly
statement assessment in section 8. No structured export was confirmed; its global
absence is not established.

Source: Florent's observation of a text popup and supplied copied statement
content. Codex did not fetch the authenticated URL or inspect a saved HTML/PDF.
The observed path is `/priv/new/releveCompte.php`, with account selector, date
and statement-type query parameters. It is an authenticated document-view path,
not evidence of a supported API; no automation or endpoint probing is authorized.
Personal identifiers, actual trade values and balances are excluded here.

### Observed statement structure

- Title `RELEVE DE COMPTE`, statement date, and columns `Date`, `Désignation`,
  `Débit (€)`, `Crédit (€)`.
- Opening balance, dated operation descriptions with `Qté` and `Cours`,
  movement totals and closing balance.
- The supplied monthly example contains two sell entries (`VTE CPT`) and one
  buy entry (`ACH CPT`). This proves those labels in that example only.
- Footer states debit/credit amounts include all taxes. No explicit ISIN,
  transaction ID, individual brokerage/tax breakdown, execution time, FX rate,
  or separate settlement date is visible in the supplied text. Net monetary
  columns are EUR; price denomination remains to verify.
- Dividends, deposits/withdrawals, standalone fees, securities transfers and
  corporate actions are not represented in the supplied month's excerpt.
  Coverage of those operation types is still unknown.
- The text copy groups dates, descriptions and monetary cells separately,
  losing their row/column relationships. Do not pair values by guessed order or
  recompute missing fees from this paste. A saved HTML document preserving
  table structure, or an inspected original PDF, is needed for extraction tests.
- A garbled accented word is present; actual encoding must be checked on the
  saved file instead of inferred from the copy. Document labels may differ
  between statements, history and contract notes.

### Proposed scope decision, not an implementation plan

Offer Florent a manual local-file import feasibility phase: saved HTML monthly
statements for ledger coverage and reconciliation, supplemented by saved
contract notes for ISIN and explicit trade costs. No automated Bourse Direct
login or site scraping. HTML table parsing of user-saved files is distinct from
browser automation against the live account. Original document download format
must be established; PDF-only access remains a separate parsing consideration.

If Florent agrees to investigate this changed scope, obtain sanitized saved
files preserving layout and consistent arithmetic. Check trade matching across
sources, currency semantics, duplicate/identical trades, unknown operation
handling, historical depth and manual download burden before claiming viability
or approving an implementation plan. Preserve all unknowns as explicit gates.
Only then decide whether a full activity importer, a deliberately limited trade
importer, or shelving is appropriate. No Beads epic, Git initialization or
application code is introduced by this checkpoint.

The existing Ghostfolio KB index remains the narrow lookup source for later API
work. These account-source observations are canonical project findings, not new
portable operational knowledge.


---

## 10. Phase 0 — supplied statement HTML source (2026-10-08)

**Verdict: offline extraction of dated trades and net cash values is technically
plausible from the supplied monthly HTML structure. The original CSV route
remains unconfirmed. Complete activity-import viability and approval of the
changed document-input scope remain open.** No parser or application code has
been written. This updates section 9's source-structure uncertainty only.

Source: complete HTML source pasted by Florent, inspected directly in this
session. No authenticated URL was fetched. The raw source contains personal
information and financial values; it is not saved in the repository. The
observations below retain structure and semantics only.

### Extraction mechanism visible in source

- The document declares `windows-1252`. HTML entities are used extensively;
  a garbled literal word remains in the supplied source. The declaration does
  not prove the encoding of a subsequently saved file or chat-transcoded text.
- The main ledger has four labelled columns: date, description, debit EUR,
  credit EUR. Each column contains its own nested table rather than one common
  row per operation. The source comment explicitly describes this layout.
- Each nested column table contains 13 direct rows in the supplied example.
  Corresponding row positions identify opening balance, three trades, totals,
  closing balance, and blank separators. Trade description rows contain three
  cells: description, quantity and price; the other column rows contain one.
- A future parser must locate the ledger by its header structure, take direct
  rows of the four nested column tables, preserve empty slots, validate alignment
  and interpret matching row positions. Globally collecting nested `tr` elements
  or dropping blank cells independently would corrupt associations. Equal row
  counts alone are insufficient: date/label/amount patterns and cash arithmetic
  must also validate; unexpected layouts must stop with an explicit error.
- Balances, totals and blank separators are control rows, not activities.
  Numeric decoding must handle entities/nonbreaking spaces, decimal commas,
  grouping spaces and signed quantities without binary floating-point drift.
- The page exposes an explicit `Format PDF` link. PDF is an alternate rendering,
  not a CSV/Excel export and not a prerequisite for saved-HTML ingestion. No
  linked resource was fetched or script executed.

### Accounting interpretation verified on this example

The supplied values satisfy opening balance + sell credits - buy debit =
closing balance. The displayed credit `Cumul mouvements` equals opening credit
balance plus the trade credits; the debit cumulative value equals the buy debit.
Therefore do not treat the displayed credit cumulative value as period inflows
alone or generate a cash-deposit activity from the opening balance. This
interpretation is observed on one example, not a universal statement-format
rule. Other months and negative opening/closing balances remain untested.

### Remaining project decisions

Monthly HTML supplies dates, quantities, prices, net EUR movements and cash
controls. It still provides no ISIN or explicit per-trade cost breakdown in
this example. A local symbol mapping and/or contract-note enrichment would be
needed; matching and price currency must be validated. The next useful source
is contract-note HTML, plus an example containing non-trade movements if a
complete ledger is desired. Original saved files remain necessary to verify
encoding and extraction behavior beyond inspection of pasted source.

The candidate product is now a manual local HTML-document importer, without
Bourse Direct credentials or browser automation, rather than the proposed CSV
adapter. Florent has supplied additional evidence but has not yet explicitly
agreed this revised scope or an implementation plan. Do not interpret the paste
as coding approval. No project epic, Git initialization, commit or deployment
has been performed. All findings changes remain unversioned under the scope
agreement gate. No new portable KB lesson is established by this local source
inspection.


---

## 11. Planning authorization — 2026-10-08

Florent authorized a solid implementation proposal on disk and Beads creation,
with independent Astra review before further work. This authorizes planning and
review, not application code or live writes. The scoped candidate is manual
saved-HTML ingestion; complete activity coverage remains gated by source evidence.

[Plan](docs/plans/2026-10-08-manual-document-import.md) records pinned sibling/API
source evidence, source characterization, exact parsing and identity candidates,
financial semantics, adoption, API side effects, isolated verification and recovery.
Beads owns current approval and execution state; CLAUDE.md holds structural pointers.
Raw supplied private source and economic values were not persisted.


---

## 12. Authorized online source inspection — 2026-10-08

**Verdict: dated monthly HTML can be obtained interactively and the inspected
monthly ledger reconciles. Full activity import remains gated: matching contract
notes, currency/cost semantics, non-trade coverage and historical completeness
are still unverified. No CSV/Excel export has been confirmed.**

Florent authorized direct online exploration through his existing Puppet and
an independent Bitwarden reader. This supersedes the historical manual-only
acquisition boundary; see the [amendment](docs/design/online-source-inspection.md).
Private infrastructure reuse is exploration only. The public product must use
its own configurable interfaces, with provenance/license review before reuse.

### Directly observed evidence

- One deliberate password submission reached an application-TOTP challenge.
  One TOTP submission completed authentication and exposed account navigation.
  The temporary device was marked untrusted. Credentials/code remained in
  memory through the private bridge; no session or TOTP seed was exported.
- The authenticated statement view embeds a legacy iframe. Its month selector
  offers 21 periods, January 2025 through September 2026. This is an observed
  menu range, not proof of document continuity or lifetime coverage.
- The monthly statement opens an HTML popup with a PDF alternative. Its four
  parallel ledger columns retain blank slots. One browser DOM serialization
  was saved privately as UTF-8 with the charset declaration corrected. This
  is not an original Windows-1252 HTTP-response capture.
- Actual local inspection reported `ledger_reconciled=true`, `BUY=1`, `SELL=2`,
  `UNKNOWN=0`, and 12 aligned slots. The command returned code 2 because
  `CONTRACT_NOTE_ENRICHMENT_UNVERIFIED` and `REAL_SOURCE_ACCEPTANCE_PENDING`
  remain, correctly preventing import readiness. No amounts or identifiers
  are recorded in versioned evidence.
- The contract-note calendar exposes two relevant days for that same month.
  Opening a sell day reused the existing popup window. Its document was not
  captured: a subsequent request for a nonexistent new window triggered the
  controller's safe stop. No second authentication attempt followed.

### Remaining evidence and acquisition correction

The next acquisition must identify an owned popup by its observed document path,
not assume every click creates another page. Capture the matching sell and buy
notes, then inspect adjacent monthly/non-trade sources and historical limits.
Do not infer ISIN, costs, price currency or opening holdings from this ledger.
Private originals and their acquisition manifest live only in ignored `inputs/`;
synthetic fixtures remain the sole versioned examples and test inputs.

The browser/context was closed and task-started Puppet stopped. Infrastructure
cleanup verification is recorded in the source-acceptance Bead. Financial
transactions, broker settings and Ghostfolio production writes were untouched.
These observations do not satisfy full G1 acceptance; infrastructure
authentication success alone is not the source-coverage verdict.


## 13. Resumed source characterization — 2026-10-08

**Verdict: monthly HTML plus daily contract notes is a technically viable source
for a strict trade importer. Complete source acceptance is conditional: explicit
price-currency evidence, approved coverage and existing-history adoption remain
gates. A full-history/all-operation sync is not established.**

### Saved-document evidence

- Two daily contract-note HTML documents contain one BUY and two SELL operations.
  Both sales share a daily document and remain distinct groups. Each of the three
  monthly trades has exactly one note match on date, type, absolute quantity,
  unit price and debit/credit amount. No name-based security matching is needed.
- Each note supplies an ISIN-shaped identifier, quantity, course, gross,
  brokerage, VAT, execution time and venue. For all three observed trades, gross
  equals absolute quantity times course; buy debit equals gross plus brokerage
  and VAT; sell credit equals gross minus brokerage and VAT. This confirms only
  the observed components, not every possible tax or fee.
- Note HTML has the same four parallel date/designation/debit/credit columns as
  the statement. Designation slots contain nested three-cell field tables.
  Blank slots are significant: one-operation and two-operation samples have
  nine and eighteen slots respectively. There is no observed unique operation
  reference; execution-time timezone and settlement-date semantics are unresolved.
- The debit/credit headers explicitly use EUR. Neither inspected note labels
  course or gross with a separate currency or provides an FX rate. Numerical
  agreement and a EUR account are insufficient proof for arbitrary instruments.
  Currency must be established explicitly before creating an activity; unsupported
  currencies/taxes must block rather than be inferred from a venue or net gap.
- July, August and September monthly HTML reconciles independently. Both adjacent
  closing/opening cash balances agree exactly. July has four recognized BUYs and
  twelve unclassified rows; August has two unclassified rows. Coupon, split and
  securities-withdrawal categories are observed. They are evidence of coverage,
  not approved financial mappings. Some other labels remain unclassified.
- The earliest offered January 2025 statement was opened and saved; its ledger
  reconciles (seven BUYs, six SELLs, eight unclassified rows). This proves that
  endpoint month is obtainable, not continuity of all intervening months or
  lifetime retention. Contract-note calendar history depth is still unverified.
- Florent confirms acquisitions before the offered history are already in
  Ghostfolio. Existing activities therefore supply the proposed opening history;
  G4 must verify coverage and reconcile manual entries without duplicate import.
  No production Ghostfolio query or write was performed here.

### Evidence handling and acquisition recovery

All six financial documents are private browser-DOM serializations under ignored
`inputs/`, with hashes in its private manifest. Original HTTP bytes and statement
revision behavior remain unverified. Public fixtures
`tests/fixtures/note-buy-synthetic.html` and
`tests/fixtures/note-multi-sell-synthetic.html` reproduce the observed slot and
nested-field layout with invented identities, dates and financial values.
Their arithmetic is checked offline; they do not establish a production parser.

The resumed pilot first failed before OTP submission: the confirmed first input
ID began with a digit, but the old worker used a raw CSS `#ID` selector. The
selector-equality guard and an isolated synthetic Chromium reproduction establish
that this path could not type the first digit or reach confirmation. The private
journal retains that attempt with a pre-submit reconciliation; it was not erased
to retry. Focus by `getElementById` corrected the selection and a deliberate fresh
session completed one password and one TOTP successfully. Unknown/rejected
submissions remain non-resumable. All exploration code stays private and ignored.

Normal close completed with controller exit code 0. The redundant final close
reported a disposed-context error; the private worker now clears closed handles
so cleanup is idempotent. Independently observed state confirms Puppet is exited
with no published ports; owned vault container and network are absent; no private
capture/control file appears in container diff.
No raw document, password, OTP seed, token or cookie was committed. No financial
transaction, broker preference change or Ghostfolio production write occurred.

### Scope recommendation and unresolved gates

Proceed with the existing reviewed design only for a first explicitly accepted
BUY/SELL boundary: unique note matching, validated instrument currency and ISIN
mapping, exact explicit costs, existing-history reconciliation, and blocking of
unsupported account periods. Do not silently skip coupons, splits, withdrawals
or unknown rows. Florent was asked whether this reduced boundary is acceptable;
Beads owns that decision and the live source-gate status.

Full operation coverage, identical-trade multiplicity, document revisions,
additional taxes/currencies, note-calendar depth and production adoption are not
proven. No new activity importer or online recurring service is delivered by
this evidence collection. Private infrastructure reuse remains exploration only.


### Accepted source boundary

Florent explicitly accepts the strict BUY/SELL first version and confirms EUR
execution for his selected PEA sample. Net columns already label EUR and exact
note arithmetic corroborates this configuration; the price currency remains an
operator-supplied fact rather than an inferred universal property of a PEA or
foreign venue. The private per-ISIN source review records this confirmation.

The source gate therefore recommends GO for this limited evidence-backed path:
exact matched trades, explicit validated mappings, unsupported periods blocked,
and existing Ghostfolio acquisitions reconciled before import. Wider currencies,
unknown taxes, revisions, ambiguous/identical matches and unsupported operation
periods fail closed. This does not authorize skipping them or claim all-history
coverage. Financial conversion, durable identity and isolated API/display proof
remain later gates, and production application requires separate authorization.
