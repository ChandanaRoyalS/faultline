# Recommendation service memory limit cut below what its interpreter needs to start

## The scenario

| | |
|---|---|
| scenario | `v2-recommendation-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `recommendation` via `v2-recommendation-memory-squeeze` |
| time to page | 5m16s |
| steady state captured | 300s |
| capture window | 2026-09-27T20:50:24+00:00 → 2026-09-27T21:10:40+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+5m16s |
| `t_revert` | T+10m16s |
| all clear | T+13m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+5m15s | `frontend` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+5m15s | `frontend-proxy` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+8m15s | `recommendation` | ServiceNoTraffic | 4.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="recommendation"}` |

`logs/recommendation.txt` — 90 lines.

## A look at the logs

From `logs/recommendation.txt` (---- onset 2026-09-27T20:55:24+00:00 ----):

```
2026-09-27T20:50:26+00:00  2026-09-27 20:50:26,053 INFO [main] [recommendation_server.py:47] [trace_id=dcd08b13ae020251b098c4eae57e9879 span_id=ded666bf36e0137e resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['OLJCESPC7Z', 'LS4PSXUNUM', 'L9ECAV7KIM', '6E92ZMYYFZ', '2ZYFJ3GM2N']
2026-09-27T20:50:33+00:00  2026-09-27 20:50:33,672 INFO [main] [recommendation_server.py:47] [trace_id=1c79b061975d68127905357b083429be span_id=cf7f0a19e99b919a resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['66VCHSJNUP', 'L9ECAV7KIM', 'LS4PSXUNUM', 'HQTGWGPNH4', '9SIQT8TOJO']
2026-09-27T20:50:33+00:00  2026-09-27 20:50:33,758 INFO [main] [recommendation_server.py:47] [trace_id=bf30cc10c838335e6392c5eb8e2bf3f0 span_id=0ddd2bc55a20d0c5 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['1YMWWN1N4O', '6E92ZMYYFZ', '9SIQT8TOJO', 'OLJCESPC7Z', 'LS4PSXUNUM']
2026-09-27T20:50:45+00:00  2026-09-27 20:50:45,621 INFO [main] [recommendation_server.py:47] [trace_id=9f77716b1fc2f48997a5d97f55bfe44c span_id=6ce53a4e42f657ab resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['OLJCESPC7Z', '66VCHSJNUP', '6E92ZMYYFZ', '9SIQT8TOJO', '0PUK6V6EV0']
2026-09-27T20:50:53+00:00  2026-09-27 20:50:53,207 INFO [main] [recommendation_server.py:47] [trace_id=1e96aa84d5328a3206b33a7df507d6b4 span_id=620e261f15ca7d96 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['1YMWWN1N4O', '2ZYFJ3GM2N', 'HQTGWGPNH4', 'LS4PSXUNUM', '6E92ZMYYFZ']
2026-09-27T20:50:54+00:00  2026-09-27 20:50:54,985 INFO [main] [recommendation_server.py:47] [trace_id=03a3626c2d12fcd119745fe050a156cc span_id=fd0579a76fab72ce resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['L9ECAV7KIM', '0PUK6V6EV0', 'LS4PSXUNUM', '66VCHSJNUP', '9SIQT8TOJO']
2026-09-27T20:50:55+00:00  2026-09-27 20:50:55,772 INFO [main] [recommendation_server.py:47] [trace_id=97cbf9606b9f5304ca19bb21fd1bda85 span_id=887c36862dbe3511 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['0PUK6V6EV0', 'OLJCESPC7Z', '9SIQT8TOJO', '6E92ZMYYFZ', '1YMWWN1N4O']
2026-09-27T20:50:57+00:00  2026-09-27 20:50:57,194 INFO [main] [recommendation_server.py:47] [trace_id=bd7c14b59adf8338d8b15991466b2879 span_id=e7842930ff00d0fc resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['LS4PSXUNUM', '9SIQT8TOJO', '2ZYFJ3GM2N', 'OLJCESPC7Z', '0PUK6V6EV0']
2026-09-27T20:50:57+00:00  2026-09-27 20:50:57,660 INFO [main] [recommendation_server.py:47] [trace_id=ce6c8ae5543ffdbcd9473e0d39eafc24 span_id=62562c8e7eb35eeb resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['L9ECAV7KIM', 'OLJCESPC7Z', '66VCHSJNUP', '2ZYFJ3GM2N', '9SIQT8TOJO']
2026-09-27T20:51:04+00:00  2026-09-27 20:51:04,880 INFO [main] [recommendation_server.py:47] [trace_id=fe0e6a6eff3fe56a282d6adb67f5798e span_id=035232ee96bdedf6 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['HQTGWGPNH4', '66VCHSJNUP', '9SIQT8TOJO', 'LS4PSXUNUM', '2ZYFJ3GM2N']
2026-09-27T20:51:10+00:00  2026-09-27 20:51:10,882 INFO [main] [recommendation_server.py:47] [trace_id=cc618e3ece1e4b2344009aa0c9807fd7 span_id=48f480c7b02ad399 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['L9ECAV7KIM', 'OLJCESPC7Z', '0PUK6V6EV0', 'LS4PSXUNUM', '2ZYFJ3GM2N']
2026-09-27T20:51:22+00:00  2026-09-27 20:51:22,780 INFO [main] [recommendation_server.py:47] [trace_id=9fcd2031bba78fd23b5900e169c2d63a span_id=d799ca0cc3c20962 resource.service.name=recommendation trace_sampled=True] - Receive ListRecommendations for product ids:['LS4PSXUNUM', '9SIQT8TOJO', '1YMWWN1N4O', '66VCHSJNUP', 'OLJCESPC7Z']
```

