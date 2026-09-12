---
id: service-quoteservice
title: Service - quoteservice
origin: authored
applies_to: [quoteservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Shipping quotes. `kind: application`, `tier: core`, owner `demo/checkout`. A PHP application
served by Apache, and the deepest node on the order path.

## Its two names are one name

Almost every service here has a container name that is not its compose service name -
`cartservice` runs in `cart-service` - which is why identity goes through `canonical_service`
rather than `==`. **quoteservice is one of the two application services where the two coincide**;
`frontend` is the other. The rest of the self-identical names are infrastructure and telemetry
containers. A self-identical name is unambiguous rather than special: such a service can be
addressed by either scheme.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `shippingservice -> quoteservice` | 286 | unmeasured |

One inbound, no outbound. `unmeasured` because no bundle has ever broken this service, so nothing
recorded says whether a failure here reaches shippingservice. In the span tree it sits one hop
below shipping on the checkout path: `shipping GetQuote` → `quote /getquote`.

**It is one step further down than a blast radius reaches from a checkout seed.** The downstream
direction is one step from the seeds only and does not compose, so a scope seeded on
checkoutservice reaches shippingservice and stops.

## What it exports

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. Whether it exports runtime-family series has not been measured. About 564 log lines an
hour at rest.

## Its resting behaviour

p95 mean **7.66ms** (min 7.05, max 9.0) over 181 samples, zero over the 250ms threshold; call
rate mean 0.313 req/s. Slower at rest than most of this world, and not one of the three services
with a measured at-rest latency tail.

**It has been measured rising 5.3-5.5× in p95 while it was not a caller of the slowed service.**
That is most likely contention on an emulated host. It is recorded so that nobody reads it as
evidence of a dependency edge, because it is not one.

## Its memory limit was raised before it blocked anything

120M sat inside the working set: measured at **95.8MiB of 120MiB, 79.8%, idle** - ten points
from the recorder's 90% pre-flight guard, which refuses to start a recording against a container
above it. It was raised to 200M
before it could block a recording mid-catalog rather than after, and afterwards it settled at
**77MiB of 200M**, below its old ceiling.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs.
