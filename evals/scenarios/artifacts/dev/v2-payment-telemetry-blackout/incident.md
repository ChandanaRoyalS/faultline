---
origin: scenario:v2-payment-telemetry-blackout
split: dev
fault_class: bad_config
recorded_from: 2026-09-26T05:05:01+00:00
capability: cap:d2b243e0
onset_to_page: 8m20s
page_to_fix: 5m00s
fix_to_all_clear: 1m04s
---

# Payment service healthy, serving, and invisible in the traffic metric

## What was observed

The page was one alert, `ServiceNoTraffic` on **payment**, 8m20s after the trouble started.
Nothing else fired then and nothing fired afterwards: no error-rate alert and no latency alert
on any service.

Payment's request rate had fallen to zero about five minutes in. The alert waits three minutes
for that to hold. Everything around payment looked normal. Checkout was placing orders at its
usual rate with an error ratio of **zero** throughout, and its latency and frontend's did not
move. Email, accounting and fraud-detection, which only see an order once it has been paid for,
kept receiving orders.

That is the contradiction the page sets up. Payment was apparently receiving no requests, while
every order in the system went through it and came out paid.

## What was checked

**Whether payment was down.** It was not. Its runtime series (Node's event-loop delay and
utilisation, V8's garbage collections, 75 series in all) reported without a gap through the
whole incident. A process that had stopped, or was restarting, would have left holes. This one
was running the whole time.

**Its logs.** Payment was taking charges. It logged `Charge request received.` and `Transaction
complete.` for every order: 4 to 11 charges a minute through the incident, against 6 to 13 in the
minutes before it. Each record is a full structured log object of about forty lines, so a whole
window's read returns the start of one record and the end of another. A short window is the
practical read. Six seconds after the change the log also showed the service coming up again:
`payment gRPC server started on 0.0.0.0:50051`.

**Its callers' traces.** Every checkout trace in the window had a
`checkout/oteldemo.PaymentService/Charge` span of two to three milliseconds, without an error.
Its self-time was its whole duration: there was no payment span beneath it. Payment's own traces
for the window returned nothing at all. The calls were arriving and succeeding. The spans that
would have recorded payment's side of them were not.

**Whether this was the telemetry pipeline as a whole.** It was not. Every other service's traffic
series was normal, and their spans, checkout's calls into payment among them, were all arriving.
Only payment's own spans were missing.

**What that adds up to.** The traffic series is computed from spans. A service whose spans do not
reach the collector has no traffic series, however much traffic it serves. Payment was working;
its tracing was not reaching anyone.

**What changed.** One record, at the start: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on
payment`. That is where payment sends its spans. Its metrics go through a separate setting, which
had not changed, and that is why its runtime series kept arriving.

## Root cause

Payment's trace exporter was pointed at an address with nothing listening on it, so the service
stopped shipping spans. Nothing about the service itself changed. It kept accepting and
completing charges, kept logging them, and kept exporting its metrics. The traffic metric the
alert watches is built from those spans, so it went to zero and the alert fired on a service that
was working. The fault was in the telemetry path, not in the service.

## Resolution

The trace endpoint was set back to the collector and payment was recreated with it. Its spans
started arriving again, and the alert cleared 1m04s after the fix. No order had failed, so there
was nothing to replay or reconcile.

Class of fix: **config_revert**. One setting was wrong and it was set back. Nothing was deployed
and nothing needed restarting for its own sake.

## Detection notes

- Onset to first page: **8m20s**, most of it the traffic series draining and the alert's
  three-minute hold. Services on the page: **one**. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes, and misleadingly so.** Payment was the
  service whose configuration was wrong, but it was not failing. The alert says it is getting no
  traffic, and it was getting all of it.
- Would the page alone have led you to the right service? **Yes, and to the wrong conclusion.**
  `ServiceNoTraffic` reads as down or unreachable. Three independent signals say otherwise: the
  process's runtime series, its own log of charges, and its callers' successful calls into it.
- **Absence in a span-derived metric is not absence of traffic.** When a service's traffic
  disappears while its callers still succeed against it, ask first whether its spans are
  arriving, before asking whether it is running.
- **What separates this from a service that is really gone:** a dead or frozen payment would stop
  its runtime series and its log, and its callers would fail or hang. This one kept all three
  going. Only its own spans stopped.