_69 further lines are in the bundle._

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

The page was `ServiceHighErrorRate` on the **frontend** and **frontend-proxy** together, 5m16s
after the trouble started. Three minutes later `ServiceNoTraffic` fired on **recommendation**.
Three alerts on three services; nothing else fired, then or later, and nothing fired after the fix.

The frontend's error ratio had been zero. It was 2% a minute in, 4.9% at two, 6.2% at three, 8.1%
at four, and from then it sat between 5.9 and 9.9% for as long as the trouble lasted, the proxy's
a fraction under it all the way. The load generator's followed at about half - 3 to 5% - and
touched the line for a minute without holding it. Not one latency moved: the frontend's p95 sat at
its usual 42 to 45ms, the proxy's and the load generator's likewise. Checkout placed orders at its
usual rate with no errors at all - 91 completed - and payment, shipping, email and the rest kept
their rates. The catalog's rate fell from about 5 lookups a second to about 3, with no errors and
its p95 easing from 6ms to 3.

What went missing was recommendation. Its span rate had been 0.5 to 0.7 a second. It was 0.43 a
minute in, 0.28 at two, 0.14 at three, 0.01 at four, and nothing from five; from then on its error
ratio and its latency had no value at all. It had recorded no error of its own before its numbers
ran out, and no rise in latency.

### What was checked

**The frontend's error traces, the service on the page.** 129 of them across the ten minutes, and
every one is the same request: a `user_get_recommendations` page load ending at
`grpc.oteldemo.RecommendationService/ListRecommendations` with **nothing beneath it** - no
recommendation span, no catalog lookups after it, because the four product lookups a
recommendation strip needs never got their list. Beneath the call, the frontend's own attempts:
`dns.lookup`, then `tcp.connect` refused at recommendation's address, five times in a row, then
`connect EHOSTUNREACH` at the same address, some of those attempts waiting three seconds, one
fourteen, one thirty-eight, and once `getaddrinfo ENOTFOUND recommendation`. The request itself
failed in about 20ms; the long waits are the client's connection attempts continuing in the
background, and they say what the address was doing: refusing, then unreachable, then not
resolving at all - a container that is there and not listening, then gone, then back and gone
again. Every recommendation request in the incident failed. Every other request kind succeeded:
checkout has no error trace, and the catalog's error ratio stayed at zero.

**Whether recommendation was idle or gone.** Gone. Its 20 runtime series - interpreter memory,
CPU, threads, garbage collection - held their last values for the store's lookback and then had
no value from about T+5 until after the fix. A process that is merely idle keeps exporting them.
Nothing called on it was answered, nothing it owns was reported, and the frontend's connection
attempts found nothing listening at its address for ten minutes.

