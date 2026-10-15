# Order publish and consume stall across the shared message bus

## What was visible first

Three services paged together: checkout, fraud-detection, accounting. Take T+0 as the page. Checkout's error ratio had a hard-zero baseline — thirty-five samples, no variance — then a single step at about T-1m. Step, not ramp. That compressed the search to the final minutes and killed any theory of slow rot through the preceding half hour. It also set a trap: peak ratio was only ~6.7%, which reads as partial failure. That framing was wrong. Most checkout spans are not order publishes, so a total failure of one span type dilutes across all spans. Do not let a low ratio argue you out of a hard-down dependency. Fraud-detection showed the same profile — flat zero, then a step at the same moment to roughly eighteen percent — which ruled out both that it failed first and that it moved in lockstep from the window's opening.

> Evidence `tr_b043ffff2d0d`:

```
<tool_result id="tr_b043ffff2d0d" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T03:21:46.664000+00:00..2026-10-14T03:54:35.673674+00:00" template="error-ratio" baseline="2026-10-14T02:48:57.654326+00:00..2026-10-14T03:21:46.664000+00:00">
service: checkout
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="checkout"}[5m]))
  incident window: n=88 mean=0.01629 min=0 max=0.06713 sd=0.02613
  baseline window: n=35 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_6c3761e36cc7`:

```
<tool_result id="tr_6c3761e36cc7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T03:21:46.664000+00:00..2026-10-14T03:54:35.673674+00:00" template="error-ratio" baseline="2026-10-14T02:48:57.654326+00:00..2026-10-14T03:21:46.664000+00:00">
service: fraud-detection
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="fraud-detection"}[5m]))
  incident window: n=88 mean=0.1847 min=0 max=1 sd=0.3866
  baseline window: n=35 mean=0 min=0 max=0 sd=0
```

## The dead ends

Checkout's log stream returned nothing at all — zero lines of any severity over about thirty-three minutes, for a service that was still serving traffic and still emitting span metrics. Two readings survived and neither was settled: the process emits nothing in this state, or its shipping path or label is broken. Still open.

The change history was queried for checkout and for fraud-detection across the full day around the event. Both came back completely empty: no deploys, config edits, flag edits, or infrastructure edits, and so no rollback available for either. Worth the honesty: both queries were scoped to the named service only. Nobody ever searched for a change against the broker tier or its infrastructure.

Fraud-detection also showed an unexplained sixteen-minute logging silence about an hour earlier, in a truncated result. Possibly a prior instability, possibly an artefact. Not closed.

> Evidence `tr_21a073a85754`:

```
<tool_result id="tr_21a073a85754" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T03:21:46.664000+00:00..2026-10-14T03:54:35.673674+00:00">
no log lines matched {service="checkout"} over this window
</tool_result:tr_21a073a85754>
```

> Evidence `tr_7da8dfecbc65`:

```
<tool_result id="tr_7da8dfecbc65" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T03:51:46.664000+00:00..2026-10-14T03:54:35.673674+00:00" radius="seed" hops="0">
no changes recorded for checkout over this window
</tool_result:tr_7da8dfecbc65>
```

> Evidence `tr_fcc1c236213b`:

```
<tool_result id="tr_fcc1c236213b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-13T03:51:46.664000+00:00..2026-10-14T03:54:35.673674+00:00" radius="seed" hops="0">
no changes recorded for fraud-detection over this window
</tool_result:tr_fcc1c236213b>
```

## The turn, and what remains open

The traces broke it. In failing checkout traces exactly one span carries an error — the order-publish producer span — and it holds essentially the whole ninety-plus-second trace duration, with messages for an open circuit breaker and a client unable to resolve or reach any broker. Every synchronous downstream was clean in single-digit milliseconds: cart and its Redis ops, product-catalog including its SQL spans, currency, shipping, payment, email, flag resolution. The errors on the ingress and load-generator spans are decoys — fifteen-second client timeouts firing while the publish span runs another seventy-five to eighty-five seconds.

Accounting confirmed from the consumer side: healthy order processing early, then only client-library errors reporting both brokers down, retrying once a second. Resolution failures for the broker host on 9092, and connection-refused on the resolved address. Not pure name resolution, since some attempts resolve and are then refused; not single-replica loss, since both brokers are down; the process was alive throughout. Fraud-detection meanwhile consumed steadily with a monotonic counter and no errors, then simply went silent at about T-5m — a consumer with no reachable broker.

