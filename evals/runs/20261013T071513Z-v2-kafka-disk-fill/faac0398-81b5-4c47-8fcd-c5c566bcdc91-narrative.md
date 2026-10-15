# Checkout stalls mid-order: calls complete, work never resumes

## Summary

Checkout kept accepting PlaceOrder requests and kept answering its own downstream calls quickly, but stopped making forward progress partway through the order. In the representative slow trace, roughly 54.2 seconds of a 54.3-second PlaceOrder span is checkout's own self-time; every call it actually issued — cart GetCart, product-catalog GetProduct, two currency Convert calls, the shipping quote HTTP call, and payment Charge — returned in single-digit milliseconds. Everything that normally happens after the charge (order confirmation email, EmptyCart, ship-order, the orders publish) never starts at all. Callers were not told anything: the only ERROR statuses in the trace sit on the load-generator and frontend-proxy ingress spans, with the caller still blocked about 39 seconds after the proxy had already given up. Socket still accepting, work abandoned mid-request, callers hanging to their deadlines. We treated this as a wedged checkout process and the fix class is a restart. Accounting's alert is a consequence, not a second failure: it shows no errors, only intervals with no traffic to measure, which is what you would expect once checkout stops publishing orders. Confidence is medium — see the open threads.

> Evidence `tr_a10c309fb10a`:

```
<tool_result id="tr_a10c309fb10a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T06:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2020d8d42fb86dcc  root load-generator/user_checkout_multi  109.6ms  started 2026-10-13T07:14:35.790045+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 109.6ms [self 50.8ms]
```

> Evidence `tr_9445b2ab213a`:

```
<tool_result id="tr_9445b2ab213a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T06:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" template="error-ratio" baseline="2026-10-13T06:18:18.014369+00:00..2026-10-13T06:51:16.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=116 mean=0 min=0 max=0 sd=0
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

## What was visible, in order

T+0 — paging on checkout, then on accounting about two minutes later. Two services alerting, ten in the blast radius, eight edges crossed that nobody had measured before.

T+3m — checkout's error ratio was the first thing to look at. The baseline is exactly zero across every sample with zero spread, so any non-zero value is a real state change rather than noise. A single change point lands at 07:20:16, about a minute before the alert timestamp, with the ratio crossing 0.05 and peaking near 6.5%. The incident-window mean is ~0.0034 against that 0.065 peak, so it reads as a narrow excursion rather than a broad degradation. Importantly, traffic was present throughout the incident window — no undefined ratio samples — so the spike is not a small-denominator artifact.

T+12m — traces were where the picture actually formed. Healthy PlaceOrder traces run 72–110ms, with email send, payment Charge and EmptyCart as the biggest contributors. The failing trace is three orders of magnitude slower and the time is all checkout's, not any child's. The trace simply stops after payment Charge returns.

T+25m — accounting. Error ratio flat zero in both baseline and incident window. The only departure is 16 sampling intervals in the incident window with no defined value at all, against none in baseline — intervals where accounting received nothing. That is a starvation signature, consistent with its upstream going quiet.

> Evidence `tr_7c332802b972`:

```
<tool_result id="tr_7c332802b972" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T05:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" template="error-ratio" baseline="2026-10-13T04:18:18.014369+00:00..2026-10-13T05:51:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=372 mean=0.003406 min=0 max=0.06497 sd=0.01337
  baseline window: n=332 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_a10c309fb10a`:

```
<tool_result id="tr_a10c309fb10a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T06:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2020d8d42fb86dcc  root load-generator/user_checkout_multi  109.6ms  started 2026-10-13T07:14:35.790045+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 109.6ms [self 50.8ms]
```

> Evidence `tr_9445b2ab213a`:

```
<tool_result id="tr_9445b2ab213a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T06:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" template="error-ratio" baseline="2026-10-13T06:18:18.014369+00:00..2026-10-13T06:51:16.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=116 mean=0 min=0 max=0 sd=0
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

## Dead ends worth keeping

Downstream blame, all six of them. The instinct was to find the slow dependency. There isn't one. Every child span checkout issued came back in milliseconds in the failing trace: payment Charge in ~2.9ms with its nested charge child, shipping's get-quote path including nested quote spans in ~5.3ms, product-catalog's SQL query spans sub-millisecond. Email is the slowest hop in healthy traces and was the natural suspect — but there is no email span in the failing trace at all, because checkout never got that far. A hop that was never called cannot be the hop that blocked you.

Propagated downstream errors. No downstream span carries an error status. The ERROR markings are exclusively client-side ingress, which is the shape of a timeout, not of an error bubbling up.

Change history, twice. Two separate change-log queries against checkout came back empty, and a third against accounting likewise. That genuinely rules out an in-incident deploy, rollback, or ongoing rollout churn on either service. But both checkout queries ran forward from the incident timestamp for ~24 hours and never looked backwards. The hours before onset — the ones that actually matter for a deploy or config theory — were never searched. Read the empty result as 'nothing during or after', not 'nothing ever'. The queries were also scoped to the seed service only, so checkout's direct dependencies were not covered.

Checkout's logs. A query for all lines from checkout over a ~63-minute window returned nothing of any severity. Initially this looked like strong corroboration of a wedged process: a healthy service still emits routine info lines. Then the same query shape against frontend came back equally empty across its whole 33-minute window — and frontend was demonstrably serving traffic. A live service producing zero lines for half an hour is not plausible, so the emptiness more likely points at a labelling or ingestion problem affecting both selectors. Treat 'checkout wrote nothing' as unconfirmed.

