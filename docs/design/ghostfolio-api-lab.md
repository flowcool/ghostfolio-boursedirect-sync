# Pinned isolated Ghostfolio API observations

Verified on 2026-10-08 against Ghostfolio **3.80.2**, official source commit
`806d83f45394bdc70e58d9b178e2ddbdf715de08` and image digest
`sha256:87a5bf6f8a1a0fa077d21716ce48c3e5fc00b108c0cd5f9af3d0c60a80c3f87b`.
These observations characterize a candidate wire contract. They do **not** pass
the complete reviewed G5 recovery gate or authorize production imports.

## Isolation and cleanup

Two disposable agentvm-local laboratories used unique `bd-gf-lab-*` containers
and networks. PostgreSQL15 and Redis7 used separate tmpfs storage. Ghostfolio
published a random port on `127.0.0.1` only. Each lab had a new synthetic user and
two EUR accounts, no production volumes or network membership. CPU/memory caps
were PostgreSQL1CPU/384MiB, Redis0.5CPU/96MiB and Ghostfolio1.5CPU/1536MiB.
Generated credentials stayed in process environment and the owned container
configuration until destruction; none were printed or persisted to project files.

PostgreSQL image digest: `sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81`.
Redis image digest: `sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499`.
The runtime package version was checked inside the application container. Signup
and one anonymous-token exchange produced lab-only access. Initial activity count
was zero. The application server used `TZ=Europe/Paris`.

Rollback selected exact created activity IDs after checking their synthetic
ownership markers and lab account membership. Each deletion returned success and
the subsequent full list was empty. Cleanup verified ownership labels before
removing exact containers with their anonymous volumes, then removed each owned
network. Both `docker ps -a --filter label=bd.source-lab` and
`docker network ls --filter label=bd.source-lab` returned no resources afterward.
Pulled image caches remain. This compensation is not a database restoration and
does not prove that asset-profile/market-data side effects are reversed.

## Requests and observations

Baseline request: `POST /api/v1/import` with an `activities` array containing
`accountId`, `comment`, `currency: EUR`, `dataSource`, `date`, numeric `fee`,
numeric `quantity`, `symbol`, `type: BUY` and numeric `unitPrice`. The synthetic
baseline was quantity3, price10.25 and fee0.15 on `2026-09-17T00:00:00.000Z`.
An initial MANUAL profile was created with the synthetic UUID symbol. Subsequent
Yahoo requests used `dataSource: YAHOO`, `symbol: AIR.PA`, without an asset-profile
payload. This is a provider-contract test, not a mapping for any real source title.

| Case | Exact observed result |
| --- | --- |
| MANUAL BUY with a107-character `BD#v1#<UUID>#<digest>` marker | HTTP201; response object `activities` has one row; GET count1, accountA, marker/date/numbers preserved |
| Identical second import | HTTP201; `activities: []`; GET count remains1 |
| Same fields and marker, changing only account toB | HTTP201; `activities: []`; B has zero rows |
| Same trade inB with a distinct account-UUID marker | HTTP201; one returned row; GET counts A1/B1 |
| Quantity as JSON string `"3"` | HTTP400; no new activity |
| Date-only `2026-09-17` | HTTP201; stored/read back `2026-09-16T22:00:00.000Z` |
| Explicit UTC-midnight timestamp | Stored/read back `2026-09-17T00:00:00.000Z` unchanged |
| Numeric quantity0.12345678901234568, price5.537, fee1.9 | Same numeric decimal tokens in import response and full list |
| SELL90 with no holdings | HTTP400; activity count0 |
| Yahoo BUY3 followed by SELL1 for the same symbol/account/date | HTTP201 for each, EUR profile, two listed rows with exact requested numeric values |
| Identical Yahoo BUY reimport | HTTP201; empty activities response, no new row |

Numeric comparison parsed raw response number tokens as Decimal. The fractional
quantity observation starts at its reviewed wire token; it does not demonstrate
that a longer source Decimal survives conversion to Python/JavaScript numbers.
No blanket numeric tolerance is justified by these examples.

`GET /api/v1/activities` returned `count` and `activities`, with per-row `account`,
`tags`, `assetProfile`, `accountId`, `comment`, dates and numeric financial fields.
The current offline snapshot normalizer accepted those lab rows and confirmed
active/date context for explicit UTC midnight. It rejected date readiness for the
date-only request's nonmidnight result. The POST response does not include the
same full account/tag context, so it cannot replace the post-import full snapshot.

## Display boundary

At the pinned source, `activities-table.component.html` passes `element.date` to
`gf-value`. `value.component.ts` uses `new Date(value).toLocaleDateString(locale,
{day: '2-digit', month: '2-digit', year: 'numeric'})` for desktop date display,
without a fixed timezone. Executing that expression with `fr-FR` in the pinned
image's JavaScript runtime produced:

| Timestamp | Europe/Zurich | Europe/Paris | America/New_York |
| --- | --- | --- | --- |
| 2026-09-17T00:00:00.000Z | 17/09/2026 | 17/09/2026 | 16/09/2026 |
| 2026-01-15T00:00:00.000Z | 15/01/2026 | 15/01/2026 | 14/01/2026 |

This source/runtime evidence supports the source-calendar candidate in the
operator's Europe/Zurich context. It is not a rendered-browser screenshot and
does not establish date preservation in every client timezone. Bare date strings
must never be sent. Execution times without source timezone remain evidence only.

## Remaining gates

HTTP201 and returned counts alone do not prove ownership or acceptance. Every
future write needs exact fields/marker/account matching and complete readback.
Distinct account namespaces are mandatory because server duplicate comparison
omits accountId. The complete G5 gate still owns delayed insertion, lost response,
partial result, crash/restart, durable uncertain-intent fences and proven
completion/cancellation before any replay. Production version, account access,
symbol/currency validation, adoption, chronological holdings and independent
security review also remain necessary. Current artifacts stay `import_ready=false`.
