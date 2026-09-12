---
id: service-frontend
title: Service - frontend
origin: authored
applies_to: [frontend]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The shop's web tier and the top of every measured call chain that matters. Five outbound edges,
and an inbound edge that the graph deliberately does not have.

## What calls it

Nothing, in the declared graph. The only thing that does is `loadgenerator`, and ADR-0017
excludes that edge as the synthetic client - excluding the edge removes the node, so the
service that alerts in almost every captured incident has no graph presence at all.

**The practical effect**: frontend is a root in the dependency graph, so a blast radius seeded
anywhere below it walks up to frontend and stops. Nothing upstream of it will ever appear.

## What it calls

All five **sync**, and the call counts are the browse path's shape:
`productcatalogservice` (4575), `cartservice` (1754), `adservice` (463),
`recommendationservice` (444), and `checkoutservice` (330, `unmeasured`).

productcatalogservice at 4575 calls is the most-called service in this world by a factor of
two and a half, which is worth knowing before reading anything into its alert frequency.

## Why it alerts so often, and what that is worth

Every synchronous callee's latency is frontend's latency, and it has four of them. A
`ServiceHighLatency` on frontend with a second latency alert one hop down is the ordinary
shape of a dependency problem, and the frontend alert is the *effect*.

**Frontend alerting alone is the interesting case.** With four synchronous callees quiet and
the caller loud, the added time is either in frontend's own process or on a path the graph
does not show. That is a narrower question than it looks, and traces answer it faster than
metrics: the span tree says whether any child span holds the time.

## What its silence means

`ServiceNoTraffic` on frontend is a statement about the load generator as much as about
frontend, because the load generator is the only source of traffic. A quiet frontend in a world
whose synthetic client has stopped is not a frontend fault, and the catalog records the client's
`artifact_only` standing so that this can be checked rather than assumed.
