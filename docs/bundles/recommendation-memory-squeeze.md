# Recommendation service memory limit cut below what its runtime needs to start

## The scenario

| | |
|---|---|
| scenario | `recommendation-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `recommendation-service` via `recommendation-memory-squeeze` |
| time to page | 5m26s |
| steady state captured | 412s |
| capture window | 2026-08-23T17:25:59+00:00 → 2026-08-23T17:47:47+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+5m26s |
| `t_revert` | T+12m18s |
| all clear | T+14m48s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+5m15s | `frontend` | ServiceHighErrorRate | 9.5 min | **paged** |
| T+5m15s | `loadgenerator` | ServiceHighErrorRate | 9.5 min | **paged** |
| T+5m45s | `frontend` | ServiceHighLatency | 7.0 min | joined later |
| T+5m45s | `loadgenerator` | ServiceHighLatency | 7.0 min | joined later |
| T+6m15s | `recommendationservice` | ServiceNoTraffic | 8.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |

`logs/recommendation-service.txt` — 175 lines.

## A look at the logs

From `logs/recommendation-service.txt` (169 lines):

```
2026-08-23T17:26:00+00:00  {"asctime": "2026-08-23 17:26:00,913", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "3bbdf14709f4127f4552caee7d7c7c63", "otelSpanID": "66d32992b90aa1cc", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:00+00:00  {"asctime": "2026-08-23 17:26:00,915", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "3bbdf14709f4127f4552caee7d7c7c63", "otelSpanID": "b16fa63063e359df", "message": "[Recv ListRecommendations] product_ids=['0PUK6V6EV0', '2ZYFJ3GM2N', '9SIQT8TOJO', '6E92ZMYYFZ', '1YMWWN1N4O']", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:02+00:00  {"asctime": "2026-08-23 17:26:02,321", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "db2acfb00df6c6cdbcd0ccd49d7e6858", "otelSpanID": "957d464fd3d9840d", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:02+00:00  {"asctime": "2026-08-23 17:26:02,323", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "db2acfb00df6c6cdbcd0ccd49d7e6858", "otelSpanID": "bc2b839f4d8152d2", "message": "[Recv ListRecommendations] product_ids=['L9ECAV7KIM', 'OLJCESPC7Z', '6E92ZMYYFZ', '66VCHSJNUP', '0PUK6V6EV0']", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:06+00:00  {"asctime": "2026-08-23 17:26:06,135", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "82fa0448df0000c6f463015376cdbebb", "otelSpanID": "0b11ce1403de4523", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:06+00:00  {"asctime": "2026-08-23 17:26:06,137", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "82fa0448df0000c6f463015376cdbebb", "otelSpanID": "8087e4aa3ef652e0", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', '0PUK6V6EV0', 'LS4PSXUNUM', '6E92ZMYYFZ', 'OLJCESPC7Z']", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:08+00:00  {"asctime": "2026-08-23 17:26:08,302", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "068c5f1dcd04002761bf71544259abdd", "otelSpanID": "c8ab23fe48208596", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:08+00:00  {"asctime": "2026-08-23 17:26:08,304", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "068c5f1dcd04002761bf71544259abdd", "otelSpanID": "8836de8ea19701be", "message": "[Recv ListRecommendations] product_ids=['6E92ZMYYFZ', 'LS4PSXUNUM', '9SIQT8TOJO', 'OLJCESPC7Z', '1YMWWN1N4O']", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:11+00:00  {"asctime": "2026-08-23 17:26:11,774", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "91b1fd68eeda3d852ffc38a12dd685d9", "otelSpanID": "8caa89ffd053d02f", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:11+00:00  {"asctime": "2026-08-23 17:26:11,775", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "91b1fd68eeda3d852ffc38a12dd685d9", "otelSpanID": "b5c88cdca95d7657", "message": "[Recv ListRecommendations] product_ids=['0PUK6V6EV0', '66VCHSJNUP', 'L9ECAV7KIM', '9SIQT8TOJO', '6E92ZMYYFZ']", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:14+00:00  {"asctime": "2026-08-23 17:26:14,380", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "e885f8e238892e1f9a8434950a55f750", "otelSpanID": "a5065a1b80580489", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-23T17:26:14+00:00  {"asctime": "2026-08-23 17:26:14,381", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "e885f8e238892e1f9a8434950a55f750", "otelSpanID": "7ebaaf2725e143ba", "message": "[Recv ListRecommendations] product_ids=['9SIQT8TOJO', 'OLJCESPC7Z', '2ZYFJ3GM2N', '1YMWWN1N4O', '0PUK6V6EV0']", "otelServiceName": "recommendationservice"}
```

_157 further lines are in the bundle._

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
It arrived 5m26s after onset — the slowest detection of any incident recorded on this
system.

Thirty seconds later both services also crossed `ServiceHighLatency`, and stayed over
it for seven minutes.

At **T+1m00s**, `ServiceNoTraffic` fired on **recommendationservice**.

Five alerts across three services. The storefront loaded, product pages rendered, the
basket and checkout worked. The recommendation strip on the home page was empty and
each page took noticeably longer to finish rendering.

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

- Onset to first page: **5m26s**, the slowest on this system. A dependency whose
  failure is tolerated by its caller takes longer to page than one whose failure is
  fatal — partial degradation crosses a ratio threshold slowly.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 5 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named neither the broken service nor anything adjacent to it.** frontend
  and loadgenerator are the edge; the culprit appeared a minute later, and only as an
  absence.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 9m30s each and neither was broken.
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
