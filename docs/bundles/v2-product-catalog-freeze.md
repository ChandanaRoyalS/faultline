# The product catalog process is frozen - its socket accepts and nothing answers

## The scenario

| | |
|---|---|
| scenario | `v2-product-catalog-freeze` |
| fault class | **`process_freeze`** |
| expected remediation | `restart` |
| split | `dev` |
| injected at | `product-catalog` via `v2-product-catalog-freeze` |
| time to page | 4m46s |
| steady state captured | 300s |
| capture window | 2026-09-24T16:48:28+00:00 → 2026-09-24T17:10:30+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m46s |
| `t_revert` | T+9m46s |
| all clear | T+15m02s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m30s | `frontend-proxy` | ServiceHighErrorRate | 8.2 min | **paged** |
| T+4m30s | `load-generator` | ServiceHighErrorRate | 8.2 min | **paged** |
| T+5m00s | `frontend-proxy` | ServiceHighLatency | 8.8 min | joined later |
| T+5m00s | `load-generator` | ServiceHighLatency | 8.8 min | joined later |
| T+5m45s | `frontend` | ServiceHighLatency | 9.2 min | joined later |
| T+8m00s | `accounting` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m00s | `currency` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m00s | `email` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m00s | `fraud-detection` | ServiceHighErrorRate | 1.8 min | joined later |
| T+8m00s | `payment` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m00s | `product-catalog` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m00s | `quote` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m00s | `shipping` | ServiceNoTraffic | 2.8 min | joined later |
| T+8m45s | `flagd` | ServiceHighLatency | 2.0 min | joined later |
| T+8m45s | `fraud-detection` | ServiceHighLatency | 1.0 min | joined later |
| T+9m00s | `recommendation` | ServiceHighErrorRate | 1.8 min | joined later |
| T+10m00s | `recommendation` | ServiceHighLatency | 5.0 min | began after the revert |
| T+13m45s | `checkout` | ServiceHighLatency | 1.2 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="product-catalog"}` |

`logs/product-catalog.txt` — 7 lines.

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

The page was two error alerts, **frontend-proxy** and **load-generator**, 4m46s after
requests started hanging. Their latency alerts followed within half a minute. Neither is a
service anyone would fix: one is the edge proxy and the other is the synthetic client. Both
were reporting what they received from below them.

About a minute after the page, **frontend** alerted on latency. Its p95 had been at the
histogram's ceiling, **15000ms**, since about two minutes *before* the page. That was the
earliest sign of anything. Frontend recorded **no errors at all**. Its error-ratio query
returned no series, not a zero, because not one of its spans ended in error. Its request
rate fell from about 10.8 to 2.1 req/s. Requests were not failing at frontend. They were
not finishing. The proxy's errors, steady at about 28%, were its own upstream timeouts at
exactly fifteen seconds.

About three minutes after the page the alert set changed shape. **ServiceNoTraffic** fired at
once on seven services: **product-catalog**, accounting, currency, email, payment, quote and
shipping. Short error and latency alerts on recommendation, fraud-detection and flagd came
in over the next minute. By the time the fix went in there were sixteen alerts across
thirteen services, eight times the size of the page. Most of the new names were services
with nothing wrong except that nobody was calling them.

### What was checked

**The proxy, because it was loudest.** Its errors were all the same kind: upstream requests
cut at the fifteen-second route timeout. The proxy was doing its job. Nothing in its own
behaviour had changed, so it was reporting the problem, not causing it.

**Frontend, because its latency was the first thing to move.** It looked like a slow
frontend, and it was not one. The error traces showed the proxy giving up at 15 s. Below the
proxy, frontend's own request did not end when the proxy gave up. Its call into the catalog,
`grpc.oteldemo.ProductCatalogService/GetProduct`, stayed open for up to **531.8 seconds**
across the window's error traces, almost nine minutes, and closed only when the fix went in. The trace tool named
that call as the degrading hop, *still waiting 516.8 s after frontend-proxy/ingress gave up*.
In three of the ten frontend traces it named frontend's call into recommendation instead,
which was waiting on the catalog in turn. Frontend was not doing work in that time. Every
trace put the time in a call frontend had made and was still waiting on.

**The seven silent services, as a group.** Seven services going quiet in the same minute
looks like seven failures, and chasing them one by one would have cost the rest of the
incident. They sit behind the catalog. Accounting, currency, email, payment, quote and
shipping are only called once a request has got past it: a priced product page, a shipping
quote, a completed order. Nothing was getting past it, so their silence was a consequence. The catalog was on the list too, and on the alert
list it looked like just another starved service.

**The catalog's own view of itself.** This is where it opened up. Its request rate had gone
to zero right at the page, and from then on its latency and error ratio had *no value*. No
errors, no slow requests, no samples. Its own runtime series (Go memory, goroutines, GC)
told the difference. The last report landed less than half a minute before the trouble
started. The allocation counter, which moves every minute on a live Go process under load,
stopped. The series dropped out of queries entirely about fifteen seconds before the page. A
service that is merely uncalled keeps sending its runtime reports on a timer. This one had
stopped reporting on itself altogether. Callers were hanging on it, and it was not saying
anything about itself either.

**The catalog's logs.** Nothing at all for the whole window, and nothing in the healthy five
minutes before it either. The catalog is quiet when healthy, so silence alone proves
nothing. What mattered was which lines were *missing*. A catalog cut off from the network
keeps running and logs its failed telemetry exports once a minute. This one logged nothing,
so it was not running.

**Its traces.** None of the catalog's spans in the window were errors. The only catalog spans
at all were requests it served *after* the fix, in about a tenth of a second each (115 and
118 ms in the two traces drawn in full). They sat under frontend calls that had been open for
five and eight minutes, so each had waited in the catalog's backlog the whole time. A running catalog under this much hung traffic would have failed some of it
while it happened and said so in a span.

**What changed.** Nothing. No deploy, no image, no configuration, no flag on any service
involved.

### Root cause

The product-catalog process was suspended. The container existed and kept its port. The
kernel went on accepting connections into its backlog. But nothing in the process ran, so
no request was ever read or answered. Every caller waited until its own deadline. The
browse path hung behind it, checkout stopped completing orders, and everything downstream
of an order went quiet. The catalog neither errored nor logged, because it was not running
at all. Nothing about it had been changed.

### Resolution

The catalog process was resumed. Its runtime reports came back within fifteen seconds and
its request rate within a minute. Where
an operator cannot resume a suspended process, restarting the container does the same job.
Class of fix: **restart**. Nothing was deployed or misconfigured, so there was nothing to
roll back or revert.

Recovery had its own short wave, and it belongs to the fix, not the fault. Every request
that had been hanging woke up at once. Recommendation's latency alert fired seconds after
the resume. Its p95 had been at the ceiling through the hang, and the alert had been building
the whole time. Checkout's p95 hit the
ceiling within a minute, as its hung calls all completed together at the fifteen-second
mark. Its alert fired about four minutes after the resume, once that had lasted. The
catalog's p95 reached 170ms while it worked through the backlog, against a normal 4ms.
Everything was quiet 5m16s after the resume.

### Detection notes

- Onset to first page: **4m46s**. Frontend's latency was at the ceiling about two minutes
  before that. Frontend's own alert came a minute after the page.
- Services on the page: **two** (two alerts), neither of them one you would fix. By the fix:
  **sixteen alerts across thirteen services**.
- Alerts that fired only during recovery: **two**, recommendation and checkout latency, as the
  hung calls woke.
- Did the loudest service turn out to be the culprit? **No.** The proxy was loudest and was
  reporting timeouts, not causing them. The culprit's own alert, ServiceNoTraffic, came about
  three minutes after the page, in the same minute as six services that had nothing wrong
  with them.
- Would the page alone have led you to the right service? **No.** It names the edge. The
  path to the catalog runs through frontend's traces, which name the catalog as the call
  frontend was still waiting on minutes after the proxy gave up.
- **Absence was the evidence, three times over.** No errors on frontend, no values on the
  catalog, and no runtime reports from it. Every one of those answers is a query returning
  nothing. Reading "no series matched" as "nothing wrong here" is the most expensive mistake
  available in this incident.
- **The runtime reports separate stopped from uncalled. The logs separate stopped from cut
  off.** A catalog that is merely idle keeps reporting its runtime. A catalog cut off from
  the network stops reporting too, but it logs its failed exports every minute. Only a
  process that has stopped running does neither.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-product-catalog-freeze/`](../../evals/scenarios/artifacts/dev/v2-product-catalog-freeze/) by `faultline-render`. [All bundles](README.md).
