---
id: alert-no-traffic
title: ServiceNoTraffic has fired
origin: authored
applies_to: [any]
signals: [ServiceNoTraffic]
actions: []
---

No calls recorded for a service over the window, held for 3 minutes. Severity `critical`.

## What the rule measures

`sum by (service_name) (rate(calls_total[3m])) == 0`, and a second clause requiring the same
service to have had traffic in a 30-minute window offset by 10. So it fires only for a service
that *was* serving and stopped - never for one that has always been quiet, and never for one
that has no `calls_total` series at all.

**It reads the metric, not the process.** `calls_total` is span-derived: a sample exists because
the service emitted a span and that span reached the collector. Every link in that chain is a
way for the samples to stop. The rule's silence is therefore silence in the telemetry, which is
a larger category than silence in the service, and nothing in what the rule reads narrows it.

## Note on coverage

`frontendproxy` is excluded from this rule deliberately. It is Envoy, it emits a handful of
spans at startup and then goes quiet by design, and including it would page on healthy silence.
