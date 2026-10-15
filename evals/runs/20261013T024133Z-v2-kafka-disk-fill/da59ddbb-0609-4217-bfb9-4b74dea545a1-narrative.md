# Checkout stalls and accounting goes quiet: a shared message-broker endpoint stops resolving

## What you would have seen first

Two pages arrived about two minutes apart. Checkout alerted first (call this T+0); accounting followed at roughly T+2m. The declared blast radius was ten services and the severity was critical, but only those two services ever produced a page.

The first thing worth knowing is that the alert time is not the onset time. Checkout's span error ratio has a single detected change point about 24 minutes before the page (T-24m), and the elevation is sustained from there: 132 samples across the window with a mean roughly fifteen times baseline and a peak at half of all calls. So checkout was already degrading for most of an hour's worth of baseline before anyone was told. If you anchor a theory to the page time you will be looking at the wrong 24 minutes.

The second thing: checkout was degraded, not down. A clear majority of requests still succeeded throughout. Anyone who opened with "checkout is hard-failing" burned time.

> Evidence `tr_51d93e2ba9bd`:

```
<tool_result id="tr_51d93e2ba9bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" template="error-ratio" baseline="2026-10-13T01:44:19.931097+00:00..2026-10-13T02:17:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=132 mean=0.1142 min=0 max=0.5 sd=0.1766
  baseline window: n=132 mean=0.007583 min=0 max=0.1736 sd=0.02966
```

## The trace is the whole story

Sampled checkout traces resolve this faster than anything else. In every sampled trace, essentially the entire request duration sits in one span: the asynchronous order-publish from the PlaceOrder handler. That span is marked ERROR and holds 93-102 seconds of self time — effectively 100% of the trace. Checkout's own handler self time is one to two milliseconds.

All the synchronous children — cart, currency, product-catalog, payment, shipping, quote, email, flag evaluation — complete cleanly in single-digit to low-tens of milliseconds. The product-catalog SQL spans finish under three milliseconds. None of them carry error status. Checkout does all of its normal work, succeeds at it, and then parks on the publish.

One trace shows the raw failure before the breaker caught it: the broker hostname fails to resolve and no broker connection can be made. The other three show an open circuit breaker instead, which is the breaker reacting to repeated connection failures rather than an independent problem. That distinction matters — it is the single piece of evidence that stops you from chasing the breaker as a cause in its own right.

The client-facing spans (load-generator, frontend-proxy ingress) error at about fifteen seconds. That is the proxy's own timeout firing while checkout is still blocked downstream. It is also the mechanical explanation for checkout's roughly fifteenfold error-ratio rise: every stalled publish eventually becomes a proxy abort. The errors do not originate at the proxy.

The pattern holds across both single-item and multi-item checkout flows, so the failure is not request-shape dependent.

> Evidence `tr_33e0a5486dc2`:

```
<tool_result id="tr_33e0a5486dc2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 569422ded7e1c9aa  root load-generator/user_checkout_single  15017.7ms  started 2026-10-13T02:48:25.689687+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 15017.7ms [self 15.7ms]
```

> Evidence `tr_51d93e2ba9bd`:

```
<tool_result id="tr_51d93e2ba9bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" template="error-ratio" baseline="2026-10-13T01:44:19.931097+00:00..2026-10-13T02:17:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=132 mean=0.1142 min=0 max=0.5 sd=0.1766
  baseline window: n=132 mean=0.007583 min=0 max=0.1736 sd=0.02966
```

## Accounting: the metric lies by omission

Accounting's span error ratio is flat at exactly zero through the whole window — 96 samples, zero mean, zero standard deviation, indistinguishable from baseline. It is tempting to read that as health and move on. Do not.

The logs say the opposite. From about T+2m26s to the end of the retrieved window, accounting's consumer client emits a continuous stream of broker-connectivity errors: both brokers unreachable, at high frequency, with suppressed-duplicate counters showing hard retry churn. The stated cause in the client's own words is name-resolution failure for the bootstrap hostname, hitting both the broker connection thread and the group-coordinator thread.

Once you know that, the flat zero makes sense: the consumer never fetches a record, so it never creates a server-handled span, so there is nothing to mark as failed. The error ratio measures work that isn't happening. Note also that 36 of 96 intervals in the window have no defined ratio at all — but the same 36 appear in the baseline, so sparse traffic is this service's normal shape and not an onset signal.

> Evidence `tr_0aaae1342ea8`:

