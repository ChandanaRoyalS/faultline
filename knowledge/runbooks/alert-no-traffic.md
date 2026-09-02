---
id: alert-no-traffic
title: ServiceNoTraffic has fired
origin: authored
applies_to: [any]
signals: [ServiceNoTraffic]
actions: [restart_service, revert_config]
---

No calls recorded for a service over the window, held for 3 minutes. Severity `critical`.

## Silence has two very different causes

**The service stopped serving.** It crashed, is crash-looping, or lost a dependency and never
accepts a request.

**The service is healthy and its telemetry is not arriving.** The process is fine and its
exporter points somewhere that does not collect. This looks identical on this rule and is
distinguishable only by looking somewhere other than the metrics: container state, container
logs, and whether neighbouring services still show calls *to* it.

Checking container liveness first separates the two in one query. Getting it backwards
produces a confident report about a service that never failed.

## Note on coverage

`frontendproxy` is excluded from this rule deliberately. It is Envoy, it emits a handful of
spans at startup and then goes quiet by design, and including it would page on healthy silence.
