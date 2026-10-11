# Checkout order placement failing on shipping quote calls

## What we saw first

The page opened with checkout as the reported origin and seven services alerting around it: checkout, accounting, email, fraud-detection, payment, quote and shipping. Thirteen services showed impact in total. From the responder's chair the first impression was a broad, multi-service event, which is the wrong impression: most of those services sit downstream of order placement and were reacting, not breaking.

The first useful number was checkout's error ratio. Over the two hours around onset it averaged roughly 22% of spans erroring, peaking near 27%. That shape matters: roughly three quarters of checkout calls were still succeeding, so this was never a hard-down service. It is a partial failure confined to one code path.

> Evidence `tr_7580feacf3e3`:

```
<tool_result id="tr_7580feacf3e3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T11:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" template="error-ratio" baseline="2026-10-06T09:49:39.072981+00:00..2026-10-06T11:55:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=32 mean=0.2165 min=0.06394 max=0.2658 sd=0.06531
  baseline window: no samples
```

## Chasing checkout's own logs - a dead end

The obvious next move was to read checkout's logs across the hour on either side of onset. The query returned nothing at all. Not zero errors - zero lines of any severity, matched only on the service label with no filter applied.

This cost time. Two readings were considered and neither helps: a healthy service under live traffic still emits info-level lines, so silence is not evidence of health; and widening the window would not have helped, since the query already spanned roughly an hour each side. The honest conclusion is a logging or label-mapping gap on checkout in this backend. A responder hitting the same wall should move straight to traces rather than trying to coax logs out of checkout.

> Evidence `tr_61cd4f19d3b4`:

```
<tool_result id="tr_61cd4f19d3b4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-06T12:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_61cd4f19d3b4>
```

## The change-history sweep - all empty, and narrower than it looks

Change history was pulled for checkout, cart and flagd. All three came back empty: no deploys, no config pushes, no flag edits, no dependency bumps.

There is a trap here worth recording. The window that was actually queried begins at the onset timestamp and runs roughly twenty-four hours forward. It therefore covers the event and its aftermath, not the hours preceding it. So what these results genuinely establish is narrow but real: nothing landed on checkout, cart or flagd during or after onset, so no concurrent rollout triggered this and no hotfix or rollback prolonged it. flagd in particular can be treated as static, which removes it as a moving target when reading checkout-side evidence. What they do not establish is the absence of a change before onset. That remains unchecked for every service.

> Evidence `tr_669e3f3c2d50`:

```
<tool_result id="tr_669e3f3c2d50" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T13:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_669e3f3c2d50>
```

> Evidence `tr_f87c07561cc3`:

```
<tool_result id="tr_f87c07561cc3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T13:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" radius="candidate_cause" hops="1">
no changes recorded for cart over this window
</tool_result:tr_f87c07561cc3>
```

> Evidence `tr_17f461169a3f`:

```
<tool_result id="tr_17f461169a3f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T13:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_17f461169a3f>
```

## Traces: where the error actually originates

Nine checkout traces were sampled, clustered between roughly T-2m and T+0. Every one tells the same story. The deepest span carrying an error status is checkout's own outbound HTTP POST to the shipping service, issued from prepareOrderItemsAndShippingQuoteFromCart. The parent PlaceOrder span wraps the same failure, and the error then propagates upward unchanged through frontend, frontend-proxy and the load generator - those spans are error-marked only by inheritance.

Three things were ruled out here. Checkout's other dependencies are clean: cart, product-catalog including its SQL query span, and currency all complete without error in sub-millisecond to few-millisecond times. Checkout's own internal work is not at issue - its self time on PlaceOrder is mostly under a millisecond. And this is not a timeout: the failing span lasts only about 2.5 to 6ms and consumes 2-19% of trace duration, which is the signature of an immediate failure to even establish the call, not of waiting on a slow peer.

Crucially, no shipping-side server span appears in any trace. The request never arrived.

> Evidence `tr_060fe16b324e`:

```
<tool_result id="tr_060fe16b324e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-06T13:25:31.664000+00:00..2026-10-06T14:01:24.255019+00:00">
service: checkout
9 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 226fc2b14a276f04  root load-generator/user_checkout_single  57.0ms  started 2026-10-06T13:53:18.732419+00:00  19 spans
  +0.0ms load-generator/user_checkout_single 57.0ms [self 19.0ms]
```

## Frontend logs: the failure mode changes mid-window

Frontend's logs were the one place with readable text, and they carry the most informative detail in the whole record. Every error line in the window is the same shape - a gRPC INTERNAL error raised while POSTing to shipping's get-quote endpoint on port 50050, from an identical call site. One code path, one downstream. No other dependency appears in frontend's error output at all.

