# A feature flag makes checkout charge cards at an address that does not exist

## The scenario

| | |
|---|---|
| scenario | `v2-payment-flag-unreachable` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `checkout` via `v2-payment-flag-unreachable` |
| time to page | 4m00s |
| steady state captured | 300s |
| capture window | 2026-09-26T22:36:46+00:00 → 2026-09-26T22:56:47+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m00s |
| `t_revert` | T+9m00s |
| all clear | T+13m01s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m00s | `checkout` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+8m00s | `accounting` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `email` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m00s | `fraud-detection` | ServiceNoTraffic | 1.0 min | joined later |
| T+8m00s | `payment` | ServiceNoTraffic | 2.0 min | joined later |

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

The page was one alert, `ServiceHighErrorRate` on **checkout**, 4m00s after the trouble started.

Checkout's error ratio had been zero. It was about 2% a minute in, 10% at three minutes and 18% at
four, and from five minutes it held at 20-22%. Its latency did not move: its p95 stayed between
about 32 and 41ms, as it had been. The storefront's error ratios followed it up without crossing
the line. The frontend reached 4.7%, frontend-proxy 4.9% and the load generator 2.7%. Browsing and
the cart worked. Checking out did not.

Behind checkout, traffic drained away. Payment's request rate fell to zero with no errors of its
own, and so did email's, accounting's and fraud-detection's. Four minutes after the page, a minute
before the fix, `ServiceNoTraffic` fired on all four together. In front of the failure, traffic
held: cart, the product catalog, currency and quote kept their usual rates. Shipping kept its
quotes and lost its other work, falling from about 0.45 spans a second to about 0.25.

Five alerts on five services by the fix. Nothing fired after it.

### What was checked

**Checkout's own log, the service on the page.** It has none the tools can read. Its errors
reach a log only through the storefront, which receives them.

**The frontend's log.** From the first minute it logged `Error: 13 INTERNAL: failed to charge
card: could not charge the card: rpc error: code = Unavailable desc = name resolver error:
produced zero addresses`. The first came within seconds of onset, then one to ten a minute, 77 in
all, until the minute of the fix, with none before and none after. It names a step, charging the
card, and that step belongs to the payment service.

**Checkout's traces.** Every failing order had the same shape. `oteldemo.CheckoutService/PlaceOrder`
errored with that message. Beneath it, the order was prepared normally: the cart read, the product
lookups, the currency conversions and the shipping quote all succeeded, each in a few
milliseconds. Then the call to `oteldemo.PaymentService/Charge` failed in **no measurable time**,
0.0ms, with `name resolver error: produced zero addresses`, and there was **no payment span beneath
it**. Nothing after the charge ran: no shipment, no confirmation email, no emptying of the cart,
no order published. Orders failed within 14 to 70ms, which is why checkout's latency did not
rise.

**Whether payment was down.** This is where the error text points, and it was not. Payment's log
recorded `Charge request received.` and `Transaction complete.` 5 to 12 times a minute before the
trouble, and **none** from the first minute on. It logged no errors, raised no error spans, and
its process stayed up and steady in memory. Payment was not refusing charges. None were reaching
it.

**What the error says.** `name resolver error: produced zero addresses` means checkout could not
turn the name it was calling into an address. The call did not reach a network, which is why it
took no time. In the same orders, the same process resolved and called cart, the catalog, currency
and shipping without trouble. Something about the one name checkout used for the charge did not
exist.

**Checkout's health.** Its Go runtime series, nine of them, reported without a gap, and it
restarted nothing. One series moved. Checkout's goroutine count had been about 80. From a minute
or so in it climbed by about thirty a minute, to 322 by the fix, and its stack memory rose from 1.7
to 2.6MB. Every failed charge was leaving something behind that kept running. A client that called
payment over its usual connection would not do that. One built afresh for each charge, and never
closed, would.

**Fraud-detection's one span during the silence.** A minute before the fix, fraud-detection
reported a single span, in error and ten minutes long: its stream to the flag service closing on
the server's ten-minute timeout, as it does at rest. It was a routine reconnect, not work, and it
cleared fraud-detection's no-traffic alert a minute before the orders came back. A dead end.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart, on checkout, on payment or anywhere else. Checkout's configured address for payment had
not changed, and payment was where it had always been. The address checkout used for the charge
came from somewhere that changes without a record, and on this world that is a feature flag.

### Root cause

The `paymentUnreachable` feature flag was turned on in the flag service. With it on, checkout
builds a new payment client for each charge on an address that does not exist, instead of using
the one configured for the payment service. Every order was prepared and then failed at the
charge, before shipping, the confirmation email or the order's publication. Payment was healthy
and was never called. Each of those clients stayed open and kept its goroutines, so checkout
accumulated them for as long as the flag was on. Nothing was deployed or reconfigured, and
checkout behaved exactly as written. The fault was the flag's value.

### Resolution

The flag was turned back off. The flag service picks up the change on its own, so nothing was
restarted or redeployed. Charges resumed within the minute: payment logged its first charge seconds
after the fix, and 6 to 12 a minute after that. Email, accounting and fraud-detection followed
with the orders, the no-traffic alerts cleared a minute after the fix, and checkout's error ratio
drained with its window. Everything was quiet 4m01s after the fix, and nothing fired during
recovery.

The goroutines did not go away. Nine minutes after the fix checkout still held 354 of them, with its
stack memory still at 2.6MB. Orders were unaffected, but only a restart releases them, and checkout
was restarted before the world was used again.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

- Onset to first page: **4m00s**. Services on the page: **one**, checkout, the service whose code
  reads the flag. By the fix: **five**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, but its error text points away from
  it. "Could not charge the card" and `Unavailable` read as the payment service being down.
- Would the page alone have led you to the right service? **Yes, and then the error points to the
  wrong one.** Payment's own log and its missing server span show it was never asked.
- **The quiet services mark where the chain breaks.** Everything before the charge kept its traffic
  and everything after it went quiet. The failure sits between the last busy step and the first
  quiet one.
- **A call that fails in no time never left the caller.** A down or overloaded server makes a call
  wait or be refused. `produced zero addresses` in 0.0ms means the caller was dialing a name that
  does not resolve, while resolving its other dependencies in the same request.
- **A count that climbs with every failure and stays after the fix is a leak, not a load.** It
  says the failing path builds something per call. It also says the fix leaves a residue that a
  cleared page does not show.
- **An empty change history is not "nothing changed".** When a caller reaches a healthy service at
  a different address than it is configured with, and nothing is recorded, look for the switch
  that can change its behaviour without a deploy.

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-payment-flag-unreachable/`](../../evals/scenarios/artifacts/holdout/v2-payment-flag-unreachable/) by `faultline-render`. [All bundles](README.md).
