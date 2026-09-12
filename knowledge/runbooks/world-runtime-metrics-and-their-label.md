---
id: world-runtime-metrics-and-their-label
title: Runtime metrics arrive under a label nobody would guess
origin: authored
applies_to: [any]
signals: []
actions: []
---

Services' own runtime metrics do reach Prometheus here, through the OTLP pipeline rather than a
scrape. Nothing had to be added to collect them - they were already there. What trips people is
how to select them.

## The label is `exported_job`, not `service_name`

Prometheus renamed the exporter's `job` label because it collided with the scrape job's. **So a
query written against `service_name` silently matches nothing on these series** - it returns no
error and no rows, which is the worst failure mode a selector has.

`exported_job` holds the **compose service name**, which is what `canonical_service` produces
from a target that might be written either way (`world-two-names-for-every-service`).

A working selector looks like:

```
process_runtime_jvm_memory_limit{exported_job="adservice",type="heap"}
runtime_cpython_memory{exported_job="recommendationservice"}
```

## Three metric families, and all three patterns are needed

`process_runtime_.*`, `runtime_.*` and `system_memory_.*`. **Prometheus anchors regexes**, so
`runtime_.*` does *not* also match `process_runtime_*`, and dropping either of the first two
silently loses a language's worth of series.

The families that appear here are `process_runtime_jvm_*`, `runtime_cpython_*`,
`process_runtime_go_*`, `process_runtime_dotnet_*` and `system_memory_*`.

## Which services export them, measured

Read off the recorded bundles rather than from a live world:

| service | series | family |
|---|---|---|
| `adservice` | 48 | `process_runtime_jvm_*` |
| `frauddetectionservice` | 38 | `process_runtime_jvm_*` |
| `cartservice` | 20 | `process_runtime_dotnet_*` |
| `recommendationservice` | 13 | `runtime_cpython_*`, `system_memory_*` |

Measured at zero: `currencyservice`, `emailservice`, `productcatalogservice`, `shippingservice`
and the feature-flag stub. For every other service the question has not been asked, and "not
measured" is a different statement from "measured at zero".

A recording made under the earlier capture set has no runtime capture at all, **and that is a
fact about the recording rather than an error in it.**

## What the series can and cannot say

**The cgroup ceiling is observable nowhere.** The runtime series report what the runtime asked
for and got, never the limit the kernel enforces; the logs do not carry it; and applying one is
not a deploy, so a deploy-shaped change history cannot see it either.

**Absence of a series is weaker evidence than presence of one.** A series can stop because the
exporter broke, because the collector dropped it, or because a label changed. It supports *this
process is not running*. It does not support *this process was killed for memory*.

**And the signal is conditional on the process never reaching a serving state.** The series stop
when a process cannot get to live; they persist when it dies just as often but comes back fast
enough to keep running. So the failure that hides from other signals - frequent death with fast
recovery - is one this signal also misses.

## There is no threshold for them

The alerting rules have numbers and these do not. This repository has **no measured threshold for
a meaningful change in call rate or in runtime memory**, so the tooling reports departures from a
service's own recent behaviour and says that is what it is doing. A floor invented here would be
a number nobody could defend.
