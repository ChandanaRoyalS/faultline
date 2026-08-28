# Latency-only degradation on the productcatalogservice call path

## What the responder saw first

The page arrived as a warning-severity, multi-service event: alerts on frontend, recommendationservice, checkoutservice, loadgenerator and productcatalogservice, with a stated blast radius of twelve services and triage starting from frontend. Nothing in the alert text said what was wrong — only that several tiers were unhappy at once. The shape of that alert list is the first useful clue in hindsight: four of the five alerting services are callers of the fifth, and loadgenerator alerting alongside them says the pain was visible all the way at the traffic source. Set T+0 at the moment the change landed on productcatalogservice; the incident timestamp on the page is roughly T+3m.

> Evidence `tr_a548b460d72d`:

```
<tool_result id="tr_a548b460d72d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
1 changes
  2026-08-28T01:34:26.372011+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_a548b460d72d>
```

## Ruling out an error-rate event

The first two lines of enquiry both went to error ratios, and both came back flat. Frontend's share of error-status calls was zero at every sample point across the fifteen-minute window, twice over, from two independent dispatches. productcatalogservice's error ratio was likewise zero at all fifty-eight samples. In both cases the ratio evaluated to a real number rather than going absent, which means the denominators were non-zero and both services were serving traffic the whole time — this was not an outage and not a dropout in collection. That knocked out the whole family of hypotheses a responder reaches for first: downstream hard failures, circuit breakers opening, deadline-exceeded aborts, retry exhaustion. Whatever was happening was producing slow but successful calls, so the investigation had to pivot to latency.

> Evidence `tr_926489735ab4`:

```
<tool_result id="tr_926489735ab4" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=59
</tool_result:tr_926489735ab4>
```

> Evidence `tr_b4f2d77fccb8`:

```
<tool_result id="tr_b4f2d77fccb8" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_b4f2d77fccb8>
```

> Evidence `tr_c1b38bb4b877`:

```
<tool_result id="tr_c1b38bb4b877" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=58
</tool_result:tr_c1b38bb4b877>
```

## Dead end: frontend metrics never answered the question

Worth recording plainly, because a future responder will be tempted to trust the same path. Both frontend metric dispatches returned only the aggregate error ratio. Neither returned a per-dependency breakdown and neither returned latency quantiles. So there is no metric-side confirmation of when frontend latency stepped up or how large the user-visible impact was; the step at T+0 is inferred from traces only. If you are working a similar event, go straight for latency histograms broken down by peer service rather than accepting an aggregate error ratio as an answer.

> Evidence `tr_926489735ab4`:

```
<tool_result id="tr_926489735ab4" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=59
</tool_result:tr_926489735ab4>
```

> Evidence `tr_b4f2d77fccb8`:

```
<tool_result id="tr_b4f2d77fccb8" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_b4f2d77fccb8>
```

## Dead end: the logs were never actually read

A Loki query over the incident window against productcatalogservice returned zero lines — not sparse, not noisy, simply empty. The temptation is to read that as a wedged or crashed process. It is not safe to read it that way: the selector used a hyphenated label value that does not match the service name under investigation, so a label mismatch explains the empty result just as well as silence does. No first-occurrence timestamp could be anchored from logs, and no claim about what the service did or did not log survives without a re-query using the correct label. This one cost time and produced nothing.

> Evidence `tr_df0b45ed3f5b`:

```
<tool_result id="tr_df0b45ed3f5b" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_df0b45ed3f5b>
```

## The change history, and the change that was not there

Frontend's change history over the window came back genuinely empty — the source was reachable and answered, it simply had no deploys, rollbacks, config edits or flag flips for frontend in the ten minutes before onset. That is a clean negative and it pushed attention downward. productcatalogservice, by contrast, had exactly one entry: at T+0 a platform-automation principal attached a traffic-shaping container to the service's network namespace, applying a fixed 300 ms egress delay with zero jitter on eth0. Note what that entry is not: not a deploy, not a new image, not a flag or environment change, and not made by a human operator or a release pipeline. The zero-jitter detail is the part that made the trace evidence legible in advance — a constant delay should present as a flat step on every crossing of the boundary, not as a widening or long-tailed distribution.

> Evidence `tr_4e51d2275621`:

```
<tool_result id="tr_4e51d2275621" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_4e51d2275621>
```

