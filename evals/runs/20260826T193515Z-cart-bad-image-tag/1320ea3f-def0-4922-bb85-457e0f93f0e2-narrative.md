# Checkout failures traced to an absent cart backend after an automated image-reference change

## What was visible, in order

The page arrived wide: thirteen services in the blast radius, critical severity, with eight services alerting including frontend, loadgenerator and several siblings. That breadth is misleading — it is downstream noise from a single broken edge. The named entry point was checkoutservice, and that is where work started.

First reading: checkoutservice's own call metrics. Errors reached roughly two-thirds of all calls at peak, across 57 samples at about fifteen-second spacing. The series also touched zero inside the window, so this was an episode with a start edge, not a chronic condition; and the peak stayed well below 1.0 with a live denominator, so checkoutservice itself was not down. Only min/max came back, not per-timestamp values, so the onset time could not be read — a gap that was never closed.

Traces narrowed it fast. Every sampled failing trace was an identical five-span shape: frontend HTTP POST, PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, terminating at checkoutservice's outbound hipstershop.CartService/GetCart, which was the deepest ERROR span. The enclosing work span was not flagged ERROR. Root spans ran a few milliseconds end to end — no slow span anywhere, which reads as immediate connection-level rejection rather than a deadline exceeded. Checkout aborted before payment, shipping, currency or email were ever attempted.

Following that edge: cartservice logs showed routine GetCart/AddItem/EmptyCart handling with no errors, a last cart read at 19:35:15.429Z (about T+5m30s), then a graceful hosting-lifetime shutdown notice, then nothing. The time of interest sits inside that silence. The change log records exactly one entry for cartservice — a platform-automation image-reference update to a hotfix-tagged build one second after the shutdown, prior value recorded as absent/unknown. Confirming it, a cartservice metrics query returned no series at all for the whole window: not even an unfiltered denominator. A workload serving badly still produces a denominator; one that never came back produces neither.

> Evidence `tr_f7e696dcd6c2`:

```
<tool_result id="tr_f7e696dcd6c2" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=57
</tool_result:tr_f7e696dcd6c2>
```

> Evidence `tr_08259ff1b6d1`:

```
<tool_result id="tr_08259ff1b6d1" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
service: checkoutservice
200 spans
  f1f6126d07037af7 frontend/HTTP POST 4.7ms ERROR
  f1f6126d07037af7 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 4.6ms ERROR
  f1f6126d07037af7 checkoutservice/hipstershop.CheckoutService/PlaceOrder 3.5ms ERROR
```

> Evidence `tr_45411d2065e7`:

```
<tool_result id="tr_45411d2065e7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T19:29:45.661931+00:00  GetCartAsync called with userId=
2026-08-26T19:29:46.075306+00:00  AddItemAsync called with userId=7ed0423c-a184-11f1-86d7-1e4ac5f08d0c, productId=0PUK6V6EV0, quantity=3
2026-08-26T19:29:46.077390+00:00  GetCartAsync called with userId=7ed0423c-a184-11f1-86d7-1e4ac5f08d0c
2026-08-26T19:29:47.399662+00:00  GetCartAsync called with userId=
```

> Evidence `tr_a059ea1b67b4`:

```
<tool_result id="tr_a059ea1b67b4" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
service: cartservice
1 changes
  2026-08-26T19:35:16.832171+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
</tool_result:tr_a059ea1b67b4>
```

> Evidence `tr_510fdfde247a`:

```
<tool_result id="tr_510fdfde247a" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_510fdfde247a>
```

## Dead ends worth keeping

A change on checkoutservice itself: the change log returned nothing for it in the window — no deploys, config pushes, flag flips, or logged rollback. Coverage was thinner than the question deserved: only the fifteen-minute window, only checkoutservice, none of its five direct dependencies.

A payment problem behind an unmeasured edge: tempting, since paymentservice sits on one. But no trace reaches a payment step; the abort is upstream of it, so that edge cannot be the origin.

Latency or timeout saturation: ruled out by single-digit-millisecond spans, far below any plausible RPC deadline.

The frontend as source: its spans carry ERROR only as inherited status, with durations tracking the child subtree.

Checkoutservice's own assembly logic: that span is consistently not flagged ERROR while its child is.

