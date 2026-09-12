---
id: service-currencyservice
title: Service - currencyservice
origin: authored
applies_to: [currencyservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Currency conversion on the order path. `kind: application`, `tier: core`, owner `demo/checkout`,
container `currency-service`. A small C++ gRPC server whose per-call work is short.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `checkoutservice -> currencyservice` | 698 | unmeasured |

One inbound at 698 calls - the largest of checkoutservice's eight outbound edges - and no
outbound of its own. The kind is `unmeasured`: nothing recorded says whether a failure here
reaches checkoutservice.

## It is the reason CPU is not a fault mechanism in this world

ADR-0013 retired container CPU throttling, superseding the mechanism ADR-0010 had added, and the
measurement that retired it was taken here. A CPU quota was verified applied - `cpu.max` reading
`5000 100000` - and held for seven minutes. **Nothing moved**: call rate 0.4 → 0.4 → 0.3 req/s,
p95 1.9ms throughout, no errors.

The arithmetic says why. This service's demand is about 0.8ms of CPU per second - **0.08% of a
core against a 5% ceiling, roughly 60× headroom.** The mechanism worked; there was nothing to
constrain. It idles at 0.04% CPU, so a quota ceiling has nothing to bind against.

And it is not special in that. `docker stats` across all 28 containers found the busiest at
**4.64%** of a core, then 3.52%, then 2.84%, with everything else under 1.4%. **No service in
this world sits between "too idle to throttle" and "too central to throttle".** The CPU code
path is left in place, unused, and it is correct - it is the world that makes it unusable, not
the implementation.

`resource_exhaustion` keeps its memory mechanism, which is unaffected, because these containers
sit near their memory ceilings under emulation even while idle on CPU.

## What it exports

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. **Zero runtime-family series** - there is no `process_runtime_*` or `runtime_*` metric
for this service to read, so logs are the only evidence family it adds beyond the span metrics.
About 1,668 log lines an hour at rest.

## Its resting behaviour

p95 **1.9ms flat** - min, mean and max identical to four decimal places over 181
samples - and call rate mean 0.455 req/s.
Zero samples over the 250ms threshold; not one of the three services with a measured at-rest
tail. Container memory limit **100M**, the smallest in the override.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs.
