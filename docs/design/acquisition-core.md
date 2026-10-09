# Durable acquisition authority core (offline)

The approved A scope is implemented in `collector/core.mjs`. This is a functional
helper boundary, not a broker connector or permission to use credentials. It never
launches Chromium, sends HTTP or supplies a production enrollment CLI. Browser
integration remains under the separate capability/design gate in the
[acquisition plan](../plans/2026-10-09-supervised-acquisition.md).

`principal` maps an ASCII login to a stable case-normalized SHA256 binding. Auth
state uses the installed OS user's fixed `~/.local/state/ghostfolio-boursedirect-sync/auth`
namespace, independent of run roots and source portfolio UUIDs. An explicit offline
`enroll` call creates immutable private enrollment; later enrollment cannot reset
it. Cooperating processes share an exclusive principal lock. There is no stale-lock
removal, reset, retry, root override or uncertain-state expiry. Different hosts,
changed HOME, intentional state deletion and hostile same-user filesystem access
remain outside this cooperation boundary. No actual enrollment was run during
implementation; all tests use newly owned temporary HOME directories.

A caller acquires the principal, starts a fresh attempt and durably transitions
into password uncertainty before arming a characterized one-use request permit.
`consumePermit` rechecks phase, page/frame epoch, exact URL/method/resource type,
nonce, deadline and redirect refusal, then durably consumes before returning.
Only a later separately approved driver may continue that request after return.
Unknown/null source-contract roles stay disabled. A source-contract evidence
reference is supplied operator data, not an authenticated proof that it is true.
No actual authentication endpoint is guessed or enabled by this component.

Password challenge and authenticated success transitions require consumed
requests; the caller still owes actual observed success evidence. Both request
and observation are trusted helper inputs here, not a browser-origin guarantee.
A crash or failed persistence retains an unfinished state and fences the next
attempt. Closed success alone permits a separate later deliberate attempt.
Locks are private mkdir entries; journal publication uses fresh exclusive temporary
files, fsync, rename and parent-directory fsync. Each newly created auth-directory
ancestor also fsyncs its parent before enrollment can succeed. Existing hard-link/symlink aliases,
wrong modes/owners and invalid schemas refuse. Partial enrollment is retained and
requires manual recovery, never automatic erasure to facilitate a retry.

Releasing a lock permanently revokes its in-memory handle before removing the
lock or synchronizing its parent. Removal, open, fsync or close failure leaves
that handle unusable for journal reads or mutations. Repeating release with the
closed handle cannot remove a subsequent owner's lock. If removal itself fails,
the retained lock remains a manual-recovery condition; the helper never retries
with stale authority or clears an uncertain journal to regain access.

`otpFromEnvironment` consumes explicit provisioned TOTP or a timestamped static
OTP, never both. It enforces integer clock, same 30-second step, age at most 20s,
not future and at least 5s remaining. TOTP is strict Base32/SHA1/30s/six digits.
The pure `totp` arithmetic helper is separately verified with RFC6238 reference
vectors; it alone is not the operational near-expiry gate. No seed was retrieved.
`diagnostic` is the sole public error shape: literal allowlisted fixed codes and readiness
false; low-level filesystem/parser errors must pass through it, not be printed.

Run `npm ci --prefix collector --ignore-scripts --no-audit --no-fund`, then
`npm test --prefix collector`. YAML 2.9.1 is pinned with integrity in the lockfile.
CI also pins setup-node's v4 commit and Node20. Tests block socket/TLS/HTTP/fetch/
WebSocket/DNS/datagram entrypoints before imports and forbid subprocess/browser
startup except one exact owned Node principal-contention fixture with isolated
HOME/minimal env and the same bootstrap. They cannot access the broker, Docker or
shared Beads. The existing socket-forbidden Python suite remains mandatory.

Rollback: revert the scoped implementation commit; keep real enrollment/attempt
records and locks intact. Any future manual reconciliation must establish exact
request outcome outside ordinary acquisition. No financial rollback or production
permission is supplied by this helper.
