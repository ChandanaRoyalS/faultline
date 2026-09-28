---
origin: scenario:v2-product-catalog-partition
split: dev
fault_class: network_partition
recorded_from: 2026-09-28T00:01:58+00:00
capability: cap:d2b243e0
onset_to_page: 4m46s
page_to_fix: 5m00s
fix_to_all_clear: 5m01s
---

# The product catalog is cut from the network - its process runs and reaches nothing

## What was observed

The page came 4m46s after requests started hanging, and it was four alerts at once: error rate
and latency on **frontend-proxy** and on **load-generator**. Neither is a service anyone would
fix. One is the edge proxy and the other is the synthetic client, and both were reporting what
they received from below them. A minute later `ServiceHighLatency` on the **frontend** and
`ServiceHighErrorRate` on **fraud-detection**; two minutes after that, `ServiceNoTraffic` on
seven services together - **product-catalog**, accounting, currency, email, payment, quote,
shipping - with error rate on **recommendation** in the same minute; then latency on flagd and
recommendation, and no-traffic on fraud-detection. Seventeen alerts on thirteen services by the
fix, six more in the five minutes after it, and the world all clear 5m01s after the fix.

The storefront was mostly gone. The proxy's 95th percentile went to the histogram's ceiling,
**15000ms**, from T+1 and stayed there; the frontend's from T+2. The proxy's error ratio climbed
to 23-25% and the load generator's to 27-28%, while the frontend's read **zero** for the whole
fault - not one of its spans ended in error - and its request rate fell from 11.9 a second to
2.4. Product pages, add-to-cart, recommendations and checkouts all hung; only the cart's own
reads and writes kept going, at a third of their rate.

The catalog's request rate went to nothing by T+4, and from then until the fix it had no error
ratio and no latency value at all: no samples, not zero errors. Recommendation went to nothing
with it. The whole order path went with them - checkout down to a few hundredths of a request a
second, currency, shipping, quote, payment, email and accounting to zero.

## What was checked

**The proxy and the load generator, because they paged.** Their error traces - 300 drawn, none
under fourteen seconds - were all the same shape: a request cut at the proxy's fifteen-second
route timeout. 143 product pages, 88 add-to-carts, 43 recommendation calls, 26 checkouts. Under
each timed-out proxy span the frontend's handler was still open, for minutes.

**The frontend, from the traces.** Under every product page the frontend's call into the
catalog, `grpc.oteldemo.ProductCatalogService/GetProduct`, was open for 200 to 430 seconds in
those drawn, with nothing beneath it: no catalog span, no answer. The frontend recorded no error
because it had not finished; it was waiting.

**Checkout, from the traces.** Under every timed-out checkout, `PlaceOrder` was open for 300 to
530 seconds. Inside it, `prepareOrderItemsAndShippingQuoteFromCart` had read the cart in about a
millisecond and then held its own `GetProduct` for the rest. When the span finally closed it
closed in error: `connection reset by peer`, naming the catalog's address on port 3550.
Recommendation's `ListProducts` told the same story at 550 to 600 seconds. Every hung path in
the system had one call in common, and it was into the catalog.

**The catalog's own view of itself.** Its nine runtime series - goroutines, heap, GC goal - had
stopped at the onset: the last report is the one before it, they held for the store's lookback
and dropped out of queries at T+5, and nothing replaced them until 89 seconds after the fix. A
service that is merely uncalled keeps sending its runtime reports on a timer. This one had
stopped reporting on itself.

**The catalog's log.** This is a service that writes nothing at rest - no request logging, no
heartbeat; there is normally no log stream for it at all. Under this fault there was one, and it
held eleven lines: at the twelfth second, `context deadline exceeded`, and a second line naming
the traces export with the same ending; then, at eight seconds past every minute from T+1 to
T+9, `failed to upload metrics: context deadline exceeded ... DeadlineExceeded`. Eleven lines, one
a minute, every one of them the process saying it could not reach its collector. It was
running. It was trying to send. Nothing it sent arrived, and nothing sent to it arrived either.
A twelfth line landed 24 seconds after the fix, from the export that had begun six seconds
before it.

