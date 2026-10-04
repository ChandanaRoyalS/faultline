# Checkout order failures traced to payment charge rejections for one customer segment

## What was visible, in order

The page covered checkout, frontend, load-generator and payment, with triage claiming thirteen services affected. The user-visible symptom was uniform: order placement failing with 'failed to charge card'. Checkout was the entry point.

Roughly T-11m, payment's workload object was created by platform automation. Around T-9m a checkout pod started, polled for a Kafka broker for about 31 seconds, then connected successfully and fell silent. At about T-1m the earliest sampled failing trace showed checkout's Charge call dying in ~1.1ms on a refused dial to a payment endpoint on port 8080, with no payment-side span at all.

From roughly T+0 (about 15:11) payment began emitting a repeating application-level rejection citing an invalid token, every ten to thirty seconds, steady and not tapering through the end of the window. Charge requests kept arriving at several per minute — payment was up and answering, rejecting rather than dropping. Checkout wrapped the rejection and the layers above reproduced the text unchanged.

Trace evidence settled the direction: the deepest span bearing an originating error is checkout's call to payment's Charge. Those spans are fast — 3.6–4.2ms checkout-side, 1.2–1.7ms inside payment — so this is a business-logic decline, not a timeout or saturation. The rejections carry a gold loyalty-tier attribute, and payment's own error lines carry the same tier value every time. The payment span on that path also carries a flag evaluation.

> Evidence `tr_60cfa54aac6a`:

```
<tool_result id="tr_60cfa54aac6a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00">
selector: {namespace="astronomy-shop",pod=~"checkout-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T15:10:02+00:00  waiting for kafka
2026-10-03T15:10:04+00:00  waiting for kafka
2026-10-03T15:10:06+00:00  waiting for kafka
2026-10-03T15:10:08+00:00  waiting for kafka
```

> Evidence `tr_0d3e77248cba`:

```
<tool_result id="tr_0d3e77248cba" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-03T14:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00">
service: checkout
6 trace(s) shown of 14 found, 200 spans; offsets are from each trace's root

trace 6dcefa8587bac50b  root load-generator/user_checkout_single  1464.9ms  started 2026-10-03T15:10:56.928615+00:00  21 spans, 1 unattached
  +0.0ms load-generator/user_checkout_single 1464.9ms [self 0.0ms]
```

> Evidence `tr_5d6996bcab13`:

```
<tool_result id="tr_5d6996bcab13" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:43:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" contains="token">
selector: {namespace="astronomy-shop",pod=~"payment-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "token"
2026-10-03T15:11:17+00:00        stack: 'Error: Payment request failed. Invalid token. app.loyalty.level=gold\n' +
2026-10-03T15:11:17+00:00        message: 'Payment request failed. Invalid token. app.loyalty.level=gold',
2026-10-03T15:11:17+00:00    body: 'Payment request failed. Invalid token. app.loyalty.level=gold',
2026-10-03T15:11:43+00:00        stack: 'Error: Payment request failed. Invalid token. app.loyalty.level=gold\n' +
```

> Evidence `tr_407873775724`:

```
<tool_result id="tr_407873775724" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:43:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" contains="Charge">
selector: {namespace="astronomy-shop",pod=~"payment-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "Charge"
2026-10-03T15:11:17+00:00    body: 'Charge request received.',
2026-10-03T15:11:43+00:00    body: 'Charge request received.',
2026-10-03T15:11:45+00:00    body: 'Charge request received.',
2026-10-03T15:11:54+00:00    body: 'Charge request received.',
```

## Dead ends worth not repeating

Checkout's own logs produced nothing. An hour-wide query returned one startup sequence, no error lines, no exceptions, and complete silence across the timestamp of interest. The Kafka polling looks alarming and is not: it resolved and never recurred, so neither a restart loop nor ongoing unreachability. The selector matched real content and was not truncated, so the silence is real.

Checkout's other dependencies were clean. Cart/valkey, product-catalog/postgresql, shipping, quote and currency all completed successfully in every failing trace, none with error status. A database or cache slowdown is retired.

The change log was the most tempting and most misleading lead. Checkout and payment each have exactly two records in 24 hours, both by platform automation, both about three minutes before onset: creation of the workload and of the service object. No rollout, no image bump, no operator edit, no recorded toggle. The three-minute proximity reads as causal and is not — these are first-provisioning records. The pipeline is confirmed reporting for both services, so the emptiness is genuine.

Metrics on both services are unusable. Checkout resolves to one defined sample near 19%, payment to one at 0.5; three of four intervals in each window are undefined, meaning no traffic rather than no errors. Both baseline windows returned zero samples, so the apparent move is a comparison against absence. Do not quote onset shape or blast-radius magnitude from these.

Payment's charge-path logging returned only the 'request received' event — no decline reason, no branch decision, no tier field. The segmentation hypothesis cannot be confirmed from payment's own logs.

> Evidence `tr_60cfa54aac6a`:

```
<tool_result id="tr_60cfa54aac6a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00">
selector: {namespace="astronomy-shop",pod=~"checkout-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T15:10:02+00:00  waiting for kafka
2026-10-03T15:10:04+00:00  waiting for kafka
2026-10-03T15:10:06+00:00  waiting for kafka
2026-10-03T15:10:08+00:00  waiting for kafka
```

> Evidence `tr_0d3e77248cba`:

```
<tool_result id="tr_0d3e77248cba" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-03T14:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00">
service: checkout
6 trace(s) shown of 14 found, 200 spans; offsets are from each trace's root

trace 6dcefa8587bac50b  root load-generator/user_checkout_single  1464.9ms  started 2026-10-03T15:10:56.928615+00:00  21 spans, 1 unattached
  +0.0ms load-generator/user_checkout_single 1464.9ms [self 0.0ms]
```

