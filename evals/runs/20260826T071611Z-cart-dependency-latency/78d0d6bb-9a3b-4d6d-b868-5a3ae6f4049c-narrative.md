# Cart path acquires a flat ~300ms floor; twelve services page on latency, nothing errors

## What the page looked like

Four services paged at warning severity within the same minute: cartservice, frontend, loadgenerator, checkoutservice. Blast radius was flagged at twelve services. Nothing in the page text said what was wrong — no error budget burn, no 5xx spike, just latency alerts stacked across a call chain. The first useful instinct, in hindsight, was to ask whether anything was actually failing before spending time on which service was failing. It was not.

> Evidence `tr_89f3a8ef9b9b`:

```
<tool_result id="tr_89f3a8ef9b9b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_89f3a8ef9b9b>
```

## First look: frontend error ratio (T+1m)

I pulled frontend's error-status calls over total calls for the fifteen minutes bracketing the page. Sixty-one sample points, identically zero, start to finish. No discontinuity anywhere, including at the moment that later turned out to matter. That single result did more work than anything else in the investigation: it killed the error-rate reading of the page, it killed the timeout theory (terminated calls would have been recorded with error status and lifted the ratio off zero), and it told me any latency step was added time on calls that succeeded, not truncation at a client ceiling. What the query did not do — and I did not notice for several minutes — was carry any histogram or per-peer dimension, so it said nothing at all about how slow anything was.

> Evidence `tr_89f3a8ef9b9b`:

```
<tool_result id="tr_89f3a8ef9b9b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_89f3a8ef9b9b>
```

## Dead end: metrics on cartservice (T+3m)

With frontend clean I went to cartservice's own call metrics expecting to see the same shape from the origin side. The query returned no series whatsoever. Because the denominator covers every status, an empty result is not "no errors" — it is no span-derived call metrics for that service name in that window at all. I spent a few minutes deciding whether this meant cartservice was down, unscraped, or simply mislabelled. It meant none of the interesting things: logs and traces both showed the service alive and serving. The metric pipeline or the service_name label for cartservice is broken independently of this incident, and it is still broken. Any follow-up query against the same series will also come back empty, so do not repeat this step.

> Evidence `tr_f68ed951fef9`:

```
<tool_result id="tr_f68ed951fef9" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_f68ed951fef9>
```

## Dead end: cartservice logs (T+5m)

Log query next, hoping for a stack trace or a cache-backend complaint. What came back was routine cart operation handler lines — reads, adds, empties — with no error or warning level anywhere and no dependency, connection pool, or capacity condition named. The result was also truncated by size: only the oldest eight lines from the very start of the window and the newest thirty-two from the tail were retained. The page timestamp falls squarely in the discarded middle. So this evidence proves cartservice was up and handling traffic normally on both sides of the event, and rules out a sustained error condition spanning the window or a crash-and-no-recovery, but it cannot speak to that exact minute. Worth knowing that the gap is a truncation artifact, not missing data — the stream is high volume and healthy.

> Evidence `tr_476780184691`:

```
<tool_result id="tr_476780184691" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T07:09:50.384226+00:00  GetCartAsync called with userId=
2026-08-26T07:09:50.763258+00:00  GetCartAsync called with userId=
2026-08-26T07:09:52.690985+00:00  AddItemAsync called with userId=2249fa10-a11d-11f1-86d7-1e4ac5f08d0c, productId=LS4PSXUNUM, quantity=10
2026-08-26T07:09:52.694154+00:00  GetCartAsync called with userId=2249fa10-a11d-11f1-86d7-1e4ac5f08d0c
```

## The traces (T+8m) — where the shape became obvious

Sampled traces settled it. Every cartservice operation clustered in a tight band around 300ms: GetCart ~301ms, AddItem ~602ms, EmptyCart ~306ms. The time sat entirely in cartservice's cache client spans — each HGET and HMSET at ~300-305ms — with the enclosing RPC exceeding its child by about a millisecond. So cartservice's own compute was negligible; it was waiting. The penalty scaled with the number of cache round-trips rather than with request type: one-op GetCart paid it once, two-op AddItem paid it twice, and a frontend-level GetCart at ~605ms reflected two nested cart round-trips. That additive-per-round-trip signature is what ruled out proportional degradation such as throttling or general saturation, and the absence of any fast cases mixed into the sample ruled out a long-tailed outlier distribution. Upstream inflation decomposed cleanly: checkoutservice PlaceOrder at ~2.46s was ~1.23s of cart preparation (dominated by a ~1.21s GetCart) plus a ~1.21s EmptyCart, with every other checkout child in the single-digit-to-20ms range. Sync dependencies were plainly innocent — productcatalogservice GetProduct sub-2ms, shippingservice GetQuote ~10-18ms with its own child accounting for most of that, ShipOrder ~0ms, emailservice ~4-6ms. Cart operations completed and callers walked the full checkout sequence, with no duplicated cache child spans, so retries were not manufacturing the time either.

