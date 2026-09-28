# The recommendation service is cut from the network - its process runs and reaches nothing

## The scenario

| | |
|---|---|
| scenario | `v2-recommendation-partition` |
| fault class | **`network_partition`** |
| expected remediation | `restart` |
| split | `holdout` |
| injected at | `recommendation` via `v2-recommendation-partition` |
| time to page | 6m46s |
| steady state captured | 300s |
| capture window | 2026-09-28T11:41:36+00:00 → 2026-09-28T12:06:23+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+6m46s |
| `t_revert` | T+11m46s |
| all clear | T+17m47s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+6m30s | `frontend-proxy` | ServiceHighLatency | 9.0 min | **paged** |
| T+6m30s | `load-generator` | ServiceHighLatency | 9.0 min | **paged** |
| T+7m30s | `recommendation` | ServiceNoTraffic | 5.0 min | joined later |
| T+14m30s | `frontend` | ServiceHighErrorRate | 2.0 min | began after the revert |
| T+14m30s | `recommendation` | ServiceHighErrorRate | 2.0 min | began after the revert |
| T+15m30s | `frontend` | ServiceHighLatency | 1.0 min | began after the revert |
| T+15m30s | `recommendation` | ServiceHighLatency | 2.0 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="recommendation"}` |

`logs/recommendation.txt` — 210 lines.

## A look at the logs

From `logs/recommendation.txt` (---- onset 2026-09-28T11:46:36+00:00 ----):

```
2026-09-28T11:41:36+00:00  2026-09-28 11:41:36,800 INFO [main] [recommendation_server.py:47] [trace_id=65c2163003f66b4671707476738a1d19 span_id=5e64edddc3c196c1 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['6E92ZMYYFZ', '0PUK6V6EV0', '9SIQT8TOJO', 'L9ECAV7KIM', 'LS4PSXUNUM']
2026-09-28T11:41:37+00:00  2026-09-28 11:41:37,991 INFO [main] [recommendation_server.py:47] [trace_id=af6cda05cfd7fa255956fe9a54b3cc94 span_id=b0e58f1632ba8b66 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['HQTGWGPNH4', '0PUK6V6EV0', 'OLJCESPC7Z', '1YMWWN1N4O', '66VCHSJNUP']
2026-09-28T11:41:58+00:00  2026-09-28 11:41:58,782 INFO [main] [recommendation_server.py:47] [trace_id=4cdbbb31943bee260c4a11fabd0c8b00 span_id=c1c269dd615eb383 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['OLJCESPC7Z', '66VCHSJNUP', '1YMWWN1N4O', '2ZYFJ3GM2N', '0PUK6V6EV0']
2026-09-28T11:42:09+00:00  2026-09-28 11:42:09,072 INFO [main] [recommendation_server.py:47] [trace_id=1aab3c5908799ce2255c6fbc4698a7ba span_id=0e109c0bc64bc105 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['OLJCESPC7Z', '1YMWWN1N4O', 'LS4PSXUNUM', '9SIQT8TOJO', '0PUK6V6EV0']
2026-09-28T11:42:09+00:00  2026-09-28 11:42:09,653 INFO [main] [recommendation_server.py:47] [trace_id=6c05bf55072fed32c1d78b3843f29ba1 span_id=e030aae66727929f resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['66VCHSJNUP', '0PUK6V6EV0', '1YMWWN1N4O', 'HQTGWGPNH4', '6E92ZMYYFZ']
2026-09-28T11:42:10+00:00  2026-09-28 11:42:10,128 INFO [main] [recommendation_server.py:47] [trace_id=ed4d5b712022f2a59f899836152311b6 span_id=bb5b36a58832dc33 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['L9ECAV7KIM', '9SIQT8TOJO', '66VCHSJNUP', '0PUK6V6EV0', 'OLJCESPC7Z']
2026-09-28T11:42:11+00:00  2026-09-28 11:42:11,164 INFO [main] [recommendation_server.py:47] [trace_id=74aa14591daecbb73eb3cbe4c98bbb65 span_id=1beef979f93e41ff resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['66VCHSJNUP', 'OLJCESPC7Z', 'L9ECAV7KIM', 'LS4PSXUNUM', '9SIQT8TOJO']
2026-09-28T11:42:11+00:00  2026-09-28 11:42:11,196 INFO [main] [recommendation_server.py:47] [trace_id=28794c25e6fda70c0b2fa29c2015df9b span_id=61b25fa0f974fc21 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['0PUK6V6EV0', '66VCHSJNUP', '2ZYFJ3GM2N', 'OLJCESPC7Z', 'HQTGWGPNH4']
2026-09-28T11:42:14+00:00  2026-09-28 11:42:14,102 INFO [main] [recommendation_server.py:47] [trace_id=fd2deb310633bbad68592ee4a8985751 span_id=a88a6a5c3fa99ae5 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['1YMWWN1N4O', '9SIQT8TOJO', 'OLJCESPC7Z', 'L9ECAV7KIM', '0PUK6V6EV0']
2026-09-28T11:42:15+00:00  2026-09-28 11:42:15,432 INFO [main] [recommendation_server.py:47] [trace_id=ca130b9b0842f62ad406256cc0e2e396 span_id=c7c055921e7ddf17 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['HQTGWGPNH4', '66VCHSJNUP', '0PUK6V6EV0', '6E92ZMYYFZ', 'OLJCESPC7Z']
2026-09-28T11:42:21+00:00  2026-09-28 11:42:21,892 INFO [main] [recommendation_server.py:47] [trace_id=d95a1374a14205b8157f222254bd323a span_id=dda80adc3f05ca25 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['L9ECAV7KIM', '6E92ZMYYFZ', '1YMWWN1N4O', 'OLJCESPC7Z', '0PUK6V6EV0']
2026-09-28T11:42:22+00:00  2026-09-28 11:42:22,906 INFO [main] [recommendation_server.py:47] [trace_id=0d3b34d1f7fe44f3b6b401b56e394594 span_id=1db9914689a298d6 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['OLJCESPC7Z', 'L9ECAV7KIM', '6E92ZMYYFZ', '66VCHSJNUP', 'HQTGWGPNH4']
```

_189 further lines are in the bundle._

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

The page came 6m46s after the first request hung, and it was thin: `ServiceHighLatency` on
**frontend-proxy** and on **load-generator**, nothing else. Neither is a service anyone would fix;
both were reporting what they received from below them. A minute later `ServiceNoTraffic` on
**recommendation**. Three alerts on three services by the fix; four more in the minutes after
it, on the **frontend** and on recommendation, error rate and then latency; the world all clear
6m01s after the fix.

The storefront was mostly fine. Product pages, carts and checkouts served at their usual speed
and 75 orders completed while the fault held. The frontend recorded no errors and no change in
latency for the length of the fault, a p95 of 45 to 71ms, its request rate easing from 12.2 a
second to about 8.0 as some users waited. At the edge, the proxy's and the load generator's 95th
percentiles went to the histogram's ceiling, **15000ms**, from T+3 and stayed there, while their
error ratios climbed only to 4.2% and 4.5% and never reached their 5% line. Something was
hanging a small share of requests to the fifteen-second route timeout: enough to hold a 95th
percentile, not enough to hold an error rate.

Recommendation's request rate went from 0.7 a second to nothing by T+4, and from then until the
fix it had no error ratio and no latency value at all: no samples, not zero errors. The catalog's
rate halved with it, from 5.2 requests a second to about 2.3, with no errors and no change in
latency: something that used to call it had stopped calling.

### What was checked

**The proxy and the load generator, because they paged.** Their error traces - 121 in twelve
minutes, none under fourteen seconds - were all one thing: `user_get_recommendations`, a GET of
`/api/recommendations`, cut at the proxy's fifteen-second route timeout. Not one product page,
cart view or checkout among them.

**The frontend, from the traces.** Under every timed-out proxy span the frontend's
`GET /api/recommendations` was still open - for 203, 471 and 706 seconds in the three drawn - on
a single call, `grpc.oteldemo.RecommendationService/ListRecommendations`, with nothing beneath
it while the fault held. The frontend recorded no error because it had not finished; it was
waiting, with no deadline of its own, on the one service that lists recommendations.

**The catalog, because its rate had halved.** Nothing was wrong with it: zero errors, its usual
latency, every call that reached it answered. Half of its calls at rest come from
recommendation, which lists the catalog on every request it serves - and recommendation was
serving nothing. The catalog's drop was a shadow of recommendation's silence, not a fault of its
own.

**Recommendation's own view of itself.** Its 20 runtime series - memory, threads, garbage
collection - had stopped at the onset: the last report is the one before it, they held for the
store's lookback and dropped out of queries at T+4, and nothing replaced them until 14 seconds
after the fix. A service that is merely uncalled keeps sending its runtime reports on a timer.
This one had stopped reporting on itself.

**Recommendation's log.** At rest it writes one line per request, about two a minute, `Receive
ListRecommendations`. The last of those came five seconds before the onset, and then no more.
What replaced them was its telemetry SDK, writing at ERROR to the same console: `Failed to
export metrics to otel-collector:4317` 28 seconds in, and then the same line once every seventy
seconds for as long as the fault held - its export interval plus a ten-second timeout - with
`Failed to export traces` twice, when it had a batch of spans to send. Eleven lines, one per
failure, no stack traces; every one of them the fault's, none in the five minutes before it. It
was running. It was trying to send on schedule. Nothing it sent had anywhere to go, and nothing
sent to it arrived.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

### Root cause

The recommendation container was disconnected from the demo network. The process kept running
and its port stayed open, on an address nothing could reach; packets on its established
connections were dropped rather than refused, so its one caller waited on a socket that would
never answer. Only the frontend calls recommendation, once per recommendations request and with
no deadline, so every recommendations request hung until the proxy cut it at fifteen seconds -
about one request in twenty-five on this load, which put the edge's latency over its line and
its error ratio under. Recommendation's own call into the catalog, made on every request, hung
the same way from its side, and the catalog lost half its traffic without losing anything else.
Everything else the storefront does ran as before. Recommendation itself was alive the whole
time and said so in the only place it could still write, its own log: its request lines stopped
and its export failures began within the same half minute. Nothing about it had been changed.

### Resolution

The container was put back on its network under its original names, on the same address. Where
an operator cannot reconnect a container with its aliases, recreating or restarting it does the
same job. Class of fix: **restart**. Nothing was deployed or misconfigured, so there was nothing
to roll back or revert.

The recovery was not clean, and it was not the fault. The requests the frontend had held open
through the cut did not complete when recommendation came back; they failed together, 126
frontend error lines in the minute after the fix, the frontend's error ratio at 17.5% and its
p95 at the ceiling for four minutes as the held spans closed at their minutes-long lengths.
Recommendation's own connections into the catalog, held open through the cut, were reset when
it returned - `Connection reset by peer`, its log carrying the tracebacks - and for the first
thirty seconds its flag lookups into flagd timed out at their 500ms deadline on a connection that
had gone stale, so its error ratio read 35% and its p95 770ms in the minute after the fix,
falling away over four. Four alerts fired only in this window - error rate on the frontend and
recommendation, then latency on both - and cleared as the wave passed. The no-traffic alert
cleared 29 seconds after the fix, the edge's latency alerts 3m29s after, and the world was all
clear 6m01s after the fix. Neither recommendation nor the catalog restarted.

### Detection notes

- Onset to first page: **6m46s**, the edge's 95th percentile holding the ceiling for three
  minutes once enough fifteen-second spans were in its window. Slow, because the hung share was
  small.
- Services on the page: **two**, the culprit not among them. By the fix: **three alerts across
  three services**, the culprit named once, as silence, a minute after the page.
- Alerts that fired only during recovery: **four** - the held requests failing together, on the
  frontend and on recommendation, as errors and then as latency.
- Did the loudest service turn out to be the culprit? **No.** The proxy and the load generator
  paged and stayed loudest; they were reporting what they received.
- Would the page alone have led you to the right service? **Not on its own.** The page named the
  edge; the no-traffic alert a minute later named recommendation, but a service that has gone
  quiet is also what a service nobody is calling looks like. The traces said the calls into
  recommendation never returned; the runtime reports said it had stopped reporting on itself;
  the log said why.
- **A page can be under the error line and over the latency line.** One request in twenty-five
  at fifteen seconds is 3 to 4% of requests - under an error rate, more than enough to hold a
  95th percentile at the ceiling. Read the latency alerts for what they contain.
- **A halved rate on a healthy service points at its caller.** The catalog lost half its traffic
  with no error and no latency of its own; the half it lost was recommendation's. A rate that
  falls without anything else moving is a shadow, and the thing casting it is the one to find.
- **The runtime reports separate stopped from uncalled. The log separates stopped from cut
  off.** A frozen process writes nothing; a crashed one writes a start-up; a cut-off one keeps
  writing that it cannot reach anything, on its export schedule, naming the collector it cannot
  reach.
- **The recovery's errors are the recovery's.** Held requests that fail when the connection
  returns, and stale connections to dependencies that fail until they are remade, put errors and
  latency on the culprit and its caller in the minutes after the fix that neither had during the
  fault. Errors that begin at the fix are not a second fault.

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-recommendation-partition/`](../../evals/scenarios/artifacts/holdout/v2-recommendation-partition/) by `faultline-render`. [All bundles](README.md).
