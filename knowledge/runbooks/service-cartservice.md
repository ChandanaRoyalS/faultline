---
id: service-cartservice
title: Service - cartservice
origin: authored
applies_to: [cartservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The shopping cart. `kind: application`, `tier: core`, owner `demo/checkout`. Its compose service
is `cartservice` and its container is `cart-service` - two names for one service, which is why
identity goes through `canonical_service` rather than `==`.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `frontend -> cartservice` | 1754 | sync |
| inbound | `checkoutservice -> cartservice` | 572 | sync |

Two inbound, both `sync` - measured rather than assumed. No outbound edge.

## Its outbound dependency is real and has no edge

**The absent outbound edge is not an absent dependency.** cartservice reaches `redis-cart`
through a Redis client, and the only trace of that is the client span (`HGET`, `HMSET`) recorded
inside cartservice's own trace. Redis emits no spans of its own and carries no `service.name`,
so there is nothing for a span-derived graph to build an edge from.

The catalog carries `redis-cart` anyway, as `infrastructure`: present in the world, absent from
the graph, and nameable. `service-redis-cart` is its document.

## What can page for it

All three rules, evaluated per `service_name`. SLO: p95 250ms, error ratio 0.05, from
`compose/prometheus/alert-rules.yml`.

Its measured healthy p95 is **1.9ms, flat** - 181 consecutive samples, min and max alike, over a
clean 45-minute baseline. That is the bottom of the 1.9-9.7ms band ADR-0025 measured across the
eleven services without a latency tail - **median p95 over twelve hours**, which is a different
statistic from the mean over 45 minutes quoted here. It puts the 250ms threshold two orders of
magnitude above resting.

An earlier baseline called this service bimodal at 353ms and was wrong: every such reading was
taken inside the warm-up window after a recreate (ADR-0012, third correction, and
`world-warm-up-latency`).

## Acting on it

`restart_service`, `revert_config` and `rollback_image` all recreate the container from its
declared definition. What that removes is what lives in the container's own process or its own
network namespace. It does not reach `redis-cart`, which is a separate container with its own
namespace and lifecycle. Both inbound edges name callers that see the connection reset while the
recreate runs.