> Evidence `tr_a548b460d72d`:

```
<tool_result id="tr_a548b460d72d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
1 changes
  2026-08-28T01:34:26.372011+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_a548b460d72d>
```

## What the traces confirmed

The traces matched that prediction almost exactly. Caller-side spans into productcatalogservice clustered tightly at 301–308 ms across many independent traces and across three different callers — frontend GetProduct, recommendationservice ListProducts, checkoutservice GetProduct — with only a few milliseconds of spread. The matching server-side handler spans reported roughly 0.0–0.1 ms with no children. The time is therefore spent between client send and handler entry, on the wire, not inside the service. That rules out the service's own handler, its data access, and CPU saturation, and it rules out any downstream of productcatalogservice for this tier, since those spans have no children at all. It also rules out a caller-specific problem such as a bad client build or a broken connection pool, because all three callers hit the same floor. The penalty stacks per call: single-product frontend requests land near 302–308 ms, fan-out traces reach 612 ms and 1206–1526 ms, and one checkout trace reached 3687 ms. Every non-productcatalog dependency in the same traces — cart, currency, payment, shipping, email, quote, accounting — stayed sub-millisecond to about 20 ms, so this was never a cluster-wide slowdown.

> Evidence `tr_0126c91be05d`:

```
<tool_result id="tr_0126c91be05d" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
200 spans
  1713ab73319e184f paymentservice/charge 0.1ms
  1713ab73319e184f checkoutservice/hipstershop.ShippingService/ShipOrder 1.7ms
  1713ab73319e184f shippingservice/hipstershop.ShippingService/ShipOrder 0.0ms
```

## The loose thread: a second latency tier

A minority of GetProduct calls do not fit the story. They run about 1207–1211 ms client-side with about 904–908 ms server-side, and in every such case the server span carries a child call to FeatureFlagService/GetFlag of essentially that same ~904–907 ms duration. That is a different mechanism from the flat 300 ms step, and no dispatch in this investigation looked at FeatureFlagService at all. It could be a second concurrent failure, or it could be a pre-existing condition — there is no measurement of that path from before T+0 to compare against. The change query also covered only a bounded window, so an earlier change contributing to this tier was never checked. Do not let the tidy 300 ms explanation absorb this.

> Evidence `tr_0126c91be05d`:

```
<tool_result id="tr_0126c91be05d" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
200 spans
  1713ab73319e184f paymentservice/charge 0.1ms
  1713ab73319e184f checkoutservice/hipstershop.ShippingService/ShipOrder 1.7ms
  1713ab73319e184f shippingservice/hipstershop.ShippingService/ShipOrder 0.0ms
```

> Evidence `tr_a548b460d72d`:

```
<tool_result id="tr_a548b460d72d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
1 changes
  2026-08-28T01:34:26.372011+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_a548b460d72d>
```

## Conclusion and what remains unsettled

The incident is a latency-only degradation of the productcatalogservice call path. Every caller crossing that boundary pays a fixed penalty added at the network layer at T+0; the alerts on frontend, checkoutservice, recommendationservice and loadgenerator are callers waiting on it, not independent problems. Fix class is a configuration revert — remove the traffic-shaping attachment. Confidence is high on mechanism. Unsettled: whether the attachment was an authorised experiment or an erroneous automation action, since the change record names the principal but not the intent, and that distinction decides whether the remedy is to stop something deliberate or to correct the automation. Also unsettled: triage crossed four unmeasured edges and the alert list spans twelve services, yet no dispatch touched checkoutservice, recommendationservice or loadgenerator directly — their alerts are attributed to the shared path by trace inference alone.

> Evidence `tr_a548b460d72d`:

```
<tool_result id="tr_a548b460d72d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
1 changes
  2026-08-28T01:34:26.372011+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_a548b460d72d>
```

> Evidence `tr_0126c91be05d`:

```
<tool_result id="tr_0126c91be05d" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-28T01:27:45.583000+00:00..2026-08-28T01:42:45.583000+00:00">
service: productcatalogservice
200 spans
  1713ab73319e184f paymentservice/charge 0.1ms
  1713ab73319e184f checkoutservice/hipstershop.ShippingService/ShipOrder 1.7ms
  1713ab73319e184f shippingservice/hipstershop.ShippingService/ShipOrder 0.0ms
```