**fraud-detection, flagd, recommendation and ad, because they were on the page.** Dead ends of
one kind. With orders stopped, fraud-detection's only span in five minutes was its routine
flag-stream reconnect, a ten-minute span closed in error, which put its error ratio at 100% and
its p95 at the ceiling; flagd's side of the same stream put its p95 there too. Recommendation's
ratio read 100% from T+5 on its one request before its traffic went to zero. Ad's p95 read the
ceiling from T+7 on a rate cut to a third and paged a minute after the fix; on the shape of it,
the same stream span. Nothing was wrong with any of them.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

## Root cause

The product-catalog container was disconnected from the demo network. The process kept running
and its port stayed open, on an address nothing could reach; packets on its established
connections were dropped rather than refused, so every caller waited on a socket that would never
answer, with no deadline of its own, and the proxy cut each request at fifteen seconds. Everything
that lists or looks up a product hung: product pages, add-to-cart, recommendations, and every
order at its first catalog lookup, after the cart read. Nothing before the catalog failed and
nothing after it ran. The catalog itself was alive the whole time, and said so once a minute in
the only place it could still write - its own log - because the same cut that stopped its
requests stopped its telemetry. Nothing about it had been changed.

## Resolution

The container was put back on its network under its original names, on the same address. Where
an operator cannot reconnect a container with its aliases, recreating or restarting it does the
same job. Class of fix: **restart**. Nothing was deployed or misconfigured, so there was nothing
to roll back or revert.

The recovery was not clean, and it was not the fault. The connections the callers had held open
for the length of the cut were reset when the catalog came back - their far end no longer
existed - so the held requests failed rather than completed: 26 of the 39 orders begun during
the cut ended in a reset on their catalog lookup, the frontend's error ratio read 48% in the
minute after the fix and its p95 stayed at the ceiling to T+13 as the held spans closed at their
minutes-long lengths, checkout's ratio 40%, recommendation's 14%. Then the woken backlog hit the
catalog together and it answered `Product Not Found` for products that exist, at 179ms against
its usual 6. Six alerts fired only in this window - ad's latency, then errors on checkout, the
frontend and recommendation, then latency on checkout and recommendation - and cleared as the
wave passed. The proxy's and the load generator's alerts cleared at T+13 and T+14 as their
fifteen-second spans aged out, and the world was all clear 5m01s after the fix. The database
behind the catalog did not restart.

## Detection notes

- Onset to first page: **4m46s**, the storefront edge's error ratio and latency crossing their
  lines in the same minute.
- Services on the page: **two**, the culprit not among them. By the fix: **seventeen alerts
  across thirteen services**, the culprit named once, as silence, alongside six others.
- Alerts that fired only during recovery: **six** - ad's latency, then the reset backlog as
  errors and latency on checkout, the frontend and recommendation.
- Did the loudest service turn out to be the culprit? **No.** The proxy and the load generator
  paged first and stayed loudest; they were reporting what they received.
- Would the page alone have led you to the right service? **No.** The page named the edge; the
  traces named the call that never returned; the catalog's own runtime reports, stopped, said it
  was not merely idle; its log said it was alive and cut off.
- **A service that logs nothing at rest and eleven lines under the fault is telling you what
  kind of fault it is.** A frozen process writes nothing; a crashed one writes a start-up; a
  cut-off one keeps writing that it cannot reach anything, once a minute, at the same second
  past the minute. Read the culprit's own log even when it is normally empty - especially then.
- **The runtime reports separate stopped from uncalled. The logs separate stopped from cut off.**
  Two questions, two sources; the traces only say where the waiting is.
- **The frontend's zero error ratio was a symptom.** Its spans had not ended. A zero next to a
  p95 at the ceiling and an error ratio one hop up is the signature of a hang, not of health.
- **The recovery's errors are not the fault's, and they are the opposite of a freeze's.** A
  frozen service answers its backlog when it resumes; a cut-off one, back on its address, resets
  it. Errors on checkout, the frontend and recommendation that begin at the fix are the held
  connections failing, not a second fault - and, read after the fact, they are a second line of
  separation between this fault and a freeze.
