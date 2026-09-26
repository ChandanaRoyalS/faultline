# Checkout pointed at a currency host that does not exist

## The scenario

| | |
|---|---|
| scenario | `v2-checkout-currency-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `checkout` via `v2-checkout-currency-misconfig` |
| time to page | 4m31s |
| steady state captured | 300s |
| capture window | 2026-09-26T07:55:53+00:00 → 2026-09-26T08:16:26+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m31s |
| `t_revert` | T+9m31s |
| all clear | T+13m33s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m15s | `checkout` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+6m15s | `frontend` | ServiceHighErrorRate | 4.0 min | joined later |
| T+6m15s | `frontend-proxy` | ServiceHighErrorRate | 4.0 min | joined later |
| T+7m15s | `accounting` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `currency` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `email` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `fraud-detection` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m15s | `payment` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `quote` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `shipping` | ServiceNoTraffic | 3.0 min | joined later |
| T+11m15s | `fraud-detection` | ServiceHighErrorRate | 1.0 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="checkout"}` |

`logs/checkout.txt` — 9 lines.

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

The page was one alert, `ServiceHighErrorRate` on **checkout**, 4m31s after the trouble started.
Checkout's error ratio had been zero. It rose from about a minute in and settled at **exactly
0.4**. Its latency did not rise. It fell, from about 37ms to about 5ms, because an order that fails
early finishes fast.

About two minutes after the page, frontend and frontend-proxy crossed their error thresholds at
5-6%, carrying checkout's failures up to the storefront. The storefront itself browsed normally,
and the cart worked. Only orders were failing.

About three minutes after the page, seven services went quiet in the same minute:
`ServiceNoTraffic` on **currency**, shipping, quote, payment, email, accounting and
fraud-detection. Nine alerts across nine services by the fix. None of the quiet services had
recorded an error.

### What was checked

**The error text, because it was the first thing a responder would read.** Checkout's error spans,
and the frontend's log, which carries checkout's errors up to the storefront, said `failed to
prepare order: failed to convert price of "<product>" to USD`, and for some orders `to CAD`. That
names a step, converting a price, and the step belongs to the currency service. It does not say
why the conversion failed. The frontend logged 6 to 13 of these a minute, from the first minute until
the fix, with none before the change and none from a minute after the fix.

**Checkout's traces.** Every failing order had the same shape.
`checkout/oteldemo.CheckoutService/PlaceOrder` errored with that message. Beneath it, checkout read
the user's cart from cart, and cart answered normally. It looked up the first product in the
catalog, and the catalog answered normally. Then its call to convert that product's price,
`checkout/oteldemo.CurrencyService/Convert`, failed in under a tenth of a millisecond with
`name resolver error: produced zero addresses`. There was **no currency span beneath it**: the call
never left checkout. Nothing followed it: no shipping quote, no payment. The trace tool named that
call as the degrading hop.

**What the resolver error means.** Checkout could not turn the address it holds for currency into
a single network address. The name it was using did not resolve. That is a failure in checkout,
before any connection is made, not a failure of currency.

**Whether currency was down.** Nothing says it was, and everything that does exist says it was
idle. Its error ratio had no value in the whole window, because it recorded no error. Its request
rate fell from about 0.35 a second to zero by about five minutes in, and it had no spans at all in
the incident. A currency service that was down or failing would have been reached and would have
answered with errors or timeouts, and checkout's call would have a currency span under it. This one
was simply never called. Currency has no log stream the tools can read, so its own view of itself
is not available. It went quiet because its only caller, checkout, stopped reaching it.

**Whether checkout was down.** It was not. It answered every order, in a few milliseconds, with an
error, and its Go runtime series, 9 of them, reported without a gap. Checkout's own logs are not
available to the tools either: it writes them only to a store none of them reads. Its spans and its
runtime series are what show it running.

**The 0.4.** Each failed order is five checkout spans: the order, the preparation step, the
cart read, the product lookup and the conversion. The order and the conversion error, the other
three do not. So an error ratio of exactly 0.4 means every order was failing.

**The other quiet services.** Shipping and quote are only asked for a price once every item is
priced. Payment, email and accounting are only reached once an order is charged. Fraud-detection
reads orders that have been placed. No order got past its first price conversion, so they had
nothing to do. Their silence was a consequence, not six more failures. Shipping had no errors: it
was never asked.

**What changed.** One record, at the start: `CURRENCY_ADDR updated on checkout`, to
`currencyservice:7001`. That is the address the failing call was built from, and the name that did
not resolve. Nothing had changed on currency or on any other service.

### Root cause

Checkout's `CURRENCY_ADDR` was changed to a host name that does not resolve. Checkout came up
normally and kept answering, and every order failed at its first price conversion, because the call
to currency could not find an address to go to. Checkout paged on its own errors. Currency was
healthy and went idle, because the one service that calls it could no longer reach it. Everything
an order touches after pricing went quiet with it. No service's code was wrong, and currency was not
at fault. The fault was the address checkout held for currency.

### Resolution

`CURRENCY_ADDR` was set back to currency's address and checkout was recreated with it. Orders
completed again, the quiet services came back within a few minutes, and the error ratios drained
with their five-minute windows. Everything was quiet 4m02s after the fix.

One alert started after the fix, and it belongs to neither the fault nor the fix. Fraud-detection's
error alert began about two minutes after the fix. The span behind it is fraud-detection's
subscription to its feature-flag service, `flagd.evaluation.v1.Service/EventStream`, which the flag
service closes every ten minutes (`stream closed due to server-side timeout`), and which is
recorded as an error lasting ten minutes. It ended while fraud-detection had no orders to read, so
with nothing else in its five-minute window, that one span was a 100% error ratio and a p95 at the
latency histogram's ceiling. On a normal minute its orders drown it out.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

- Onset to first page: **4m31s**. Services on the page: **one**, the service that changed. By the
  fix: **nine alerts across nine services**.
- Alerts that fired only during recovery: **one** by its start time, fraud-detection's, and it was
  its flag subscription's routine ten-minute reconnect, exposed by the quiet.
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

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-checkout-currency-misconfig/`](../../evals/scenarios/artifacts/holdout/v2-checkout-currency-misconfig/) by `faultline-render`. [All bundles](README.md).
