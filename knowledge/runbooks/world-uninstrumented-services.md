---
id: world-uninstrumented-services
title: Services that cannot page on their own behalf
origin: authored
applies_to: [featureflagservice]
signals: [ServiceNoTraffic]
actions: []
---

Not every service in this world emits span metrics, and one in particular emits none.

## featureflagservice

ADR-0006 replaced it with a stub that reproduces its gRPC contract and none of its
instrumentation. Measured against Prometheus: `count by (service_name) (calls_total)` returns
15 services and it is not among them.

**The consequence is exact.** Neither `calls_total` nor `latency_bucket` has any series for it
under any spelling, and all three alert rules are grouped by `service_name` over one of those
two families - so **none of the three can evaluate for it**, and a fault targeting it can never
page on its own behalf. It is not that an alert "did not fire": it *cannot*.

An earlier version of this document said two of three. That was the count for the two
`calls_total` rules alone, and it left `ServiceHighLatency` out of an argument that reaches it
too.

## What the catalog records about presence

A service is `present`, `uninstrumented`, `artifact_only` or `infrastructure` for graph
reasoning, with a measured reason on every absence. Those are four different ways to be missing
from a span-derived graph and the catalog keeps them apart, because "not connected", "not
visible" and "emits no spans of its own" are different facts that a bare node set cannot
separate. `service-redis-cart` is the `infrastructure` case written out.
