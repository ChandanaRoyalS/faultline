# Cart service pointed at the wrong Redis port

## The scenario

| | |
|---|---|
| scenario | `cart-redis-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `cartservice` via `cart-redis-misconfig` |
| time to page | 2m45s |
| steady state captured | 300s |
| capture window | 2026-08-24T04:39:27+00:00 → 2026-08-24T04:57:13+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+2m45s |
| `t_revert` | T+7m45s |
| all clear | T+10m46s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+2m45s | `frontend` | ServiceHighErrorRate | 7.5 min | **paged** |
| T+2m45s | `loadgenerator` | ServiceHighErrorRate | 7.5 min | **paged** |
| T+3m00s | `checkoutservice` | ServiceHighErrorRate | 7.0 min | joined later |
| T+6m00s | `currencyservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m00s | `emailservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m00s | `quoteservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m15s | `accountingservice` | ServiceNoTraffic | 2.0 min | joined later |
| T+6m15s | `cartservice` | ServiceNoTraffic | 2.0 min | joined later |
| T+6m15s | `frauddetectionservice` | ServiceNoTraffic | 2.0 min | joined later |
| T+6m15s | `shippingservice` | ServiceNoTraffic | 2.0 min | joined later |
| T+10m15s | `emailservice` | ServiceHighErrorRate | 0.5 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |

`logs/cart-service.txt` — 506 lines.

## A look at the logs

From `logs/cart-service.txt` (500 lines):

```
2026-08-24T04:45:04+00:00  Unhandled exception. System.ApplicationException: Wasn't able to connect to redis
2026-08-24T04:45:04+00:00     at cartservice.cartstore.RedisCartStore.EnsureRedisConnected() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 89
2026-08-24T04:45:04+00:00     at cartservice.cartstore.RedisCartStore.InitializeAsync() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 62
2026-08-24T04:45:04+00:00     at Program.<Main>$(String[] args) in /usr/src/app/src/Program.cs:line 39
2026-08-24T04:45:20+00:00  Unhandled exception. System.ApplicationException: Wasn't able to connect to redis
2026-08-24T04:45:20+00:00     at cartservice.cartstore.RedisCartStore.EnsureRedisConnected() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 89
2026-08-24T04:45:20+00:00     at cartservice.cartstore.RedisCartStore.InitializeAsync() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 62
2026-08-24T04:45:20+00:00     at Program.<Main>$(String[] args) in /usr/src/app/src/Program.cs:line 39
2026-08-24T04:45:57+00:00  Unhandled exception. System.ApplicationException: Wasn't able to connect to redis
2026-08-24T04:45:57+00:00     at cartservice.cartstore.RedisCartStore.EnsureRedisConnected() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 89
2026-08-24T04:45:57+00:00     at cartservice.cartstore.RedisCartStore.InitializeAsync() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 62
2026-08-24T04:45:57+00:00     at Program.<Main>$(String[] args) in /usr/src/app/src/Program.cs:line 39
```

_488 further lines are in the bundle._

## The incident record

Written from the responder's chair, by someone who did not know the fault class
or that anything had been injected. This text is also corpus material, which is
why it never names the injector.

**It keeps its own clock.** The table above is measured from the injection, which
is the only origin the manifest records; a narrative's `T+` offsets are the
responder's own and start wherever that responder started counting — usually the
page, sometimes the injection, sometimes an event in the logs. The same moment can
therefore carry two different offsets on this page. The absolute timestamps in the
bundle are the tiebreak.

### What was observed

The page named two services: `ServiceHighErrorRate` on **frontend** and
**loadgenerator**, 2m45s after the first bad request. **checkoutservice** joined fifteen
seconds later.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

Then seven services went quiet in two waves fifteen seconds apart —
currencyservice, emailservice and quoteservice first, at T+3m15s; then
accountingservice, **cartservice**, frauddetectionservice and shippingservice. All
`ServiceNoTraffic`.

