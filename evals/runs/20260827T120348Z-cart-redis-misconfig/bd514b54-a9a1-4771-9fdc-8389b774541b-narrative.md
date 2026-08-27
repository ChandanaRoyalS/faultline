# Checkout order placement fails at the cart lookup hop

## What we saw first

The page opened with three alerts arriving close together: checkoutservice, frontend, and loadgenerator. That grouping is misleading on its face — loadgenerator and frontend are downstream consumers of the checkout path, so their alarms are echoes rather than signals. Blast radius was assessed at twelve services, severity critical, with checkoutservice named as the starting point. The responder's first instinct, reasonably, was that checkoutservice had broken itself. That instinct cost about the first third of the investigation and turned out to be wrong.

## The change-history dead end (T+0 to T+6m)

The opening move was to pull the change history for checkoutservice covering the ninety minutes before onset. It came back empty — no deploys, no config edits, no flag flips. That is useful in one narrow direction (there is nothing to roll back on checkoutservice) but it carries a trap worth recording: the query window actually resolved to roughly fifteen minutes, not the ninety that was asked for. The earlier part of the lookback was never examined, and nobody noticed the discrepancy until much later. If you are re-treading this ground, verify the window your change-history tool actually used before you treat an empty result as an answer.

> Evidence `tr_382063006eb4`:

```
<tool_result id="tr_382063006eb4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_382063006eb4>
```

## The metric that pointed the wrong way (T+6m to T+14m)

Next came the error ratio for checkoutservice. It showed elevated error fractions peaking around two-thirds of calls, but bursty — dipping back to zero at several sample points across thirty-five samples. Two conclusions were drawn from this and both were premature. First, the burstiness was read as intermittent behaviour, which steered thinking toward a flapping or partial condition. Second, and more damaging, the series was aggregated by service name only, with no downstream-target dimension, no absolute request rate, and no latency percentiles. It could not attribute the errors to any dependency, and roughly eight minutes were spent trying to make it do so. It did rule out one thing cleanly: checkoutservice was not simply an innocent bystander in the path — its own spans were error-coded at a real rate.

> Evidence `tr_28f9f06549f8`:

```
<tool_result id="tr_28f9f06549f8" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=35
</tool_result:tr_28f9f06549f8>
```

## Traces broke it open (T+14m to T+22m)

The trace query was the turn. Around forty distinct failing traces came back and every single one had the same five-span shape: frontend HTTP POST, frontend PlaceOrder, checkoutservice PlaceOrder, checkoutservice's order-preparation span, and then an outbound CartService/GetCart call issued by checkoutservice. That GetCart span is the deepest span present and the only span carrying an ERROR status that was not inherited from below. The order-preparation span sitting directly above it is clean; everything above that is error-marked purely by propagation.

Two details from the timing matter. All spans complete in single-digit milliseconds, with the GetCart leaves typically well under one millisecond and the slowest whole trace around six. Nothing is waiting on anything — these are immediate rejections at the cart hop, not timeouts and not a slow dependency saturating checkout. And the uniformity contradicts the earlier metric read: no successful PlaceOrder traces appeared at all in the sample, so this is not a partial degradation, a canary, or a single bad pod. The reconciliation between a bursty error ratio and uniformly failing traces was never completed and remains open.

The traces also disposed of a whole branch of hypothesis at once. No spans for payment, shipping, email, currency, or product catalog appear anywhere — checkout aborts during order preparation before those calls are ever attempted. Chasing any of them would have been wasted effort.

> Evidence `tr_39d61a838631`:

```
<tool_result id="tr_39d61a838631" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
service: checkoutservice
200 spans
  12fefea218179329 frontend/HTTP POST 2.7ms ERROR
  12fefea218179329 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 2.6ms ERROR
  12fefea218179329 checkoutservice/hipstershop.CheckoutService/PlaceOrder 1.3ms ERROR
```

## Confirming the cart side, and where it stopped (T+22m to T+31m)

With cartservice identified as the abort point, the obvious next step was to look at its metrics. The error-ratio query returned no series whatsoever. Critically, this is not the same as "no errors": the call-count denominator was absent too, so neither the numerator nor the denominator matched any data. A service that is up and healthy still produces a denominator. A total absence of both is what you get from a process that is not serving RPCs at all.

For contrast, productcatalogservice was queried and returned a computable ratio flat at zero across thirty-eight points spanning the whole window — a working service, serving traffic, no errors. That comparison is what makes the cartservice emptiness meaningful rather than ambiguous.

One more query is recorded and it is a dead end worth keeping: paymentservice also returned no series at all, numerator and denominator both. On first read this looked like a second broken service and briefly widened the search. It is not corroborating evidence — the traces already established that payment is never reached, so its telemetry gap is a separate and probably unrelated observability problem (missing emission, a collector gap, or a label mismatch). Do not let it pull you sideways; it will look like a lead and it is not.

> Evidence `tr_1a4680ab07c2`:

```
<tool_result id="tr_1a4680ab07c2" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_1a4680ab07c2>
```

> Evidence `tr_88f35ed09b48`:

```
<tool_result id="tr_88f35ed09b48" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=38
</tool_result:tr_88f35ed09b48>
```

> Evidence `tr_061309e5c840`:

```
<tool_result id="tr_061309e5c840" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))' over this window
</tool_result:tr_061309e5c840>
```

## Where the investigation ended

The metrics budget ran out here. What is established: every failing PlaceOrder aborts at checkoutservice's outbound cart call; the rejection is immediate; checkoutservice is exonerated as the origin (clean internal span, no change records in the interval that was actually covered); the other checkout downstreams are either never reached or demonstrably healthy; and cartservice emits no span metrics at all, consistent with a process not serving requests.

What is not established is why cartservice stopped serving. No cart-side logs, pod status, restart counts, or change records were ever queried. At the depth reached, at least three distinct causes produce this exact signature and cannot be told apart: a crash loop on a wrong image, a memory-kill and restart loop, or a process that is up but rejecting every connection due to a bad listen address or a credential problem. Confidence in any specific cause is low and no fix class is proposed.

> Evidence `tr_39d61a838631`:

```
<tool_result id="tr_39d61a838631" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
service: checkoutservice
200 spans
  12fefea218179329 frontend/HTTP POST 2.7ms ERROR
  12fefea218179329 frontend/grpc.hipstershop.CheckoutService/PlaceOrder 2.6ms ERROR
  12fefea218179329 checkoutservice/hipstershop.CheckoutService/PlaceOrder 1.3ms ERROR
```

> Evidence `tr_382063006eb4`:

```
<tool_result id="tr_382063006eb4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_382063006eb4>
```

> Evidence `tr_1a4680ab07c2`:

```
<tool_result id="tr_1a4680ab07c2" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_1a4680ab07c2>
```

## Next moves for whoever picks this up

Start at cartservice, not checkoutservice. Get pod state and restart counts first — that single query separates a crash loop from an up-but-rejecting process and collapses most of the remaining ambiguity. Then pull cartservice logs and its change history, and when you do, check the window your tool actually queried against the window you asked for. Finally, the unexplained tension is worth resolving: checkoutservice's error ratio dipped to zero at points while every sampled trace failed. That is either a restart loop producing genuine gaps in traffic, or a sampling artefact in the trace query. Either answer changes how you read the onset timing.

> Evidence `tr_28f9f06549f8`:

```
<tool_result id="tr_28f9f06549f8" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=35
</tool_result:tr_28f9f06549f8>
```

> Evidence `tr_382063006eb4`:

```
<tool_result id="tr_382063006eb4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T11:56:15.583000+00:00..2026-08-27T12:11:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_382063006eb4>
```
