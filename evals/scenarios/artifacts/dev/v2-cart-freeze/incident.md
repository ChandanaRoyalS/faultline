---
origin: scenario:v2-cart-freeze
split: dev
fault_class: process_freeze
recorded_from: 2026-09-27T21:35:10+00:00
capability: cap:d2b243e0
onset_to_page: 5m31s
page_to_fix: 5m00s
fix_to_all_clear: 5m01s
---

# The cart process is frozen - its socket accepts and nothing answers

## What was observed

The page came 5m31s after requests started hanging, and it was four alerts at once: error rate
and latency on **frontend-proxy** and on **load-generator**. Neither is a service anyone would
fix; one is the edge proxy and the other the synthetic client, and both were reporting what they
got from below. A latency alert on **frontend** followed a minute later. Then, two minutes after
the page, `ServiceNoTraffic` fired at once on **nine services**: cart, checkout, payment,
shipping, quote, currency, email, accounting and fraud-detection. By the fix there were fourteen
alerts across twelve services, and most of the names were services with nothing wrong except that
nobody was calling them.

The earliest sign was the proxy's p95, at the histogram's ceiling, **15000ms**, from two minutes
after onset, and the frontend's at the ceiling from three. The frontend recorded **no errors at
all** through the whole fault: its error ratio read zero, because not one of its spans ended in
error. Its request rate fell from about 11 to 4.5 a second. The proxy's errors were its own
upstream timeouts: 1.5% a minute in, 3.8% at two, 9.2% at three, 13% at four, and 14 to 16% from
five until the fix, the load generator's a point or two above it. Requests were not failing at
the frontend. They were not finishing.

The browse path kept working, slower. The catalog answered at about half its usual rate with no
errors and its usual 7ms, ads and recommendations likewise. Everything that starts with a cart
read did not: cart's own rate fell from 3.4 a second to nothing by T+4, checkout's from 1.6 to
nothing in the same minute, and payment, shipping, quote, currency, email, accounting and
fraud-detection went to zero with it. From T+4 none of the nine had an error ratio or a latency
value at all.

## What was checked

**The proxy, because it was loudest.** Its error traces - 247 of them across the ten minutes -
were all the same kind: a request cut at its fifteen-second route timeout. And they were all the
same four requests: `user_add_to_cart` (132), `user_view_cart` (71), `user_checkout_multi` (23)
and `user_checkout_single` (21). Not one product page, ad or recommendation among them. The
proxy was doing its job; the requests it was timing out were the ones that touch the cart.

**The frontend, because its latency was the next thing to move.** It looked like a slow frontend
and it was not one. Under every timed-out proxy span, the frontend's own request was still open
- `GET /api/cart` for 235 and 462 seconds, `POST /api/checkout` for 393 - and under each, one
call: `grpc.oteldemo.CartService/GetCart` or `AddItem`, open for the whole of that time, and
beneath it, when it finally closed, cart's answer in two milliseconds. The frontend was not doing
work in that time. It was waiting on the cart, with no deadline of its own.

**Checkout, the same thing from the order path.** Every `PlaceOrder` that ran into the fault
stayed open at `oteldemo.CartService/GetCart` under `prepareOrderItemsAndShippingQuoteFromCart`,
the first thing an order does, for as long as the freeze lasted - 393 seconds in one trace, 598
in another - with nothing after it. Checkout has no deadline on that call either. That is why the
whole order path went quiet: the shipping quote, the currency conversion, the charge, the
confirmation email and the order record all come after a cart read that never returned.

**The nine silent services, as a group.** Nine services going quiet in one minute looks like nine
failures, and chasing them one by one would have cost the rest of the incident. Eight of them
sit behind checkout's cart read, and checkout sits behind the cart. Nothing was getting past the
cart, so their silence was a consequence. The cart was on the list too, and on the alert list it
looked like just another starved service. It was the only one of the nine that was not.

**The cart's own view of itself.** This is where it opened up. Its 36 runtime series - .NET heap,
garbage collection, threads, working set - stopped at the freeze: the last samples are from the
minutes before onset, they held for the store's four-minute lookback and then dropped out of
queries, and nothing replaced them until fourteen seconds after the fix. A service that is
merely uncalled keeps sending its runtime reports on a timer. This one had stopped reporting on
itself altogether.

