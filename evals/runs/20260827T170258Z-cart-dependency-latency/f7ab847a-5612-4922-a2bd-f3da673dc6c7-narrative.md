# Cart path slow on every request: a delay on the cart store hop

## What we saw, and the change that explained it

Four services paged together — cartservice, frontend, loadgenerator, checkoutservice — at warning severity, twelve services in blast radius. Nothing was down. Take T+0 as the alert marker; the interesting moment is earlier.

The change history for cartservice held exactly one entry, at roughly T-3m30s: a platform-automation principal, not a human deploy pipeline, attached a traffic-shaping container to the cart-service network namespace with a fixed 300ms egress delay, zero jitter, on eth0. That single entry closed several doors at once. No image rollout or version bump. No feature flag toggle. No application config or environment change touching pool sizes, timeouts or cache endpoints. And nothing done to the cart datastore itself — the action lives inside cartservice's own network namespace, so datastore slowness would be an artefact rather than a problem on the dependency side. The zero-jitter determinism predicted a clean step, not a noisy ramp; worth holding on to when reading traces.

> Evidence `tr_8aad7663d02d`:

```
<tool_result id="tr_8aad7663d02d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00">
service: cartservice
1 changes
  2026-08-27T17:03:03.290504+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_8aad7663d02d>
```

## Three dead ends, kept because they will cost you the same time

Cartservice RED metrics returned zero series. Not zero errors — zero series, with the unfiltered total-call denominator empty too. That rules out reading this as a partial degradation (a good/bad mix would still populate the denominator), but it also means error rate and latency percentiles for cartservice were never measured from metrics at all. Label mismatch, missing scrape target, or genuinely absent spans: unresolved. Try an alternate label set before assuming the service is silent.

Cartservice logs came back truncated to the oldest 8 and newest 32 lines, and T+0 falls entirely inside the dropped middle. All returned lines are routine cart operations, no errors. Useful negatives: the service was not down or crash-looping, and there was no window-wide error flood, since one would have shown in the newest 32 lines. But error output at the alert moment can be neither confirmed nor denied. A trailing gap of about two and a half minutes with no lines is indistinguishable from ingestion lag.

Both frontend metric dispatches returned error ratios instead of latency percentiles. Flat zero across 59 and 61 samples, no gaps, populated denominator — so this is a true zero, not missing telemetry. That kills the error-rate reading at the edge, kills upstream errors propagating as hard failures, and kills retry-on-error amplification. It answers nothing about latency: no frontend percentile series was ever retrieved, and the predicted step is inferred from traces alone.

> Evidence `tr_4312edc27553`:

```
<tool_result id="tr_4312edc27553" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_4312edc27553>
```

> Evidence `tr_6f0c3e1ed887`:

```
<tool_result id="tr_6f0c3e1ed887" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T16:56:31.618464+00:00  GetCartAsync called with userId=
2026-08-27T16:56:31.790369+00:00  AddItemAsync called with userId=4100b798-a238-11f1-86d7-1e4ac5f08d0c, productId=L9ECAV7KIM, quantity=3
2026-08-27T16:56:31.793330+00:00  GetCartAsync called with userId=4100b798-a238-11f1-86d7-1e4ac5f08d0c
2026-08-27T16:56:31.896604+00:00  AddItemAsync called with userId=411150e4-a238-11f1-86d7-1e4ac5f08d0c, productId=OLJCESPC7Z, quantity=3
```

> Evidence `tr_88035e786843`:

```
<tool_result id="tr_88035e786843" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=59
</tool_result:tr_88035e786843>
```

> Evidence `tr_06a7eced1cdd`:

```
<tool_result id="tr_06a7eced1cdd" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_06a7eced1cdd>
```

## The traces, the conclusion, and what stays open

Traces settled it. Every cart store operation sat in a tight 300-305ms band with no fast outliers. GetCart, one HGET, ran ~302ms; AddItem, HGET plus HMSET, ran ~605ms. Cartservice self-time outside those children is 1-3ms — it is healthy and waiting. Because the penalty scales with datastore call count rather than request count, a uniform per-request inbound step (sidecar, interceptor, handshake) is excluded. A cluster-wide network problem is excluded too: productcatalog, currency, payment, shipping, quote, email, accounting and frauddetection all came in under ~20ms in the same traces. Checkout's ~2460ms PlaceOrder is ~2410ms of cart interactions. Frontend originates nothing; its spans decompose cleanly down to the datastore. Across 200 sampled spans, none was fast, so this is not a tail.

Conclusion, high confidence: a dependency call path became slow and callers fail by waiting. Fix class is a configuration revert.

Still open, in order of how much it should bother you. Caller spans are two to four times the server spans they wrap — frontend ~605ms against ~302ms, checkout ~1205ms against ~301ms. Client-side retries or queueing was offered; nothing confirms it. A 300ms delay does not obviously produce a clean doubling at the edge and quadrupling at checkout, and if retry logic is amplifying, reverting the change hides the symptom and leaves an untuned retry path. Second, whether the shaping attachment was sanctioned with a scheduled end, and whether the same automation touched other namespaces, is unknown; four unmeasured edges were crossed and only cartservice and frontend were examined directly. Third, loadgenerator and checkoutservice both paged and neither was dispatched against — checkout's latency is explained by the cart hop in one trace sample, but nothing independently confirms checkout has no separate problem.

> Evidence `tr_ce21084268a8`:

```
<tool_result id="tr_ce21084268a8" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00">
service: cartservice
200 spans
  648dda90eee9f6b6 cartservice/hipstershop.CartService/GetCart 301.6ms
  648dda90eee9f6b6 cartservice/HGET 300.9ms
  3aaed704f6da3609 checkoutservice/hipstershop.ProductCatalogService/GetProduct 2.5ms
```

> Evidence `tr_8aad7663d02d`:

```
<tool_result id="tr_8aad7663d02d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00">
service: cartservice
1 changes
  2026-08-27T17:03:03.290504+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_8aad7663d02d>
```

> Evidence `tr_6f0c3e1ed887`:

```
<tool_result id="tr_6f0c3e1ed887" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T16:56:30.583000+00:00..2026-08-27T17:11:30.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T16:56:31.618464+00:00  GetCartAsync called with userId=
2026-08-27T16:56:31.790369+00:00  AddItemAsync called with userId=4100b798-a238-11f1-86d7-1e4ac5f08d0c, productId=L9ECAV7KIM, quantity=3
2026-08-27T16:56:31.793330+00:00  GetCartAsync called with userId=4100b798-a238-11f1-86d7-1e4ac5f08d0c
2026-08-27T16:56:31.896604+00:00  AddItemAsync called with userId=411150e4-a238-11f1-86d7-1e4ac5f08d0c, productId=OLJCESPC7Z, quantity=3
```