```
<tool_result id="tr_0aaae1342ea8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" template="error-ratio" baseline="2026-10-13T01:44:19.931097+00:00..2026-10-13T02:17:16.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=96 mean=0 min=0 max=0 sd=0
  baseline window: n=96 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_42eb28a5deb4`:

```
<tool_result id="tr_42eb28a5deb4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-13T02:17:20.440284+00:00  info: Accounting.Consumer[174880625]
2026-10-13T02:17:20.440428+00:00        Order details: { "orderId": "38256d9d-c6ac-11f1-91d4-7edc4251f9f7", "shippingTrackingId": "dd2d48de-c9b9-43c6-ba0e-ff7351a3d171", "shippingCost": { "currencyCode": "USD", "units": "98", "nanos": 890000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "6E92ZMYYFZ", "quantity": 6 }, "cost": { "currencyCode": "USD", "units": "69", "nanos": 950000000 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 5 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-10-13T02:17:20.452767+00:00  fail: Accounting.Consumer[0]
2026-10-13T02:17:20.452780+00:00        Order parsing failed:
```

## Why the two symptoms are one failure

A producer written in one runtime and a consumer written in another, with no code path in common, both fail at the same hostname with the same resolution error, within minutes of each other. Neither has any recorded change against it in the preceding twenty-four hours. That coincidence is doing the real work in this conclusion: the problem is the reachability of the broker endpoint, not a defect in either caller.

The fix class is reconnect — restore name resolution and broker reachability for the bootstrap hostname, and both clients should recover on their own retry loops. Confidence is medium, for the reasons in the open items below.

> Evidence `tr_33e0a5486dc2`:

```
<tool_result id="tr_33e0a5486dc2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 569422ded7e1c9aa  root load-generator/user_checkout_single  15017.7ms  started 2026-10-13T02:48:25.689687+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 15017.7ms [self 15.7ms]
```

> Evidence `tr_42eb28a5deb4`:

```
<tool_result id="tr_42eb28a5deb4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-13T02:17:20.440284+00:00  info: Accounting.Consumer[174880625]
2026-10-13T02:17:20.440428+00:00        Order details: { "orderId": "38256d9d-c6ac-11f1-91d4-7edc4251f9f7", "shippingTrackingId": "dd2d48de-c9b9-43c6-ba0e-ff7351a3d171", "shippingCost": { "currencyCode": "USD", "units": "98", "nanos": 890000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "6E92ZMYYFZ", "quantity": 6 }, "cost": { "currencyCode": "USD", "units": "69", "nanos": 950000000 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 5 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-10-13T02:17:20.452767+00:00  fail: Accounting.Consumer[0]
2026-10-13T02:17:20.452780+00:00        Order parsing failed:
```

> Evidence `tr_31460f5b3278`:

```
<tool_result id="tr_31460f5b3278" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T02:47:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_31460f5b3278>
```

> Evidence `tr_9abf8eaf5170`:

```
<tool_result id="tr_9abf8eaf5170" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T02:47:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" radius="seed" hops="0">
no changes recorded for accounting over this window
</tool_result:tr_9abf8eaf5170>
```

## Dead ends, kept on purpose

These were checked and came back empty or negative. They are listed so the next responder does not re-run them.

Change history for checkout across a full day: nothing. No release, no config push, no dependency or infrastructure edit. There is no rollback to perform for checkout.

Change history for accounting across the same day: also nothing. No deploy, no config edit, no credential or secret rotation. Rollback is likewise unavailable here.

Checkout's logs: a query for every line under the checkout service label returned zero lines across the entire window — including the early, healthy portion. That is almost certainly a collection or labeling gap (shipper down, label renamed, index gap) rather than genuine silence. The result was empty, not truncated. Any theory that depends on reading checkout's own exception text cannot be sourced from here.

Payment metrics: the error-ratio query returned no samples in either the incident or the baseline window. This is a standing instrumentation gap, not telemetry going dark at onset. Critically, this does not clear payment — an empty result is not a flat result. If payment needs to be excluded, it needs a different metric source or label set.

Accounting's Entity Framework exception: at the very start of the window (about T-30m) accounting was consuming and processing an order normally and logged an application-level order-parsing error from the entity-update pipeline. It is a real, separate defect in the consume path, roughly 32 minutes earlier than the connectivity loss, and it is not the cause of this incident. It looks relevant and isn't.

Also ruled out along the way: a slow or erroring synchronous dependency of checkout; checkout being CPU- or GC-starved; the frontend-proxy or load-generator as origin; a database problem behind the errors; the circuit breaker opening spuriously; the brokers being up but rejecting or throttling the client at the protocol layer (the error precedes connection establishment); and consumer lag from slow processing or a stuck message (nothing is being fetched at all).

