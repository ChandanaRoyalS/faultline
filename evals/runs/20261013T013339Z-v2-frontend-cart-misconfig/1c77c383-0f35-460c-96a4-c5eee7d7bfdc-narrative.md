# Checkout order placement fails on the shipping quote path

## What we saw first

The page opened with four services paging at once — checkout, frontend, frontend-proxy and load-generator — and a blast radius that eventually counted thirteen services. That breadth was the first thing that turned out not to matter. The frontend tier and the proxy were never sick in their own right; their error status was inherited from the deepest errored leaf, and each had negligible self-time. If you are reading this months later with a similar page, start by collapsing the alert list: the edge services alerting here were reporters, not participants.

The seed for the investigation was checkout. Checkout's error ratio gave us the cleanest timing signal we got: flat at exactly zero across the entire baseline (129 samples, zero min, max, mean and standard deviation), then a single discrete change point where it crossed threshold at 6.25%. Because the baseline was literally zero, the shift could not be expressed as a multiple of normal — it was a move from no errors to errors, which is the strongest kind of change point you can ask for. During the window the mean sat around 3.3% with a peak of 50% and a dispersion roughly three times the mean, i.e. bursty rather than a plateau, and most requests still succeeded even at the worst sample.

> Evidence `tr_af564839b03e`:

```
<tool_result id="tr_af564839b03e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" template="error-ratio" baseline="2026-10-13T00:35:13.803753+00:00..2026-10-13T01:07:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=129 mean=0.03348 min=0 max=0.5 sd=0.1066
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_53f95f690a9b`:

```
<tool_result id="tr_53f95f690a9b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00">
service: checkout
10 trace(s) shown of 10 found, 150 spans; offsets are from each trace's root

trace cf7633cb2f2b6816  root load-generator/user_checkout_single  18.8ms  started 2026-10-13T01:36:24.224144+00:00  15 spans
  +0.0ms load-generator/user_checkout_single 18.8ms [self 10.0ms]
```

## Narrowing to a single hop

Traces did the real work. All ten sampled checkout traces failed identically: the error propagated up from checkout's PlaceOrder span, and the only errored downstream call inside checkout was its outbound HTTP POST to shipping's get-quote endpoint. The parallel cart lookup in the same parent operation was clean in every single trace, cart and its Redis HGET both completing in under a couple of milliseconds. Requests aborted early, inside prepareOrderItemsAndShippingQuoteFromCart, so no payment, currency, product-catalog or order-confirmation spans appear anywhere in a failing trace — those services were never reached and are not suspects.

Two shapes of hypothesis died here. First, slowness: end-to-end traces ran roughly 15–106ms and the errored shipping hop contributed only 0.8–8.1ms, between 1% and 20% of trace time, with the largest time block being self-time in the load generator root. These requests failed fast; nothing stalled, nothing timed out. Second, intermittency: all ten traces, across both single- and multi-item checkout flows and spread through the window, carried the identical message and the identical failing hop. The burstiness in the metric is about traffic mix, not about a flapping dependency.

The detail that pointed onward: checkout's root error text attributed the quote failure to a non-200 — specifically a 400 — returned from an email-service call made on the quote path. Worth noting precisely where that error lives. Shipping's server-side span for the quote endpoint completed in roughly 0.0–1.4ms and was *not* marked errored, while checkout's client span wrapping it was errored and held nearly all the self-time of the hop. The error was recorded caller-side.

> Evidence `tr_53f95f690a9b`:

```
<tool_result id="tr_53f95f690a9b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00">
service: checkout
10 trace(s) shown of 10 found, 150 spans; offsets are from each trace's root

trace cf7633cb2f2b6816  root load-generator/user_checkout_single  18.8ms  started 2026-10-13T01:36:24.224144+00:00  15 spans
  +0.0ms load-generator/user_checkout_single 18.8ms [self 10.0ms]
```

## The email detour