**The cart's log.** It logs every request, seventy to eighty lines a minute at rest. Twelve
lines in the first seconds of the fault, then **nothing** for ten minutes: not an error, not a
shutdown line, not a start-up sequence, not a line. A cart that had been cut off from the network
would keep running and keep logging - its own requests would fail, and it would say so. A cart
that had crashed would show its runtime starting again. This one wrote nothing because nothing in
it was running. And then, in the thirty seconds after the fix, two hundred request lines at
once: the backlog, answered together.

**Its traces.** The cart had no spans of its own while requests hung on it. Its only spans in the
window are answers it gave *after* the fix, under calls that had been open for minutes.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

**The dead ends.** fraud-detection's error ratio read 100% at T+9 on a rate of 0.004 - one
span in five minutes, its routine flag-stream reconnect, closed by flagd at the ceiling - and
flagd's own p95 sat at 15000ms for two minutes on the same long stream spans; ad's and
recommendation's error ratios read 1 to 3% on the same thinness. With orders and cart reads
stopped, those few long stream spans were most of what those services reported. None of it was
a second fault.

## Root cause

The cart process was suspended. The container existed and kept its port; the kernel went on
accepting connections into its backlog; but nothing in the process ran, so no request was ever
read or answered. Every add-to-cart, cart view and checkout hung until its caller's deadline -
the proxy's fifteen seconds, or, for the frontend and checkout, which set none, until the
process resumed. Because checkout reads the cart before it does anything else, no order got past
its first step, and payment, shipping, email and the order topic's consumers went quiet while
browsing, ads and recommendations carried on. The cart neither errored nor logged, because it was
not running. Nothing about it had been changed.

## Resolution

The cart process was resumed. Its runtime reports came back within fifteen seconds and its log
within one; it answered two hundred held requests in the first half-minute. Where an operator
cannot resume a suspended process, restarting the container does the same job. Class of fix:
**restart**. Nothing was deployed or misconfigured, so there was nothing to roll back or revert.

Recovery had its own wave, and it belongs to the fix, not the fault. Every request that had been
hanging woke at once. Checkout's held orders found their cart connection draining, read the cart
again in fifty milliseconds, and went on: 29 completed - charged, shipped, confirmed and booked
minutes after they were placed - and 18 failed at the shipping quote with a 400, the frontend
logging those 18 errors in the minutes after the resume and none after that. The five-minute
windows carried the wait: checkout's p95 read 15000ms from the resume until T+14 as spans that
had been open for minutes closed, its error ratio 17% falling to 8%, and checkout alerted on
error rate 3 minutes after the resume and on latency 4 minutes after. Cart's rate ran at up to
two and a half times its usual for four minutes as the blocked users caught up, its p95 at 29ms
against 4. Everything was quiet 5m01s after the resume.

## Detection notes

- Onset to first page: **5m31s**. The proxy's latency was at the ceiling three and a half
  minutes before that, the frontend's two and a half.
- Services on the page: **two** (four alerts), neither of them one you would fix. By the fix:
  **fourteen alerts across twelve services**, nine of them silence.
- Alerts that fired only during recovery: **two**, checkout's errors and latency as the backlog
  woke.
- Did the loudest service turn out to be the culprit? **No.** The proxy and the load generator
  paged first and longest; the culprit was one of nine names in the no-traffic wave.
- Would the page alone have led you to the right service? **No.** The page names the edge. The
  edge's traces name the request kinds; the request kinds share one dependency; that
  dependency's own series and log say it was not running.
- **A frozen service pages its callers, and the errors surface at the first deadline.** The
  frontend and checkout set none, so they showed latency and no errors; the proxy's fifteen
  seconds turned the hang into errors one hop up.
- **The size of the page is the share of requests that touch the target.** A quarter of this
  storefront's requests read the cart; the proxy's error ratio settled at 14 to 16% as those
  requests hung and their users stopped generating others. The catalog, on every product page,
  took the frontend's rate down by four fifths; the cart took it down by three fifths.
- **Silence in a group is a consequence; find the one that stopped reporting on itself.** Nine
  services went quiet together. Eight kept exporting their runtime series. One did not.
- **A frozen process leaves no line.** No error, no shutdown, no restart - the log simply stops,
  and resumes with a burst. A partition would have kept logging; a crash would have logged a
  start.
- **The fix has a second wave.** Held requests close together, their durations are the length of
  the fault, and the rate windows carry them for five minutes. Two alerts here belong to the
  resume, not to the freeze.