Cache/Redis connection errors or an auth failure inside cartservice: no such lines appear anywhere, and the service emitted nothing at the time of interest.

A panic or crashloop: the final line is an ordinary informational shutdown with no error path before it.

A broken metrics pipeline or a bad log selector explaining the silence: 57 regularly spaced samples with no gaps flagged, and the same log query returned substantial volume earlier in the window. Both silences are real.

Deploy thrash on cartservice: exactly one change entry in the interval.

> Evidence `tr_5ea5f12bf4c3`:

```
<tool_result id="tr_5ea5f12bf4c3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_5ea5f12bf4c3>
```

> Evidence `tr_08259ff1b6d1`:

```
<tool_result id="tr_08259ff1b6d1" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
service: checkoutservice
200 spans
  f1f6126d07037af7 frontend/HTTP POST 4.7ms ERROR
  f1f6126d07037af7 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 4.6ms ERROR
  f1f6126d07037af7 checkoutservice/hipstershop.CheckoutService/PlaceOrder 3.5ms ERROR
```

> Evidence `tr_45411d2065e7`:

```
<tool_result id="tr_45411d2065e7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T19:29:45.661931+00:00  GetCartAsync called with userId=
2026-08-26T19:29:46.075306+00:00  AddItemAsync called with userId=7ed0423c-a184-11f1-86d7-1e4ac5f08d0c, productId=0PUK6V6EV0, quantity=3
2026-08-26T19:29:46.077390+00:00  GetCartAsync called with userId=7ed0423c-a184-11f1-86d7-1e4ac5f08d0c
2026-08-26T19:29:47.399662+00:00  GetCartAsync called with userId=
```

> Evidence `tr_510fdfde247a`:

```
<tool_result id="tr_510fdfde247a" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_510fdfde247a>
```

## Conclusion, and what is still open

cartservice was moved to a hotfix-tagged build at about T+5m31s, the running instance stopped cleanly one second earlier, and the replacement never began serving. Callers saw immediate connection-level rejection on GetCart, which propagated up as checkout failure and lit eight alerts. The problem lies in the artifact now referenced, not in any code path that executed. Fix class: rollback. Confidence: medium — the mechanism is inferred from total metric and log silence, not directly observed.

Still open. No pod- or workload-level evidence was ever gathered: nobody confirmed whether the new image is crashlooping, stuck pulling, failing readiness, or scaled to zero. That is the first check next time and it costs one query. The rollback target is not established, because the prior image reference is recorded as absent/unknown; recover it from deployment history before acting. Why automation pushed a hotfix build at that moment is unexplained — if it was remediating something earlier, the preceding two hours are entirely uncovered. The arithmetic also does not fully close: checkoutservice peaks near two-thirds errors while traces show no successful PlaceOrder at all, and the surviving successful calls were never identified. Finally, the cartservice log result was truncated between roughly 19:29:49Z and 19:35:01Z, so an early degradation ramp in that gap cannot be excluded, and the cache backend was checked only for change records, never for health.

> Evidence `tr_a059ea1b67b4`:

```
<tool_result id="tr_a059ea1b67b4" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
service: cartservice
1 changes
  2026-08-26T19:35:16.832171+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
</tool_result:tr_a059ea1b67b4>
```

> Evidence `tr_45411d2065e7`:

```
<tool_result id="tr_45411d2065e7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T19:29:45.661931+00:00  GetCartAsync called with userId=
2026-08-26T19:29:46.075306+00:00  AddItemAsync called with userId=7ed0423c-a184-11f1-86d7-1e4ac5f08d0c, productId=0PUK6V6EV0, quantity=3
2026-08-26T19:29:46.077390+00:00  GetCartAsync called with userId=7ed0423c-a184-11f1-86d7-1e4ac5f08d0c
2026-08-26T19:29:47.399662+00:00  GetCartAsync called with userId=
```

> Evidence `tr_510fdfde247a`:

```
<tool_result id="tr_510fdfde247a" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_510fdfde247a>
```

> Evidence `tr_f7e696dcd6c2`:

```
<tool_result id="tr_f7e696dcd6c2" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T19:29:45.583000+00:00..2026-08-26T19:44:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=57
</tool_result:tr_f7e696dcd6c2>
```
