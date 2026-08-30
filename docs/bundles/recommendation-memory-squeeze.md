# Recommendation service memory limit cut below what its runtime needs to start

## The scenario

| | |
|---|---|
| scenario | `recommendation-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `recommendation-service` via `recommendation-memory-squeeze` |
| time to page | 4m45s |
| steady state captured | 300s |
| capture window | 2026-08-30T00:58:52+00:00 → 2026-08-30T01:17:22+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m45s |
| `t_revert` | T+9m45s |
| all clear | T+11m30s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m30s | `loadgenerator` | ServiceHighErrorRate | 6.8 min | **paged** |
| T+4m45s | `frontend` | ServiceHighErrorRate | 6.5 min | joined later |
| T+6m15s | `recommendationservice` | ServiceNoTraffic | 4.8 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="recommendationservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/recommendation-service.txt` — 159 lines.

## A look at the logs

From `logs/recommendation-service.txt` (153 lines):

```
2026-08-30T00:58:53+00:00  {"asctime": "2026-08-30 00:58:53,069", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "75046b303a8314e61f49a2a169773099", "otelSpanID": "c6597d4c2487010e", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:53+00:00  {"asctime": "2026-08-30 00:58:53,070", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "75046b303a8314e61f49a2a169773099", "otelSpanID": "bc85323b8d910a3a", "message": "[Recv ListRecommendations] product_ids=['9SIQT8TOJO', 'L9ECAV7KIM', '66VCHSJNUP', '1YMWWN1N4O', '0PUK6V6EV0']", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:53+00:00  {"asctime": "2026-08-30 00:58:53,677", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "d62697f24b7e6f14a590ac71f7cd1632", "otelSpanID": "d3a953a1db4ec857", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:53+00:00  {"asctime": "2026-08-30 00:58:53,678", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "d62697f24b7e6f14a590ac71f7cd1632", "otelSpanID": "9d6bfaa185918fbf", "message": "[Recv ListRecommendations] product_ids=['66VCHSJNUP', '2ZYFJ3GM2N', '1YMWWN1N4O', '9SIQT8TOJO', 'L9ECAV7KIM']", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:58+00:00  {"asctime": "2026-08-30 00:58:58,592", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "07d74ca51debadbca0a8ad7569625fa8", "otelSpanID": "4b6f20a2dba8cb4c", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:58+00:00  {"asctime": "2026-08-30 00:58:58,594", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "07d74ca51debadbca0a8ad7569625fa8", "otelSpanID": "4ce6a9fd5507d4fb", "message": "[Recv ListRecommendations] product_ids=['L9ECAV7KIM', 'OLJCESPC7Z', 'LS4PSXUNUM', '6E92ZMYYFZ', '0PUK6V6EV0']", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:59+00:00  {"asctime": "2026-08-30 00:58:59,568", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "0b42cd33c847177d40949f072ec9e74c", "otelSpanID": "a1525835ba24d3b6", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-30T00:58:59+00:00  {"asctime": "2026-08-30 00:58:59,570", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "0b42cd33c847177d40949f072ec9e74c", "otelSpanID": "65ad001270410098", "message": "[Recv ListRecommendations] product_ids=['6E92ZMYYFZ', '2ZYFJ3GM2N', '1YMWWN1N4O', '66VCHSJNUP', 'L9ECAV7KIM']", "otelServiceName": "recommendationservice"}
2026-08-30T00:59:07+00:00  {"asctime": "2026-08-30 00:59:07,081", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "1e372ba72fb70c536957c0b14eaa3210", "otelSpanID": "e0775f6e474ef478", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-30T00:59:07+00:00  {"asctime": "2026-08-30 00:59:07,082", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "1e372ba72fb70c536957c0b14eaa3210", "otelSpanID": "4ced12a8d96a4feb", "message": "[Recv ListRecommendations] product_ids=['2ZYFJ3GM2N', 'LS4PSXUNUM', '9SIQT8TOJO', '6E92ZMYYFZ', 'L9ECAV7KIM']", "otelServiceName": "recommendationservice"}
2026-08-30T00:59:10+00:00  {"asctime": "2026-08-30 00:59:10,223", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "137e92ea56456a99eec653578235ee75", "otelSpanID": "2ea6da268572c452", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-30T00:59:10+00:00  {"asctime": "2026-08-30 00:59:10,225", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "137e92ea56456a99eec653578235ee75", "otelSpanID": "6eeda14d850e5b53", "message": "[Recv ListRecommendations] product_ids=['0PUK6V6EV0', 'OLJCESPC7Z', '2ZYFJ3GM2N', '9SIQT8TOJO', '1YMWWN1N4O']", "otelServiceName": "recommendationservice"}
```

_141 further lines are in the bundle._

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

The page was a single alert: `ServiceHighErrorRate` on **loadgenerator**, with **frontend**
joining fifteen seconds later.
It arrived 4m45s after onset.

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
and an idle process keeps publishing. **Those series stop and do not resume until after
the fix.** A service that has stopped reporting its own memory is not a service that is
waiting for work.

Read the stop as a fact and not as a timestamp. The series remain *visible* for up to five minutes past the moment they stop being scraped, because the metrics store serves the last sample forward — so this dates the death only to within that window, and the direction of the error is always late. Nothing else here dates
it either — this service leaves no logs when it dies — so on this incident the onset is
known from the alerting and the death only to within five minutes of it.

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

- Onset to first page: **4m45s**. A dependency whose failure is tolerated by its caller
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
