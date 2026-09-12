---
id: world-log-volume
title: How much this world logs, and what a log query can actually see
origin: authored
applies_to: [any]
signals: []
actions: []
---

Measured on an idle world with the load generator running, no fault injected, over a ten-minute
window. **About 29,000 lines an hour across the whole world**, very unevenly distributed.

## The table, by container

| container | lines/hour | | container | lines/hour |
|---|---:|---|---|---:|
| `cart-service` | 5,424 | | `email-service` | 1,128 |
| `kafka` | 5,250 | | `payment-service` | 1,128 |
| `otel-col` | 4,524 | | `loki` | 1,044 |
| `checkout-service` | 2,256 | | `ad-service` | 852 |
| `shipping-service` | 2,256 | | `accounting-service` | 564 |
| `recommendation-service` | 1,680 | | `frauddetection-service` | 564 |
| `currency-service` | 1,668 | | `quoteservice` | 564 |
| | | | `redis-cart` | 72 |

**These are container names, not compose service names.** Loki's `service` label holds the
container name, so a query has to go through the naming map to get there from a service
(`world-two-names-for-every-service`).

## Several services log only when something is wrong

`frontend` measured **0** lines in this window and 6,355 lines in a thirty-minute window earlier
the same hour, when a fault was live. So **log volume is itself a signal**: a service going from
zero to thousands of lines an hour is evidence in its own right.

**Four are silent even under load**, in three groups - the source's own heading says three and
then names four. The product catalog prints one startup banner and nothing per request, a single
line in nearly five hours. The feature-flag stub prints one line per start and nothing per
request. The load generator and the proxy are quiet by design. Anything that
expects log evidence from those is expecting something the world does not produce.

## What a log query actually returns

The tool caps a query at **500 lines**, matching the recorder's cap so that a recording and a live
query see the same shape. Against ~29,000 lines an hour across the world, that is a small
fraction of any multi-minute window on a talkative service.

What it does with the cap matters more than the cap: it takes **both ends** - the oldest lines
and the newest - rather than truncating to one. When the two ends meet, the window is fully
covered and no elision is marked, which is the ordinary case for a quiet service. When they do
not, the gap is marked rather than hidden.

The query window may open **before** the onset, and usually should.

There is a six-hour bound on how wide a window can be. **Its justification changed and the number
did not**: it was originally the metric retention period, retention was later raised well past
it, and six hours stayed as a policy bound rather than a technical one.

## Anything that removes telemetry ships with a measurement of what it removes

That rule came out of a log filter this project once ran. Measured over thirty minutes across all
twenty logging containers: 16,510 lines emitted, **24 matched the filter - 0.15%** - and all 24
came from Loki's own container.

It was **deleted rather than narrowed**. A no-op filter is a rot risk that also advertises that
noise is being handled when nothing is, and **a filter nobody can state the cost of is not narrow,
whatever its regex looks like.**

The log-shipping configuration is under `observability_digest` for the same reason: it decides
which containers ship logs and under what label, so it decides every log query's result.
