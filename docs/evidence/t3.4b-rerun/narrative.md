# Checkout aborts at the shipping-quote hop

## What was visible, in order

The page arrived critical: twelve services in the radius, alerts on checkoutservice, emailservice, frauddetectionservice, quoteservice, shippingservice, accountingservice and the loadgenerator, with five crossed edges carrying no measurements at all. The handed starting point was checkoutservice, and the alert set made it look like the origin. It was not.

First move was to look for something that moved. A change-history query on checkoutservice over the fifteen minutes around onset came back completely empty — no deploys, no config edits, no flag flips. Widened to the five direct dependencies (paymentservice, currencyservice, cartservice, productcatalogservice, frontend), also empty. Useful negatives: there was no rollback candidate, and nobody should have burned the incident hunting a revert. The caveat that survives is coverage — only a fifteen-minute slice was queried; roughly the preceding fifty minutes were never looked at.

Metrics on checkoutservice then showed a real but partial problem: span error ratio peaking near 28% across sixty-one points at thirty-second resolution, touching zero at its minimum. So: not a total outage, most calls succeeded, the service was up and reporting continuously, and the condition was not a flat elevated floor. Why it peaks at 28% and dips to zero — partial-window onset, intermittency, or partial routing — was never resolved.

> Evidence `tr_8deedf529f24`:

```
<tool_result id="tr_8deedf529f24" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_8deedf529f24>
```

> Evidence `tr_cd8b667857a0`:

```
<tool_result id="tr_cd8b667857a0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00">
no changes recorded for checkoutservice and its direct dependencies (paymentservice, currencyservice, cartservice, productcatalogservice, frontend) over this window
</tool_result:tr_cd8b667857a0>
```

> Evidence `tr_33efb69359f7`:

```
<tool_result id="tr_33efb69359f7" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2821 n=61
</tool_result:tr_33efb69359f7>
```

## The dead end worth keeping

An error-ratio query was run against the four checkout dependencies and returned nothing. It is very tempting to read that as "zero errors" or "they stopped reporting." Both readings are wrong. The selector packed all four service names into a single label value, which cannot match any individual service_name label, so it matched no series at all — not even the denominator of total calls. A genuine zero-error condition would still have produced a series with a zero numerator. The empty result is an artifact of query construction and neither implicates nor exonerates any of those four. It also does not cast doubt on the metric or label schema, which remains untested. Separately, no latency percentiles were ever retrieved; that question stayed unanswered.

Logs were the second near-miss. The query was truncated, keeping only the oldest eight and newest thirty-two lines and leaving about eleven minutes in the middle unverified. Every returned line was severity info — no error text, no exception, no dependency named in any failure context. Anyone expecting the logs to name the culprit came away empty. The signal was in absence: early orders showed a full lifecycle (order start, payment success, confirmation email, queue write with incrementing offset), while in the last three and a half minutes only order-start lines remain. Intake never faltered, no restart banner appeared, and no queue produce errors were logged — that step is simply never reached. This is not a crash, not an ingress problem, and not a loud queue failure.

> Evidence `tr_ac12205653b5`:

```
<tool_result id="tr_ac12205653b5" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="paymentservice, currencyservice, cartservice, productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice, currencyservice, cartservice, productcatalogservice"}[2m]))' over this window
</tool_result:tr_ac12205653b5>
```

> Evidence `tr_04ef8cf2aed4`:

```
<tool_result id="tr_04ef8cf2aed4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T02:17:02.273945+00:00  {"message":"[PlaceOrder] user_id=\"397f9b78-a0f4-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T02:17:02.273679879Z"}
2026-08-26T02:17:02.292713+00:00  {"message":"payment went through (transaction_id: 4cca32d0-a95a-4ac7-a71b-e8f0e48e5714)","severity":"info","timestamp":"2026-08-26T02:17:02.292616129Z"}
2026-08-26T02:17:02.297883+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-08-26T02:17:02.297634379Z"}
2026-08-26T02:17:02.299025+00:00  {"message":"Successful to write message. offset: 5149","severity":"info","timestamp":"2026-08-26T02:17:02.298919629Z"}
```

## Where it localizes, and what is still open

Traces resolved it. Every sampled failing checkout ends at the same place: checkoutservice's client span for ShippingService/GetQuote, the last child under prepareOrderItemsAndShippingQuoteFromCart, marked ERROR — with no matching shippingservice server span in any trace. Durations of roughly 0.3–2.4ms, with whole PlaceOrder traces finishing in about 5–16ms, mean nothing accumulates latency anywhere: these are fast refusals or rejections, not hangs or timeouts. Drop every slow-dependency theory on sight.

Everything upstream succeeds in the same failing traces — GetCart with its Redis HGET child, GetProduct including its flag lookups, and Convert — all clean and fast, which clears cart, product catalog and currency individually. No payment, shipping-order or email spans exist at all, matching the log picture: execution aborts during quote retrieval. The ERROR on checkoutservice/PlaceOrder, frontend gRPC and the frontend HTTP POST is inherited from the failing leaf, not a problem at those tiers. Cart size is irrelevant; traces with one, two and four iterations end identically.

Conclusion: the failure localizes to the shipping-quote hop immediately downstream of checkoutservice, not to checkoutservice itself. Confidence medium, no fix class identified, and do not frame remediation as a revert.

Still open, in priority order: shippingservice and quoteservice were never dispatched to — their changes, metrics, logs and restart or memory state are wholly unexamined, and that is where the next responder should start; change history before the queried window, back roughly an hour, is unqueried for every service; and the shape of the error ratio remains unexplained.

> Evidence `tr_74791dcc5b78`:

```
<tool_result id="tr_74791dcc5b78" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00">
service: checkoutservice
200 spans
  20ce7061b91d4ba3 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.8ms
  20ce7061b91d4ba3 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
  20ce7061b91d4ba3 checkoutservice/hipstershop.CurrencyService/Convert 1.3ms
```

> Evidence `tr_04ef8cf2aed4`:

```
<tool_result id="tr_04ef8cf2aed4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T02:17:00.583000+00:00..2026-08-26T02:32:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T02:17:02.273945+00:00  {"message":"[PlaceOrder] user_id=\"397f9b78-a0f4-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T02:17:02.273679879Z"}
2026-08-26T02:17:02.292713+00:00  {"message":"payment went through (transaction_id: 4cca32d0-a95a-4ac7-a71b-e8f0e48e5714)","severity":"info","timestamp":"2026-08-26T02:17:02.292616129Z"}
2026-08-26T02:17:02.297883+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-08-26T02:17:02.297634379Z"}
2026-08-26T02:17:02.299025+00:00  {"message":"Successful to write message. offset: 5149","severity":"info","timestamp":"2026-08-26T02:17:02.298919629Z"}
```