Conclusion: loss of connectivity to the broker endpoint, not a defect in any application service. Fix class: reconnect. Confidence medium, because nobody examined the broker tier itself — its process, logs, storage, or resources — so what stopped it accepting is unestablished. Start there, then search the change log against the broker, then settle whether checkout's silence is the process or the log pipeline.

> Evidence `tr_2ec5bf2571f1`:

```
<tool_result id="tr_2ec5bf2571f1" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T02:51:46.664000+00:00..2026-10-14T03:54:35.673674+00:00">
service: checkout
4 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace db860dd04fe7f8fd  root load-generator/user_checkout_multi  15028.3ms  started 2026-10-14T03:53:47.344157+00:00  54 spans
  +0.0ms load-generator/user_checkout_multi 15028.3ms [self 26.7ms]
```

> Evidence `tr_9f9b92f621c4`:

```
<tool_result id="tr_9f9b92f621c4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T03:21:46.664000+00:00..2026-10-14T03:54:35.673674+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-14T03:26:21.849781+00:00  info: Accounting.Consumer[174880625]
2026-10-14T03:26:21.849871+00:00        Order details: { "orderId": "0703720f-c77f-11f1-a869-9ee861b76b02", "shippingTrackingId": "9a050fa0-d58c-40cf-b519-a20add7295dc", "shippingCost": { "currencyCode": "USD", "units": "98", "nanos": 890000000 }, "shippingAddress": { "streetAddress": "100 Winchester Circle", "city": "Los Gatos", "state": "CA", "country": "United States", "zipCode": "95032" }, "items": [ { "item": { "productId": "6E92ZMYYFZ", "quantity": 4 }, "cost": { "currencyCode": "USD", "units": "69", "nanos": 950000000 } }, { "item": { "productId": "LS4PSXUNUM", "quantity": 3 }, "cost": { "currencyCode": "USD", "units": "57", "nanos": 799999999 } }, { "item": { "productId": "66VCHSJNUP", "quantity": 4 }, "cost": { "currencyCode": "USD", "units": "349", "nanos": 949999999 } } ] }.
2026-10-14T03:26:33.789189+00:00  info: Accounting.Consumer[174880625]
2026-10-14T03:26:33.789539+00:00        Order details: { "orderId": "0df14516-c77f-11f1-a869-9ee861b76b02", "shippingTrackingId": "6db635d0-38e1-4cc3-b6da-c3cbc5dc11f2", "shippingCost": { "currencyCode": "USD", "units": "89", "nanos": 900000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "L9ECAV7KIM", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } }, { "item": { "productId": "9SIQT8TOJO", "quantity": 3 }, "cost": { "currencyCode": "USD", "units": "3599" } }, { "item": { "productId": "6E92ZMYYFZ", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "69", "nanos": 950000000 } }, { "item": { "productId": "HQTGWGPNH4", "quantity": 3 }, "cost": { "currencyCode": "USD", "nanos": 990000000 } } ] }.
```

> Evidence `tr_d9de5df438bd`:

```
<tool_result id="tr_d9de5df438bd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T02:51:46.664000+00:00..2026-10-14T03:54:35.673674+00:00" oldest_kept="8" newest_kept="32">
selector: {service="fraud-detection"}
2026-10-14T02:52:13.965506+00:00  2026-10-14 02:52:13 - fraud-detection - Consumed record with orderId: 42682d90-c77a-11f1-a869-9ee861b76b02, and updated total count to: 240 trace_id=7f5187e61c8bdb012b08f8dea901e7dc span_id=a7a8f3e10381c6d9 trace_flags=01 
2026-10-14T02:52:27.303299+00:00  2026-10-14 02:52:27 - fraud-detection - Consumed record with orderId: 4a5bf805-c77a-11f1-a869-9ee861b76b02, and updated total count to: 241 trace_id=005aef8f48f115dcd7783212271c722b span_id=593390f3c0f20d37 trace_flags=01 
2026-10-14T02:52:29.597811+00:00  2026-10-14 02:52:29 - fraud-detection - Consumed record with orderId: 4bbcf96e-c77a-11f1-a869-9ee861b76b02, and updated total count to: 242 trace_id=1bb6d9d3b6172589711034352698d3dc span_id=bf2723d19dc771a6 trace_flags=01 
2026-10-14T02:52:38.878462+00:00  2026-10-14 02:52:38 - fraud-detection - Consumed record with orderId: 50f533be-c77a-11f1-a869-9ee861b76b02, and updated total count to: 243 trace_id=b762d928d7da413c7f409dc989bce3d4 span_id=bdf2520ab7d543d1 trace_flags=01 
```

