---
id: service-emailservice
title: Service - emailservice
origin: authored
applies_to: [emailservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Order confirmation mail. `kind: application`, `tier: core`, owner `demo/comms`, container
`email-service`. A Ruby application.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `checkoutservice -> emailservice` | 286 | sync |

One inbound, `sync` by measurement: a recorded bundle broke this service and checkoutservice's
own error ratio moved with it, 0 → 0.061. No outbound edge.

## What it exports

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. **Zero runtime-family series.** About 1,128 log lines an hour at rest.

It is one of only six services with a measured **error-ratio** series in the clean baseline, and
that series reads 0.00% at mean, min, max and p95 across all 181 samples.

## Its resting behaviour

p95 mean **2.019ms** (min 1.9, max 3.867) over 181 samples, zero over the 250ms threshold; call
rate mean 0.625 req/s. Not one of the three services with a measured at-rest latency tail.
Container memory limit 250M.

## A reading of its error ratio was withdrawn, and the reason generalises

A 2026-08-23 measurement put this service's error ratio at **4.77%** on what was taken to be a
quiet world. ADR-0012 withdrew it: *"an averaging artifact of a contaminated window - its only
non-zero samples were an injected incident's recovery phase."* No threshold change was warranted.

The transferable part is about the instrument, not this service: **a mean over a window that
contains a recovery phase is not a baseline**, and a single aggregate cannot tell you which it
was. The clean 45-minute baseline that replaced it carries per-sample minima and maxima for that
reason.

## Its container has crossed the memory guard

`email-service` crossed the recorder's 90% memory-headroom guard during T7.22's recording
attempts, and cycling it is the documented remedy rather than a workaround. That guard refuses to
start a recording against any container above 90% of its limit, so this is a condition that stops
a run rather than one that shows up in an incident.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs.
