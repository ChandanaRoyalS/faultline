---
origin: scenario:v2-checkout-currency-misconfig
split: holdout
fault_class: bad_config
recorded_from: 2026-09-27T04:22:29+00:00
capability: cap:d2b243e0
onset_to_page: 4m17s
page_to_fix: 5m00s
fix_to_all_clear: 3m01s
---

# Checkout pointed at a currency host that does not exist

## What was observed

The page was one alert, `ServiceHighErrorRate` on **checkout**, 4m17s after the trouble started.
Checkout's error ratio had been zero. It rose from about two minutes in and settled at **exactly
0.4**. Its latency did not rise. It fell, from about 40ms to under 4ms, because an order that fails
early finishes fast.

About two minutes after the page, frontend and frontend-proxy crossed their error thresholds at
about 6%, carrying checkout's failures up to the storefront. The storefront itself browsed
normally, and the cart worked. Only orders were failing.

About three minutes after the page, six services went quiet in the same minute:
`ServiceNoTraffic` on **currency**, shipping, quote, payment, email and accounting. None of them
had recorded an error. Fraud-detection, which also stopped receiving orders, did not go quiet: a
minute later it raised `ServiceHighErrorRate`, and a minute after that, just before the fix, it and
**flagd** both raised `ServiceHighLatency`. Twelve alerts across eleven services by the fix.

## What was checked

**The error text, because it was the first thing a responder would read.** Checkout's error spans,
and the frontend's log, which carries checkout's errors up to the storefront, said `failed to
prepare order: failed to convert price of "<product>" to USD`. That names a step, converting a
price, and the step belongs to the currency service. It does not say why the conversion failed.
The frontend logged 164 lines naming it over about ten minutes, 4 to 32 a minute (each error takes
two lines, so about 80 failed orders), with none in the five minutes before the change and none in
the five after the fix.

**Checkout's traces.** Every failing order had the same shape.
`checkout/oteldemo.CheckoutService/PlaceOrder` errored with that message. Beneath it, checkout read
the user's cart and looked up the first product, and both answered normally. Then its call to
convert that product's price, `checkout/oteldemo.CurrencyService/Convert`, failed with `name
resolver error: produced zero addresses`. There was **no currency span beneath it**: the call never
left checkout. Nothing followed it: no shipping quote, no payment. The trace tool named the step
from checkout's order preparation to that call as the degrading hop, in all ten traces it sampled.

**What the resolver error means.** Checkout could not turn the address it holds for currency into
a single network address. The name it was using did not resolve. That is a failure in checkout,
before any connection is made, not a failure of currency.

**Whether currency was down.** Nothing says it was, and everything that does exist says it was
idle. Its error ratio had no value in the whole window, because it recorded no error. Its request
rate fell from about 0.3 a second to zero by about five minutes in, and it had no spans at all
from then until the fix. A currency service that was down or failing would have been reached and
would have answered with errors or timeouts, and checkout's call would have a currency span under
it. This one was simply never called. Currency has no log stream the tools can read, so its own
view of itself is not available. It went quiet because its only caller, checkout, stopped reaching
it.

**Whether checkout was down.** It was not. It answered every order, in a few milliseconds, with an
error, and its Go runtime series, 9 of them, reported without a gap. Checkout's own logs are not
available to the tools either: it writes them only to a store none of them reads. Its spans and its
runtime series are what show it running.

**The 0.4.** Each failed order is five checkout spans: the order, the preparation step, the
cart read, the product lookup and the conversion. The order and the conversion error, the other
three do not. So an error ratio of exactly 0.4 means every order was failing.

**The other quiet services.** Shipping and quote are only asked for a price once every item is
priced. Payment, email and accounting are only reached once an order is charged. No order got past
its first price conversion, so they had nothing to do. Their silence was a consequence, not five
more failures. Shipping had no errors: it was never asked.

**Fraud-detection and flagd: a dead end.** Fraud-detection reads placed orders, and it had none.
Its only error spans in the window were its subscription to the feature-flag service,
`flagd.evaluation.v1.Service/EventStream`, ended by flagd with `stream closed due to server-side
timeout`. That is the routine ten-minute reconnect, and flagd's own side of the stream is a span
ten minutes long. With no orders, those few long stream spans were nearly all either service
reported, so fraud-detection's error ratio read 100% and both p95s sat at the histogram's ceiling.
No order was involved. It was not a second fault.

**What changed.** One record, at the start: `CURRENCY_ADDR updated on checkout`, to
`currencyservice:7001`. That is the address the failing call was built from, and the name that did
not resolve. Nothing had changed on currency or on any other service.

## Root cause

Checkout's `CURRENCY_ADDR` was changed to a host name that does not resolve. Checkout came up
normally and kept answering, and every order failed at its first price conversion, because the call
to currency could not find an address to go to. Checkout paged on its own errors. Currency was
healthy and went idle, because the one service that calls it could no longer reach it. Everything
an order touches after pricing went quiet with it. No service's code was wrong, and currency was not
at fault. The fault was the address checkout held for currency.

## Resolution

`CURRENCY_ADDR` was set back to currency's address and checkout was recreated with it. Orders
completed again and the quiet services came back within about two minutes. Fraud-detection's and
flagd's alerts ended with them, as orders drowned out the stream spans again. The error ratios
drained with their five-minute windows, and everything was quiet 3m01s after the fix. No alert
started after the fix.

Class of fix: **config_revert**. One setting was wrong and it was set back.

## Detection notes

- Onset to first page: **4m17s**. Services on the page: **one**, the service that changed. By the
  fix: **twelve alerts across eleven services**.
- Alerts that fired only during recovery: **none**. Fraud-detection's and flagd's three began
  while orders were stopped, and were its flag subscription's routine reconnect, exposed by the
  quiet.
- Did the loudest service turn out to be the culprit? **Yes.** Checkout paged, and it is the
  service whose setting was wrong.
- Would the page alone have led you to the right service? **Yes, and the error text then points
  one step past it.** `failed to convert price` names the currency service's job, and currency was
  one of the services that went quiet. Both invite the conclusion that currency failed. It did not:
  it was never called.
- **The cause is on the client span, not in the message.** Checkout's message drops the underlying
  error. The span for its call to currency carries it: `name resolver error: produced zero
  addresses`, with nothing beneath it. A name that does not resolve points at the caller's
  configuration, not at the service it was trying to reach.
- **A dependency that fails leaves traces of failing. A dependency that is not reached leaves
  nothing.** Currency had no errors, no slow requests and no spans. Silence from the service an
  error names means the calls are not arriving.
- **An error ratio of exactly 0.4 is a count.** Two of the five spans in every order failed. Read
  as "40% of orders fail", it undersells a total failure.
