---
origin: scenario:v2-cart-bad-image-tag
split: dev
fault_class: bad_deploy
recorded_from: 2026-09-27T06:31:29+00:00
capability: cap:91279a09
onset_to_page: 3m17s
page_to_fix: 5m00s
fix_to_all_clear: 5m02s
---

# Cart deployed on an image tag that was never published

## What was observed

The page was three alerts in the same moment, `ServiceHighErrorRate` on **checkout**, **frontend**
and **frontend-proxy**, 3m17s after the trouble started. `ServiceHighErrorRate` on
**load-generator** followed a minute later. The service the failures would turn out to name was not
on it.

Checkout's error ratio had been zero. It climbed through the first five minutes and from six
minutes held at **exactly two thirds**. Its p95, after one reading of 4.7 seconds just past four
minutes, fell from about 35ms to under 2ms: its orders were failing almost before they started. The
frontend's error ratio settled at 26-29%, frontend-proxy's at 27-29% and the load generator's at
15-17%. The storefront itself kept serving: product pages, recommendations and ads went on. Adding
to a cart, viewing it and checking out failed.

About four minutes after the page, services went quiet: `ServiceNoTraffic` on **cart**, currency
and shipping, and a minute later on quote, payment, email and accounting. None of the seven had
recorded more than a trace of errors. Eleven alerts on eleven services by the fix. In the minutes
after the fix three more fired, on fraud-detection and flagd, and they led nowhere.

## What was checked

**The page names callers.** Frontend-proxy forwards what the frontend returns, and the load
generator is the synthetic shoppers counting their own failures. Frontend and checkout were the
two services making calls that failed.

**Checkout's error traces.** Every failing order was the same.
`oteldemo.CheckoutService/PlaceOrder` errored with `cart failure: failed to get user cart during
checkout: rpc error: code = Unavailable desc = name resolver error: produced zero addresses`.
Beneath it, the first step of preparing the order, `oteldemo.CartService/GetCart`, failed, and
there was no cart span beneath it. Nothing else in the order ran: no product lookup, no currency
conversion, no quote, no charge. That is checkout's two thirds, the order and its cart read failing
out of three spans, and it is why its latency fell. "Produced zero addresses" means the name `cart`
resolved to nothing at all.

**The frontend.** Its failing traces were cart calls, `frontend/grpc.oteldemo.CartService/AddItem`
and `GetCart`, in error with no cart span beneath. Its log said the same thing in other words:
`Error: 14 UNAVAILABLE: No connection established. Last error: connect EHOSTUNREACH`, 624 times
during the trouble, up to 94 a minute, and 82 more in the five minutes after the fix. The frontend
had kept the address cart used to have and could no longer reach anything at it. Checkout looked the
name up afresh and found none. Two callers, two wordings, one absence.

**Cart itself.** It raised almost no errors, a few tenths of a percent from its last seconds,
because it served nothing after them. Its traffic did not fall to a failing level; it fell to zero,
and that is what finally paged on it. Its log ended one second after the trouble began with
`Application is shutting down...` and the feature provider shutting down, after about 90 request
lines a minute, and after that there was nothing at all for more than eight minutes. A service that
is failing logs its failures. This one had stopped. Its 43 .NET runtime series did not stop at once
to the eye: they held their last values for five minutes, the store's lookback, and then
disappeared, so for the first minutes they looked like a process that was up and idle.

**Why seven services went quiet together.** Everything an order touches after its cart read -
currency, quote and shipping for the quote, payment, email and accounting after it - is reached
only through a successful cart read, so all of it stopped when orders stopped at the first step.
The services the storefront calls for browsing kept serving: recommendation and ad at their usual
rates, product-catalog at about four fifths of its, having lost the lookups that orders and cart
pages make.

**Fraud-detection and flagd, after the fix.** A dead end. Fraud-detection also lost its orders, but
it did not go quiet: its one remaining span was its `flagd.evaluation.v1.Service/EventStream` stream
to flagd, which flagd ended with `stream closed due to server-side timeout`, its routine ten-minute
reconnect. With no orders beside it, that one long span was all fraud-detection reported, an error
ratio of 100% and a p95 at the top of the histogram, 15 seconds, and flagd's p95 went the same way.
`ServiceHighErrorRate` on fraud-detection fired a minute after the fix, before orders reached it
again, and `ServiceHighLatency` on fraud-detection and flagd a minute after that. No order was
involved, and all three cleared within three minutes of the fix, as orders came back.

**What changed.** One record, at the start: `image reference updated on cart`, to
`ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2`. The running cart had been
`ghcr.io/open-telemetry/demo:2.2.0-cart`. The old container was stopped for the new one and no new
one ever ran: the registry has no such tag, so there was nothing to start. Nothing else had changed
on cart, on valkey-cart or on any of the callers.

## Root cause

A deploy moved cart to an image tag, `2.2.0-cart-hotfix.2`, that was never published. The running
container was stopped to make way for it and the replacement could not be pulled, so cart was
absent rather than unhealthy: its name resolved to nothing and its address answered nothing. The
storefront could not read or add to carts, and every order failed at its first step, reading the
cart. The store behind cart was healthy, and nothing was wrong with any caller.

## Resolution

Cart was rolled back to the published `2.2.0-cart` image. It was connected to its store within a
second and listening two seconds after the fix, and it was serving cart reads about a minute later,
as its callers found it again; a new set of runtime series began with it. The quiet services'
traffic came back within two minutes of the fix and the error ratios drained with their windows.
Everything was quiet 5m02s after the fix. The only alerts that began during recovery were the three
stream-timeout alerts on fraud-detection and flagd.

Class of fix: **rollback**. A deploy was wrong and it was undone. Restarting cart would have found
nothing to restart, and nothing about its configuration needed to change.

## Detection notes

- Onset to first page: **3m17s**. Services on the page: **three**, none of them cart. By the fix:
  **eleven**, cart among them.
- Alerts that fired only during recovery: **three**, `ServiceHighErrorRate` on fraud-detection and
  `ServiceHighLatency` on fraud-detection and flagd, a routine flag-stream timeout showing through
  while fraud-detection had no orders.
- Did the loudest service turn out to be the culprit? **No.** The callers were loud and cart was
  silent; its only alert was the absence of traffic, four minutes after the page.
- Would the page alone have led you to the right service? **No, but one trace does.** Every failing
  order ends at a cart call with nothing beneath it.
- **A missing service does not error; it goes quiet.** An erroring service still records calls.
  Cart's error ratio stayed near zero while every call to it failed, and its traffic fell to
  nothing.
- **An error ratio of exactly two thirds is a shape.** Every failing order was the same three spans
  with the same two in error, so the failure is at the same step every time - here the first.
- **A log that ends is evidence.** `Application is shutting down` and then silence says the process
  stopped, and a change at that moment says why.
- **Runtime series that stop do not stop at once.** They held their last values for five minutes
  before vanishing. Flat and then gone is a process that ended, not one that is idle.
- **A quiet service can alert on its background.** With its orders gone, fraud-detection's routine
  stream to flagd was all it reported, and that tripped error and latency lines on its own.