> Evidence `tr_325315286bc8`:

```
<tool_result id="tr_325315286bc8" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
service: cartservice
200 spans
  c52d0ca0440e65de checkoutservice/hipstershop.CurrencyService/Convert 1.1ms
  c52d0ca0440e65de currencyservice/CurrencyService/Convert 0.0ms
  c52d0ca0440e65de checkoutservice/hipstershop.ShippingService/GetQuote 10.6ms
```

## Change history (T+11m) and the cause

One change landed on cartservice in the window, roughly three and a half minutes before the page: an actor identified as platform-automation attached a traffic-shaping container to cartservice's network namespace, imposing a fixed 300ms egress delay with zero jitter on the primary interface where none had existed before. Zero jitter predicts exactly the flat floor the traces showed, which is why the trace shape and the change record corroborate each other rather than merely coinciding. No image rollout, no version bump, no flag or config mutation, and no concurrent change to a downstream dependency appears in that history — so the deploy reading, the feature-flag reading, and the cartservice-as-victim reading all fail for lack of any supporting event. There is also no competing change to disambiguate. Conclusion, high confidence: an infrastructure network configuration change on cartservice's egress path. Fix class is a config revert. The warning-severity pages on frontend, checkoutservice and loadgenerator are latency propagating up the cart path, not an error event of their own.

> Evidence `tr_33df3caf2e8f`:

```
<tool_result id="tr_33df3caf2e8f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
service: cartservice
1 changes
  2026-08-26T07:16:15.678853+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_33df3caf2e8f>
```

> Evidence `tr_325315286bc8`:

```
<tool_result id="tr_325315286bc8" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
service: cartservice
200 spans
  c52d0ca0440e65de checkoutservice/hipstershop.CurrencyService/Convert 1.1ms
  c52d0ca0440e65de currencyservice/CurrencyService/Convert 0.0ms
  c52d0ca0440e65de checkoutservice/hipstershop.ShippingService/GetQuote 10.6ms
```

## What is still unexplained

The caller/callee gap is the biggest loose thread. Checkoutservice observed ~1.21s for a GetCart whose cartservice server span was only ~302ms. Egress shaping on the response path plausibly accounts for some of that, but roughly 900ms is unattributed and could be a second contributor — queueing, connection setup, or shaping applied more broadly than the change record describes. Second, scope: the change record covers cartservice alone and no other service's history was queried, so a fleet-wide automation rollout touching additional namespaces is not excluded. Third, intent: whether this was a scheduled experiment, a misapplied policy, or unintended reconciliation is unknown, and therefore so is whether a revert survives the next reconciliation cycle. Fourth, cartservice has no call metrics in this window at all, which is a monitoring defect predating and outliving the incident. Fifth, latency percentiles were never measured for any service — the ~300ms step is confirmed from sampled traces only, never from aggregate data. Sixth, triage crossed four unmeasured edges; no adservice or recommendationservice spans appear in the sample, so their state is unassessed, as is most of the twelve-service radius. Finally, the log truncation means a distinct transient event at the exact page minute, layered on top of the latency floor, cannot be excluded.

> Evidence `tr_325315286bc8`:

```
<tool_result id="tr_325315286bc8" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
service: cartservice
200 spans
  c52d0ca0440e65de checkoutservice/hipstershop.CurrencyService/Convert 1.1ms
  c52d0ca0440e65de currencyservice/CurrencyService/Convert 0.0ms
  c52d0ca0440e65de checkoutservice/hipstershop.ShippingService/GetQuote 10.6ms
```

> Evidence `tr_33df3caf2e8f`:

```
<tool_result id="tr_33df3caf2e8f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
service: cartservice
1 changes
  2026-08-26T07:16:15.678853+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_33df3caf2e8f>
```

> Evidence `tr_f68ed951fef9`:

```
<tool_result id="tr_f68ed951fef9" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_f68ed951fef9>
```

> Evidence `tr_89f3a8ef9b9b`:

```
<tool_result id="tr_89f3a8ef9b9b" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_89f3a8ef9b9b>
```

> Evidence `tr_476780184691`:

```
<tool_result id="tr_476780184691" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T07:09:45.583000+00:00..2026-08-26T07:24:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T07:09:50.384226+00:00  GetCartAsync called with userId=
2026-08-26T07:09:50.763258+00:00  GetCartAsync called with userId=
2026-08-26T07:09:52.690985+00:00  AddItemAsync called with userId=2249fa10-a11d-11f1-86d7-1e4ac5f08d0c, productId=LS4PSXUNUM, quantity=10
2026-08-26T07:09:52.694154+00:00  GetCartAsync called with userId=2249fa10-a11d-11f1-86d7-1e4ac5f08d0c
```
