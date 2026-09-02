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

**The consequence is exact.** Two of the three alert rules cannot evaluate for it, so a fault
targeting it can never page on its own behalf. It is not that the alert "did not fire" - it
*cannot*. A service reasoned about as healthy because nothing alerted on it may simply be
invisible.

## How to tell the difference

The service catalog carries this distinction directly: a service is `present`,
`uninstrumented`, or `artifact_only` for graph reasoning, with a measured reason on every
absence. Read the presence before concluding anything from the absence of a signal, because
"not connected" and "not visible" are different facts and a bare node set cannot separate them.

## What it looks like when it breaks

The cascade is real even when the origin is silent: a failure in an uninstrumented service
surfaces on its *callers*, which are instrumented and do page. So an incident whose alerts all
name instrumented services may still originate in one that cannot alert, and the only way to
consider that possibility is to know which services those are.
