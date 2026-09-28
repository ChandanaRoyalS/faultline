# The ad service is cut from the network - its process runs and reaches nothing

## The scenario

| | |
|---|---|
| scenario | `v2-ad-partition` |
| fault class | **`network_partition`** |
| expected remediation | `restart` |
| split | `dev` |
| injected at | `ad` via `v2-ad-partition` |
| time to page | 7m01s |
| steady state captured | 300s |
| capture window | 2026-09-28T08:33:09+00:00 → 2026-09-28T08:55:10+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+7m01s |
| `t_revert` | T+12m01s |
| all clear | T+15m01s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+7m00s | `frontend-proxy` | ServiceHighLatency | 8.0 min | **paged** |
| T+7m00s | `load-generator` | ServiceHighLatency | 8.0 min | **paged** |
| T+8m00s | `ad` | ServiceNoTraffic | 5.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="ad"}` |

`logs/ad.txt` — 509 lines.

## A look at the logs

From `logs/ad.txt` (---- onset 2026-09-28T08:38:09+00:00 ----):

```
2026-09-28T08:33:25+00:00  2026-09-28 08:33:25 - oteldemo.AdService - no baggage found in context trace_id=2f7e0919e6d6c40f6d3d62514ce50eb8 span_id=93d60079c9ca8200 trace_flags=01
2026-09-28T08:33:25+00:00  2026-09-28 08:33:25 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=2f7e0919e6d6c40f6d3d62514ce50eb8 span_id=93d60079c9ca8200 trace_flags=01
2026-09-28T08:33:28+00:00  2026-09-28 08:33:28 - oteldemo.AdService - no baggage found in context trace_id=7912bf46ab8b6956a52bde67884ed34b span_id=881a0a475592a597 trace_flags=01
2026-09-28T08:33:28+00:00  2026-09-28 08:33:28 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=7912bf46ab8b6956a52bde67884ed34b span_id=881a0a475592a597 trace_flags=01
2026-09-28T08:33:35+00:00  2026-09-28 08:33:35 - oteldemo.AdService - no baggage found in context trace_id=bd8d9208e1c33079f28569e6d032455c span_id=ba4435289819bbae trace_flags=01
2026-09-28T08:33:35+00:00  2026-09-28 08:33:35 - oteldemo.AdService - Targeted ad request received for [books] trace_id=bd8d9208e1c33079f28569e6d032455c span_id=ba4435289819bbae trace_flags=01
2026-09-28T08:33:56+00:00  2026-09-28 08:33:56 - oteldemo.AdService - no baggage found in context trace_id=de61b1330098f58f3305ea8009b7569d span_id=6a4e744a953af16a trace_flags=01
2026-09-28T08:33:56+00:00  2026-09-28 08:33:56 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=de61b1330098f58f3305ea8009b7569d span_id=6a4e744a953af16a trace_flags=01
2026-09-28T08:34:01+00:00  2026-09-28 08:34:01 - oteldemo.AdService - no baggage found in context trace_id=c3c4422883d73aca1cae6d33bed6df1e span_id=1c5ad4fa84949817 trace_flags=01
2026-09-28T08:34:01+00:00  2026-09-28 08:34:01 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=c3c4422883d73aca1cae6d33bed6df1e span_id=1c5ad4fa84949817 trace_flags=01
2026-09-28T08:34:10+00:00  2026-09-28 08:34:10 - oteldemo.AdService - no baggage found in context trace_id=e926f223ca580f7f165dbf4e6c8b9157 span_id=b0fa7ce0bc926926 trace_flags=01
2026-09-28T08:34:10+00:00  2026-09-28 08:34:10 - oteldemo.AdService - Targeted ad request received for [books] trace_id=e926f223ca580f7f165dbf4e6c8b9157 span_id=b0fa7ce0bc926926 trace_flags=01
```

_488 further lines are in the bundle._

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

The page came 7m01s after the first request hung, and it was thin: `ServiceHighLatency` on
**frontend-proxy** and on **load-generator**, nothing else. Neither is a service anyone would fix;
both were reporting what they received from below them. A minute later `ServiceNoTraffic` on
**ad**. Three alerts on three services by the fix, nothing after it, and the world all clear
3m00s after the fix.

The storefront was almost entirely fine. Product pages, carts, recommendations and checkouts all
served at their usual speed; 82 orders completed while the fault held. The frontend recorded no
errors and no change in latency, a p95 of 42 to 49ms throughout, its request rate easing from
11.6 a second to about 8.2 as some users waited. What had changed was at the edge: the proxy's
and the load generator's 95th percentiles went to the histogram's ceiling, **15000ms**, from T+4
and stayed there, while their error ratios climbed only to 4.5% and 5.1% - the load generator's
touched its 5% line for one minute and fell back, the proxy's never reached it. Something was
hanging a small share of requests to the fifteen-second route timeout: enough to hold a 95th
percentile, not enough to hold an error rate.

Ad's request rate went from 0.4 a second to nothing by T+4, and from T+5 until the fix it had no
error ratio and no latency value at all: no samples, not zero errors. Nothing else went quiet.

### What was checked

**The proxy and the load generator, because they paged.** Their error traces - 125 in twelve
minutes, none under fourteen seconds - were all one thing: `user_get_ads`, a GET of `/api/data`,
cut at the proxy's fifteen-second route timeout. Not one product page, cart view or checkout
among them. Each carried two ingress spans, a two-millisecond one and the fifteen-second one: the
load generator asks for `/api/data/` with a trailing slash, the frontend answers a redirect at
once, and the second request is the one that hangs.

**The frontend, from the traces.** Under every timed-out proxy span the frontend's `GET /api/data`
was still open - for 300, 537 and 745 seconds in the three drawn - on a single call,
`grpc.oteldemo.AdService/GetAds`, with nothing beneath it while the fault held. The frontend
recorded no error because it had not finished; it was waiting, with no deadline of its own, on
the one service that serves ads.

**Ad's own view of itself.** Its 51 runtime series - JVM threads, classes, memory pools, garbage
collection - had stopped at the onset: the last report is the one before it, they held for the
store's lookback and dropped out of queries at T+4, and nothing replaced them until 29 seconds
after the fix. A service that is merely uncalled keeps sending its runtime reports on a timer.
This one had stopped reporting on itself.

**Ad's log.** At rest ad writes about ten lines a minute, one or two per request: `Targeted ad
request received for [...]`, `no baggage found in context`. Those stopped two seconds before the
onset. What replaced them was the agent that ships its telemetry, writing at ERROR to the same
console: `Failed to export spans. The request could not be executed` twelve seconds in, `Failed
to export metrics` at 38 seconds, each on a request that timed out; then `Failed to export
metrics` once a minute, at 45 seconds past every minute, for as long as the fault held, and the
cause had changed: `UnknownHostException: otel-collector`. The process could no longer even
resolve the name of the collector it had been sending to a minute earlier. It was running, it was
trying to send on schedule, and nothing it sent had anywhere to go. Fourteen failures, thirty
lines of the agent's own, every one of them the fault's; none in the five minutes before it.

**The rest of the world, because nothing else was on the page.** Checkout, cart, the catalog,
recommendation, currency, shipping, payment, email, accounting: rates within their usual range,
error ratios zero, latencies unmoved. Orders were completing. Flagd, which ad talks to for its
feature flags, was fine too - ad was not reaching anything, but nothing else needed ad.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

### Root cause

The ad container was disconnected from the demo network. The process kept running and its port
stayed open, on an address nothing could reach; packets on its established connections were
dropped rather than refused, so its one caller waited on a socket that would never answer. Only
the frontend calls ad, once per ads request and with no deadline, so every ads request hung
until the proxy cut it at fifteen seconds - about one request in twenty on this load, which put
the edge's latency over its line and its error ratio just under. Everything else the storefront
does ran as before. Ad itself was alive the whole time and said so in the only place it could
still write, its own log: its request lines stopped and its export failures began at the same
moment. Nothing about it had been changed.

### Resolution

The container was put back on its network under its original names, on the same address. Where
an operator cannot reconnect a container with its aliases, recreating or restarting it does the
same job. Class of fix: **restart**. Nothing was deployed or misconfigured, so there was nothing
to roll back or revert.

The recovery was clean. The connections the frontend had held open through the cut resumed
rather than reset: every held ads call was answered when ad came back, in 11 to 15 milliseconds
after up to twelve minutes of waiting, and not one of them failed. Ad's request rate ran at three
times its usual for four minutes on the backlog, its p95 at 48ms against its usual 8 to 12, with
no errors. The no-traffic alert cleared 2m35s after the fix and the two latency alerts 4m35s
after, as the fifteen-second spans aged out of their windows; the world was all clear 3m00s
after the fix, and no alert fired only in recovery. The frontend's 95th percentile did read the
ceiling from T+13 as the held calls closed at their minutes-long lengths; whether a latency rule
held on it is not recorded, because the record ends two minutes after the all-clear.

### Detection notes

- Onset to first page: **7m01s**, the edge's 95th percentile holding the ceiling for three
  minutes once enough fifteen-second spans were in its window. Slow, because the hung share was
  small.
- Services on the page: **two**, the culprit not among them. By the fix: **three alerts across
  three services**, the culprit named once, as silence, a minute after the page.
- Alerts that fired only during recovery: **none.**
- Did the loudest service turn out to be the culprit? **No.** The proxy and the load generator
  paged and stayed loudest; they were reporting what they received.
- Would the page alone have led you to the right service? **Not on its own.** The page named the
  edge; the no-traffic alert a minute later named ad, but a service that has gone quiet is also
  what a service nobody is calling looks like. The traces said the calls into ad never returned;
  the runtime reports said it had stopped reporting on itself; the log said why.
- **A page can be under the error line and over the latency line.** One request in twenty at
  fifteen seconds is 4 to 5% of requests - not enough to hold an error rate, more than enough to
  hold a 95th percentile at the ceiling. Read the latency alerts for what they contain, not just
  that they fired.
- **The runtime reports separate stopped from uncalled. The log separates stopped from cut off.**
  A frozen process writes nothing; a crashed one writes a start-up; a cut-off one keeps writing
  that it cannot reach anything, on its export schedule. When the culprit's own request lines
  stop and its export failures start in the same second, that is the fault's signature.
- **The name that stops resolving is a clue in itself.** `UnknownHostException` for a host the
  same process reached a minute earlier is not a DNS incident; it is a process that is no longer
  on the network where that name lives.
- **Not every cut-off service resets its callers when it returns.** This one answered every held
  call, so the recovery left no errors at all. A clean recovery does not rule the fault out.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-ad-partition/`](../../evals/scenarios/artifacts/dev/v2-ad-partition/) by `faultline-render`. [All bundles](README.md).
