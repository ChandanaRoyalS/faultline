# Ad service memory limit cut below the working set its JVM was sized for

## The scenario

| | |
|---|---|
| scenario | `ad-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `ad-service` via `ad-memory-squeeze` |
| time to page | 3m45s |
| steady state captured | 300s |
| capture window | 2026-08-28T02:36:26+00:00 → 2026-08-28T02:53:56+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m45s |
| `t_revert` | T+8m45s |
| all clear | T+10m30s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `frontend` | ServiceHighErrorRate | 6.8 min | **paged** |
| T+3m30s | `loadgenerator` | ServiceHighErrorRate | 6.8 min | **paged** |
| T+6m00s | `adservice` | ServiceNoTraffic | 4.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="adservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/ad-service.txt` — 137 lines.

## A look at the logs

From `logs/ad-service.txt` (131 lines):

```
2026-08-28T02:41:26+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-28T02:41:26+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-28T02:41:26+00:00  [otel.javaagent 2026-08-28 02:41:26:874 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-08-28T02:41:29+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-28T02:41:30+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-28T02:41:30+00:00  [otel.javaagent 2026-08-28 02:41:30:194 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-08-28T02:41:33+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-28T02:41:33+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-28T02:41:34+00:00  [otel.javaagent 2026-08-28 02:41:34:129 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-08-28T02:41:37+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-28T02:41:37+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-28T02:41:38+00:00  [otel.javaagent 2026-08-28 02:41:38:078 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
```

_119 further lines are in the bundle._

## The incident record

Written from the responder's chair, by someone who did not know the fault class
or that anything had been injected. This text is also corpus material, which is
why it never names the injector.

**It keeps its own clock.** The table above is measured from the injection, which
is the only origin the manifest records; a narrative's `T+` offsets are the
responder's own and start wherever that responder started counting — usually the
page, sometimes the injection, sometimes an event in the logs. The same moment can
therefore carry two different offsets on this page. The absolute timestamps in the
bundle are the tiebreak.

### What was observed

The page was `ServiceHighErrorRate` on **frontend** and **loadgenerator** together,
3m45s after onset. No service between them and the edge was named, and both alerts then
stayed up continuously for the rest of the incident.

Two and a half minutes later, at **T+6m00s**, `ServiceNoTraffic` fired on **adservice** —
the first time anything named a service other than the edge, and the only alert in this
incident that points inward.

Three alerts across three services. The storefront was mostly usable throughout:
product pages loaded, baskets worked, checkout completed. The advertisement panel was
missing.

### What was checked

**loadgenerator.** The page named it and it explains nothing. It is the synthetic
client; its error rate restates whatever the storefront is failing to do.

**Error rate by service.** frontend intermittently over threshold, loadgenerator over,
everything else flat. adservice itself: zero errors, then no data at all.

**Which page elements were failing.** The store worked apart from the ad panel. That
narrowed it faster than any metric did — frontend's errors were confined to one
dependency, and the storefront said which one before the alerting did.

**Whether adservice was idle or absent.** `ServiceNoTraffic` cannot tell those apart:
both look like a call rate of zero. The runtime metrics can. adservice exports its own
JVM heap series, and a process that is merely idle keeps exporting them. **Those
series continued for the first four and a half minutes of the incident and then
stopped entirely at T+4m30s, not returning until after the fix.** A service that has stopped
reporting how much heap it is using does not have a heap. That is the moment the
investigation stopped being about traffic and started being about the process.

**adservice's logs, which say nothing at all.** Ordinary request lines up to seconds
before onset, then total silence until two minutes after the fix. No error, no crash
message, not even a startup banner from a restart attempt. **An empty log is not
evidence of a healthy service; it is evidence that nothing survived long enough to
speak.** The silence here is total where other incidents on this system have at least
left truncated startup attempts — which restart supervision produces is not
guaranteed, and its absence must not be read as the absence of restarts.

**What changed.** Not the image, not the environment, not the code, not any
dependency. The change history shows one edit: the container's memory ceiling was
reduced to 256 MiB. Steady-state usage is around 350 MiB, and the JVM's heap was sized
against the previous ceiling of 700 MiB — so the runtime ran until it grew into the
new wall, was killed, and never got back up.

### Root cause

adservice's container memory limit was reduced below the footprint its JVM was
configured for. Nothing about the service changed — only the ceiling it was allowed to
occupy. The process ran for a few minutes on the heap it had already committed, grew,
was killed by the kernel, and could not complete a restart inside the new limit.

This is why it produced no errors of its own: a process that is killed records no
calls, and therefore no errored ones. Its evidence was absence, three times over — of
traffic, of logs, and of the runtime metrics it publishes about itself.

### Resolution

The memory limit was restored to its previous value. adservice came back and the ad
panel returned. Everything was clear 1m45s after the fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

### Detection notes

- Onset to first page: **3m45s**.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 3
  alerts.
- Alerts that fired only during recovery: **none**.
- **The page named the edge, twice over, and the culprit only as an absence two and a
  half minutes later.** The strongest early signal was not in the alerting at all: the
  storefront worked except for one panel.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 6.8 minutes each, and one of them is not a service in any meaningful
  sense.
- **A partial failure can look completely ordinary in the alerting.** Only the requests
  touching the ad panel were failing, and frontend's error ratio crossed the threshold
  and stayed there like any total outage would. Nothing in the shape of that alert says
  "one dependency out of many" — the storefront's own behaviour said it, and the metric
  did not.
- **A service's own runtime metrics disappearing is stronger evidence than its traffic
  disappearing.** An idle service still reports its heap; a dead one reports nothing.
  This incident's record carries that evidence directly: the heap series run to
  T+4m30s and stop.
- **The runtime series also outlived the traffic.** The heap kept reporting for
  minutes after calls stopped being served — a process can be alive and useless. The
  reverse transition, from reporting to gone, is the one that dates the death.
- **Silence in the logs carries no timestamp of its cause and no cause at all.** This
  run left no crash message and no restart banners — nothing between the last ordinary
  request and the post-fix recovery. What filled that gap was the runtime metrics
  stopping. The failure signature does not name its cause either way: only the change
  history distinguishes a lowered ceiling from a service that grew.
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A leaf consumed by one caller produces exactly this narrow spread;
  nothing on the critical path can.

---

Rendered from [`evals/scenarios/artifacts/dev/ad-memory-squeeze/`](../../evals/scenarios/artifacts/dev/ad-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
