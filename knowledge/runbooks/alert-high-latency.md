---
id: alert-high-latency
title: ServiceHighLatency has fired
origin: authored
applies_to: [any]
signals: [ServiceHighLatency]
actions: []
---

`histogram_quantile(0.95, sum by (service_name, le) (rate(latency_bucket[2m]))) > 250`, held
for 3 minutes. Severity `warning`.

**The healthy baseline is under 50 ms on every service**, measured flat over 45 clean minutes
(ADR-0012). A p95 above 250 ms is five times the ceiling of normal, not a marginal excursion.

**Three services are a measured exception to that, found by a later twelve-hour census**
(ADR-0025). `checkoutservice`, `frontend` and `loadgenerator` enter multi-minute p95 excursions
far above 250 ms on a world at rest, sustained past this rule's `for:` clause; every other
service recorded zero samples over threshold. The rule is not wrong when it fires on them and it
was deliberately left alone. What handles it is the scoring gate, which refuses to begin a
recording during an excursion - so this alert inside a recorded incident's window is not the
tail.

## Read the clock before the metric

A container recreated in the last few minutes is still warming up, and its p95 is not a
baseline reading. Check container uptime before concluding anything from a latency number: a
service that has just been restarted looks slow for reasons unrelated to the incident.

## What the rule reads

A p95 over `latency_bucket`, grouped by `service_name` - so it is scoped to a service, not to a
call path, and a service whose histogram has no series cannot trip it at all. The 2-minute rate
window must fill before the quantile moves, and the 3-minute `for:` clause runs after that, so
the alert's `activeAt` lags the onset of whatever caused it by minutes rather than seconds.

`class-dependency-latency` carries what a delay mechanism does to this number, and
`world-saturation-is-invisible` carries what this world has no rule for at all.