The mode shifts across the window. The earliest retained lines, around T-3m, show the shipping name resolving to a concrete pod IP and the TCP connection being actively refused. The latest retained lines, around T+5m to T+6m, show name resolution for shipping failing outright against the embedded resolver. So shipping was first registered-but-unreachable, then gone from discovery altogether.

Two caveats a later reader should carry. The result was truncated to the oldest handful and newest batch of lines, dropping everything between roughly T-3m and T+5m - the onset instant itself sits inside that gap and was bracketed, never observed directly. And errors were still being emitted seconds before the window closed, so this had not recovered by the end of what we looked at.

> Evidence `tr_34c97c9955a6`:

```
<tool_result id="tr_34c97c9955a6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T13:25:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T13:52:09.665808+00:00  Error: 13 INTERNAL: shipping quote failure: failed POST to shipping service: Post "http://shipping:50050/get-quote": dial tcp 172.18.0.25:50050: connect: connection refused
2026-10-06T13:52:09.665873+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-06T13:52:09.665876+00:00      at new Promise (<anonymous>) {
2026-10-06T13:52:09.665877+00:00    code: 13,
```

## What we concluded

Shipping stopped serving. Its socket actively refused connections while the name still resolved, and shortly afterward the name vanished from service discovery. Callers never reached a shipping process. Checkout's elevated error ratio is exactly the subset of its traffic that needs a shipping quote; everything else on the checkout path kept working, which is why the ratio sat near 22% rather than near 100%.

The remedy class is a restart of shipping. Confidence is medium, and the reasons for that reservation are in the next section.

> Evidence `tr_34c97c9955a6`:

```
<tool_result id="tr_34c97c9955a6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T13:25:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T13:52:09.665808+00:00  Error: 13 INTERNAL: shipping quote failure: failed POST to shipping service: Post "http://shipping:50050/get-quote": dial tcp 172.18.0.25:50050: connect: connection refused
2026-10-06T13:52:09.665873+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-06T13:52:09.665876+00:00      at new Promise (<anonymous>) {
2026-10-06T13:52:09.665877+00:00    code: 13,
```

> Evidence `tr_060fe16b324e`:

```
<tool_result id="tr_060fe16b324e" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-06T13:25:31.664000+00:00..2026-10-06T14:01:24.255019+00:00">
service: checkout
9 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 226fc2b14a276f04  root load-generator/user_checkout_single  57.0ms  started 2026-10-06T13:53:18.732419+00:00  19 spans
  +0.0ms load-generator/user_checkout_single 57.0ms [self 19.0ms]
```

> Evidence `tr_7580feacf3e3`:

```
<tool_result id="tr_7580feacf3e3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T11:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" template="error-ratio" baseline="2026-10-06T09:49:39.072981+00:00..2026-10-06T11:55:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=32 mean=0.2165 min=0.06394 max=0.2658 sd=0.06531
  baseline window: no samples
```

## Open questions and what we never measured

Ten edges in the blast radius were never measured, and the most important gap is that no dispatch ever looked at shipping directly. Its own logs, metrics, change history and restart or memory-kill status are entirely unexamined. Whether the process crashed, was reclaimed for memory, or was deliberately stopped is unsettled.

The refused-connection phase is worth arguing about. A process that is merely frozen typically keeps its listening socket accepting and leaves callers hanging; active refusal followed by loss of the DNS name reads more like the process exiting and the container being descheduled. If that is right, the mechanism should be reclassified even though the remedy is unchanged.

Three smaller gaps. The pre-onset period was never queried for any service, so an earlier deploy or config push remains possible. Checkout's total log silence is unexplained and could be a second, independent problem. And checkout's error ratio never dropped below about 6.4% even before the nominal onset, so the true start time - and whether shipping was partially degraded earlier - is unknown. Treat the onset timestamp as an escalation point, not a beginning. One more caution on the metrics: the baseline comparison returned no samples at all, so any tool verdict of "no departure from baseline" for checkout is vacuous and must not be used to call 22% errors normal.

> Evidence `tr_7580feacf3e3`:

```
<tool_result id="tr_7580feacf3e3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T11:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" template="error-ratio" baseline="2026-10-06T09:49:39.072981+00:00..2026-10-06T11:55:31.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=32 mean=0.2165 min=0.06394 max=0.2658 sd=0.06531
  baseline window: no samples
```

> Evidence `tr_61cd4f19d3b4`:

```
<tool_result id="tr_61cd4f19d3b4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-06T12:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_61cd4f19d3b4>
```

> Evidence `tr_669e3f3c2d50`:

```
<tool_result id="tr_669e3f3c2d50" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T13:55:31.664000+00:00..2026-10-06T14:01:24.255019+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_669e3f3c2d50>
```

