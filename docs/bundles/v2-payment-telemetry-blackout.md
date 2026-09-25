# Payment service healthy, serving, and invisible in the traffic metric

## The scenario

| | |
|---|---|
| scenario | `v2-payment-telemetry-blackout` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `payment` via `v2-payment-telemetry-blackout` |
| time to page | 7m49s |
| steady state captured | 300s |
| capture window | 2026-09-25T00:08:04+00:00 → 2026-09-25T00:28:43+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+7m49s |
| `t_revert` | T+12m49s |
| all clear | T+13m39s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+7m30s | `payment` | ServiceNoTraffic | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="payment"}` |

`logs/payment.txt` — 509 lines.

## A look at the logs

From `logs/payment.txt` (---- onset 2026-09-25T00:13:04+00:00 ----):

```
2026-09-25T00:12:49+00:00      cardType: 'visa',
2026-09-25T00:12:49+00:00      lastFourDigits: '8031',
2026-09-25T00:12:49+00:00      amount: {
2026-09-25T00:12:49+00:00        units: { low: 742, high: 0, unsigned: false },
2026-09-25T00:12:49+00:00        nanos: 349226003,
2026-09-25T00:12:49+00:00        currencyCode: 'CAD'
2026-09-25T00:12:49+00:00      },
2026-09-25T00:12:49+00:00      loyalty_level: 'silver'
2026-09-25T00:12:49+00:00    }
2026-09-25T00:12:49+00:00  }
2026-09-25T00:12:54+00:00  {
2026-09-25T00:12:54+00:00    resource: {
```

_488 further lines are in the bundle._

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

The page was one alert, `ServiceNoTraffic` on **payment**, 7m49s after the trouble started.
Nothing else fired then and nothing fired afterwards: no error-rate alert and no latency
alert on any service.

Payment's request rate had fallen to zero about four and a half minutes in. The alert waits
three minutes for that to hold. Everything around payment looked normal. Checkout was placing
orders at its usual rate with an error ratio of **zero** throughout, and its latency and
frontend's did not move. Email, accounting and fraud-detection, which only see an order once
it has been paid for, kept receiving orders.

That is the contradiction the page sets up. Payment was apparently receiving no requests,
while every order in the system went through it and came out paid.

### What was checked

**Whether payment was down.** It was not. Its runtime series (Node's event-loop delay and
utilisation, V8's garbage collections, 75 series in all) reported without a gap through the
whole incident. A process that had stopped, or was restarting, would have left holes. This one
was running the whole time.

**Its logs.** Payment was taking charges. It logged `Charge request received.` and `Transaction
complete.` for every order: 4 to 13 charges a minute through the incident, the same range as
the minutes before it. Each record is a full structured log object of about forty lines, so a
short window is the practical read; a long one is mostly the middle of records. Straight after
the change the log also showed the service coming up again: `payment gRPC server started on
0.0.0.0:50051`.

**Its callers' traces.** Every checkout trace in the window had a
`checkout/oteldemo.PaymentService/Charge` span of one to two milliseconds, without an error. Its
self-time was its whole duration: there was no payment span beneath it. Payment's own traces for
the window returned nothing at all. The calls were arriving and succeeding. The spans that
would have recorded payment's side of them were not.

**Whether this was the telemetry pipeline as a whole.** It was not. Every other service's traffic
series was normal, and their spans, checkout's calls into payment among them, were all arriving.
Only payment's own spans were missing.

**What that adds up to.** The traffic series is computed from spans. A service whose spans do not
reach the collector has no traffic series, however much traffic it serves. Payment was working;
its tracing was not reaching anyone.

**What changed.** One record, at the start: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on
payment`. That is where payment sends its spans. Its metrics go through a separate setting,
which had not changed, and that is why its runtime series kept arriving.

### Root cause

Payment's trace exporter was pointed at an address with nothing listening on it, so the service
stopped shipping spans. Nothing about the service itself changed. It kept accepting and
completing charges, kept logging them, and kept exporting its metrics. The traffic metric the
alert watches is built from those spans, so it went to zero and the alert fired on a service
that was working. The fault was in the telemetry path, not in the service.

### Resolution

The trace endpoint was set back to the collector and payment was recreated with it. Its spans
started arriving again, and the alert cleared 50 seconds after the fix. No order had failed, so
there was nothing to replay or reconcile.

Class of fix: **config_revert**. One setting was wrong and it was set back. Nothing was deployed
and nothing needed restarting for its own sake.

### Detection notes

- Onset to first page: **7m49s**, most of it the traffic series draining and the alert's
  three-minute hold. Services on the page: **one**. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes, and misleadingly so.** Payment was
  the service whose configuration was wrong, but it was not failing. The alert says it is getting
  no traffic, and it was getting all of it.
- Would the page alone have led you to the right service? **Yes, and to the wrong conclusion.**
  `ServiceNoTraffic` reads as down or unreachable. Three independent signals say otherwise: the
  process's runtime series, its own log of charges, and its callers' successful calls into it.
- **Absence in a span-derived metric is not absence of traffic.** When a service's traffic
  disappears while its callers still succeed against it, ask first whether its spans are
  arriving, before asking whether it is running.
- **What separates this from a service that is really gone:** a dead or frozen payment would
  stop its runtime series and its log, and its callers would fail or hang. This one kept all
  three going. Only its own spans stopped.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-payment-telemetry-blackout/`](../../evals/scenarios/artifacts/dev/v2-payment-telemetry-blackout/) by `faultline-render`. [All bundles](README.md).
