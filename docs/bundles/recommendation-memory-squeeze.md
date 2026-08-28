# Recommendation service memory limit cut below what its runtime needs to start

## The scenario

| | |
|---|---|
| scenario | `recommendation-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `recommendation-service` via `recommendation-memory-squeeze` |
| time to page | 4m30s |
| steady state captured | 300s |
| capture window | 2026-08-28T05:15:49+00:00 → 2026-08-28T05:35:20+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m30s |
| `t_revert` | T+9m30s |
| all clear | T+12m31s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m30s | `frontend` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+4m30s | `loadgenerator` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+6m15s | `recommendationservice` | ServiceNoTraffic | 6.2 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="recommendationservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/recommendation-service.txt` — 122 lines.

## A look at the logs

From `logs/recommendation-service.txt` (116 lines):

```
2026-08-28T05:15:49+00:00  {"asctime": "2026-08-28 05:15:49,031", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "2644cccaec1d416f9c6540acbf41819e", "otelSpanID": "41cd7b4c2a799572", "message": "[Recv ListRecommendations] product_ids=['0PUK6V6EV0', 'L9ECAV7KIM', '66VCHSJNUP', '2ZYFJ3GM2N', 'OLJCESPC7Z']", "otelServiceName": "recommendationservice"}
2026-08-28T05:15:49+00:00  {"asctime": "2026-08-28 05:15:49,450", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "226bc871e0bd8cf5f75da86bb57fa145", "otelSpanID": "a7677a63f8b0a546", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-28T05:15:49+00:00  {"asctime": "2026-08-28 05:15:49,755", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "226bc871e0bd8cf5f75da86bb57fa145", "otelSpanID": "b3d98bcb0ed422d1", "message": "[Recv ListRecommendations] product_ids=['OLJCESPC7Z', '66VCHSJNUP', '6E92ZMYYFZ', '0PUK6V6EV0', '9SIQT8TOJO']", "otelServiceName": "recommendationservice"}
2026-08-28T05:15:52+00:00  {"asctime": "2026-08-28 05:15:52,947", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "ba0e1b6840e37759b317f6937b776911", "otelSpanID": "cb9fabfb99c0d21c", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-28T05:15:53+00:00  {"asctime": "2026-08-28 05:15:53,252", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "ba0e1b6840e37759b317f6937b776911", "otelSpanID": "ead3532d3965d55f", "message": "[Recv ListRecommendations] product_ids=['66VCHSJNUP', 'LS4PSXUNUM', '0PUK6V6EV0', 'L9ECAV7KIM', '9SIQT8TOJO']", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:29+00:00  {"asctime": "2026-08-28 05:16:29,977", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "1bdb55cd8d502fa993ac200a85b37936", "otelSpanID": "d37799d8e9fd8028", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:30+00:00  {"asctime": "2026-08-28 05:16:30,283", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "1bdb55cd8d502fa993ac200a85b37936", "otelSpanID": "1603aa888fb2804a", "message": "[Recv ListRecommendations] product_ids=['0PUK6V6EV0', 'LS4PSXUNUM', '9SIQT8TOJO', 'L9ECAV7KIM', '2ZYFJ3GM2N']", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:40+00:00  {"asctime": "2026-08-28 05:16:40,782", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "ea4d335c8539d6ffd9a9036ddb97110e", "otelSpanID": "1fdae1d229c3e079", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:41+00:00  {"asctime": "2026-08-28 05:16:41,085", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "ea4d335c8539d6ffd9a9036ddb97110e", "otelSpanID": "7014f5ef5acd59f5", "message": "[Recv ListRecommendations] product_ids=['OLJCESPC7Z', '66VCHSJNUP', '2ZYFJ3GM2N', 'L9ECAV7KIM', '6E92ZMYYFZ']", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:42+00:00  {"asctime": "2026-08-28 05:16:42,566", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "d4e1df3ded9afbafd631e1de32610213", "otelSpanID": "ec313218ef843ac9", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:42+00:00  {"asctime": "2026-08-28 05:16:42,868", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "d4e1df3ded9afbafd631e1de32610213", "otelSpanID": "db375cf39fc730e8", "message": "[Recv ListRecommendations] product_ids=['LS4PSXUNUM', '66VCHSJNUP', '2ZYFJ3GM2N', 'L9ECAV7KIM', '0PUK6V6EV0']", "otelServiceName": "recommendationservice"}
2026-08-28T05:16:51+00:00  {"asctime": "2026-08-28 05:16:51,412", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "cc521517557305b6bc32984acaedb247", "otelSpanID": "bec6848f639e1692", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
```

_104 further lines are in the bundle._

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

