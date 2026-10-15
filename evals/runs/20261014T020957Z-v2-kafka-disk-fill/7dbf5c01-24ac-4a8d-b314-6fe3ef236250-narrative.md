# Checkout order publishing stalls on an unresolvable broker hostname

## What we saw first

Three services paged at once: checkout, accounting, and fraud-detection. Checkout was the loudest and the obvious place to start, since it sits at the head of the order path and the other two sit downstream of it on the messaging side. Blast radius as estimated at the time was twelve services, severity critical, with nine edges between the seed and the far reaches of the graph that we had no measurements for.

The first useful shape came from checkout's error ratio. It was exactly flat at zero through the whole baseline stretch — minimum zero, maximum zero, no variance at all — and then crossed the five percent line at a discrete change point roughly half an hour into the observed window. Mean across the incident window was around one percent, peaking near six and a half, with real variance between samples. That told us two things worth holding onto: the problem did not predate the window, and it did not arrive as a clean step. It ramped or stuttered in.

> Evidence `tr_b83ec1a2cf03`:

```
<tool_result id="tr_b83ec1a2cf03" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=132 mean=0.0102 min=0 max=0.06627 sd=0.02153
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

## Following checkout's request path

Traces settled it faster than anything else. In every PlaceOrder trace examined, exactly one step was burning time: the span that publishes the order. Self-time of roughly sixty-eight to eighty seconds, ending in an error. The error text named the reason outright — the Kafka broker hostname could not be resolved, a 'no such host' answer from the local resolver at 127.0.0.11:53. In a fourth trace the same span failed instantly with a circuit-breaker-open error, which tells us failures had already accumulated far enough to trip the breaker by that point.

Everything else in the same traces was healthy. Payment, cart, shipping, currency, product-catalog, and email all returned in single-digit to low-double-digit milliseconds with no errors. The PlaceOrder handler's own self-time was sub-millisecond. So checkout was running, was scheduled, had working network paths to six other services, and resolved all of their names fine. One name, and only one, had stopped resolving.

> Evidence `tr_dbffa43306da`:

```
<tool_result id="tr_dbffa43306da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 813c4a2735eeb917  root load-generator/user_checkout_single  15010.1ms  started 2026-10-14T02:16:47.605437+00:00  46 spans
  +0.0ms load-generator/user_checkout_single 15010.1ms [self 9.4ms]
```

## The downstream pages

Accounting and fraud-detection both consume from the same message stream, and both paged. Neither was actually broken.

Accounting's error ratio was flat zero across both baseline and incident windows — not a single elevated sample, no lag behind checkout, nothing. What did change was that sixteen samples in the incident window carried no defined value at all, meaning no traffic arrived in those intervals. The baseline had zero such gaps. That is the signature of a consumer with nothing to eat, not a consumer that is failing.

Fraud-detection told the same story with more noise on top. Its mean error ratio nudged from about 0.0067 to about 0.0082 — a 1.23x move with heavy standard-deviation overlap, and no sustained departure from baseline. Peak crept from 0.021 to 0.027. We spent some time on that delta before concluding it was not load-bearing. The signal that mattered was the same one accounting showed: sixteen samples with no defined value, i.e. intervals with no traffic at all. The service kept producing defined values for a hundred of a hundred and sixteen samples, so it was never unreachable or fully erroring.

> Evidence `tr_d3a3ea324e8a`:

```
<tool_result id="tr_d3a3ea324e8a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=116 mean=0 min=0 max=0 sd=0
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_ce236c7cc1a0`:

```
<tool_result id="tr_ce236c7cc1a0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=116 mean=0.008212 min=0 max=0.02703 sd=0.01015
  baseline window: n=132 mean=0.006681 min=0 max=0.02128 sd=0.008943
