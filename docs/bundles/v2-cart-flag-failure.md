# A feature flag makes the cart fail to empty after an order

## The scenario

| | |
|---|---|
| scenario | `v2-cart-flag-failure` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `cart` via `v2-cart-flag-failure` |
| time to page | 5m16s |
| steady state captured | 300s |
| capture window | 2026-09-27T04:54:36+00:00 → 2026-09-27T05:13:52+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+5m16s |
| `t_revert` | T+10m16s |
| all clear | T+12m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+5m00s | `checkout` | ServiceHighErrorRate | 7.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="cart"}` |

`logs/cart.txt` — 89 lines.

## A look at the logs

From `logs/cart.txt` (---- onset 2026-09-27T04:59:36+00:00 ----):

```
2026-09-27T05:11:25+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-27T05:11:25+00:00        GetCartAsync called with userId=
2026-09-27T05:11:27+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-27T05:11:27+00:00        GetCartAsync called with userId=
2026-09-27T05:11:27+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-27T05:11:27+00:00        GetCartAsync called with userId=
2026-09-27T05:11:31+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-27T05:11:31+00:00        GetCartAsync called with userId=
2026-09-27T05:11:33+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-27T05:11:33+00:00        GetCartAsync called with userId=
2026-09-27T05:11:33+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-27T05:11:33+00:00        GetCartAsync called with userId=
```

_68 further lines are in the bundle._

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

The page was one alert, `ServiceHighErrorRate` on **checkout**, 5m16s after the trouble started.
Nothing else fired, then or later, and nothing fired after the fix.

Checkout's error ratio had been zero. It rose from about a minute in and held at 7.1-7.4%. Its
latency rose too, from a p95 of about 34ms to between 85 and 160ms, without reaching the latency
alert. The storefront's latency followed it up a little, from about 42ms to about 68ms at the
peak, and its error ratio stayed at **zero**. So did frontend-proxy's and the load generator's.
Payment, email and accounting kept their usual traffic: orders were being charged, confirmed and
recorded at the normal rate.

That is the puzzle on the page: checkout erroring on about 7% of its spans while every order it
was asked to place went through.

### What was checked

**Checkout's error traces, to see which of its calls failed.** Every order completed: the cart
read, the product lookups, the currency conversions, the shipping quote, the payment and the
confirmation email all succeeded, and `PlaceOrder` itself did not error. One call in each order
failed: `checkout/oteldemo.CartService/EmptyCart`, the last step, which clears the customer's cart
once the order is placed. Its error was `Can't access cart storage. System.ApplicationException:
Wasn't able to connect to redis`. Checkout does not treat that as an order failure, which is why
the orders succeeded and why the storefront saw nothing.

**How long it took.** Anywhere from tens of milliseconds to several seconds, the order held open
until `EmptyCart` gave up, and the confirmation went out only after it. That is checkout's latency
rise: its orders were waiting on a call that was going to fail.

**The cart, where the error came from.** Cart's own `EmptyCart` span was in error with the same
message, `FailedPrecondition`, `Can't access cart storage`. Beneath it was a single call, to the
flag service, a feature-flag lookup, and then nothing: no call to the cart store at all. In the
same traces, cart's `GetCart` ran its store query, `HGET`, and answered in about a millisecond.

**Its log.** Cart logged 98 `EmptyCartAsync called with userId=...` lines between onset and the
fix, and beside them 182 lines saying it `Wasn't able to connect to redis`, 2 to 26 a minute, none
in the five minutes before onset and none in the five after the fix. Its `AddItemAsync` lines went
on at their usual pace beside them, 268 during the fault against 120 and 176 in the five minutes
either side.

**Whether the cart's store was down.** This is where the log points, and it was not. "Wasn't able
to connect to redis" reads like the cart's Valkey store is unreachable. But in the same minutes
cart was adding items and reading carts through that store without an error, and its store queries
answered in a millisecond. The store has no telemetry of its own the tools can read, so its health
shows only through cart's calls to it, and those were fine. Something that could reach the store
for two operations and not for the third was not failing on the store. It was going somewhere else
for the third.

**Whether cart was struggling.** It was not. Its error ratio rose only to about 4.3%, because
`EmptyCart` is about one call in ten to cart and its other spans stayed clean, so cart itself never
paged. Its .NET runtime series reported without a gap and its latency rose only slightly. The one
new series was an exception counter: `ApplicationException`, first seen 30 seconds in, reached 91
by the fix and stopped there, while its socket-exception count went from 5 to over 26,000 in the
same minutes and also stopped at the fix. Cart was trying, and failing, to open connections.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart. The one thing in the failing span besides the error is the feature-flag lookup made just
before it, on the only operation that failed.

### Root cause

The `cartFailure` feature flag was turned on in the flag service. With it on, cart's `EmptyCart`
switches to a second store configured with an address that does not exist, tries to connect, and
fails. Adding to carts and reading them keep using the real store and keep working. Checkout
empties the cart after every placed order and ignores that call's failure, so every order
completed, each one slowed by the failing call and each customer's cart left full afterwards.
Checkout paged on the errors of a call it does not act on. Nothing was deployed or reconfigured,
and the cart's store was healthy. The fault was the flag's value.

### Resolution

The flag was turned back off. The flag service picks up the change on its own, so nothing was
restarted or redeployed. `EmptyCart` went back to the real store and succeeded at once, cart's
exception counters stopped climbing, and the error ratios drained with their windows. Checkout's
alert went out about a minute and a half after the fix, everything was quiet 2m00s after it, and
nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

- Onset to first page: **5m16s**. Services on the page: **one**, checkout, which was not at fault.
  By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** Checkout paged on its calls to cart.
  Cart, where the flag acts, stayed under the line at 4.3%.
- Would the page alone have led you to the right service? **No, but the traces do in one step.**
  Checkout's error traces all fail at the same call, `EmptyCart`, and nowhere else.
- **An error ratio can rise while nothing fails for the user.** Checkout's orders all went through.
  The errors were on a clean-up call it does not act on. Check what the failing span is before
  reading a caller's error ratio as a failure rate.
- **"Can't connect to the store" is not proof the store is down.** The same service was using the
  same store for its other operations in the same minute. A failure confined to one operation
  points at something that operation does differently.
- **Look at what the failing span did instead.** It made a feature-flag lookup and never reached the
  store. With nothing in change history, a flag evaluated on exactly the failing path is the change
  to look at.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-cart-flag-failure/`](../../evals/scenarios/artifacts/dev/v2-cart-flag-failure/) by `faultline-render`. [All bundles](README.md).
