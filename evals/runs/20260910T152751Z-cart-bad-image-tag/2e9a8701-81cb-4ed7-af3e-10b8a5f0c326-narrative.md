# Checkout orders stop completing mid-path with no error output

## What the responder sees first

The page arrives as a wide one: fourteen services in the blast radius, critical severity, checkoutservice named as the seed. Alerts land in a staggered pattern — checkoutservice, frontend and loadgenerator first, then currencyservice, emailservice, frauddetectionservice, quoteservice, accountingservice, cartservice and shippingservice roughly three to four minutes after onset. The width is misleading. Treat the later arrivals as downstream noise until proven otherwise; the staggering is exactly what propagation from a single stuck upstream looks like, and nothing found later contradicted that reading.

Anchor the clock at the detected regime change and call it T+0. The analysis window opened at T-28m and closed at T+4m.

## The metric picture, and why it nearly sent us the wrong way

The obvious first move is the service error ratio for checkoutservice against a preceding baseline. The headline number is boring: the mean error ratio in the incident window is within about 4% of baseline. Read alone, that says checkout is fine. It is not fine, and the shape tells you so — variance roughly doubles, the peak reaches about two-thirds of calls against a baseline peak under 0.3, and exactly one change point fires, at T+0.

Two details matter more than the headline. First, the single change point sits about two minutes *before* the timeframe the alert pointed at, so anyone searching the alert minute for a trigger is looking in the wrong place. Second, two 2-minute intervals in the incident window return an undefined ratio. That is not a quiet period with zero errors — an undefined ratio means an empty denominator, i.e. no calls recorded at all. Zero such intervals appear in the baseline. Those gaps are new, and they are the metric-side shadow of the real behaviour.

One caveat we carried forward: the peak ratio is consistent with a very small call denominator, so the magnitude may be inflated by low volume around the gaps rather than representing many failed orders.

> Evidence `tr_901d1f42767a`:

```
<tool_result id="tr_901d1f42767a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=129 mean=0.08608 min=0 max=0.2927 sd=0.1173
```

> Evidence `tr_1737543b4c48`:

```
<tool_result id="tr_1737543b4c48" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=129 mean=0.08608 min=0 max=0.2927 sd=0.1173
```

## The logs, which are where the answer actually is

Checkout's own log stream is entirely info severity for the whole window. No error text, no status codes, no named downstream, nothing to grep for. The temptation is to conclude the service is healthy or that the logs are useless. Both are wrong.

Read the *shape* of the lines instead. Early in the window each order produces a complete quartet: placement start, payment success with a transaction id, confirmation email sent, and a successful order-message write with an incrementing offset. From roughly T+0 onward, only the placement start line appears. The other three are not replaced by rejections or timeouts — they are simply absent. Requests keep arriving right up to the last log line at T+4m, in both USD and CAD.

That is a service that is stalling, not erroring. Handlers are being entered and never leaving, which points at a synchronous downstream call on the PlaceOrder path that never returns. It also explains the metric gaps: when every handler is parked, completed calls stop being recorded.

> Evidence `tr_44e356406471`:

```
<tool_result id="tr_44e356406471" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T15:02:31.089836+00:00  {"message":"[PlaceOrder] user_id=\"a567df4a-ad28-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T15:02:31.089696042Z"}
2026-09-10T15:02:31.106464+00:00  {"message":"payment went through (transaction_id: 11bba9ae-396e-4436-b574-504741e5a3cf)","severity":"info","timestamp":"2026-09-10T15:02:31.106378875Z"}
2026-09-10T15:02:31.111342+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-09-10T15:02:31.111180833Z"}
2026-09-10T15:02:31.112522+00:00  {"message":"Successful to write message. offset: 32603","severity":"info","timestamp":"2026-09-10T15:02:31.112420708Z"}
```

## Dead ends worth keeping

**Checkout's own change history.** Queried twice over the ~24h preceding the window. Empty both times — no deploys, no config edits, no flag flips. There is no release to correlate with onset and nothing to roll back. This closed the single most attractive hypothesis and forced the search off the seed service. Note the limitation, because it bit us: both queries ran at zero hops, so they covered checkoutservice only. Dependency change activity was never looked at.

**paymentservice metrics.** Because the log trail goes dark right where the payment line used to be, paymentservice was the natural next hop. Its error-ratio query returned nothing — no samples in the incident window and none in the baseline either. The denominator is empty too, so there is no request-rate series at all. Because the emptiness predates onset, it is not an incident-onset change; it is a standing condition, either an instrumentation gap, a different metric label, or the service genuinely not being on the measured path under that name. paymentservice can therefore be neither confirmed nor cleared as the blocked hop, and RED-metric inspection is not a viable line here until the naming question is settled.

**A currency-specific bug.** Late-window stalled orders include both USD and CAD, so the conversion path is not selectively implicated.

**Slow degradation / a gradual ramp.** Only one change point exists across the whole window, at the very end of it. The preceding ~28 minutes show no regime change. Whatever happened, happened sharply.

> Evidence `tr_f4ee40922f92`:

```
<tool_result id="tr_f4ee40922f92" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T15:32:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_f4ee40922f92>
```

> Evidence `tr_917c94b6a060`:

```
<tool_result id="tr_917c94b6a060" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T15:32:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_917c94b6a060>
```

> Evidence `tr_c5d2633b4d50`:

```
<tool_result id="tr_c5d2633b4d50" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_44e356406471`:

```
<tool_result id="tr_44e356406471" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T15:02:31.089836+00:00  {"message":"[PlaceOrder] user_id=\"a567df4a-ad28-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T15:02:31.089696042Z"}
2026-09-10T15:02:31.106464+00:00  {"message":"payment went through (transaction_id: 11bba9ae-396e-4436-b574-504741e5a3cf)","severity":"info","timestamp":"2026-09-10T15:02:31.106378875Z"}
2026-09-10T15:02:31.111342+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-09-10T15:02:31.111180833Z"}
2026-09-10T15:02:31.112522+00:00  {"message":"Successful to write message. offset: 32603","severity":"info","timestamp":"2026-09-10T15:02:31.112420708Z"}
```

> Evidence `tr_1737543b4c48`:

```
<tool_result id="tr_1737543b4c48" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=129 mean=0.08608 min=0 max=0.2927 sd=0.1173
```

## What turned out not to matter

The breadth of the alert list. Ten services paged, fourteen in the radius, and none of the later arrivals contributed evidence — they are consistent with propagation from a stalled checkout rather than independent problems, and time spent triaging them individually would have been wasted.

The flat mean error ratio. It looks like an all-clear and is not one; the mean is the least informative statistic in this record.

The alert timestamp as a search anchor. The change point sits two minutes earlier.

> Evidence `tr_901d1f42767a`:

```
<tool_result id="tr_901d1f42767a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=129 mean=0.08608 min=0 max=0.2927 sd=0.1173
```

## Conclusion and confidence

checkoutservice is stalling, not failing. It accepts PlaceOrder requests through the end of the window, logs no error or warning, and from T+0 emits only the entry line per order. The metrics agree: flat mean, doubled variance, one change point at T+0, and two intervals with no completed calls. No checkout-local change exists to explain it. The cause therefore sits on a checkout dependency along the order path.

Confidence is **low** and no fix class is proposed. The inference of a blocking call rests on log shape alone — no traces and no latency data were collected at any point.

> Evidence `tr_44e356406471`:

```
<tool_result id="tr_44e356406471" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T15:02:31.089836+00:00  {"message":"[PlaceOrder] user_id=\"a567df4a-ad28-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T15:02:31.089696042Z"}
2026-09-10T15:02:31.106464+00:00  {"message":"payment went through (transaction_id: 11bba9ae-396e-4436-b574-504741e5a3cf)","severity":"info","timestamp":"2026-09-10T15:02:31.106378875Z"}
2026-09-10T15:02:31.111342+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-09-10T15:02:31.111180833Z"}
2026-09-10T15:02:31.112522+00:00  {"message":"Successful to write message. offset: 32603","severity":"info","timestamp":"2026-09-10T15:02:31.112420708Z"}
```

> Evidence `tr_901d1f42767a`:

```
<tool_result id="tr_901d1f42767a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=129 mean=0.08608 min=0 max=0.2927 sd=0.1173
```

> Evidence `tr_1737543b4c48`:

```
<tool_result id="tr_1737543b4c48" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=127 mean=0.08924 min=0 max=0.6667 sd=0.2279
  baseline window: n=129 mean=0.08608 min=0 max=0.2927 sd=0.1173
```

> Evidence `tr_f4ee40922f92`:

```
<tool_result id="tr_f4ee40922f92" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T15:32:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_f4ee40922f92>
```

## Still open — start here next time

1. **No dependency was ever queried.** paymentservice, productcatalogservice, currencyservice, cartservice and the order-message write path are all unexamined for both changes and latency. Re-run the change history at one hop, not zero.

2. **Why paymentservice emits no call samples** under that service name in either window. Resolve whether this is an instrumentation gap, a label mismatch, or a genuinely unmeasured path before drawing any conclusion from its silence.

3. **The log result was truncated** to the oldest 8 and newest 32 lines. The T-28m to T+0 transition — which contains the first stalled order and its first blocked stage — was never read. Pull that span with a narrower query; it is the highest-value unread evidence in this record.

4. **Collect traces or per-dependency latency.** A single trace of a stalled PlaceOrder would identify the blocked hop directly and replace the whole chain of inference above.

> Evidence `tr_44e356406471`:

```
<tool_result id="tr_44e356406471" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T15:02:31.089836+00:00  {"message":"[PlaceOrder] user_id=\"a567df4a-ad28-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T15:02:31.089696042Z"}
2026-09-10T15:02:31.106464+00:00  {"message":"payment went through (transaction_id: 11bba9ae-396e-4436-b574-504741e5a3cf)","severity":"info","timestamp":"2026-09-10T15:02:31.106378875Z"}
2026-09-10T15:02:31.111342+00:00  {"message":"order confirmation email sent to \"moore@example.com\"","severity":"info","timestamp":"2026-09-10T15:02:31.111180833Z"}
2026-09-10T15:02:31.112522+00:00  {"message":"Successful to write message. offset: 32603","severity":"info","timestamp":"2026-09-10T15:02:31.112420708Z"}
```

> Evidence `tr_c5d2633b4d50`:

```
<tool_result id="tr_c5d2633b4d50" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T15:02:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" template="error-ratio" baseline="2026-09-10T14:30:28.943916+00:00..2026-09-10T15:02:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_f4ee40922f92`:

```
<tool_result id="tr_f4ee40922f92" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T15:32:30.583000+00:00..2026-09-10T15:34:32.222084+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_f4ee40922f92>
```

