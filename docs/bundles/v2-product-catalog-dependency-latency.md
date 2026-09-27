# The product catalog's network path acquires 300ms of delay, and every page slows

## The scenario

| | |
|---|---|
| scenario | `v2-product-catalog-dependency-latency` |
| fault class | **`dependency_latency`** |
| expected remediation | `restart` |
| split | `holdout` |
| injected at | `product-catalog` via `v2-product-catalog-dependency-latency` |
| time to page | 3m50s |
| steady state captured | 300s |
| capture window | 2026-09-27T11:54:06+00:00 → 2026-09-27T12:14:58+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m50s |
| `t_revert` | T+8m50s |
| all clear | T+13m52s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `recommendation` | ServiceHighLatency | 10.0 min | **paged** |
| T+4m30s | `checkout` | ServiceHighLatency | 8.0 min | joined later |
| T+4m30s | `frontend` | ServiceHighLatency | 9.0 min | joined later |
| T+4m30s | `frontend-proxy` | ServiceHighLatency | 9.0 min | joined later |
| T+4m30s | `load-generator` | ServiceHighLatency | 9.0 min | joined later |
| T+4m30s | `product-catalog` | ServiceHighLatency | 9.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="product-catalog"}` |

`logs/product-catalog.txt` — 10 lines.

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

The page was one alert, `ServiceHighLatency` on **recommendation**, 3m50s after the trouble
started. A minute later `ServiceHighLatency` fired on five more services at once: **frontend**,
**frontend-proxy**, **load-generator**, **checkout** and **product-catalog**. Six alerts on six
services by the fix, all of them latency, and none after it. Nothing errored: every error ratio
on the world stayed at zero, or at the sliver it always shows, for the whole incident.

The numbers were large. The catalog's p95 had been 5 to 6ms; it was 791ms at two minutes and
about 1.8 seconds from four. Recommendation's went from about 8ms to about 1.7 seconds. The
frontend's went from about 43ms to 1.9 seconds at two minutes and about 4.2 seconds from four,
and frontend-proxy's and the load generator's followed it to about 4.2 and 4.1. Checkout's went
from about 38ms to 860ms at two minutes and between 1.6 and 2.2 seconds from five. It was a step,
not a ramp: the numbers climbed for three minutes only because the windows they are measured
over were filling with slow requests, and then they were flat.

Not everything slowed. Cart, currency, shipping, payment, email and product-reviews kept their
usual milliseconds throughout, and so did ad. Traffic thinned and did not stop: the frontend's
rate from about 12 spans a second to about 10.5, the load generator's from about 5 to 4.4, the
catalog's from about 5.3 to 4.6, as shoppers waited on slow pages; recommendation's and
checkout's eased with them. Every page that showed a product, every recommendation and every
order was slow. Everything else was fine.

### What was checked

**The traces, because six services slowed at once and one of them had to be first.** Every slow
trace touched the product catalog, and inside the catalog the time was in one place. At rest, the
catalog answered a `GetProduct` in 0.8ms and its database answered a `sql.conn.query` in 0.5ms.
Under the fault, in 80 traces drawn, every `sql.conn.query` beneath a `GetProduct` took **600 to
605ms**, and the one beneath a `ListProducts` took 301: the delay, paid twice by the one query
and once by the other. A `GetProduct` was therefore 601ms at the catalog. And each caller's span
was **another 300ms longer** than the catalog's answer beneath it: the frontend's `GetProduct`
call 904ms over the catalog's 602, checkout's 902 over 601, recommendation's `ListProducts` 603
over 301. A product page, one lookup, cost the frontend 905ms. An order, which looks up each of
its items in turn, cost checkout 1.8 seconds for two items and up to 2.7 for more. Everything
else in those traces - the cart, currency, the shipping quote, payment, email - answered in its
usual milliseconds.

**Where the 300ms was.** Not inside the catalog's handler and not inside the database. The
database's work had not changed and the catalog's had not either; what had changed was that
every message *leaving* the catalog took 300ms to arrive: its queries to the database, and its
answers to whoever had called it. A query that is two exchanges paid it twice, a query that is
one paid it once, and every answer paid it again on the way back. That is a delay on the
catalog's network interface, on egress, and nothing else produces that shape.

**Why the recommendations page cost 2.7 seconds, and the catalog's p95 read 1.8.** A
recommendations page asks the catalog for its product list and then for four products at once.
The list took 603ms. Of the four lookups, the first took 602ms and the other three 1,809 to
1,812 each - and each of those three held a single 601ms query and 1.2 seconds of waiting before
it. The catalog was serving the lookups one at a time: with each query holding its database
connection for 600ms instead of half a millisecond, concurrent lookups queued behind it. That
queue is what the catalog's own p95 measured, 1.8 seconds, three queries deep, and it is why the
frontend's p95 sat at 4.2 seconds. The delay was 300ms; the queueing it caused was the rest.

**The agent's trace tool, which names a degrading hop.** On the catalog's and the frontend's
traces it named the catalog's own query, `GetProduct` to `sql.conn.query`, in eight and seven of
ten: the deepest slow span there is. On recommendation's traces it named the frontend's lookups
into the catalog, and on checkout's the load generator's session span, a dead end that holds the
scripted shopper's pauses. The tool points at the query; it takes the trees to see that the
query's slowness is the catalog's egress, and that the database is not slow.

**Whether the catalog was unwell.** It was not. Its 9 Go runtime series reported every fifteen
seconds without a gap: goroutines at 44 to 46, as at rest, its heap flat, its allocation counter
moving at its usual rate. It raised no error. It has no log the tools can read, at rest or under
the fault, so its log answered nothing, which is what it always answers. A service short of
anything shows it in one of those; this one was idle and slow.

**Whether the database was slow.** It has no spans and no metrics of its own, but the catalog's
client spans to it say it was not: every query took the delay and a fraction, with two
milliseconds of spread across 144 of them, reads of one row and reads of the whole list alike. A
struggling database is uneven. Its log showed its usual two lines every five minutes and nothing
else. And the catalog's answers were slow by the same 300ms as its queries, which no database
could cause.

**The flag readers' sliver.** A dead end. Recommendation, product-reviews, ad, fraud-detection
and flagd showed error ratios under 2% for a few minutes at onset and again around ten minutes
in, and had shown the same before the trouble: the flag service's routine ten-minute stream
reconnect. Recommendation's 0.7% is among them and is not why it paged.

**What changed.** No deploy, no image change, no environment change, no limit change, on the
catalog, on its database or on any of the services that paged. And one record, under the
catalog's name, at the start, that is none of those: a **container created**, described as a
traffic-shaping container attached to product-catalog's network namespace, carrying `eth0
delay=300ms jitter=0ms`. Five services paged and the sixth was the one the record named.

### Root cause

A traffic-shaping rule attached to the product catalog's network namespace added 300ms of delay
to every packet leaving the container. The catalog's code, image, configuration, process and
database were untouched. Every product lookup paid the delay on its query to the database and
again on its answer, and lookups queued behind each other while each held the catalog's database
connection for 600ms. Because the storefront, the recommendations and every order look products
up, the whole store slowed at once, by seconds. Nothing failed.

### Resolution

The shaping container was removed and the rule went with it: the rule lives in the catalog's
network namespace and does not outlive what holds it, so recreating the catalog would have
cleared it as well. The p95s drained with their five-minute windows: checkout's alert cleared
three and a half minutes after the fix and the other five at four and a half, the catalog's p95
reading 666ms a minute before it read 5 again. Everything was quiet 5m02s after the fix, and
nothing fired during recovery.

Class of fix: **restart**. The rule is bound to the container's network namespace; recreating the
container is the operator's remedy, and removing the shaping container is the same fix from the
other end. Nothing about the catalog's image or configuration, and nothing about its database,
needed to change.

### Detection notes

- Onset to first page: **3m50s**. Services on the page: **one**, recommendation, which was not at
  fault. By the fix: **six**, the catalog among them.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The frontend's p95 was the highest
  at 4.2 seconds and the catalog's 1.8; the culprit was the quietest of the six that paged.
- Would the page alone have led you to the right service? **No, but the set of services does.**
  Six services slowed and every one of them looks products up; the ones that do not, cart,
  payment, shipping, product-reviews, did not slow. The shared dependency of the slow set is
  the thing to find.
- **The shared dependency of everything that slowed is the culprit.** Recommendation, the
  storefront and checkout have one dependency in common. A fault on a shared leaf shows up
  everywhere at once and looks like six faults.
- **A constant added per exchange is a network delay.** A two-exchange query paid 600, a
  one-exchange query 300, and every answer 300 more. Count the exchanges and the delay is
  arithmetic; a slow database or a slow handler would not divide so cleanly.
- **A delay times concurrency is a queue.** The 300ms became 1.8 seconds at the catalog and 4.2
  at the frontend because lookups arriving together waited for each other. The size of the
  numbers said nothing about the size of the fault.
- **The deepest span is not the culprit when the culprit is the wire.** The trace tool named the
  query; the query was fine. The delay sat on both sides of the catalog, which only the
  catalog's own interface touches.
- **"Nothing changed" is a conclusion about four queries, not about a service.** Deploy, image,
  environment and limit all came back empty on six services; the change record held the answer
  under the catalog's name, as a container that was not the catalog.

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-product-catalog-dependency-latency/`](../../evals/scenarios/artifacts/holdout/v2-product-catalog-dependency-latency/) by `faultline-render`. [All bundles](README.md).