```

## Dead ends worth keeping

**The change log, twice.** We queried a full twenty-four hours of change history against checkout and its immediate dependencies, and separately against fraud-detection and the shared messaging infrastructure. Both came back empty. No deployments, no config edits, no flag flips, no resource-limit changes, nothing of any type. This is the single most expensive dead end in the record because it removes the hypothesis a responder reaches for first. Whatever happened here, nobody is recorded as having done it. A previously-working endpoint stopped resolving with no act attached to it.

**Checkout's own logs.** We asked Loki for every line checkout emitted across the whole window and got nothing back — not an error, not a warning, not an info line. Meanwhile the same service was emitting spans the entire time. The most likely reading is a log-shipping gap rather than a dead process, but we could not confirm that, and it means checkout never gave its own account of what it saw. Do not read the empty log result as evidence the service was down; the traces contradict that.

**Fraud-detection's logs.** Every line returned was a routine 'consumed record' message, no errors or warnings anywhere. But the result was truncated — oldest eight and newest thirty-two lines kept — and the newest line predated the interesting part of the window by several minutes. So the clean log is not evidence of health during the failure; it is evidence about an earlier period we did not care about. We nearly took it as reassurance before noticing the truncation.

**Blaming the broker itself.** The temptation is to assume the broker crashed or started refusing connections. The error text rules that out: a name-resolution failure means the client never got as far as opening a socket. Nothing about broker load or broker-side rejection is supported here.

> Evidence `tr_36884e2a7d77`:

```
<tool_result id="tr_36884e2a7d77" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:15:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_36884e2a7d77>
```

> Evidence `tr_3cd2d3ded37d`:

```
<tool_result id="tr_3cd2d3ded37d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T02:15:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_3cd2d3ded37d>
```

> Evidence `tr_1e53b8ffb6d9`:

```
<tool_result id="tr_1e53b8ffb6d9" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_1e53b8ffb6d9>
```

> Evidence `tr_028aa13e91d1`:

```
<tool_result id="tr_028aa13e91d1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-14T01:45:37.924152+00:00  2026-10-14 01:45:37 - fraud-detection - Consumed record with orderId: f49663e4-c770-11f1-9eef-8a8e625f59f5, and updated total count to: 13403 trace_id=86a3c5be5f5c5a17c758dbc71ee6c0af span_id=b64662274cce91cf trace_flags=01 
2026-10-14T01:45:41.439767+00:00  2026-10-14 01:45:41 - fraud-detection - Consumed record with orderId: f69ed2cf-c770-11f1-9eef-8a8e625f59f5, and updated total count to: 13404 trace_id=021e59de82970a23fe77f86952f9224e span_id=e819c420c17636f1 trace_flags=01 
2026-10-14T01:45:51.572769+00:00  2026-10-14 01:45:51 - fraud-detection - Consumed record with orderId: fcb52e7b-c770-11f1-9eef-8a8e625f59f5, and updated total count to: 13405 trace_id=b72e06e530172852b20da4c54f9d707d span_id=5e35173ca43380e5 trace_flags=01 
2026-10-14T01:45:53.929773+00:00  2026-10-14 01:45:53 - fraud-detection - Consumed record with orderId: fe2154c3-c770-11f1-9eef-8a8e625f59f5, and updated total count to: 13406 trace_id=e5837f3823a8d0a37afb41af64da4ca1 span_id=11d664763e1cff2a trace_flags=01 
```

> Evidence `tr_dbffa43306da`:

```
<tool_result id="tr_dbffa43306da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 813c4a2735eeb917  root load-generator/user_checkout_single  15010.1ms  started 2026-10-14T02:16:47.605437+00:00  46 spans
  +0.0ms load-generator/user_checkout_single 15010.1ms [self 9.4ms]
```

## Where we landed

Checkout's order path fails at a single hop. The publish span cannot resolve the broker hostname, burns sixty-plus seconds per attempt, errors, and eventually trips a circuit breaker. Orders stop flowing into the stream, so the two consumer services downstream go quiet in intervals — which is what their alerts were really reporting. The endpoint has disappeared from the name-resolution or service-discovery plane without any recorded change producing it.

Confidence is medium, not high. Fix class: reconnect — restore the broker's presence in service discovery and verify resolution from a checkout container before declaring it closed.

> Evidence `tr_dbffa43306da`:

```
<tool_result id="tr_dbffa43306da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 813c4a2735eeb917  root load-generator/user_checkout_single  15010.1ms  started 2026-10-14T02:16:47.605437+00:00  46 spans
  +0.0ms load-generator/user_checkout_single 15010.1ms [self 9.4ms]
```

> Evidence `tr_b83ec1a2cf03`:

```
<tool_result id="tr_b83ec1a2cf03" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=132 mean=0.0102 min=0 max=0.06627 sd=0.02153
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

## What a later responder should still chase

Three gaps, none of them closed.

First, no one ever dispatched a query at the broker itself. There are no broker logs, no broker metrics, no process state, and no records from the resolver or the service registry anywhere in this briefing. Whether the broker crashed, was descheduled, or was severed at the network layer is inferred entirely from one client-side error string. That is a single point of evidence carrying the whole conclusion.

Second, checkout returned zero log lines for the entire window while demonstrably emitting spans. Until someone confirms that is a shipping gap, checkout's own view of the failure is unread.

Third — and this is the weakest link in the causal story — the traffic gaps in accounting and fraud-detection were never time-aligned against checkout's change point. The ordering we assert (checkout stops publishing, consumers starve) is plausible and consistent, but it was not demonstrated. If you reopen this, line those timestamps up first; it is cheap and it either firms the conclusion or breaks it.

> Evidence `tr_dbffa43306da`:

```
<tool_result id="tr_dbffa43306da" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 813c4a2735eeb917  root load-generator/user_checkout_single  15010.1ms  started 2026-10-14T02:16:47.605437+00:00  46 spans
  +0.0ms load-generator/user_checkout_single 15010.1ms [self 9.4ms]
```

> Evidence `tr_1e53b8ffb6d9`:

```
<tool_result id="tr_1e53b8ffb6d9" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_1e53b8ffb6d9>
```

> Evidence `tr_d3a3ea324e8a`:

```
<tool_result id="tr_d3a3ea324e8a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=116 mean=0 min=0 max=0 sd=0
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_ce236c7cc1a0`:

```
<tool_result id="tr_ce236c7cc1a0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=116 mean=0.008212 min=0 max=0.02703 sd=0.01015
  baseline window: n=132 mean=0.006681 min=0 max=0.02128 sd=0.008943
```

> Evidence `tr_b83ec1a2cf03`:

```
<tool_result id="tr_b83ec1a2cf03" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:45:31.664000+00:00..2026-10-14T02:18:16.410121+00:00" template="error-ratio" baseline="2026-10-14T01:12:46.917879+00:00..2026-10-14T01:45:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=132 mean=0.0102 min=0 max=0.06627 sd=0.02153
  baseline window: n=132 mean=0 min=0 max=0 sd=0
```

