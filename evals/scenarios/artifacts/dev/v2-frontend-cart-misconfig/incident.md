---
origin: scenario:v2-frontend-cart-misconfig
split: dev
fault_class: bad_config
recorded_from: 2026-09-26T06:12:49+00:00
capability: cap:d2b243e0
onset_to_page: 3m31s
page_to_fix: 5m00s
fix_to_all_clear: 4m02s
---

# Frontend pointed at a cart port where nothing listens

## What was observed

The page was three alerts in the same moment, `ServiceHighErrorRate` on **checkout**, on
**frontend** and on **frontend-proxy**, 3m31s after the trouble started. Load-generator joined them
a minute later. Frontend's error ratio had been zero. It rose from about a minute in and settled
at a little over a quarter of its spans. Frontend-proxy's followed it step for step. Checkout's
settled at **exactly one half**.

Nothing got slower. Frontend's latency eased slightly, from about 38ms to about 32ms, and its
request rate barely moved: the storefront was serving pages at close to its usual rate.
Checkout's latency fell from about 28ms to under 5ms, because an order that fails early finishes
fast.

About seven minutes in, five services went quiet at once: `ServiceNoTraffic` on accounting,
currency, email, payment and quote. **Cart**, the service the storefront's failures would turn out
to name, never alerted. Its error ratio stayed at zero and its latency did not move.

## What was checked

**The error text, because it was the first thing a responder would read.** Checkout's error spans
and the frontend's log said `shipping quote failure: failed POST to email service: expected 200,
got 400`. That names two services, and neither was at fault. It is checkout's own wording for
shipping answering with a non-200 status, and it names the email service by mistake. The part that
matters here is the `400`: shipping was not failing, it was refusing the request it was sent.

**Checkout's traces, to see what it sent.** Every failing order had the same shape.
`checkout/oteldemo.CheckoutService/PlaceOrder` errored with that message. Beneath it, checkout
read the user's cart from cart, and cart answered normally, reading its store and returning in
about a millisecond. Then checkout called shipping for a quote, and shipping's `get-quote` span
ended in a tenth of a millisecond without an error. There was nothing between the two calls: no
product lookups, no currency conversion. In a healthy order, checkout looks up every item in the
cart at that point. It looked up none, because the cart it read was **empty**. Shipping rejected a
quote request with nothing in it, and checkout reported that as the error above. Checkout was
working. It was being handed empty carts.

**The one-half.** Each failed order is four checkout spans: the order, the preparation step, the
cart read and the call to shipping. The order and the shipping call error, the other two do not.
So an error ratio of exactly 0.5 means every order was failing, not half of them.

**Why the carts were empty: the frontend's own errors.** The frontend's traces answered it.
`load-generator/user_view_cart` failed at `frontend/GET /api/cart`, and the deepest span was the
frontend's own client call, `frontend/grpc.oteldemo.CartService/GetCart`, in error after under a
millisecond. There was **no cart span beneath it**: the call never reached cart. The trace tool
named that call as the degrading hop. Adding to a cart goes through the same client. Nothing a
shopper put in a cart got there, so when the order was placed, the cart was empty.

**The frontend's log.** At rest the frontend logs nothing. Within a second of the frontend coming
up at the start, it logged `Error: 14 UNAVAILABLE: No connection established. Last error: connect
ECONNREFUSED 172.18.0.17:7071`, and it kept logging it until the fix, between about 20 and 44
refused cart calls a minute, with none before the change and none from a minute after the fix.
Checkout's failures show up there too, 4 to 12 a minute. `ECONNREFUSED` means the host was reached
and nothing was listening on that port: the frontend was calling cart's host on **7071**.

**Whether cart was down.** It was not. Its error ratio was zero throughout, its latency held at
about 2ms, and its own log recorded `GetCartAsync called` for every read, through the whole
incident. Its request rate fell from about 4.2 a second to about 0.33, and never to zero: what was
left was checkout's reads and cart's own flag lookups. The frontend's share of its traffic had
vanished. A service that loses one caller's traffic while the other caller still reaches it is
not the service that broke.

**Whether the frontend was down or restarting.** It was not. Its Node runtime series, 75 of them,
reported without a gap, and it kept serving at close to its usual rate and latency.

**The five quiet services.** Currency, quote, payment, email and accounting are only reached once
an order has items and a shipping price. No order got that far, so they had nothing to do. Their
silence was a consequence, not five more failures.

**What changed.** One record, at the start: `CART_ADDR updated on frontend`, to `cart:7071`. That is
the address the refused calls were going to. Nothing had changed on cart, on checkout or on
shipping.

## Root cause

The frontend's `CART_ADDR` was changed to a port on the cart host where nothing listens. The
frontend came up normally and served its pages, and every cart call it made was refused at
connect, so nothing a shopper added to a cart was stored and every cart it showed failed. Cart
itself was healthy and kept serving its other caller, checkout. Checkout then read empty carts,
sent shipping a quote request with no items, and failed each order on shipping's refusal. Checkout
paged beside the frontend, with an error that names shipping and email. No service's code was
wrong, and cart was not at fault. The fault was the address the frontend held for cart.

## Resolution

`CART_ADDR` was set back to cart's address and the frontend was recreated with it. The refused
calls stopped, carts filled again, orders completed, and the quiet services came back. The error
ratios drained with their five-minute windows, and everything was quiet 4m02s after the fix.

One alert started after the fix, and it belongs to the fault rather than the recovery.
Fraud-detection's error alert began 44 seconds after the fix. The span behind it came before:
while fraud-detection had no orders to read, it recorded a single span, which errored and lasted
fifteen seconds. With nothing else in its five-minute window, that one span was a 100% error ratio
and a fifteen-second p95. The error search from the fix onwards found no errors for it.

Class of fix: **config_revert**. One setting was wrong and it was set back.

## Detection notes

- Onset to first page: **3m31s**. Services on the page: **three**, and one of them was the service
  that changed. By the fix: **nine alerts across nine services**.
- Alerts that fired only during recovery: **one** by its start time, fraud-detection's, and it was
  caused by a span recorded during the fault.
- Did the loudest service turn out to be the culprit? **Partly.** The frontend paged, and it is the
  service whose setting was wrong. Checkout paged beside it and was only reporting what it had been
  handed.
- Would the page alone have led you to the right service? **Yes, but not to the cause, and the
  page offers a better-looking wrong one.** Checkout's error names shipping and email, and
  following it leads through two healthy services. The cause is in the frontend's cart spans, which
  have nothing beneath them, in its log, which names the port, and in the change record.
- **What a trace does not contain is evidence.** Checkout's failed orders had no product lookups
  in them. That absence is what says the cart was empty, and an empty cart moves the question
  from checkout to whoever fills the carts.
- **A healthy service can be named by every error.** Cart appeared in the frontend's failures and
  was fine. It still served checkout, and its own log showed it doing so. When a call fails with
  no server span beneath it, the call never arrived: look at the caller's address for it.
- **An error ratio of exactly one half is a count, not a severity.** Two of the four spans in every
  order failed. Read as "half of orders fail", it undersells a total failure.
