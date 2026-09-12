---
id: service-recommendationservice
title: Service - recommendationservice
origin: authored
applies_to: [recommendationservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Product recommendations on the browse path. `kind: application`, `tier: core`, owner
`demo/storefront`, container `recommendation-service`. CPython.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `frontend -> recommendationservice` | 444 | sync |
| outbound | `recommendationservice -> productcatalogservice` | 444 | sync |

**Four services in this world have an outbound edge in the measured graph and this is one of
them**, alongside `frontend`, `checkoutservice` and `shippingservice`. Its catalog `depends_on`
names the same callee. (The catalog counts five; the fifth is the synthetic client, whose only
edge ADR-0017 excludes.) In and out at the same count: every call it takes becomes a call
it makes.

Its outbound edge is `sync` on a measured **p95 91.9×** - the largest latency multiple of any edge
in the table.

## Its inbound edge reads `sync`, and a narrative saying the frontend copes is also true

The frontend degrades rather than erroring outright when recommendations fail - *and it does
error*, 0.013 → 0.077. Both statements are about the same measurement. **Partial propagation is
still propagation, and for blast radius the caller belongs in the radius.** An edge kind records
whether a callee's failure was observed to reach the caller, not whether the caller handled it
gracefully.

## What it exports

**13 runtime series**: `runtime_cpython_*` and `system_memory_*`, labelled `exported_job` rather
than `service_name`, so `runtime_cpython_memory{exported_job="recommendationservice"}` is the
shape of a working selector. Spans, `calls_total` and `latency_bucket` are all present, so all
three alert rules can evaluate for it, and it is one of only six services with a measured
error-ratio series in the clean baseline. About 1,680 log lines an hour at rest.

## What its runtime series do under memory pressure, and what they cannot say

**Under a squeeze the series do not degrade. They vanish**, and the signal is conditional on the
process never reaching a serving state - a service that keeps being killed but keeps coming back
keeps exporting, and this signal says nothing about it.

Two limits worth carrying, both stated as limits rather than as tests:

- **Absence of a series is weaker evidence than presence of one.** It supports *this process is
  not running*; it does not support *this process was OOM-killed*.
- **The cgroup ceiling itself is observable nowhere** - in no metric, in no log - and applying one
  is not a deploy.

There is a runtime difference here worth knowing for its own sake: a JVM is slow enough to restart
that its absence lands inside an observation window, and a CPython service is not. Same mechanism,
different visibility, because of what the runtime does rather than what the fault does.

## Its resting behaviour

p95 mean **4.289ms** (min 3.777, max 5.2) over 181 samples of the clean baseline, with zero
samples over the 250ms threshold, and an error ratio of 0.00% across the same 181. Not one of the
three services with a measured at-rest latency tail. Container memory limit 800M.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs; its callee does not, since an action here changes nothing on the other side of an
outbound edge.