The page was two alerts: `ServiceHighErrorRate` on **frontend** and **loadgenerator**.
It arrived 4m30s after onset.

`ServiceNoTraffic` fired on **recommendationservice** at **T+6m15s**, a minute and
three-quarters after the page and the only alert naming the broken service.

Three alerts across three services. The storefront loaded, product pages rendered, the
basket and checkout worked. The recommendation strip on the home page was empty, and
pages finished rendering without it — nothing in this incident crossed a latency
threshold anywhere in the system.

### What was checked

**Why detection was so slow.** frontend does not fail when recommendations fail; it
waits, then renders without them. Only a fraction of its requests error, so the ratio
climbed toward the five percent threshold slowly rather than jumping. The latency alert
followed for the same reason — the time is frontend waiting on something that never
answers.

**Error rate by service.** frontend and loadgenerator over threshold, everything else
flat. recommendationservice itself: no errors at all, then no data.

**Whether recommendationservice was idle or gone.** `ServiceNoTraffic` cannot tell those
apart. Its runtime metrics can: the service publishes its own interpreter memory usage,
and an idle process keeps publishing. **Those series stopped at onset and did not resume
until the fix.** A service that has stopped reporting its own memory is not a service
that is waiting for work.

**recommendationservice's logs, which say nothing at all.** This is the hardest part of
this incident. There is no error, no traceback, no truncated startup banner — the stream
simply ends mid-traffic and the next line is a clean startup twelve minutes later, after
the fix. Nothing was written because nothing got far enough to write it, and because the
runtime buffers its output and lost whatever was pending when it was killed. **An empty
log is not evidence of a healthy service; it is evidence that nothing survived long
enough to speak.**

**What that combination rules out.** No errors, no traffic, no logs, no runtime metrics,
and callers that time out rather than receive failures. Nothing is refusing requests —
there is nothing there to refuse them. That eliminates every explanation involving the
service's own behaviour and leaves only explanations about its existence.

**What changed.** Not the image, not the code, not the environment, not any dependency.
The change history shows one edit: the container's memory ceiling was lowered to 32 MiB.
Steady-state usage is around 55 MiB, and the runtime needs more than the new ceiling
merely to finish starting — so the process was killed during initialisation, restarted,
and killed again, without ever reaching a serving state.

### Root cause

recommendationservice's container memory limit was reduced below the footprint its
runtime requires to start. Nothing about the service changed — only the ceiling it was
allowed to occupy — and the effect was not degradation but non-existence.

This is why it produced no errors of its own: a process that never finishes starting
records no calls, and therefore no errored ones. Its only signal was absence, and that
absence arrived a full minute after the downstream errors did.

### Resolution

The memory limit was restored. recommendationservice completed startup on its next
attempt and the recommendation strip returned. Everything was clear 2m30s after the
fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

### Detection notes

- Onset to first page: **4m30s**. A dependency whose failure is tolerated by its caller
  takes longer to page than one whose failure is fatal — partial degradation crosses a
  ratio threshold slowly.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 3 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named neither the broken service nor anything adjacent to it.** frontend
  and loadgenerator are the edge; the culprit appeared a minute and three-quarters later,
  and only as an absence.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 8.0 minutes each and neither was broken.
- **Nothing here was slow, only missing.** No latency rule fired on any service. A
  dependency that vanishes cheaply — one its caller can skip rather than wait for —
  produces a failure with no latency signature at all, so a responder scanning latency
  dashboards for the cause of a degraded storefront would find every one of them clean.
- **Absence is the only alert this service can ever produce.** Its healthy p95 is around
  4ms against a 250ms threshold — sixty times of headroom. No amount of slowing down
  can reach the rule. If a fault on this service does not stop it serving, nothing in
  the alerting will ever see it.
- **This service leaves no logs when it dies**, unlike a runtime that prints a banner on
  every start. Its silence is total, and the absence of a crash message must not be read
  as the absence of a crash. What filled that gap was the runtime metrics stopping.
- **Blast radius shape.** One leaf and one caller, nothing else. A narrow, two-service
  spread points at something with a single consumer; it cannot be produced by anything
  on the critical path.
- Both an error-rate and a latency alert fired on the same two services. That pairing
  is what waiting on a dead dependency looks like: some requests fail, the rest are
  slow because they waited first.
- **The signature does not name its cause.** Everything above establishes that the
  process is gone. Nothing in it says *why* the ceiling and the footprint stopped
  fitting — only the change history distinguishes a lowered limit from a service that
  grew.

---

Rendered from [`evals/scenarios/artifacts/holdout/recommendation-memory-squeeze/`](../../evals/scenarios/artifacts/holdout/recommendation-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
