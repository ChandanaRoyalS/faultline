# Cart is slow because its datastore is, and the datastore has no spans

## The scenario

| | |
|---|---|
| scenario | `redis-cart-dependency-latency` |
| fault class | **`dependency_latency`** |
| expected remediation | `restart` |
| split | `dev` |
| injected at | `redis-cart` via `redis-cart-dependency-latency` |
| time to page | 3m50s |
| steady state captured | 300s |
| capture window | 2026-08-31T03:44:32+00:00 → 2026-08-31T04:02:53+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m50s |
| `t_revert` | T+8m50s |
| all clear | T+11m21s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `cartservice` | ServiceHighLatency | 7.5 min | **paged** |
| T+3m45s | `checkoutservice` | ServiceHighLatency | 6.8 min | joined later |
| T+3m45s | `frontend` | ServiceHighLatency | 6.8 min | joined later |
| T+4m00s | `loadgenerator` | ServiceHighLatency | 6.8 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="redis-cart", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/redis-cart.txt` — 24 lines.

## A look at the logs

From `logs/redis-cart.txt` (18 lines):

```
2026-08-31T03:46:15+00:00  1:M 31 Aug 2026 03:46:15.051 * 100 changes in 300 seconds. Saving...
2026-08-31T03:46:15+00:00  1:M 31 Aug 2026 03:46:15.052 * Background saving started by pid 282
2026-08-31T03:46:15+00:00  282:C 31 Aug 2026 03:46:15.058 * BGSAVE done, 14277 keys saved, 0 keys skipped, 1236714 bytes written.
2026-08-31T03:46:15+00:00  282:C 31 Aug 2026 03:46:15.065 * DB saved on disk
2026-08-31T03:46:15+00:00  282:C 31 Aug 2026 03:46:15.066 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-08-31T03:46:15+00:00  1:M 31 Aug 2026 03:46:15.152 * Background saving terminated with success
2026-08-31T03:51:16+00:00  1:M 31 Aug 2026 03:51:16.004 * 100 changes in 300 seconds. Saving...
2026-08-31T03:51:16+00:00  1:M 31 Aug 2026 03:51:16.004 * Background saving started by pid 283
2026-08-31T03:51:16+00:00  283:C 31 Aug 2026 03:51:16.016 * BGSAVE done, 14360 keys saved, 0 keys skipped, 1243514 bytes written.
2026-08-31T03:51:16+00:00  283:C 31 Aug 2026 03:51:16.018 * DB saved on disk
2026-08-31T03:51:16+00:00  283:C 31 Aug 2026 03:51:16.019 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-08-31T03:51:16+00:00  1:M 31 Aug 2026 03:51:16.106 * Background saving terminated with success
```

_6 further lines are in the bundle._

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

<!-- NO ABSOLUTE TIMESTAMPS IN THE PROSE. Write "T+3m" or "about four minutes after
     the page", never "08:02:41". This file is read months later as a past incident,
     where the hour it happened means nothing - and a re-record would orphan every
     timestamp written here.

     `recorded_from` in the front matter above is the deliberate exception. It is
     absolute precisely so that it breaks when the recording changes: it pins this
     narrative to one recording, and a guard fails if they drift apart. Front matter
     is written to fail on a re-record; prose is written to survive one. Do not
     "fix" the inconsistency - see ARTIFACTS.md. -->

### What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

**On the page:** ServiceHighLatency/cartservice

#### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+3m50s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighLatency | cartservice | T-20s | 7.5m |
| later | ServiceHighLatency | checkoutservice | T-5s | 6.8m |
| later | ServiceHighLatency | frontend | T-5s | 6.8m |
| later | ServiceHighLatency | loadgenerator | T+10s | 6.8m |

The page named 1 service(s). By the time the fault was removed 4 alert(s) had fired - 3 more than the responder saw when they started.

### What was checked

**Whether anything was actually failing.** Nothing was. The error ratio was flat at zero on every
service for the whole window. Four services were slow together and none of them was returning
errors, which reads as queuing behind something rather than as a service falling over.

**Where in the chain the slowness started.** cartservice was the deepest service alerting and the
first to page, with checkout, the frontend and the load generator following it - the shape of
callers waiting on a callee rather than of a fault spreading outward. That put cartservice at the
bottom of the visible chain.

**Whether cartservice's own work had got slower.** This is where it stopped being obvious.
cartservice's p95 was ~655ms against a baseline of 1.9ms, but splitting its spans by kind showed
client-side p95 at ~390ms - a large part of its handler time was spent inside outbound calls, not
in its own code. Something cartservice talks to was answering late.

**Dead end: looking for what cartservice was waiting on, in the service metrics.** There is nothing
there to find. Cart's dependency is Redis, and Redis is not an instrumented service - it emits no
spans, exports no runtime metrics and has no service-level series of any kind. **No metric in the
system mentions it.** From the metrics alone, cart is a service that has become slow for no visible
reason.

**Dead end: cartservice's own recent history.** No deploy, no config change, no restart. Whatever
had changed, it had not changed on the service that looked broken.

**What named it:** the change history on `redis-cart`, which showed a network delay applied to the
container's interface. The one thing that had changed was the one thing with no telemetry.

### Root cause

Redis, the cart service's datastore, had a 300ms network delay applied to its interface, so every
response it sent back arrived late. Cart was not broken and was not doing anything differently - it
was blocking on a datastore that had become slow, and everything that calls cart inherited the wait.
The component at fault produces no telemetry of its own, so the only signal of it was the latency
appearing in its caller and a change recorded against its container.

### Resolution

The delay was removed from the Redis container's interface and latency returned to baseline as the
alert windows drained. **Class of fix: `restart`** - the intervention was on the container carrying
the fault, not a revert of any application configuration. Nothing about cartservice was changed at
any point, because nothing about cartservice was wrong.

### Detection notes

- Onset to first firing alert: 3m50s
- Services alerting on the page: 1
- Services alerting by the end of the fault: 4
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 2m31s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->

---

Rendered from [`evals/scenarios/artifacts/dev/redis-cart-dependency-latency/`](../../evals/scenarios/artifacts/dev/redis-cart-dependency-latency/) by `faultline-render`. [All bundles](README.md).
