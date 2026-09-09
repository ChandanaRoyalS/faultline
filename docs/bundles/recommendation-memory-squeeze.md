# Recommendation service memory limit cut below what its runtime needs to start

## The scenario

| | |
|---|---|
| scenario | `recommendation-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `recommendation-service` via `recommendation-memory-squeeze` |
| time to page | 3m45s |
| steady state captured | 300s |
| capture window | 2026-09-09T06:11:50+00:00 → 2026-09-09T06:28:36+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m45s |
| `t_revert` | T+8m45s |
| all clear | T+9m46s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `frontend` | ServiceHighErrorRate | 6.0 min | **paged** |
| T+3m30s | `loadgenerator` | ServiceHighErrorRate | 6.0 min | **paged** |
| T+6m00s | `recommendationservice` | ServiceNoTraffic | 3.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="recommendationservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/recommendation-service.txt` — 201 lines.

## A look at the logs

From `logs/recommendation-service.txt` (195 lines):

```
2026-09-09T06:11:52+00:00  {"asctime": "2026-09-09 06:11:52,001", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "dcd17748fa3892f588cc3b5ce3a2d322", "otelSpanID": "9d6911e70776c2c3", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:52+00:00  {"asctime": "2026-09-09 06:11:52,003", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "dcd17748fa3892f588cc3b5ce3a2d322", "otelSpanID": "5c2c97ccb7d7bac6", "message": "[Recv ListRecommendations] product_ids=['OLJCESPC7Z', '0PUK6V6EV0', '2ZYFJ3GM2N', 'LS4PSXUNUM', '1YMWWN1N4O']", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:52+00:00  {"asctime": "2026-09-09 06:11:52,052", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "e1d0811691f7dc5f8786bfef1b5e341a", "otelSpanID": "10790e75486384e0", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:52+00:00  {"asctime": "2026-09-09 06:11:52,053", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "e1d0811691f7dc5f8786bfef1b5e341a", "otelSpanID": "c6e8ea697d506d5d", "message": "[Recv ListRecommendations] product_ids=['OLJCESPC7Z', '66VCHSJNUP', 'L9ECAV7KIM', '6E92ZMYYFZ', '2ZYFJ3GM2N']", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:55+00:00  {"asctime": "2026-09-09 06:11:55,056", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "d1957c8305ab953abb2abedea29646b2", "otelSpanID": "96776fec78435910", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:55+00:00  {"asctime": "2026-09-09 06:11:55,058", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "d1957c8305ab953abb2abedea29646b2", "otelSpanID": "0832c6fd2a72ab53", "message": "[Recv ListRecommendations] product_ids=['2ZYFJ3GM2N', '0PUK6V6EV0', 'LS4PSXUNUM', '1YMWWN1N4O', 'OLJCESPC7Z']", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:58+00:00  {"asctime": "2026-09-09 06:11:58,239", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "af810c0dad2e390f0c2e7e1da1740c00", "otelSpanID": "3eaf2839c37b5974", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:58+00:00  {"asctime": "2026-09-09 06:11:58,242", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "af810c0dad2e390f0c2e7e1da1740c00", "otelSpanID": "a4deecf30bc8b94c", "message": "[Recv ListRecommendations] product_ids=['6E92ZMYYFZ', '9SIQT8TOJO', 'L9ECAV7KIM', '1YMWWN1N4O', 'OLJCESPC7Z']", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:59+00:00  {"asctime": "2026-09-09 06:11:59,656", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "572cb4fed24babd887e568057adcbc5e", "otelSpanID": "6b37df4f23fbf2e5", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-09-09T06:11:59+00:00  {"asctime": "2026-09-09 06:11:59,658", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "572cb4fed24babd887e568057adcbc5e", "otelSpanID": "190053e6522f1dd2", "message": "[Recv ListRecommendations] product_ids=['6E92ZMYYFZ', '1YMWWN1N4O', '0PUK6V6EV0', '9SIQT8TOJO', 'OLJCESPC7Z']", "otelServiceName": "recommendationservice"}
2026-09-09T06:12:00+00:00  {"asctime": "2026-09-09 06:12:00,059", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "65defb26ba46b49e80e74ebe437a0ada", "otelSpanID": "9312ad6ab7ff9fc8", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-09-09T06:12:00+00:00  {"asctime": "2026-09-09 06:12:00,061", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "65defb26ba46b49e80e74ebe437a0ada", "otelSpanID": "62a700a366f8d543", "message": "[Recv ListRecommendations] product_ids=['66VCHSJNUP', 'OLJCESPC7Z', '6E92ZMYYFZ', '0PUK6V6EV0', '1YMWWN1N4O']", "otelServiceName": "recommendationservice"}
```

_183 further lines are in the bundle._

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

The page was `ServiceHighErrorRate` on **loadgenerator** and **frontend** together.
It arrived 3m45s after onset.

`ServiceNoTraffic` fired on **recommendationservice** at **T+6m00s**, two and a half
minutes after the page and the only alert naming the broken service.

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
attempt and the recommendation strip returned. Everything was clear 1m01s after the
fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

### Detection notes

- Onset to first page: **3m45s**. A dependency whose failure is tolerated by its caller
  takes longer to page than one whose failure is fatal — partial degradation crosses a
  ratio threshold slowly.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 3 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named neither the broken service nor anything adjacent to it.** frontend
  and loadgenerator are the edge; the culprit appeared two and a half minutes later,
  and only as an absence.
- Did the loudest service turn out to be the culprit? **No.** frontend and loadgenerator
  alerted longest at 6.8 minutes each and neither was broken.
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