The obvious next move was to go confirm that email was rejecting shipping's quote requests. It wasn't — or at least, not in any form email could see. Every email request line in the window was the same endpoint, POST /send_order_confirmation, all status 200, all sub-100ms, each paired with a successful send message naming a recipient. No quote-related path appears anywhere in email's logs, and only one upstream client IP is recorded. That simultaneously killed several tidy stories: email being down or crash-looping (it served continuously through the late window), email being a latency source (slowest recorded duration around 68ms), and email's own mail-delivery dependency failing (every request completed its send).

This is the contradiction the record exists to preserve. Checkout's trace text says a call to email returned 400 on the quote path; email's own logs say it never served a quote path at all. The reading that reconciles the two is that the quote path is calling email at an address or endpoint email does not serve, or with a payload that does not match the endpoint named, so the request never reaches a handler and comes back 400 without ever appearing in email's access lines as quote traffic. A wrong configured value would itself be the failure mechanism. That is the best available reading, not a proven one — see the open items.

> Evidence `tr_2abd7e054e38`:

```
<tool_result id="tr_2abd7e054e38" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" oldest_kept="8" newest_kept="32">
selector: {service="email"}
2026-10-13T01:07:23.487666+00:00  Order confirmation email sent to: bill@example.com
2026-10-13T01:07:23.488231+00:00  172.18.0.28 - - [13/Oct/2026:01:07:23 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0094
2026-10-13T01:07:35.581712+00:00  Order confirmation email sent to: moore@example.com
2026-10-13T01:07:35.582675+00:00  172.18.0.28 - - [13/Oct/2026:01:07:35 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0394
```

> Evidence `tr_53f95f690a9b`:

```
<tool_result id="tr_53f95f690a9b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00">
service: checkout
10 trace(s) shown of 10 found, 150 spans; offsets are from each trace's root

trace cf7633cb2f2b6816  root load-generator/user_checkout_single  18.8ms  started 2026-10-13T01:36:24.224144+00:00  15 spans
  +0.0ms load-generator/user_checkout_single 18.8ms [self 10.0ms]
```

## Dead ends worth keeping

Three lines of inquiry consumed real time and produced nothing, and a future responder should know not to re-run them with high expectations.

Change history, three times over. Checkout: nothing recorded in the ~24h pre-onset window — no deploys, no config edits, no flag flips — which removes rollback of checkout as an available remediation and pushes the investigation off the owning team. Shipping: same, empty, including anything touching the get-quote path or its email call. Email and its one-hop neighbours: same, empty. Note one scoping trap: the checkout query was run at seed radius with zero dependency hops, so the absence of checkout's dependencies from that result carries no information at all. Do not read it as clearance.

Checkout's logs. A query for all lines from checkout over the window returned zero lines — not zero errors, zero lines of any level under the service label. That absence is itself a finding with three explanations this evidence cannot separate: checkout stopped emitting, the log shipping path for checkout broke, or the label value no longer matches how checkout is tagged. What it definitively removes is logs as a usable source for checkout here: no exception text, no stack trace, no timestamps to order against onset.

Email's error-ratio metric. The span-metrics query returned no samples in either the incident window or the baseline. Because the gap spans both, it is not telemetry going dark at onset; it is more consistent with email not emitting under that service label at all. Critically, the tool's 'no sustained departure from baseline' phrasing derives from an empty series and must not be read as evidence of health. The query also filtered on span error status, not HTTP status classes, so it could never have answered the 4xx question we were actually asking.

> Evidence `tr_b293df6ab5ea`:

```
<tool_result id="tr_b293df6ab5ea" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T01:37:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_b293df6ab5ea>
```

> Evidence `tr_155c0516bcbe`:

```
<tool_result id="tr_155c0516bcbe" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T01:37:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" radius="candidate_cause" hops="1">
no changes recorded for shipping over this window
</tool_result:tr_155c0516bcbe>
```

> Evidence `tr_964ee2f0534d`:

```
<tool_result id="tr_964ee2f0534d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T01:37:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" radius="candidate_cause" hops="1">
no changes recorded for email over this window
</tool_result:tr_964ee2f0534d>
```

> Evidence `tr_09a87e0757e1`:

```
<tool_result id="tr_09a87e0757e1" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_09a87e0757e1>
```

> Evidence `tr_485523473454`:

```
<tool_result id="tr_485523473454" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" template="error-ratio" baseline="2026-10-13T00:35:13.803753+00:00..2026-10-13T01:07:16.664000+00:00">
service: email
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="email",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="email"}[5m]))
  incident window: no samples
  baseline window: no samples
```

## Where we landed, and how much to trust it

Attribution landed on shipping, on the grounds that it owns the failing quote path and makes the email call that comes back 400. Fix class is a configuration revert. Confidence is low, deliberately.

The weakest joint in the chain: no specialist ever queried shipping's own logs, metrics or traces. The entire case against shipping rests on error text observed from the checkout side, and shipping's own account of why it calls email on a quote path at all is unread. That is the first thing to do if this recurs.

The 400 appears only inside a checkout error string. The actual request URL, payload and response body of the shipping-to-email call were never observed, so whether the misconfiguration is an address, an endpoint, or a malformed payload is unsettled — and those imply different fixes.

Email's log result was truncated: only the oldest handful and newest few dozen lines were retained, leaving roughly a twenty-five-minute span unreturned in the middle, and the newest line predates the change point by about ninety seconds. Rejected or 4xx quote requests could exist in that unreturned span. Re-run that query with tighter bounds around the change point before trusting 'email never saw it'.

Finally, no change record exists anywhere for any of the three services involved, so the triggering act is unidentified. It is entirely possible the change log simply does not cover whatever mutation occurred. That leaves the recommended revert without a concrete target, which is the honest state of this record.

> Evidence `tr_2abd7e054e38`:

```
<tool_result id="tr_2abd7e054e38" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" oldest_kept="8" newest_kept="32">
selector: {service="email"}
2026-10-13T01:07:23.487666+00:00  Order confirmation email sent to: bill@example.com
2026-10-13T01:07:23.488231+00:00  172.18.0.28 - - [13/Oct/2026:01:07:23 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0094
2026-10-13T01:07:35.581712+00:00  Order confirmation email sent to: moore@example.com
2026-10-13T01:07:35.582675+00:00  172.18.0.28 - - [13/Oct/2026:01:07:35 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0394
```

> Evidence `tr_53f95f690a9b`:

```
<tool_result id="tr_53f95f690a9b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00">
service: checkout
10 trace(s) shown of 10 found, 150 spans; offsets are from each trace's root

trace cf7633cb2f2b6816  root load-generator/user_checkout_single  18.8ms  started 2026-10-13T01:36:24.224144+00:00  15 spans
  +0.0ms load-generator/user_checkout_single 18.8ms [self 10.0ms]
```

> Evidence `tr_af564839b03e`:

```
<tool_result id="tr_af564839b03e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-13T01:07:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" template="error-ratio" baseline="2026-10-13T00:35:13.803753+00:00..2026-10-13T01:07:16.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=129 mean=0.03348 min=0 max=0.5 sd=0.1066
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_b293df6ab5ea`:

```
<tool_result id="tr_b293df6ab5ea" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T01:37:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_b293df6ab5ea>
```

> Evidence `tr_155c0516bcbe`:

```
<tool_result id="tr_155c0516bcbe" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T01:37:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" radius="candidate_cause" hops="1">
no changes recorded for shipping over this window
</tool_result:tr_155c0516bcbe>
```

> Evidence `tr_964ee2f0534d`:

```
<tool_result id="tr_964ee2f0534d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-12T01:37:16.664000+00:00..2026-10-13T01:39:19.524247+00:00" radius="candidate_cause" hops="1">
no changes recorded for email over this window
</tool_result:tr_964ee2f0534d>
```

