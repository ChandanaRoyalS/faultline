---
id: service-frauddetectionservice
title: Service - frauddetectionservice
origin: authored
applies_to: [frauddetectionservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Order screening. `kind: application`, **`tier: async`**, owner `demo/risk`, container
`frauddetection-service`. It is a JVM, and it is one of exactly two Kafka consumers here.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `checkoutservice -> frauddetectionservice` | 286 | async |

## The `async` kind on this edge is a measurement, and it is the one that defines the value

Edge kinds in this world are measured from recorded bundles rather than read off `span.kind` -
the bundles carry no trace data at all. `async` means **a callee's failure was observed not to
reach the caller**, and that is what was observed on this edge.

Blast-radius traversal crosses no `async` edge in either direction, for exactly this reason.

**The graph cannot see any of it.** This edge is a Kafka topic: trace context propagates through
the broker, so the producer's span and the consumer's span join into one trace and the dependency
job renders the pair as a direct edge. Four of checkoutservice's outbound edges are identical in
the topology - same parent, all at 286 calls - and the four carry three different edge kinds
between them. The topology is what cannot tell them apart: it records call causality, not failure
propagation, and the kinds come from the recorded bundles rather than from `span.kind`.

## What it exports

**38 runtime series**, `process_runtime_jvm_*`, labelled `exported_job`. Spans, `calls_total` and
`latency_bucket` are all present, so all three alert rules can evaluate for it. About 564 log
lines an hour at rest.

## Its traffic is sparse, and that changes when a rule agrees rather than whether it can

Call rate mean **0.156 req/s** across the clean baseline - joint sparsest served service in this
world. `ServiceNoTraffic` reads `rate(calls_total[3m])` against a 2-minute-windowed baseline and
holds for `for: 3m`. Fed one call every ten seconds or so, those windows empty slowly and the
for-clause starts late. A fault bites immediately; the *rule* can take minutes longer to agree.

p95 is **1.9ms flat** - min, mean and max identical to four decimal places over 181
samples - and it is not one of the three
services with a measured at-rest tail. Its container memory limit is 500M against a measured
resting usage of 326MiB.

## After a broker cycle

Measured: **frauddetectionservice reconnects on its own within about three minutes** after kafka
is restarted. The operational procedure restarts it anyway, because the other consumer does not
recover on its own and restarting both is one step rather than two.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable. Because its inbound
edge is `async`, a recreate here does not put its producer's calls in doubt - they complete
whether or not this service is consuming.
