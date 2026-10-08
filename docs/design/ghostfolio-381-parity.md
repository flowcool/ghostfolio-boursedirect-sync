# Disposable Ghostfolio 3.81.0 parity evidence

Observed on 2026-10-09 (Europe/Zurich), under the approved G5 scope. This repeats
the [API bench](ghostfolio-api-lab.md) and
[recovery bench](ghostfolio-recovery-lab.md) on the version observed read-only at
the destination. It does not authorize production writes or make artifacts ready.

## Prerequisites and isolation

Official source: `920d0787541a8568920fc11f978aa01e5a52c581`.
Image: `ghostfolio/ghostfolio@sha256:7c925671dba267cc2175195f064b42b9733f3ea170a21db488b7d2be3319e088`.
Running package version was exactly `3.81.0`. The import service, import controller
and create-order DTO have no source diff against the previous pinned 3.80.2
revision; this observation alone does not prove their runtime dependencies.

The existing reviewed controller and scenarios were read in full. Only its image
digest and required runtime version changed. All previously documented isolation
controls remained: unique task labels/network, synthetic user and two EUR accounts,
tmpfs PostgreSQL/Redis, process-environment credentials, resource limits, no
production volumes or credentials, and a random loopback-only application port.
Initial activity count was zero. Server timezone was Europe/Paris.

An initial startup-only run received closed stdin, exercised no scenarios and
cleaned up. The complete run used an explicit local JSONL command file and checked
every expected result before recording success. No conclusion relies on startup
alone.

## API results

The synthetic BUY used the same reviewed EUR/YAHOO provider fixture as the earlier
bench, quantity 3, unit price 10.25, fee 0.15 and an explicit UTC-midnight date.
These are synthetic test values, not account-source evidence.

| Case | Observed result |
| --- | --- |
| First BUY in A | HTTP201, one returned activity, full GET count1; exact numeric fields and ownership marker preserved |
| Identical second request | HTTP201, zero returned activities, count remains1 |
| Identical trade/marker in B | HTTP201, zero returned activities; B count0 |
| B with distinct account namespace | HTTP201, one returned activity; full GET A1/B1 |
| Explicit `2026-09-17T00:00:00.000Z` | Full timestamp unchanged; both active and date contexts validated |
| Bare `2026-09-17` | Stored `2026-09-16T22:00:00.000Z`; normalizer date context remains unverified |
| Exact owned activity deletion | Full GET count0 after each isolated API sequence |

The report does not repeat every earlier numeric precision, SELL or desktop
display test. Those remain earlier-version evidence until specifically rehearsed.

## Delayed/lost/partial recovery

1. An exact reviewed BUY body was persisted as uncertain. A lab PostgreSQL SHARE
   lock blocked INSERT after native duplicate inspection. Full GET count0 did
   not clear the fence. A fresh Python process refused replay.
2. The client discarded the POST response, then released the insertion barrier.
   Complete readback found exactly one matching owned activity. Positive exact
   resolution cleared uncertainty; no second POST was sent.
3. A two-BUY batch committed its first activity and waited inside a lab-only
   trigger before the second INSERT. Full readback found one present/one absent
   batch marker. Partial readback and a fresh process both retained the fence.
4. Only the owned application was stopped. Its stopped state and zero remaining
   application database sessions established bounded cancellation. After restart,
   the loopback port was rediscovered and complete readback was unchanged.
   Request-bound explicit cancellation evidence resolved one accepted/one absent
   marker to quiescent; no replay was dispatched.
5. Exact owned activity deletion left count0. Ownership-checked container/anonymous
   volume cleanup and exact network removal completed. Label-filtered container
   and network lists were empty afterward. Private uncertainty journals remain.

## Provenance, limits and rollback

Owning evidence: `infra-4g8u.40`; ignored controller and command/event hashes are
recorded there. Safe event assertions checked exact response/count transitions,
all expected recovery milestones, and absence of failure/cleanup-required events.

The demonstrated cancellation procedure applies to the sole disposable app and
database. It proves neither production quiescence nor absence of external workers,
queues or replicas. Activity deletion compensates owned activities; it does not
restore asset profiles or market-data side effects. Actual history completeness,
legacy date/fee adoption, source mappings, independent security review, final
delivery acceptance and explicit production permission remain separate gates.

Rollback performed: owned activity deletion/count0, owned containers and anonymous
volumes removed, exact network removed; cached images and private journals retained.
Documentation rollback: revert this scoped report commit. No live Ghostfolio or
broker request was made during these tests.
