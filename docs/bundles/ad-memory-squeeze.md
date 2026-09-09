# Ad service memory limit cut below the working set its JVM was sized for

## The scenario

| | |
|---|---|
| scenario | `ad-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `ad-service` via `ad-memory-squeeze` |
| time to page | 4m16s |
| steady state captured | 300s |
| capture window | 2026-09-09T02:51:49+00:00 → 2026-09-09T03:10:05+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m16s |
| `t_revert` | T+9m16s |
| all clear | T+11m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m00s | `frontend` | ServiceHighErrorRate | 7.0 min | **paged** |
| T+4m00s | `loadgenerator` | ServiceHighErrorRate | 5.0 min | **paged** |
| T+6m00s | `adservice` | ServiceNoTraffic | 4.0 min | joined later |
| T+8m15s | `frontend` | ServiceHighLatency | 2.8 min | joined later |
| T+8m15s | `loadgenerator` | ServiceHighLatency | 0.8 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="adservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/ad-service.txt` — 148 lines.

## A look at the logs

From `logs/ad-service.txt` (142 lines):

```
2026-09-09T02:56:50+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T02:56:50+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T02:56:50+00:00  [otel.javaagent 2026-09-09 02:56:50:450 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-09-09T02:56:53+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T02:56:53+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T02:56:53+00:00  [otel.javaagent 2026-09-09 02:56:53:722 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-09-09T02:56:56+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T02:56:57+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T02:56:57+00:00  [otel.javaagent 2026-09-09 02:56:57:210 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-09-09T02:57:00+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T02:57:01+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T02:57:01+00:00  [otel.javaagent 2026-09-09 02:57:01:163 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
```

_130 further lines are in the bundle._

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
4m16s after onset. No service between them and the edge was named, and both stayed up for the
rest of the incident.

Two minutes later, at **T+6m00s**, `ServiceNoTraffic` fired on **adservice** —
the first time anything named a service other than the edge, and the only alert in this
incident that points inward.

Latency followed errors rather than preceding them: `ServiceHighLatency` on the same two edge
services at **T+8m15s**, four minutes after they were already erroring.

Five alerts across three services. The storefront was mostly usable throughout:
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

**adservice's logs, which is where this one breaks open.** The capture opens at T+0m01s and
holds **twenty-three startup attempts** inside the fault window — each a JVM banner, the
OpenTelemetry agent announcing itself, and then nothing. The last is at T+8m43s, twenty-seven
seconds *after* the ceiling was restored, and it is the one that succeeds: the same banner, then
ordinary request lines. No line explains a failure, because until then the process is being
stopped before it can form an opinion about anything. **A truncated, repeating startup is a process being killed from
outside**, and it is the strongest evidence in this incident.

**Whether adservice was idle or absent.** `ServiceNoTraffic` cannot tell those apart:
both look like a call rate of zero. The runtime metrics can, with a caveat that matters.
adservice exports its own JVM heap series, and a process that is merely idle keeps
exporting them; these cease. **What they cannot do is date it.** The series remain
visible until T+4m30s and then stop — but the metrics store serves a scrape forward for
five minutes after the last one, so the true stop is anywhere in the five minutes before
that, and the logs place the first kill at T+0. **The series answer *whether*, the logs
answer *when*, and reading a stop time off a series overstates by up to five minutes.**

**What changed.** Not the image, not the environment, not the code, not any
dependency. The change history shows one edit: the container's memory ceiling was
reduced to 256 MiB. Steady-state usage is around 350 MiB, and the JVM's heap was sized
against the previous ceiling of 700 MiB — so the runtime ran until it grew into the
new wall, was killed, and never got back up.

### Root cause

adservice's container memory limit was reduced below the footprint its JVM was
configured for. Nothing about the service changed — only the ceiling it was allowed to
occupy. From the first restart after the change, the runtime could not complete a startup
inside the new limit: it was killed during initialisation, twenty-two times over, and never
served a request again until the ceiling was restored — the twenty-third attempt, after the
restore, is the one that came up.

This is why it produced no errors of its own: a process that dies before it serves records
no calls, and therefore no errored ones. Its evidence was absence in the metrics and
repetition in the logs — nothing failing, and the same startup over and over.

### Resolution

The memory limit was restored to its previous value. adservice came back and the ad
panel returned. Everything was clear 2m00s after the fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

### Detection notes

- Onset to first page: **4m16s**.
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
- **But a series' end is a soft edge, and this bundle shows how soft.** The heap series
  remain visible until T+4m30s while the logs place the first kill at T+0 — because the
  metrics store serves the last scrape forward for five minutes. **A series appearing is
  sharp to one scrape; a series disappearing is late by up to five minutes.** Anything
  dated off a disappearance carries that error, here and everywhere else.
- **A truncated, repeating startup names the shape of the failure and not its cause.**
  Sixteen JVM banners with nothing after them say the process is being killed from
  outside. That is all they say: it does not distinguish "the ceiling came down" from
  "the thing inside it got bigger", and those have opposite fixes. Only the change
  history separates them.
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A leaf consumed by one caller produces exactly this narrow spread;
  nothing on the critical path can.

---

Rendered from [`evals/scenarios/artifacts/dev/ad-memory-squeeze/`](../../evals/scenarios/artifacts/dev/ad-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
