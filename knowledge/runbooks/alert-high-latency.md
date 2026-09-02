---
id: alert-high-latency
title: ServiceHighLatency has fired
origin: authored
applies_to: [any]
signals: [ServiceHighLatency]
actions: [restart_service]
---

`histogram_quantile(0.95, sum by (service_name, le) (rate(latency_bucket[2m]))) > 250`, held
for 3 minutes. Severity `warning`.

**The healthy baseline is under 50 ms on every service**, measured flat over 45 clean minutes
(ADR-0012). A p95 above 250 ms is five times the ceiling of normal, not a marginal excursion.

## Read the clock before the metric

A container recreated in the last few minutes is still warming up, and its p95 is not a
baseline reading. Check container uptime before concluding anything from a latency number: a
service that has just been restarted looks slow for reasons unrelated to the incident.

## What it usually is here

Latency without a matching error-rate alert is most often `dependency_latency` - delay
injected into a container's network namespace. The signature is that the *caller* slows while
the callee's own latency stays flat, because the delay is on the wire rather than in the
handler.

## What to propose

`dependency_latency` resolves by **restart**, not by reverting configuration. The delay lives
in the container's network namespace, so recreating the container removes it. Proposing a
config revert here fixes nothing and reads as a misdiagnosis.
