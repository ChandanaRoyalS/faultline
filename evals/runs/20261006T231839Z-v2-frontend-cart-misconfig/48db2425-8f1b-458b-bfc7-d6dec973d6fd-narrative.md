# Checkout PlaceOrder fails at the shipping-quote hop; mechanism unresolved

## What was visible, in order

Four alerts arrived effectively together: checkout, frontend, frontend-proxy and load-generator. That reads as one failure propagating up a single call chain, not four problems. Pages failed fast, not slowly — worth holding onto, because it eliminated a whole family of hypotheses.

By roughly T+10m the trace sample became the strongest evidence and has remained so. Ten failing checkout traces share an identical shape: PlaceOrder errors, and the only erroring child beneath it is checkout's own outbound HTTP POST to shipping's get-quote endpoint, issued from prepareOrderItemsAndShippingQuoteFromCart. That hop lasts 1-13ms; whole traces finish in 14-102ms with no timeout-length gap anywhere.

The central unresolved fact: shipping's server-side span for that same call is present in every trace, completes in 0.0-0.5ms, and carries no error. Shipping answered promptly and called it a success; checkout's client side recorded a failure. Upstream, frontend, frontend-proxy and load-generator merely relay the error with small self-times, which fully explains the simultaneous four-way alert.

One trap: checkout's root error message blames a bad HTTP status from the email service, yet no email-service span appears in any trace. Treat that string as suspect, not as a lead.

> Evidence `tr_144a6c7eb049`:

```
<tool_result id="tr_144a6c7eb049" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T22:51:46.664000+00:00..2026-10-06T23:23:39.723513+00:00">
service: checkout
10 trace(s) shown of 10 found, 150 spans; offsets are from each trace's root

trace 5f89e23d707e64ac  root load-generator/user_checkout_multi  102.4ms  started 2026-10-06T23:19:42.303764+00:00  15 spans
  +0.0ms load-generator/user_checkout_multi 102.4ms [self 72.2ms]
```

## The dead ends - read these before re-running anything

Checkout's own error metrics do not show the incident. The aggregate error ratio in the incident window averaged ~0.095 against a ~0.138 baseline — it went down. Samples were complete, so this is not a collection gap. The signal is spiky in both periods, so bursts prove nothing. This rules out a newly-failing path of material volume but is blind to a low-volume path failing completely, which is probably what we have.

Logs are useless on both sides. Queries for checkout and for shipping over the same ~32-minute window each returned zero lines of any severity. The tempting reading — they fell silent when they broke — is wrong: the silence covers thirty minutes of pre-onset time when traces prove both were serving. It is a collection or labeling gap, not a symptom. This is what cost us the mechanism.

Shipping's span metrics are likewise empty in both incident and baseline windows. Beware any summary reporting "no departure from baseline" here; with zero samples on both sides the comparison is undefined and carries no weight.

Change history found nothing adjacent to onset. Checkout's log is empty — but note the queried window runs *forward* ~24h from onset, not backward, so the pre-incident interval was never covered. Query backward if you revisit. Shipping's eight entries are all automated image-reference flaps ending on a revert, net delta zero, the last one ~8.2h before onset.

> Evidence `tr_00f4f66624d9`:

```
<tool_result id="tr_00f4f66624d9" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T22:51:46.664000+00:00..2026-10-06T23:23:39.723513+00:00" template="error-ratio" baseline="2026-10-06T22:19:53.604487+00:00..2026-10-06T22:51:46.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=128 mean=0.09463 min=0 max=0.5 sd=0.1591
  baseline window: n=128 mean=0.1384 min=0 max=0.5 sd=0.1859
```

> Evidence `tr_09b92440a2ac`:

```
<tool_result id="tr_09b92440a2ac" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-06T22:51:46.664000+00:00..2026-10-06T23:23:39.723513+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_09b92440a2ac>
```

> Evidence `tr_487c5096137d`:

```
<tool_result id="tr_487c5096137d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T23:21:46.664000+00:00..2026-10-06T23:23:39.723513+00:00" radius="candidate_cause" hops="1">
service: shipping
8 changes, ranked by suspicion
  #1  8.2h before onset  2026-10-06T15:06:57.278891+00:00  platform-automation  image reverted: image reference reverted on shipping
      ghcr.io/open-telemetry/demo:2.2.0-ad  ->  None
  #2  8.4h before onset  2026-10-06T14:57:02.735130+00:00  platform-automation  image updated: image reference updated on shipping
```

## Eliminated, and what remains open

Eliminated by the traces: cart and its Redis backend (all succeed, 0.3-12.3ms); payment, currency, product-catalog, ad, product-reviews and recommendation (no spans at all — checkout aborts before reaching them); any stall or timeout (millisecond-scale hops); shipping being slow or saturated (sub-millisecond, error-free server span); frontend and frontend-proxy as sources; and intermittency — ten of ten traces fail identically across single- and multi-item flows.

Established: the failing hop and its location. Not established: why. Confidence low, fix class none — there was nothing to roll back.

Open, in priority order. What status and body does get-quote actually return, and does it mention email? No shipping logs exist to answer this; it will need reproduction or new instrumentation. Why does checkout's error name email when no email span exists — uninstrumented synchronous call, or mislabeled message? And what changed at onset, given no adjacent change record for either service: an unrecorded flag flip, or a change on a service never queried, such as email.

> Evidence `tr_144a6c7eb049`:

```
<tool_result id="tr_144a6c7eb049" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T22:51:46.664000+00:00..2026-10-06T23:23:39.723513+00:00">
service: checkout
10 trace(s) shown of 10 found, 150 spans; offsets are from each trace's root

trace 5f89e23d707e64ac  root load-generator/user_checkout_multi  102.4ms  started 2026-10-06T23:19:42.303764+00:00  15 spans
  +0.0ms load-generator/user_checkout_multi 102.4ms [self 72.2ms]
```

> Evidence `tr_3266ccd76997`:

```
<tool_result id="tr_3266ccd76997" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-06T22:51:46.664000+00:00..2026-10-06T23:23:39.723513+00:00">
no log lines matched {service="shipping"} over this window
</tool_result:tr_3266ccd76997>
```

> Evidence `tr_d0e5acbb3108`:

```
<tool_result id="tr_d0e5acbb3108" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-06T22:51:46.664000+00:00..2026-10-06T23:23:39.723513+00:00" template="error-ratio" baseline="2026-10-06T22:19:53.604487+00:00..2026-10-06T22:51:46.664000+00:00">
service: shipping
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="shipping",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="shipping"}[5m]))
  incident window: no samples
  baseline window: no samples
```

