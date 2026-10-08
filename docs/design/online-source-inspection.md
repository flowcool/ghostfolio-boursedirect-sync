# Interactive source acquisition amendment

## Authorization and retained gates

On 2026-10-08 Florent replaced manual-only source acquisition with direct online
inspection by the agent. He authorized use/start of Puppet, and opening ports or
creating a dedicated Docker network if necessary. Infrastructure inventory was
explicitly delegated to ChatGPT Terra. These instructions supersede the original
proposal's ban on broker navigation for G1 evidence collection. The reviewed
proposal remains unchanged as a historical design reference.

The importer remains an offline local-document consumer until a separately
evidenced acquisition design exists. This amendment does not authorize recurring
broker synchronization, orders, transfers, account-setting changes, Ghostfolio
production writes, or production/shared-state agent tests. Source, conversion,
identity, isolated API/recovery and delivery acceptance gates remain required.

## Acquisition procedure

1. Identify the browser capability from pinned source and actual owning runtime.
   `infra-oh7l` owns the initial Komodo inventory; `infra-p8a4` establishes direct
   embedded Chromium/Puppeteer control through SSH stdin with a private CDP pipe.
   Its first API-only verdict was corrected: the screenshot API is insufficient,
   but the browser executable is usable without new ports. Do not reuse the shared
   Changedetection browser/session.
2. Establish an agent-owned browser context through a private control path, with
   exact startup/shutdown and rollback evidence from infra. Prefer an existing
   SSH/container-exec path. Any necessary service/network change must be owned by
   an atomic infra issue under Florent's GO; do not publish an unauthenticated
   browser-control endpoint to the Internet. No broker connection occurs while
   merely characterizing infrastructure capability.
3. Establish account access. Reuse an explicitly available authenticated session
   only with clear ownership; otherwise use user-assisted authentication or
   credentials supplied exclusively through `os.environ` by an approved private
   credential bridge. Its service unlock material comes from the existing off-git
   SOPS store; the broker item remains in Bitwarden. Do not duplicate broker
   credentials into SOPS merely to accommodate the bridge. A storage pointer is
   enough for coordination. Never ask for
   passwords, OTPs, TOTP seeds or cookies in chat/Beads. This session has not found
   `BD_LOGIN` or `BD_PASSWORD` in its environment. Florent identified the requested
   Bitwarden item as `boursedirect.fr`; require an exact unique item name and verify
   its login URI against the broker origin before exposing fields to the controller.
4. Perform one deliberate authentication attempt after inspecting the actual
   login form. An incorrect password, failed OTP, challenge or uncertain submit
   outcome stops authentication work; no blind retry. Three wrong passwords lock
   the account. An OTP is never replayed after an uncertain response. Do not
   assume TOTP availability authorizes retrieving/exporting its secret.
5. Navigate only the known account-history, statement and contract-note views.
   Read account selectors and popup links; do not construct hidden endpoints,
   submit investment orders or change account/authentication preferences.
   Collect a monthly statement with its matching BUY/SELL notes and adjacent
   months/non-trade examples to establish the existing G1 coverage matrix.
6. Store originals only under ignored `inputs/` (directory 0700, files 0600),
   with neutral aliases. Source HTML/response and a serialized DOM are distinct
   evidence: record the acquisition method privately; a UTF-8 DOM serialization
   must declare UTF-8 rather than retain an incompatible legacy charset. No raw
   document, account reference, balance, URL query, screenshot, cookie or token
   belongs in routine logs, versioned examples or Beads. Derive synthetic fixtures
   and publish structural/semantic findings only.
7. Close agent-owned pages/context and stop a container started for this task
   when the handed-over infra procedure requires it. Do not delete an existing
   user's session/profile or stop unrelated writers. Source acceptance is owned
   by `infra-4g8u.4`; infrastructure capability alone does not satisfy G1.

## Verification and rollback

`infra-jnvj` records the existing Archivage Bitwarden CLI mechanism. Recreate its
reader access with independent appdata and private connectivity rather than
attaching Puppet to the production BillCollector vault API. Never borrow its
live `BW_SESSION`, list the whole vault, or print credentials/TOTP. An exact-name
lookup must stop on absence or ambiguity. Password and TOTP must stay in memory;
request the TOTP only when the known authentication challenge requires it. The
API's required Host header and secret injection are supplied by the owning infra
contract, not guessed from a successful TCP connection.

The public Bourse Direct homepage was reached with a fresh Puppet browser context
on 2026-10-08; it exposed `/fr/login`. This proves basic browser egress only, not
account access. That context was closed and the task-started container stopped.

This phase gathers real evidence, not a broker canary or a production importer
test. Validation of the parser and future import behavior uses synthetic files
and a disposable Ghostfolio instance. Characterize operation matching, ISIN,
currencies, explicit costs/taxes, calendar semantics and history completeness
before building activities; no values inferred from names or net-price gaps.

The scope change affects documentation and project Beads. Documentation rollback
is a new revert of the amendment commit, retaining the user's decision in Beads.
Runtime rollback must be supplied by the owning infra issue before startup or
network changes. Authentication cannot be rolled back by deleting local files;
prevent unsafe attempts instead. No financial operation is part of this phase.