A stale baseline comparison. One metric pull used a window on the previous day and showed checkout's error ratio flat at zero during the window with a noisy, high-variance baseline before it — the opposite direction from the real incident, with only ~40 samples against 1200+ in an equal-length baseline. That result does not describe this incident and should not be read as evidence that checkout was clean.

> Evidence `tr_a10c309fb10a`:

```
<tool_result id="tr_a10c309fb10a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T06:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2020d8d42fb86dcc  root load-generator/user_checkout_multi  109.6ms  started 2026-10-13T07:14:35.790045+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 109.6ms [self 50.8ms]
```

> Evidence `tr_e7add6c1b1a7`:

```
<tool_result id="tr_e7add6c1b1a7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_e7add6c1b1a7>
```

> Evidence `tr_69e4bd1acccd`:

```
<tool_result id="tr_69e4bd1acccd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_69e4bd1acccd>
```

> Evidence `tr_e0a12cd78f8b`:

```
<tool_result id="tr_e0a12cd78f8b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" radius="seed" hops="0">
no changes recorded for accounting over this window
</tool_result:tr_e0a12cd78f8b>
```

> Evidence `tr_54d5d5fffcf0`:

```
<tool_result id="tr_54d5d5fffcf0" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T06:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_54d5d5fffcf0>
```

> Evidence `tr_c8569dc6ec21`:

```
<tool_result id="tr_c8569dc6ec21" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T06:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_c8569dc6ec21>
```

> Evidence `tr_5d999c65d3a3`:

```
<tool_result id="tr_5d999c65d3a3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-12T13:21:16.664000+00:00" template="error-ratio" baseline="2026-10-12T01:21:16.664000+00:00..2026-10-12T07:21:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=40 mean=0 min=0 max=0 sd=0
  baseline window: n=1289 mean=0.04567 min=0 max=0.6667 sd=0.1318
```

## Why this landed on a wedged process

The combination is what carries the argument, not any single signal. The listening socket kept accepting — traffic continued throughout the incident window. Work was abandoned mid-request at a specific, repeatable point: after the charge succeeds and before the post-charge sequence begins. Callers received no error from checkout and sat blocked until their own deadlines expired. No change is recorded against the service during the window. Nothing about this looks like a dependency, a code path returning an error, or a rollout. It looks like the process stopped executing.

The conclusion follows from behaviour rather than from internals, which is the weakness in it. We never retrieved latency percentiles, CPU, memory, thread or connection-pool counts, or GC series for checkout. A deadlock or an exhausted pool inside the process would produce exactly this trace shape and we have no measurement that would distinguish it from any other reason the process stopped moving.

> Evidence `tr_a10c309fb10a`:

```
<tool_result id="tr_a10c309fb10a" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-13T06:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 2020d8d42fb86dcc  root load-generator/user_checkout_multi  109.6ms  started 2026-10-13T07:14:35.790045+00:00  73 spans
  +0.0ms load-generator/user_checkout_multi 109.6ms [self 50.8ms]
```

> Evidence `tr_7c332802b972`:

```
<tool_result id="tr_7c332802b972" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T05:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" template="error-ratio" baseline="2026-10-13T04:18:18.014369+00:00..2026-10-13T05:51:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=372 mean=0.003406 min=0 max=0.06497 sd=0.01337
  baseline window: n=332 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_69e4bd1acccd`:

```
<tool_result id="tr_69e4bd1acccd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_69e4bd1acccd>
```

## Open threads for whoever reads this next

Three things were left undone and each one could change the conclusion.

First, the log silence. Confirm whether checkout and frontend logs exist under a different label, tenant, or stream, or whether the shipping path is broken. If the logs are recoverable, they may contain the one line that names the cause and would upgrade confidence from medium.

Second, the unmeasured internals. Pull p95/p99 latency, CPU, memory, thread and connection-pool utilisation, and GC pauses for checkout across onset. A saturation or deadlock cause inside the process is currently unexcluded, and a restart that fixes the symptom will also erase the evidence.

Third, re-run the change history over the hours *before* 07:20:16, and extend it one hop out to checkout's direct dependencies. Both prior queries pointed the wrong way in time and were scoped to the seed service only. A pre-onset deploy or config edit remains entirely unsearched.

> Evidence `tr_c8569dc6ec21`:

```
<tool_result id="tr_c8569dc6ec21" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T06:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
no log lines matched {service="frontend"} over this window
</tool_result:tr_c8569dc6ec21>
```

> Evidence `tr_54d5d5fffcf0`:

```
<tool_result id="tr_54d5d5fffcf0" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T06:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_54d5d5fffcf0>
```

> Evidence `tr_5d999c65d3a3`:

```
<tool_result id="tr_5d999c65d3a3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-12T13:21:16.664000+00:00" template="error-ratio" baseline="2026-10-12T01:21:16.664000+00:00..2026-10-12T07:21:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=40 mean=0 min=0 max=0 sd=0
  baseline window: n=1289 mean=0.04567 min=0 max=0.6667 sd=0.1318
```

> Evidence `tr_7c332802b972`:

```
<tool_result id="tr_7c332802b972" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T05:51:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" template="error-ratio" baseline="2026-10-13T04:18:18.014369+00:00..2026-10-13T05:51:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=372 mean=0.003406 min=0 max=0.06497 sd=0.01337
  baseline window: n=332 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_e7add6c1b1a7`:

```
<tool_result id="tr_e7add6c1b1a7" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_e7add6c1b1a7>
```

> Evidence `tr_69e4bd1acccd`:

```
<tool_result id="tr_69e4bd1acccd" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T07:21:16.664000+00:00..2026-10-13T07:24:15.313631+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_69e4bd1acccd>
```