> Evidence `tr_31460f5b3278`:

```
<tool_result id="tr_31460f5b3278" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T02:47:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_31460f5b3278>
```

> Evidence `tr_9abf8eaf5170`:

```
<tool_result id="tr_9abf8eaf5170" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T02:47:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" radius="seed" hops="0">
no changes recorded for accounting over this window
</tool_result:tr_9abf8eaf5170>
```

> Evidence `tr_af22c0686fed`:

```
<tool_result id="tr_af22c0686fed" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_af22c0686fed>
```

> Evidence `tr_3a19a9a4a37e`:

```
<tool_result id="tr_3a19a9a4a37e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" template="error-ratio" baseline="2026-10-13T01:44:19.931097+00:00..2026-10-13T02:17:16.664000+00:00">
service: payment
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment"}[5m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_42eb28a5deb4`:

```
<tool_result id="tr_42eb28a5deb4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-13T02:17:20.440284+00:00  info: Accounting.Consumer[174880625]
2026-10-13T02:17:20.440428+00:00        Order details: { "orderId": "38256d9d-c6ac-11f1-91d4-7edc4251f9f7", "shippingTrackingId": "dd2d48de-c9b9-43c6-ba0e-ff7351a3d171", "shippingCost": { "currencyCode": "USD", "units": "98", "nanos": 890000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "6E92ZMYYFZ", "quantity": 6 }, "cost": { "currencyCode": "USD", "units": "69", "nanos": 950000000 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 5 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-10-13T02:17:20.452767+00:00  fail: Accounting.Consumer[0]
2026-10-13T02:17:20.452780+00:00        Order parsing failed:
```

> Evidence `tr_33e0a5486dc2`:

```
<tool_result id="tr_33e0a5486dc2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 569422ded7e1c9aa  root load-generator/user_checkout_single  15017.7ms  started 2026-10-13T02:48:25.689687+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 15017.7ms [self 15.7ms]
```

## Left open

The broker tier itself was never directly examined. Whether the brokers are running but unreachable, or gone entirely — which would also explain the missing DNS record — is unresolved. That is the first thing to check on a repeat.

Onset is not pinned. Checkout's change point is about 24 minutes before its page; the earliest accounting broker error we actually retrieved is about 26 minutes after that, at roughly T+2m26s. Accounting's log result was truncated to the oldest 8 and newest 32 lines of the window, so lines around the accounting alert time were never returned. The true start of the accounting-side failure may be considerably earlier than what is recorded here.

Two services have no usable self-account: checkout produced no logs at all for the window, and payment produced no metric samples in either window. Eight edges in the declared blast radius were crossed without measurement.

> Evidence `tr_51d93e2ba9bd`:

```
<tool_result id="tr_51d93e2ba9bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" template="error-ratio" baseline="2026-10-13T01:44:19.931097+00:00..2026-10-13T02:17:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=132 mean=0.1142 min=0 max=0.5 sd=0.1766
  baseline window: n=132 mean=0.007583 min=0 max=0.1736 sd=0.02966
```

> Evidence `tr_42eb28a5deb4`:

```
<tool_result id="tr_42eb28a5deb4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-13T02:17:20.440284+00:00  info: Accounting.Consumer[174880625]
2026-10-13T02:17:20.440428+00:00        Order details: { "orderId": "38256d9d-c6ac-11f1-91d4-7edc4251f9f7", "shippingTrackingId": "dd2d48de-c9b9-43c6-ba0e-ff7351a3d171", "shippingCost": { "currencyCode": "USD", "units": "98", "nanos": 890000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "6E92ZMYYFZ", "quantity": 6 }, "cost": { "currencyCode": "USD", "units": "69", "nanos": 950000000 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 5 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-10-13T02:17:20.452767+00:00  fail: Accounting.Consumer[0]
2026-10-13T02:17:20.452780+00:00        Order parsing failed:
```

> Evidence `tr_af22c0686fed`:

```
<tool_result id="tr_af22c0686fed" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_af22c0686fed>
```

> Evidence `tr_3a19a9a4a37e`:

```
<tool_result id="tr_3a19a9a4a37e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-13T02:17:16.664000+00:00..2026-10-13T02:50:13.396903+00:00" template="error-ratio" baseline="2026-10-13T01:44:19.931097+00:00..2026-10-13T02:17:16.664000+00:00">
service: payment
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment"}[5m]))
  incident window: no samples
  baseline window: no samples
```

