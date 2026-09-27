---
origin: scenario:v2-cart-bad-image-tag
split: dev
fault_class: bad_deploy
recorded_from: 2026-09-27T00:10:12+00:00
capability: cap:d2b243e0
onset_to_page: 4m47s
page_to_fix: 5m00s
fix_to_all_clear: 6m01s
---

# Cart deployed on an image tag that was never published

## What was observed

The page was four alerts in the same moment, `ServiceHighErrorRate` on **checkout**, **frontend**,
**frontend-proxy** and **load-generator**, 4m47s after the trouble started. The service the
failures would turn out to name was not on it.

Checkout's error ratio had been zero. It climbed through the first four minutes and from five
minutes held at **exactly two thirds**. Its latency fell, from about 38ms to under 2ms: its orders
were failing almost before they started. The frontend's error ratio settled at 26-29%,
frontend-proxy's at 25-28% and the load generator's at 14-15%. The storefront itself kept
serving: product pages, recommendations and ads went on. Adding to a cart, viewing it and checking
out failed.

About three minutes after the page, eight services went quiet in the same minute:
`ServiceNoTraffic` on **cart**, and on currency, quote, shipping, payment, email, accounting and
fraud-detection. None of the eight had recorded an error. Twelve alerts on twelve services by the
fix, and none after it.

## What was checked

**The page names callers.** Frontend-proxy forwards what the frontend returns, and the load
generator is the synthetic shoppers counting their own failures. Frontend and checkout were the
two services making calls that failed.

**Checkout's error traces.** Every failing order was the same eleven spans.
`oteldemo.CheckoutService/PlaceOrder` errored with `cart failure: failed to get user cart during
checkout: rpc error: code = Unavailable desc = name resolver error: produced zero addresses`.
Beneath it, the first step of preparing the order, `oteldemo.CartService/GetCart`, failed in no
measurable time with `name resolver error: produced zero addresses`, and there was no cart span
beneath it. Nothing else in the order ran: no product lookup, no currency conversion, no quote,
no charge. That is checkout's two thirds, the order and its cart read failing out of three spans,
and it is why its latency fell. "Produced zero addresses" means the name `cart` resolved to
nothing at all.

**The frontend.** Its failing traces were adds to the cart: `frontend/grpc.oteldemo.CartService/
AddItem` in error in under a millisecond, again with no cart span beneath. Its log said the same
thing in other words: `Error: 14 UNAVAILABLE: No connection established. Last error: connect
EHOSTUNREACH 172.18.0.17:7070`, over and over until the fix. The frontend had kept the address cart
used to have and could no longer reach anything at it. Checkout looked the name up afresh and found
none. Two callers, two wordings, one absence.

**Cart itself.** It raised no error, because it served nothing. Its traffic did not fall to a
failing level; it fell to zero, and that is what finally paged on it. Its log ended at the moment
the trouble began with `Application is shutting down...` and the feature provider shutting down,
after 116 to 174 request lines a minute, and after that there was nothing at all for nearly ten
minutes. A service that is failing logs its failures. This one had stopped. Its 39 .NET runtime
series did not stop at once to the eye: they held their last values for five minutes, the store's
lookback, and then disappeared, so for the first minutes they looked like a process that was up
and idle. Its store, valkey-cart, was running throughout.

**Why eight services went quiet together.** Everything an order touches after its cart read -
currency, quote and shipping for the quote, payment, email, accounting and fraud-detection after
it - is reached only through a successful cart read, so all of it stopped when orders stopped at
the first step. The services the storefront calls for browsing kept serving: recommendation and ad
at their usual rates, product-catalog at about two thirds of its, having lost the lookups that
orders and cart pages make.

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

Cart was rolled back to the published `2.2.0-cart` image. It started within a second and was
serving cart reads twenty seconds later, and its callers found it again. One order just after the
fix failed at the shipping quote instead: its cart read succeeded and was followed by no product
lookup, so the cart was empty, and shipping refused to quote nothing. Checkout reported that as
`shipping quote failure: failed POST to email service: expected 200, got 400`, a message from its
own quote code that names the wrong service. It was a straggler of the outage, not a second fault.
The quiet services' traffic came back within two minutes of the fix and the error ratios drained
with their windows. Everything was quiet 6m01s after the fix, and nothing new fired during recovery.

Class of fix: **rollback**. A deploy was wrong and it was undone. Restarting cart would have found
nothing to restart, and nothing about its configuration needed to change.

## Detection notes

- Onset to first page: **4m47s**. Services on the page: **four**, none of them cart. By the fix:
  **twelve**, cart among them.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The callers were loud and cart was
  silent; its only alert was the absence of traffic, three minutes after the page.
- Would the page alone have led you to the right service? **No, but one trace does.** Every failing
  order ends at a cart call with nothing beneath it.
- **A missing service does not error; it goes quiet.** An erroring service still records calls.
  Cart's error ratio stayed at zero while every call to it failed, and its traffic fell to nothing.
- **An error ratio of exactly two thirds is a shape.** Every failing order was the same three spans
  with the same two in error, so the failure is at the same step every time - here the first.
- **A log that ends is evidence.** `Application is shutting down` and then silence says the process
  stopped, and a change at that moment says why.
- **Runtime series that stop do not stop at once.** They held their last values for five minutes
  before vanishing. Flat and then gone is a process that ended, not one that is idle.
- **After the fix, stragglers.** Carts left empty by the outage can fail an order once more, with an
  error that names a different step and, here, the wrong service.