Eleven alerts across ten services.

### What was checked

**Error rate by service.** frontend, loadgenerator and checkout were over threshold.
cartservice showed no errors at all — flat zero, below every healthy service in the
system. That reading was taken as evidence cart was fine.

**loadgenerator.** Set aside. It is the synthetic client, so its error rate mirrors
whatever the storefront is doing and carries no information about cause.

**Traces from frontend.** Checkout spans failing on their call to cart. The first real
narrowing, roughly three minutes in.

**The two waves of silence.** Tempting to read as a failure spreading — one thing
knocking over another, which knocks over more. It is not. Both waves are the same event
seen at two evaluation boundaries: those services stopped being called at the same
moment and their rate windows emptied a scrape apart. **Fifteen seconds between groups
is scrape granularity, not causal ordering.**

**The seven quiet services.** This is where the time went. Seven going silent at once
reads as a platform-wide event, and cartservice is one entry in an alphabetical list of
seven — no more conspicuous than accountingservice. Six of them are downstream of
checkout and went quiet because checkout had stopped calling them; only one was the
cause. Nothing in the alerting distinguishes them.

**cartservice container state, and its logs.** The container was restarting repeatedly,
and unlike a service that was never created it had plenty to say. Its logs run to
hundreds of lines of the same cycle: the process starts, checks its Redis connection,
fails that check, exits, and is restarted. The failure message names the address it was
trying to reach.

**Recent changes to cartservice.** `REDIS_ADDR` set to `redis-cart:6380`. Redis was
listening on 6379 and healthy throughout — every other consumer of it was unaffected.

### Root cause

cartservice was configured with the wrong Redis port. The dependency was never
unhealthy; only the address was wrong.

Because cart validates its Redis connection during startup rather than on first use, the
wrong address stopped the process coming up at all. Cart did not degrade — it
disappeared. That is why it never appeared in the error-rate metric: a service that is
not running records no calls, and therefore no errored ones. Its apparent good health
was an absence of data, not an absence of problems.

### Resolution

`REDIS_ADDR` restored to `redis-cart:6379`. cartservice came up on its next restart and
the no-traffic alerts cleared fifteen seconds later — those six services had never been
broken, only starved.

A brief `ServiceHighErrorRate` appeared on **emailservice** after the fix and lasted
half a minute, on a service that had not errored once during the incident. It is a
recovery artifact: checkout resumed and pushed queued work through a service that had
been idle. Everything was clear at **T+8m01s**.

Class of fix: **config_revert**. Nothing had been deployed and there was no version to
roll back to — one environment value was wrong.

### Detection notes

- Onset to first page: **2m45s**.
- Services alerting at the page: **2**. Over the whole incident: **10**, across 11
  alerts.
- Alerts that fired only during recovery: **1** — emailservice, thirty seconds, on a
  service that was never part of the failure.
- **The broken service was indistinguishable from six healthy ones.** cartservice
  appeared in the second wave of `ServiceNoTraffic` alongside three services merely
  downstream of it, and was never singled out by any alert.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 7m30s each, and neither was broken.
- Would the page alone have been enough? **No.** It named two services, neither of them
  cart, and pointed at the edge of the system rather than at its cause.
- **A restarting container is a talkative one.** The decisive evidence was in cart's own
  logs, and it existed because the process reached the point of trying and failing. A
  service that is repeatedly killed, or that was never created at all, leaves nothing to
  read — so "the logs are empty" and "the logs are damning" are both findings, and the
  difference between them narrows the cause before anything else does.
- The most misleading signal was cart's own error rate: a flat zero throughout, read as
  health when it meant absence.

---

Rendered from [`evals/scenarios/artifacts/dev/cart-redis-misconfig/`](../../evals/scenarios/artifacts/dev/cart-redis-misconfig/) by `faultline-render`. [All bundles](README.md).
