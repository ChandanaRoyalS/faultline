---
id: service-adservice
title: Service - adservice
origin: authored
applies_to: [adservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The storefront's ad panel. `kind: application`, `tier: core`, owner `demo/storefront`, container
`ad-service`. It is a JVM, and it is the best-instrumented service in this world.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `frontend -> adservice` | 463 | sync |

One inbound, no outbound. **adservice is a leaf**: it serves ads from memory and calls nothing.

## Why being a leaf changes what a fault on it can show

`tc netem` delays egress. A leaf's delayed egress lands *after* its server span has already
closed, so it never enters that service's own span metrics. This was measured here: a delay held
for a full alert budget plus steady state, reverted cleanly, and **adservice's p95 never left
1.9ms. No rule fired.**

The rule T7.22 drew from it is general and worth carrying: **a mechanism's observability is a
property of the target, not of the mechanism.** The property that decides it is whether the
target makes a downstream call inside the span being measured.

## What it exports

**48 runtime series**, `process_runtime_jvm_*` — the highest count of any service measured, and
the reason this one is called the best-instrumented here. They are labelled `exported_job`, not
`service_name`: Prometheus renamed the exporter's `job` label because it collided with the scrape
job's, so `process_runtime_jvm_memory_limit{exported_job="adservice",type="heap"}` is the shape
of a working selector.

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. It logs about 852 lines an hour at rest.

## Its resting behaviour

p95 mean **1.934ms** (min 1.9, max 2.8) over 181 samples of a clean 45-minute baseline, with
zero samples over the 250ms threshold; call rate mean 0.477 req/s. It is not one of the three
services with a measured at-rest latency tail.

Its container memory limit is **700M**, raised from the demo's native-x86 300M because the JVM
sits at its limit under emulation.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs. `world-warm-up-latency` covers what the p95 does next.