**Recommendation's log, which says nothing at all.** Its last line came 0.6 seconds before the
trouble began - an ordinary `Receive ListRecommendations` - and then **nothing**: no error, no
traceback, no shutdown line, not even a start-up banner, for eleven minutes. The next line is the
one a fresh process writes when it is up - `Recommendation service started, listening on port
9001` - 48 seconds after the fix, followed by ordinary requests. A process that is killed writes
nothing, and a process that is killed before it finishes starting never gets as far as its first
line; a log that simply stops and resumes with a start-up line is the signature of a process that
was killed, and killed again, and only once allowed to start.

**What changed.** No deploy, no image change - the same `2.2.0-recommendation` before and after -
no environment change, no flag. One record, at onset, under recommendation's name: `memory limit
lowered on recommendation`, to `memory=16m`, from 500M. Recommendation had been using 46MB at rest,
and an interpreter of its kind needs more than 16MB simply to finish loading. The record names a
ceiling below what the process needs to exist, and the log names the second it stopped.

**What it was not.** A wrong image - that shows another program's output in the log and an image
in the record, and here the log is empty and the record is a limit. A slow catalog behind it -
that shows latency on recommendation with recommendation present, and here nothing is slow and
recommendation is absent. A flag - that leaves no record and a process that stays up and keeps
exporting. A starved process that still fits - that shows a slow service, restarts announcing
themselves in the log, and latency on the target; here there is no latency anywhere and the log
has no start-up line until the fix, because no process ever got that far.

### Root cause

The recommendation service container's memory limit was lowered from 500M to 16m, below what its
Python interpreter needs to finish starting. The kernel killed the running process at once and
killed every replacement before it could listen, so the service was never available for the whole
incident: the storefront's recommendation requests all failed, the frontend and its proxy paged on
the errors, and recommendation itself went silent - no spans, no series, no log, because nothing
survived long enough to write. Nothing about its image, code or configuration changed; restoring
the limit fixed it.

### Resolution

The memory limit was restored to 500M. The restart policy had backed off to about a minute between
attempts by then, so the next start came 47 seconds after the fix, and that one finished: the
start-up line at 48 seconds, the first recommendation served nine seconds after that, and its
rate climbing back through its window from then on. `ServiceNoTraffic` cleared 1m44s after the
fix and the two error-rate alerts 2m44s after it, as their windows drained; the world was all
clear 3m00s after the fix, and nothing fired during recovery.

Class of fix: **config_revert**. The container's resource limit was wrong and it was set back.
Restarting recommendation was what the runtime had been doing, nineteen times, and none of those
starts could finish under the limit; rolling back its image would have changed nothing, because
the image was never the problem.

### Detection notes

- Onset to first page: **5m16s**, the frontend's five-minute error ratio crossing 5% and holding
  for the rule's two minutes. Services on the page: **2**, frontend and frontend-proxy, neither the
  culprit. By the fix: **3**, the culprit last.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The frontend and its proxy paged
  first and longest, and the frontend's own error traces name recommendation in their first line.
- Would the page alone have led you to the right service? **Not on its own.** The page names the
  callers; the callers' traces name the leaf; the leaf's silence names the class.
- **A leaf that fails fast pages its callers on errors, not latency.** Every recommendation
  request failed in about 20ms, so the frontend's error ratio climbed and its p95 never moved. The
  same absence on a caller that waits would have paged on latency instead.
- **The page arrives when the arithmetic says.** A recommendation request errors four frontend
  spans and two proxy spans; at the frontend's request mix that is 6 to 10% of its spans, over a
  5% line, and the load generator's one span per request stayed under it. The page is a function
  of the callers' span counts, not of how broken the leaf is.
- **An empty log is not a healthy service.** No error, no traceback, no banner: the process never
  got far enough to write one. Read the stop off the last ordinary line and the death off the
  series; the cause is in the change record.
- **The frontend's connection attempts tell the container's story.** Refused, unreachable, not
  resolving: there and not listening, gone, and back and gone again - a restart loop seen from
  the outside, without the container being visible at all.
- **Recovery waits on the restart policy's backoff.** The limit was restored at once; the next
  start took 47 seconds to come, because the runtime had backed off to a minute after nineteen
  kills. A fix to a crash-looping service takes effect on the next attempt, not immediately.

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-recommendation-memory-squeeze/`](../../evals/scenarios/artifacts/holdout/v2-recommendation-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
