# The product catalog process is frozen - its socket accepts and nothing answers

## The scenario

| | |
|---|---|
| scenario | `v2-product-catalog-freeze` |
| fault class | **`process_freeze`** |
| expected remediation | `restart` |
| split | `dev` |
| injected at | `product-catalog` via `v2-product-catalog-freeze` |
| time to page | 4m15s |
| steady state captured | 300s |
| capture window | 2026-09-27T02:10:42+00:00 → 2026-09-27T02:31:58+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m15s |
| `t_revert` | T+9m15s |
| all clear | T+14m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m00s | `frontend-proxy` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+4m00s | `load-generator` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+5m00s | `fraud-detection` | ServiceHighErrorRate | 2.0 min | joined later |
| T+5m00s | `frontend-proxy` | ServiceHighLatency | 8.0 min | joined later |
| T+5m00s | `load-generator` | ServiceHighLatency | 8.0 min | joined later |
| T+6m00s | `flagd` | ServiceHighLatency | 1.0 min | joined later |
| T+6m00s | `fraud-detection` | ServiceHighLatency | 1.0 min | joined later |
| T+6m00s | `frontend` | ServiceHighLatency | 8.0 min | joined later |
| T+6m00s | `recommendation` | ServiceHighErrorRate | 1.0 min | joined later |
| T+8m00s | `accounting` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `currency` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `email` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `payment` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `product-catalog` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `quote` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `shipping` | ServiceNoTraffic | 2.0 min | joined later |
| T+12m00s | `frontend` | ServiceHighErrorRate | 2.0 min | began after the revert |
| T+13m00s | `checkout` | ServiceHighLatency | 1.0 min | began after the revert |
| T+13m00s | `product-catalog` | ServiceHighLatency | 1.0 min | began after the revert |
| T+13m00s | `recommendation` | ServiceHighLatency | 1.0 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="product-catalog"}` |

`logs/product-catalog.txt` — 9 lines.

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

The page came 4m15s after requests started hanging: two alerts at once, error rate on
**frontend-proxy** and on **load-generator**. Neither is a service anyone would fix. One is the
edge proxy and the other is the synthetic client, and both were reporting what they received
from below them. Latency alerts on the same two followed 45 seconds later.

The earliest sign was the proxy's own p95, at the histogram's ceiling, **15000ms**, from about
two minutes after onset, more than two minutes before the page. **Frontend**'s p95 reached the
ceiling a minute after the proxy's, and its latency alert came under two minutes after the page.
Frontend recorded **no errors at all**: its error ratio read zero through the whole fault,
because not one of its spans ended in error. Its request rate fell from about 12.0 to 2.1 req/s.
Requests were not failing at frontend. They were not finishing. The proxy's errors, steady at
25-29% once they peaked (the load generator's at 29-31%), were its own upstream timeouts.

In the minutes after the page, alerts appeared on services that are nowhere near the browse
path. **fraud-detection** alerted on error rate 45 seconds after the page and on latency a
minute later, together with **flagd** on latency and **recommendation** on error rate. Just
under four minutes after the page, **ServiceNoTraffic** fired at once on seven services:
**product-catalog**, accounting, currency, email, payment, quote and shipping. By the time the
fix went in, 1m15s later, there were sixteen alerts across thirteen services. Most of the new
names were services with nothing wrong except that nobody was calling them.

### What was checked

**The proxy, because it was loudest.** Its errors were all the same kind: upstream requests
cut at the fifteen-second route timeout. The proxy was doing its job. Nothing in its own
behaviour had changed, so it was reporting the problem, not causing it.

**Frontend, because its latency was the next thing to move.** It looked like a slow frontend,
and it was not one. The error traces showed the proxy giving up at 15 s, and below it frontend's
request still open. All six frontend error traces drawn in full named the same degrading hop:
frontend's product route calling into the catalog,
`grpc.oteldemo.ProductCatalogService/GetProduct`, which stayed open long after the proxy had
given up. The checkout traces said the same thing from the order path. All five drawn named
checkout's call into the catalog while it prepared the order's items. Frontend was not doing
work in that time. Every trace put the time in a call that was waiting on the catalog.

**fraud-detection and flagd, because they alerted first after the page.** A dead end. Their
error traces were fraud-detection's `flagd.evaluation.v1.Service/EventStream` stream to flagd,
closed by flagd with `stream closed due to server-side timeout`, a routine reconnect every ten
minutes, and flagd's own EventStream spans are ten minutes long. No order was involved: with
orders stopped, those few long stream spans were almost everything the two services reported,
so the ratios crossed the lines. Recommendation's error alert rested on the same kind of
thinness: a single request in five minutes, one that ended in error at the latency ceiling, just
before its traffic went to nothing. Recommendation asks the catalog for its product list, which
fits, but I did not draw that trace. None of it was a second fault.

**The seven silent services, as a group.** Seven services going quiet in the same minute looks
like seven failures, and chasing them one by one would have cost the rest of the incident. They
sit behind the catalog. Accounting, currency, email, payment, quote and shipping are only called
once a request has got past it: a priced product page, a shipping quote, a completed order.
Nothing was getting past the catalog, so their silence was a consequence. The catalog was on the
list too, and on the alert list it looked like just another starved service.

**The catalog's own view of itself.** This is where it opened up. Its request rate had gone to
zero within a minute of the page, and from then on its latency and error ratio had *no value*.
No errors, no slow requests, no samples. Its own runtime series (Go memory, goroutines, GC)
told the difference. Its last report landed half a minute before the trouble started. The
allocation counter, which moves every minute on a live Go process under load, stopped. The
series dropped out of queries entirely at the page. A service that is merely uncalled keeps
sending its runtime reports on a timer. This one had stopped reporting on itself altogether.

**The catalog's logs.** Nothing at all for the whole window, and nothing in the healthy five
minutes before it either. The catalog is quiet when healthy, so silence alone proves nothing.
What mattered was which lines were *missing*. A catalog cut off from the network keeps running
and logs its failed telemetry exports once a minute. This one logged nothing, so it was not
running.

**Its traces.** The catalog had no spans of its own while requests hung on it. Its only spans
in the window are requests it served *after* the fix, under calls that had been open for
minutes. Some of those late answers were errors, `Product Not Found`, for products that exist.
That belongs to the recovery, below, not to the hang.

**What changed.** Nothing. No deploy, no image, no configuration, no flag on any service
involved.

### Root cause

The product-catalog process was suspended. The container existed and kept its port. The
kernel went on accepting connections into its backlog. But nothing in the process ran, so no
request was ever read or answered. Every caller waited until its own deadline. The browse
path hung behind it, checkout stopped completing orders, and everything downstream of an order
went quiet. The catalog neither errored nor logged, because it was not running at all. Nothing
about it had been changed.

### Resolution

The catalog process was resumed. Its runtime reports came back within fifteen seconds and its
request rate within a minute. Where an operator cannot resume a suspended process, restarting
the container does the same job. Class of fix: **restart**. Nothing was deployed or
misconfigured, so there was nothing to roll back or revert.

Recovery had its own wave, and it belongs to the fix, not the fault. Every request that had been
hanging woke up at once. The catalog answered some of them `Product Not Found`, and checkout's
orders failed with `failed to prepare order: failed to get product`. Frontend wrote 77 error
lines, all in the minute of the resume, and none after it. The five-minute rate windows carried
that minute: frontend's error ratio read 11% right after the resume, the catalog's 6%, and
frontend alerted on error rate 2m45s after the resume. Latency alerts on checkout, the catalog
and recommendation followed a minute later, as the requests that had waited for minutes closed.
The catalog's p95 reached about 390ms while it worked through the backlog, against a normal
6ms. Everything was quiet 5m01s after the resume.

### Detection notes

- Onset to first page: **4m15s**. The proxy's latency was at the ceiling more than two minutes
  before that, frontend's a minute later, and frontend's own alert came under two minutes after
  the page.
- Services on the page: **two** (two alerts), neither of them one you would fix. By the fix:
  **sixteen alerts across thirteen services**.
- Alerts that fired only during recovery: **four**, the errors and latency of the backlog waking
  at once.
- Did the loudest service turn out to be the culprit? **No.** The proxy was loudest and was
  reporting timeouts, not causing them. The culprit's own alert, ServiceNoTraffic, came just
  under four minutes after the page, in the same minute as six services that had nothing wrong
  with them.
- **Two services alerted that had nothing to do with it.** fraud-detection and flagd crossed
  their lines on a routine stream timeout once orders stopped. They were the first new names
  after the page and the wrong ones to chase.
- Would the page alone have led you to the right service? **No.** It names the edge. The path
  to the catalog runs through frontend's traces, which name the catalog as the call frontend
  was still waiting on after the proxy gave up.
- **Absence was the evidence, three times over.** No errors on frontend, no values on the
  catalog, and no runtime reports from it. Every one of those answers is a query returning
  nothing or zero. Reading "nothing here" as "nothing wrong here" is the most expensive
  mistake available in this incident.
- **The runtime reports separate stopped from uncalled. The logs separate stopped from cut
  off.** A catalog that is merely idle keeps reporting its runtime. A catalog cut off from the
  network stops reporting too, but it logs its failed exports every minute. Only a process that
  has stopped running does neither.
- **The recovery's errors are not the fault's.** The `Product Not Found` burst came as the whole
  backlog woke at once. It is loud, it names the right service, and it describes the wrong
  mechanism.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-product-catalog-freeze/`](../../evals/scenarios/artifacts/dev/v2-product-catalog-freeze/) by `faultline-render`. [All bundles](README.md).
