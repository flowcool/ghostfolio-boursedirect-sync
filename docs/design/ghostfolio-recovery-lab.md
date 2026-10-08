# Isolated delayed-write recovery evidence

Observed2026-10-08 on the same pinned Ghostfolio3.80.2 image/source and isolated
resource policy as [the basic API bench](ghostfolio-api-lab.md). The successful
owned lab was `bd-gf-lab-572f2f23ba`: synthetic user, two EUR accounts, initially
zero activities, fresh tmpfs PostgreSQL/Redis, loopback-only random port and no
production data/network/volumes. Private controllers consume only that lab's
process-environment tokens. No controller is a production transport.

## Executed scenarios

1. A strict EUR YAHOO BUY review body was durably persisted as uncertain. A
   PostgreSQL SHARE lock on `Order` permitted reads while blocking insertion.
   The exact reviewed bytes were POSTed once. `pg_stat_activity` showed the
   application's INSERT waiting for a lock: the pinned import service checks
   duplicates before its createActivity loop, so this barrier is downstream of
   duplicate inspection. A full GET returned count0. Local resolution rejected
   absence, and a fresh Python process reloaded the journal and refused replay.
2. The HTTP client deliberately closed without reading any response, then the
   insertion barrier was released. Full readback showed exactly one owned
   activity with matching account/date/profile/numbers. That complete positive
   evidence resolved the intent; no second POST was sent.
3. A two-BUY review was durably persisted. A lab-only PostgreSQL BEFORE INSERT
   trigger selected the second exact ownership marker and waited on a held
   advisory lock. The first activity committed; the second INSERT was observed
   waiting. Full GET showed the prior activity plus one of the two new markers.
   Partial evidence could not resolve uncertainty; a fresh process refused replay.
4. The client again discarded the response. Only the owned disposable application
   was stopped. Its running state was false; the advisory lock was released and
   PostgreSQL showed zero remaining application sessions (excluding the verifying
   psql connection). This established bounded cancellation of that instance's
   outstanding in-process work. After application restart, full readback still
   showed exactly the same two activities. An explicit reviewed cancellation
   record bound to the request digest resolved the partial batch to quiescent,
   retaining one accepted marker and one absent marker. No replay was dispatched.
5. Only exact owned marker/account IDs were deleted, followed by count0 readback.
   Both lab containers/anonymous volumes and network were removed by ownership-
   checked cleanup. Label-filtered container/network lists were empty afterward.
   Private journals remain retained, including the first interrupted lab.

The fresh-process check exercises retained disk state independently of Python
memory. Separate unit tests exercise a crash after journal rename before the
caller returns. This bench loses responses deliberately; it does not infer
server completion from a client socket close, timeout or empty snapshot.

## Failed first rehearsal and controller correction

Lab `bd-gf-lab-d0a4ec3b9f` proved the initial delayed/lost/partial scenarios but
did not complete post-cancellation readback: Docker reassigned its random host
port on restart, while the controller retained the old one. Read-only health
inspection confirmed the application running on its new loopback binding.
The controller now rediscovers and revalidates the port after start. The first
lab's finally cleanup removed its resources and preserved its uncertain journal;
no criteria were closed from that incomplete attempt. The successful fresh lab
completed all scenarios and ownership rollback.

## Scope and production limit

These observations establish a feasible **isolated** cancellation procedure:
stop the sole owned application, verify no application DB sessions remain, then
perform complete exact readback after restart. They do not authorize stopping a
shared/production Ghostfolio service. A production deployment may have replicas,
external workers, connection proxies or request queues: the demonstrated bound
must be independently validated there. Without approved, proven quiescence, an
absent/partial outcome remains fenced indefinitely. Complete exact positive
readback can resolve a fully accepted request without stopping any service.

All existing source, mapping, adoption, chronological holdings, destination-
version/display/security and production authorization gates remain. This is
recovery evidence, not production import readiness or rollback of profile/market
side effects. No apply/transport command exists. Local helper results remain false.

Rollback performed here: exact owned activities deleted with empty full readback,
then ownership-checked disposable resources destroyed. Private journals retained;
image cache retained. No other container or service was stopped or modified.

Authority: [Astra R1](../reviews/2026-10-08-manual-document-import-astra.md),
[reviewed plan](../plans/2026-10-08-manual-document-import.md), and pinned official
import service at806d83f45394bdc70e58d9b178e2ddbdf715de08
(`extendActivitiesWithErrors` before `createActivity`). Exact private controller
digests are recorded in the owning Beads issue for reproducibility.
