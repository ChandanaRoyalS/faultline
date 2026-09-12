---
id: service-accountingservice
title: Service - accountingservice
origin: authored
applies_to: [accountingservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Order bookkeeping. `kind: application`, **`tier: async`**, owner `demo/risk`, container
`accounting-service`. One of exactly two Kafka consumers in this world, and the one with the
sharper operational property.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `checkoutservice -> accountingservice` | 286 | unmeasured |

## The edge is a Kafka topic rendered as a direct call, and it is deliberately `unmeasured`

Trace context propagates through the broker, so the producer's span and the consumer's span join
into one trace and the dependency job renders the pair as a direct edge. **The broker is not a
node, so the hop through it is invisible.**

The sibling edge out of checkoutservice reaching the other consumer is `async` by measurement.
This one is **not** marked async by analogy: *probably-async on a structural argument is exactly
the inference the edge-kind exercise exists to avoid making.* Nothing recorded says what happens
to checkoutservice when this consumer fails, and `unmeasured` is the honest value for that.

## It exits rather than idling when its broker is unreachable

Measured: pointed at an address that does not answer, this consumer logs `severity: fatal` -
*"kafka: client has run out of available brokers to talk to"* - and the process exits. With
`restart: always` that is a crashloop; nine restarts in about 58 seconds were recorded against a
pre-fault restart count of zero. Every wrong address produces the same fatal, including a
blackhole IP, which arrives there by dial timeout instead.

The general form, which is the part worth carrying: **a consumer in this world does not sit alive
and idle when its broker is gone.**

## And it does not come back when the broker does

Measured at T7.27: **restarting kafka strands accountingservice, and it does not self-heal.** The
other consumer reconnected on its own within three minutes; this one sat at 0.000 req/s until it
was restarted. That is why the recycle procedure for the broker has a second step, and why the
harness refuses to recycle kafka automatically - an automatic recycle that forgets the consumers
leaves the world quietly broken, because a stranded consumer is silent rather than alerting.

## What it exports

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. Whether it exports runtime-family series has not been measured. About 564 log lines an
hour at rest.

## Its resting behaviour

p95 **1.9ms flat** - min, mean and max identical to four decimal places over 181
samples of a clean 45-minute baseline. Call
rate mean **0.156 req/s**, joint sparsest served service here, with the same consequence for
`ServiceNoTraffic`'s windows that `service-frauddetectionservice` sets out. Not one of the three
services with a measured at-rest tail. Container memory limit 300M.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable. A restart is also the
documented remedy for the stranded state above, which is a case where the action is right and the
incident that motivated it happened somewhere else.
