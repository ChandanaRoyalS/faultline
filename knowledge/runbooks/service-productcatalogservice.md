---
id: service-productcatalogservice
title: Service - productcatalogservice
origin: authored
applies_to: [productcatalogservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The product catalog. `kind: application`, `tier: core`, owner `demo/catalog`, container
`product-catalog-service`. It takes more measured calls than any other service in the graph, and
its catalog `depends_on` is empty: nothing it calls appears in any trace.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `frontend -> productcatalogservice` | 4575 | sync |
| inbound | `checkoutservice -> productcatalogservice` | 451 | sync |
| inbound | `recommendationservice -> productcatalogservice` | 444 | sync |

Three inbound, all `sync`, no outbound. `frontend -> productcatalogservice` at 4575 is the
largest edge in the graph. It is not the largest in the raw capture: the synthetic client's edge
into frontend is larger and is excluded by ADR-0017, which is why "most-called" here is a
statement about the graph rather than about the world.

## What the call volume does and does not do

**The alert rules are rate-based, not count-based.** The error rule is a ratio over a 2-minute
window and the latency rule is a p95 over the same, so a busy service and a quiet one are held
to the same threshold. Volume does not make productcatalogservice page more readily.

Where volume does matter is statistical rather than procedural: a ratio computed over thousands
of calls in a window is a sharper measurement than the same ratio over a few hundred. The
threshold is identical; the confidence behind a reading of it is not.

## What can page for it

All three rules, evaluated per `service_name`. SLO: p95 250ms, error ratio 0.05, from
`compose/prometheus/alert-rules.yml`. Its resting p95 sits in the 1.9-9.7ms band ADR-0025
measured across the eleven services without a latency tail.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Three inbound edges name three callers that see the
connection reset while the recreate runs, which is the largest such set in this world.
`world-warm-up-latency` covers what the recreated container's p95 does next.
