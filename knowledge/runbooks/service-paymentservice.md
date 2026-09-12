---
id: service-paymentservice
title: Service - paymentservice
origin: authored
applies_to: [paymentservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Card authorisation on the order path. `kind: application`, `tier: core`, owner `demo/checkout`,
container `payment-service`. Node.js.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `checkoutservice -> paymentservice` | 286 | unmeasured |

A direct RPC, not a broker hop, and **the canonical `unmeasured` edge in this world**: the graph
source names it in as many words - *nothing recorded says what `checkoutservice -> paymentservice`
does when payment fails*, because no bundle has ever broken this service. Five of the world's
fifteen edges are `unmeasured` for that reason.

## It exports no runtime-family series at all, and that is a property of the target

`runtime.json` captures only `RUNTIME_FAMILIES` - `process_runtime_*`, `runtime_*`,
`system_memory_*` - and **paymentservice exports none of them at any time.** That capture would
read 0 on a healthy recording of this service too. It is a clear example of a reading that looks
like an effect and is a property of the target, and it was read off the recorder's own derived
field rather than declared by an author.

It does export a business counter, `app_payment_transactions`, under `exported_job`. That counter
is reachable to a live PromQL query and is **not** in any recorded bundle, because it is not a
runtime family.

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. About 1,128 log lines an hour at rest, which works out at roughly 130 lines in a
seven-minute window.

## Its resting behaviour

p95 mean **2.398ms** (min 1.9, max 6.7) over 181 samples, zero over the 250ms threshold; call
rate mean 0.326 req/s. Not one of the three services with a measured at-rest latency tail.

## Its memory limit was raised, and how it settled afterwards is the informative part

200M sat *inside* the working set - measured at 191.5MiB of 200MiB, 95.7%, idle - which is above
the recorder's 90% guard, so the pre-flight would not run against it. It was raised to **320M**,
and afterwards it settled at **160MiB of 320M**: below its old ceiling.

**That is what a genuinely undersized container looks like when it is given room.** A container
whose usage climbs back to the new limit is doing something else, and this world has one of
those; `service-kafka` is its document.

Bundles recorded before that raise describe a different world, which is why the limits are
digest-locked.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs.
