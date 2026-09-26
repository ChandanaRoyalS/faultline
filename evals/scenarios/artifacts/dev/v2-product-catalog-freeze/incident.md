---
origin: scenario:v2-product-catalog-freeze
split: dev
fault_class: process_freeze
recorded_from: 2026-09-26T04:31:26+00:00
capability: cap:d2b243e0
onset_to_page: 5m01s
page_to_fix: 5m00s
fix_to_all_clear: 5m00s
---

# The product catalog process is frozen - its socket accepts and nothing answers

## What was observed

The page came 5m01s after requests started hanging: four alerts at once, error rate and latency
on **frontend-proxy** and on **load-generator**. Neither is a service anyone would fix. One is the
edge proxy and the other is the synthetic client, and both were reporting what they received
from below them.

A minute after the page, **frontend** alerted on latency. Its p95 had been near the histogram's
ceiling, **15000ms**, since about two minutes *before* the page, and at the ceiling for the
minute before it. That was the earliest sign of anything. Frontend recorded **no errors at
all**: its error ratio read zero through the whole fault, because not one of its spans ended in
error. Its request rate fell from about 12.8 to 2.2 req/s. Requests were not failing at
frontend. They were not finishing. The proxy's errors, steady at 27-29%, were its own upstream
timeouts at exactly fifteen seconds.

Under three minutes after the page the alert set changed shape. **ServiceNoTraffic** fired at
once on nine services: **product-catalog**, accounting, currency, email, fraud-detection,
payment, quote, recommendation and shipping. By the time the fix went in there were fourteen
alerts across twelve services. Most of the new names were services with nothing wrong except
that nobody was calling them.

## What was checked

**The proxy, because it was loudest.** Its errors were all the same kind: upstream requests
cut at the fifteen-second route timeout. The proxy was doing its job. Nothing in its own
behaviour had changed, so it was reporting the problem, not causing it.

**Frontend, because its latency was the first thing to move.** It looked like a slow frontend,
and it was not one. The error traces showed the proxy giving up at 15 s. Below the proxy,
frontend's own request did not end when the proxy gave up. Its call into the catalog,
`grpc.oteldemo.ProductCatalogService/GetProduct`, stayed open for up to **588.3 seconds**, almost
ten minutes, and closed only when the fix went in. The trace tool named that call as the
degrading hop, *still waiting 573.3 s after frontend-proxy/ingress gave up*. Of the six error
traces drawn in full, four named frontend's call into the catalog. One named checkout's call into
the catalog, from an order that could not be priced. One named frontend's call into
recommendation, which was waiting on the catalog in turn. Frontend was not doing work in that
time. Every trace put the time in a call that was still waiting on the catalog.

**The nine silent services, as a group.** Nine services going quiet in the same minute looks
like nine failures, and chasing them one by one would have cost the rest of the incident. They
sit behind the catalog. Accounting, currency, email, fraud-detection, payment, quote and
shipping are only called once a request has got past it: a priced product page, a shipping
quote, a completed order. Recommendation asks the catalog for its product list. Nothing was
getting past the catalog, so their silence was a consequence. The catalog was on the list too,
and on the alert list it looked like just another starved service.

**The catalog's own view of itself.** This is where it opened up. Its request rate had gone to
zero right at the page, and from then on its latency and error ratio had *no value*. No errors,
no slow requests, no samples. Its own runtime series (Go memory, goroutines, GC) told the
difference. Its last report landed less than a minute before the trouble started. The
allocation counter, which moves every minute on a live Go process under load, stopped. The
series dropped out of queries entirely just under a minute before the page. A service that is
merely uncalled keeps sending its runtime reports on a timer. This one had stopped reporting on
itself altogether. Callers were hanging on it, and it was not saying anything about itself
either.

**The catalog's logs.** Nothing at all for the whole window, and nothing in the healthy five
minutes before it either. The catalog is quiet when healthy, so silence alone proves nothing.
What mattered was which lines were *missing*. A catalog cut off from the network keeps running
and logs its failed telemetry exports once a minute. This one logged nothing, so it was not
running.

**Its traces.** The catalog had no spans at all while requests hung on it. The only catalog
spans in the window are requests it served *after* the fix, each taking between about 80 and 450
milliseconds, under frontend calls that had been open for up to ten minutes. Each had waited in
the catalog's backlog the whole time. Many of those late answers were errors, `Product Not
Found`, for products that exist. That belongs to the recovery, below, not to the hang.

**What changed.** Nothing. No deploy, no image, no configuration, no flag on any service
involved.

## Root cause

The product-catalog process was suspended. The container existed and kept its port. The
kernel went on accepting connections into its backlog. But nothing in the process ran, so no
request was ever read or answered. Every caller waited until its own deadline. The browse
path hung behind it, checkout stopped completing orders, and everything downstream of an order
went quiet. The catalog neither errored nor logged, because it was not running at all. Nothing
about it had been changed.

## Resolution

The catalog process was resumed. Its runtime reports came back within fifteen seconds and its
request rate within a minute. Where an operator cannot resume a suspended process, restarting
the container does the same job. Class of fix: **restart**. Nothing was deployed or
misconfigured, so there was nothing to roll back or revert.

Recovery had its own wave, and it belongs to the fix, not the fault. Every request that had been
hanging woke up at once, and the catalog opened database connections for them in the same
second. Postgres turned away **157** connection attempts in the first minute, with `sorry, too
many clients already` and `remaining connection slots are reserved for roles with the SUPERUSER
attribute`. The catalog answered those requests `Product Not Found`. Frontend wrote 266 log lines
naming that error in the minute after the resume and none after it, and checkout's orders failed
with `failed to prepare order: failed to get product`. Postgres did not restart. The five-minute
rate windows carried that one minute: error-rate alerts fired on checkout, frontend and the
catalog itself, and latency alerts on recommendation, then checkout and the catalog, between
164 and 224 seconds after the resume. The catalog's p95 reached 445ms while it worked through
the backlog, against a normal 3ms. Everything was quiet 5m00s after the resume.

## Detection notes

- Onset to first page: **5m01s**. Frontend's latency was near the ceiling about two minutes
  before that, and its own alert came a minute after the page.
- Services on the page: **two** (four alerts), neither of them one you would fix. By the fix:
  **fourteen alerts across twelve services**.
- Alerts that fired only during recovery: **six**, the errors and latency of the backlog waking
  at once.
- Did the loudest service turn out to be the culprit? **No.** The proxy was loudest and was
  reporting timeouts, not causing them. The culprit's own alert, ServiceNoTraffic, came under
  three minutes after the page, in the same minute as eight services that had nothing wrong
  with them.
- Would the page alone have led you to the right service? **No.** It names the edge. The path
  to the catalog runs through frontend's traces, which name the catalog as the call frontend
  was still waiting on minutes after the proxy gave up.
- **Absence was the evidence, three times over.** No errors on frontend, no values on the
  catalog, and no runtime reports from it. Every one of those answers is a query returning
  nothing or zero. Reading "nothing here" as "nothing wrong here" is the most expensive
  mistake available in this incident.
- **The runtime reports separate stopped from uncalled. The logs separate stopped from cut
  off.** A catalog that is merely idle keeps reporting its runtime. A catalog cut off from the
  network stops reporting too, but it logs its failed exports every minute. Only a process that
  has stopped running does neither.
- **The recovery's errors are not the fault's.** The `Product Not Found` burst came from the
  database refusing a stampede of connections at the resume. It is loud, it names the right
  service, and it describes the wrong mechanism.
