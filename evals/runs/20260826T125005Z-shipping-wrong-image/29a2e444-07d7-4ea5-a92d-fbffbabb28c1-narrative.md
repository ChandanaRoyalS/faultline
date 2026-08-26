# Checkout fails fast at the shipping-quote edge; mechanism unidentified

## What was visible, in order

The page arrived as a fan-out: six services alerting together at roughly T+13m (checkoutservice, shippingservice, accountingservice, emailservice, frauddetectionservice, quoteservice), blast radius eleven services, severity critical. The first read — six independent degradations — was wrong, and most of the early effort went into disproving it.

The first useful signal was checkoutservice's own error ratio: sixty-one sample points ranging from zero up to a peak near 32%. Not total, not flat, with a transition inside the window. It told us nothing about which downstream call failed, because the aggregation was by service name only.

Logs were all info severity — no exceptions, no status lines, nothing self-reported. What they did show was a shape change. Early in the window, order flows completed end to end: initiation, payment authorization, confirmation email, message write. From roughly T+11m onward only initiation entries remain, with no completion lines beside them, at a steady cadence through T+14m50s. The service was alive and starting orders it never finished. That ruled out a crash or restart, and ruled out cohort selectivity — both currencies and many user ids were affected.

Traces resolved it. Every complete checkout trace terminates at checkoutservice's call to ShippingService/GetQuote, marked ERROR, propagating up through prepareOrderItemsAndShippingQuoteFromCart, PlaceOrder, frontend PlaceOrder and the frontend HTTP POST. The failing spans are sub-millisecond to a few milliseconds and whole failing requests finish under about 17ms: an immediate rejection, not a wait. Sibling dependencies in those same traces — cartservice and its Redis HGET, productcatalogservice, featureflagservice, currencyservice — are all present, fast and unflagged. Across two hundred spans there is no payment, email, or message-bus span at all, which is why the logs go quiet: the path never gets that far.

> Evidence `tr_67a639c6feff`:

```
<tool_result id="tr_67a639c6feff" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.3171 n=61
</tool_result:tr_67a639c6feff>
```

> Evidence `tr_dc4dd324c0ed`:

```
<tool_result id="tr_dc4dd324c0ed" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T12:43:14.699923+00:00  {"message":"[PlaceOrder] user_id=\"b468e34c-a14b-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T12:43:14.699726716Z"}
2026-08-26T12:43:14.717748+00:00  {"message":"payment went through (transaction_id: c144c47c-fcc2-48d0-95a9-d3c31ce321bd)","severity":"info","timestamp":"2026-08-26T12:43:14.717693966Z"}
2026-08-26T12:43:14.722782+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-26T12:43:14.722708549Z"}
2026-08-26T12:43:14.723579+00:00  {"message":"Successful to write message. offset: 9528","severity":"info","timestamp":"2026-08-26T12:43:14.723459383Z"}
```

> Evidence `tr_89474c9be033`:

```
<tool_result id="tr_89474c9be033" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
service: checkoutservice
200 spans
  9e33e6a41d462dbf cartservice/HGET 0.4ms
  9e33e6a41d462dbf checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.8ms
  9e33e6a41d462dbf productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

## Dead ends worth keeping

The alert fan-out as six independent failures. emailservice's error ratio is flat zero at all sixty-one points including the alert minute, and it resolves to a defined zero, which requires a non-zero denominator — it was still handling calls. Combined with the traces, the fan-out is downstream starvation: work stopped arriving. Note what this does not close: no consumer-lag, queue-depth or in-flight series were queried, so those are unmeasured, not healthy.

cartservice as the upstream trigger. The error-ratio query returned nothing — and the unfiltered denominator also matched nothing. An idle service would still yield a zero-valued total-calls series, so this points at a metric-name or label-schema mismatch, or missing span-metrics instrumentation, not zero traffic. That metric path can support no conclusion either way; a retry needs different names. Traces independently show cartservice healthy on the checkout path.

Latency saturation, a downstream timeout, payment, email, and a backed-up message write. All ruled out: durations are far too small for a timeout, and none of those spans exist in the failing traces.

A local change on checkoutservice or paymentservice. Both change queries returned empty — no deploys, config edits or flag flips. Two caveats: both started about eight minutes after the requested window opened, and both were scoped to one service each, carrying no information about the message bus, service mesh, or shared config repositories.

> Evidence `tr_c0d43c9cb03d`:

```
<tool_result id="tr_c0d43c9cb03d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="emailservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="emailservice"}[2m]))
1 series
  {service_name=emailservice} min=0 max=0 n=61
</tool_result:tr_c0d43c9cb03d>
```

> Evidence `tr_9059d8e2b3e8`:

```
<tool_result id="tr_9059d8e2b3e8" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_9059d8e2b3e8>
```

> Evidence `tr_8361564246d9`:

```
<tool_result id="tr_8361564246d9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_8361564246d9>
```

> Evidence `tr_d2099c6952f8`:

```
<tool_result id="tr_d2099c6952f8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
no changes recorded for paymentservice over this window
</tool_result:tr_d2099c6952f8>
```

## Where it stopped, and what is open

The failing edge is identified; the mechanism behind it is not. Confidence is low and no fix class was reached. The reason is coverage, not analysis: nothing was retrieved for shippingservice or quoteservice in any modality, despite both alerting. Everything known about that edge comes from the caller's side. A wrong artifact, a wrong configuration value, and an immediate rejection under resource pressure all fit the fast-error signature equally well.

Open for whoever picks this up: (1) What does shippingservice return on GetQuote, and why — pull its logs and traces, and quoteservice's. This is the whole investigation now. (2) Were there changes to shippingservice, quoteservice, or shared mesh/bus/config scopes? Only two services were checked, and only from eight minutes in. (3) Fix the onset estimate: logs suggest roughly T+11m, but the earliest partial trace already shows the ERROR GetQuote, so the failure may predate the queried window.

Two instrumentation defects to file regardless: checkoutservice emits no error-severity line when a dependency rejects it, and cartservice's calls-total series is not retrievable under the expected metric and label names.

> Evidence `tr_89474c9be033`:

```
<tool_result id="tr_89474c9be033" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
service: checkoutservice
200 spans
  9e33e6a41d462dbf cartservice/HGET 0.4ms
  9e33e6a41d462dbf checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.8ms
  9e33e6a41d462dbf productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

> Evidence `tr_dc4dd324c0ed`:

```
<tool_result id="tr_dc4dd324c0ed" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T12:43:14.699923+00:00  {"message":"[PlaceOrder] user_id=\"b468e34c-a14b-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T12:43:14.699726716Z"}
2026-08-26T12:43:14.717748+00:00  {"message":"payment went through (transaction_id: c144c47c-fcc2-48d0-95a9-d3c31ce321bd)","severity":"info","timestamp":"2026-08-26T12:43:14.717693966Z"}
2026-08-26T12:43:14.722782+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-26T12:43:14.722708549Z"}
2026-08-26T12:43:14.723579+00:00  {"message":"Successful to write message. offset: 9528","severity":"info","timestamp":"2026-08-26T12:43:14.723459383Z"}
```

> Evidence `tr_9059d8e2b3e8`:

```
<tool_result id="tr_9059d8e2b3e8" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T12:43:00.583000+00:00..2026-08-26T12:58:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_9059d8e2b3e8>
```