> Evidence `tr_d3518340b0ba`:

```
<tool_result id="tr_d3518340b0ba" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T15:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" radius="seed" hops="0">
service: checkout
2 changes, ranked by suspicion
  #1  3m before onset  2026-10-03T15:09:57+00:00  platform-automation  container created: workload first created
  #2  3m before onset  2026-10-03T15:09:56+00:00  platform-automation  config created: Service checkout created
</tool_result:tr_d3518340b0ba>
```

> Evidence `tr_1778ce8ce3e6`:

```
<tool_result id="tr_1778ce8ce3e6" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T15:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" radius="seed" hops="0">
service: payment
2 changes, ranked by suspicion
  #1  3m before onset  2026-10-03T15:09:59+00:00  platform-automation  container created: workload first created
  #2  3m before onset  2026-10-03T15:09:56+00:00  platform-automation  config created: Service payment created
</tool_result:tr_1778ce8ce3e6>
```

> Evidence `tr_ab5bfd8c7f3b`:

```
<tool_result id="tr_ab5bfd8c7f3b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-03T13:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" template="error-ratio" baseline="2026-10-03T11:13:00.291667+00:00..2026-10-03T13:13:06.503059+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=1 mean=0.1875 min=0.1875 max=0.1875 sd=0
  baseline window: no samples
```

> Evidence `tr_463410507be2`:

```
<tool_result id="tr_463410507be2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-03T13:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" template="error-ratio" baseline="2026-10-03T11:13:00.291667+00:00..2026-10-03T13:13:06.503059+00:00">
service: payment
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="payment"}[5m]))
  incident window: n=1 mean=0.5 min=0.5 max=0.5 sd=0
  baseline window: no samples
```

> Evidence `tr_407873775724`:

```
<tool_result id="tr_407873775724" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:43:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" contains="Charge">
selector: {namespace="astronomy-shop",pod=~"payment-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "Charge"
2026-10-03T15:11:17+00:00    body: 'Charge request received.',
2026-10-03T15:11:43+00:00    body: 'Charge request received.',
2026-10-03T15:11:45+00:00    body: 'Charge request received.',
2026-10-03T15:11:54+00:00    body: 'Charge request received.',
```

## Conclusion and what is still open

Payment is rejecting a subset of Charge calls with an invalid-token rejection tagged gold tier; checkout surfaces it as 'failed to charge card'. The failure begins at a definite moment, is segmented by a customer attribute, is produced by the service's own code while the service stays healthy and accepts traffic, and leaves the change log empty. The shape that fits all four is a runtime value flip in the flag store enabling a failing code path on the charge route for gold-tier requests. Remediation class: configuration revert. Confidence medium — the inference is structural, not direct.

Open: the flag store was never queried. Nobody read its configuration or history, so the flag name, its value, who set it, and the exact flip time are unconfirmed. This is the cheapest and highest-value next step.

Also open: whether the rejection truly affects only gold-tier traffic or whether that attribute merely happens to appear on every sampled failure; the refused dial at ~T-1m with no payment child span, possibly cold-start churn given payment's workload age, possibly a separate earlier problem; the ~1042ms currency Convert outlier in that same trace, never investigated; and the nine other affected services, on which nothing was gathered — their inclusion rests on trace topology and triage, not measurement.

> Evidence `tr_0d3e77248cba`:

```
<tool_result id="tr_0d3e77248cba" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-03T14:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00">
service: checkout
6 trace(s) shown of 14 found, 200 spans; offsets are from each trace's root

trace 6dcefa8587bac50b  root load-generator/user_checkout_single  1464.9ms  started 2026-10-03T15:10:56.928615+00:00  21 spans, 1 unattached
  +0.0ms load-generator/user_checkout_single 1464.9ms [self 0.0ms]
```

> Evidence `tr_5d6996bcab13`:

```
<tool_result id="tr_5d6996bcab13" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:43:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" contains="token">
selector: {namespace="astronomy-shop",pod=~"payment-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "token"
2026-10-03T15:11:17+00:00        stack: 'Error: Payment request failed. Invalid token. app.loyalty.level=gold\n' +
2026-10-03T15:11:17+00:00        message: 'Payment request failed. Invalid token. app.loyalty.level=gold',
2026-10-03T15:11:17+00:00    body: 'Payment request failed. Invalid token. app.loyalty.level=gold',
2026-10-03T15:11:43+00:00        stack: 'Error: Payment request failed. Invalid token. app.loyalty.level=gold\n' +
```

> Evidence `tr_1778ce8ce3e6`:

```
<tool_result id="tr_1778ce8ce3e6" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T15:13:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" radius="seed" hops="0">
service: payment
2 changes, ranked by suspicion
  #1  3m before onset  2026-10-03T15:09:59+00:00  platform-automation  container created: workload first created
  #2  3m before onset  2026-10-03T15:09:56+00:00  platform-automation  config created: Service payment created
</tool_result:tr_1778ce8ce3e6>
```

> Evidence `tr_407873775724`:

```
<tool_result id="tr_407873775724" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:43:06.503059+00:00..2026-10-03T15:13:12.714451+00:00" contains="Charge">
selector: {namespace="astronomy-shop",pod=~"payment-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "Charge"
2026-10-03T15:11:17+00:00    body: 'Charge request received.',
2026-10-03T15:11:43+00:00    body: 'Charge request received.',
2026-10-03T15:11:45+00:00    body: 'Charge request received.',
2026-10-03T15:11:54+00:00    body: 'Charge request received.',
```

