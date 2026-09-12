---
id: service-redis-cart
title: Service - redis-cart
origin: authored
applies_to: [redis-cart]
signals: []
actions: [restart_service, revert_config]
---

The cart's datastore. `kind: infrastructure`, `tier: infrastructure`, owner `demo/platform`, and
`slo: null` - it has no SLO row because no rule can evaluate one for it.

## Its measured edges

No measured edges: this service appears in no trace and has no node in the graph.

## Why no rule can fire for it

Redis emits no spans and carries no `service.name`, so it has no series under either metric
family the rules read. `ServiceHighErrorRate` and `ServiceNoTraffic` are `sum by (service_name)`
over `calls_total`, which does not return it; `ServiceHighLatency` is a `service_name`-grouped
quantile over `latency_bucket`, which it does not export either. **So none of the three can fire
for redis-cart** - not "did not fire", cannot. Its `signals` list above is empty for that reason
and not by oversight. `world-uninstrumented-services` describes a service in the same position,
arriving at it by a different route.

It reaches the telemetry stack only through `cartservice`, whose Redis client emits a span per
operation (`HGET`, `HMSET`). Those spans belong to cartservice's trace, so they record
redis-cart's work as work cartservice did, never as a service of its own.

The catalog carries it anyway, as `infrastructure`, which resolves `usable_for_graph_reasoning`
to false while leaving the service nameable. ADR-0017 Addendum 3 records what settled that: a
service that cannot be named is a service that cannot be blamed, and the culprit-service axis
needed to be able to name this one.

## Acting on it

`restart_service` and `revert_config` operate on the container and are performable here.

**Confirmation has to be planned around a different service.** There is no alert on redis-cart to
clear, because there is no alert on redis-cart at all, so recovery is observed on cartservice and
on cartservice's two callers. A confirmation window drawn around the container that changed will
be watching a service that never pages.
