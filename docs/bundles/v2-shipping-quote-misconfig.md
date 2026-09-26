# Shipping service pointed at a quote service that does not resolve

## The scenario

| | |
|---|---|
| scenario | `v2-shipping-quote-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `shipping` via `v2-shipping-quote-misconfig` |
| time to page | 4m46s |
| steady state captured | 300s |
| capture window | 2026-09-26T05:29:41+00:00 → 2026-09-26T05:51:29+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m46s |
| `t_revert` | T+9m46s |
| all clear | T+14m48s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m30s | `checkout` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+4m30s | `shipping` | ServiceHighErrorRate | 10.0 min | **paged** |
| T+7m30s | `accounting` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m30s | `email` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m30s | `fraud-detection` | ServiceHighErrorRate | 2.0 min | joined later |
| T+7m30s | `payment` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m30s | `quote` | ServiceNoTraffic | 3.0 min | joined later |
| T+8m30s | `fraud-detection` | ServiceHighLatency | 1.0 min | joined later |
| T+9m30s | `frontend` | ServiceHighErrorRate | 2.0 min | joined later |
| T+9m30s | `frontend-proxy` | ServiceHighErrorRate | 2.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="shipping"}` |

`logs/shipping.txt` — 9 lines.

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

The page was two alerts in the same moment, `ServiceHighErrorRate` on **checkout** and on
**shipping**, 4m46s after the trouble started. Checkout's error ratio had been zero. It rose from
about a minute and a half in and settled at roughly a quarter of its spans. Shipping's went to
**100%**: every span it produced was an error. Checkout's latency did not rise. It fell, from
about 28ms to under 10ms, because an order that fails early finishes fast.

About three minutes after the page, four services went quiet at once: `ServiceNoTraffic` on
**quote**, payment, email and accounting. Fraud-detection fired error and latency alerts on the
few spans it still made. About five minutes after the page, frontend and frontend-proxy crossed
their error thresholds at 5-6%, carrying checkout's failures up to the storefront. The storefront
itself browsed normally. Only orders were failing.

### What was checked

**The error text, because it was the first thing a responder would read.** Frontend's log and
checkout's error span both said the same thing: `shipping quote failure: failed POST to email
service: expected 200, got 500`. That sentence names two services. The email service is the dead
end it invites: email was not being called at all, because no order got far enough to send a
confirmation. The words that matter are the first three. The message is checkout's own wording
for shipping answering with an error status, and it names the wrong service after the colon.

**The traces, below checkout.** Every failing checkout trace had the same shape.
`checkout/oteldemo.CheckoutService/PlaceOrder` errored; beneath it, checkout's HTTP call to
shipping errored; beneath that, `shipping//get-quote` answered `Internal Server Error`; and beneath
that, shipping's own client call, `shipping/POST quote-gone`, errored with `Connect(Resolver(...
"failed to lookup address information: Name or service not known"))`. The trace tool named that
last span as the degrading hop. The call's name carries the host it was trying to reach,
`quote-gone`, and the error says that name does not resolve. Everything else in the trace, the
cart, the catalog and currency, answered normally.

**Whether shipping was down.** It was not. It was answering every request, in a few
milliseconds, with an error. Shipping's spans are the only evidence of that: it exports no
runtime series, and its logs go only to a store none of the tools read, so there is no log stream
for it at all. Here that costs nothing, because shipping's own error spans show it running and
failing. The question of whether it was alive does not arise.

**Quote, which went quiet.** Quote is called only by shipping. Its request rate fell to zero
about four and a half minutes in, and its own log, which records every `POST /getquote`, went from
four to ten requests a minute to none, and stayed at none until the fix. Its latency and error
ratio had no new values. A quiet quote looks like a failed quote, and it was healthy: nothing was
reaching it, because the one service that calls it was calling a different name.

**The other quiet services.** Payment, email and accounting are only reached by an order that has
been priced. Nothing got past the quote step, so they had nothing to do. Their silence was a
consequence, not three more failures.

**What changed.** One record, at the start: `QUOTE_ADDR updated on shipping`. That is the
address the failing call was built from. Nothing had changed on checkout, on quote, or on any
service that alerted apart from shipping.

### Root cause

Shipping's `QUOTE_ADDR` was changed to a host that does not resolve. Shipping reads the address
on every request, so it kept running and kept answering, and every quote request failed at the
name lookup before it left the container. Without a shipping quote, checkout cannot price an
order, so every order failed at that step. Both services paged on errors: shipping on its failed
calls to quote, checkout on its failed calls to shipping. Quote was healthy and went quiet because
nothing reached it. No service's code was wrong. The fault was the address shipping held for
quote.

### Resolution

`QUOTE_ADDR` was set back to the quote service's address and shipping was recreated with it.
Quote's requests resumed within a minute, orders completed again, and the error ratios drained
with their five-minute windows. Everything was quiet 5m02s after the fix, and nothing fired
during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

- Onset to first page: **4m46s**. Services on the page: **two**, and one of them was the service
  that changed. By the fix: **ten alerts across nine services**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Partly.** Shipping paged, and it is the
  service whose setting was wrong. Checkout paged beside it with a larger share of the traffic,
  and was only reporting shipping's failures.
- Would the page alone have led you to the right service? **Yes, but not to the cause.** The cause
  is in the deepest span of the trace, `POST quote-gone` failing to resolve, and in the change
  record. The page and the metrics do not name the address.
- **An error message can name the wrong service.** `failed POST to email service` sat above a
  shipping failure in every trace. Read the span tree, not only the message at its top.
- **A quiet service beside a failing one is often the victim, not the cause.** Quote went to zero
  requests and did nothing wrong. Ask who calls it, and whether they still can.
- **When a target has no logs and no runtime series, its spans are the only evidence of it.**
  Shipping's reachability is `[]`: nothing the tools read can say whether it was idle or absent.
  This incident never needs to ask, because shipping's own spans show it running.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-shipping-quote-misconfig/`](../../evals/scenarios/artifacts/dev/v2-shipping-quote-misconfig/) by `faultline-render`. [All bundles](README.md).
