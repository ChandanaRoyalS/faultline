# Cart-path latency traced to a re-applied 300ms egress delay

## What was visible, in order

Four alerts landed together at T+0: cartservice, checkoutservice, frontend and loadgenerator. Severity warning, blast radius twelve services, cartservice named as origin. Triage also reported four unmeasured edges crossed; none were ever named or probed, and other cartservice consumers beyond checkoutservice were never assessed.

The alert set alone pointed at the cart path — frontend and loadgenerator are pure consumers, checkoutservice sits between them and cartservice — but it took trace evidence to show the time was genuinely spent there rather than merely surfacing there.

## Dead ends: metrics and logs

The first move was to quantify cartservice with span-derived RED metrics. Two separate attempts returned nothing at all across the full fifteen-minute window — not zero errors, but no series for either the error-filtered numerator or the unfiltered total-call denominator. This is the trap in this record: an empty error ratio renders as a flat or absent line and reads as "cart is healthy." It is not. With an empty denominator there is no recorded call volume either, so the metric name and label set simply do not exist here. Two prior incidents in this corpus record responders being misled by exactly that reading. It also does not mean cartservice was down; an outage would still produce series with dropping values.

Logs were pulled next and were clean — ordinary AddItem/GetCart/EmptyCart lifecycle lines, no exception, timeout, cache-connection or OOM text. But the result is truncated to the oldest eight lines (~T-10m) and newest thirty-two (~T+3m), so the alert minute itself is unobserved. What the logs do establish: cartservice was alive and serving a steady interleaved read/write mix at the end of the window, and both retained edges are error-free. A recurring pattern of cart reads with an empty user identifier briefly looked like a signal; it appears in both segments during normal operation and is almost certainly a health probe. It did not matter.

> Evidence `tr_bf15eaa38ba8`:

```
<tool_result id="tr_bf15eaa38ba8" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T03:32:45.583000+00:00..2026-08-26T03:47:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_bf15eaa38ba8>
```

> Evidence `tr_adb11a0d6b19`:

```
<tool_result id="tr_adb11a0d6b19" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T03:32:45.583000+00:00..2026-08-26T03:47:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_adb11a0d6b19>
```

> Evidence `tr_274ab1322988`:

```
<tool_result id="tr_274ab1322988" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T03:32:45.583000+00:00..2026-08-26T03:47:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T03:32:45.864864+00:00  AddItemAsync called with userId=cbdb7c62-a0fe-11f1-86d7-1e4ac5f08d0c, productId=LS4PSXUNUM, quantity=1
2026-08-26T03:32:46.088078+00:00  GetCartAsync called with userId=c9cb277e-a0fe-11f1-86d7-1e4ac5f08d0c
2026-08-26T03:32:46.775961+00:00  GetCartAsync called with userId=cbdb7c62-a0fe-11f1-86d7-1e4ac5f08d0c
2026-08-26T03:32:46.962830+00:00  GetCartAsync called with userId=
```

## Traces, the change, and what is still open

Four complete checkout traces resolved it. End-to-end ~2.46-2.48s at the frontend POST root, essentially all inside checkoutservice's PlaceOrder. Two sequential cartservice calls dominate: GetCart ~1.21s and EmptyCart ~1.21s, together ~2.42s. Cartservice's own server spans are only ~301-305ms, and within each a single Redis operation eats nearly the whole span (HGET ~301-304ms, HMSET ~300-302ms) — one flat ~300ms penalty per round trip, identical on read and write. Everything else is trivial: catalog, currency, payment, shipping and email sum to tens of milliseconds. That killed several hypotheses: adservice and recommendationservice are not on this path at all; the distribution is bimodal, so no cluster-wide slowdown; checkoutservice's own logic leaves only ~50ms; the read path is as slow as the write path, so no write-only Redis stall; and all four traces match, so this is steady state, not tail latency.

The change log for cartservice contains exactly two entries, both platform-automation lifecycle events on a traffic-shaping sidecar in the cart-service network namespace: detached ~T-7m30s, re-attached ~T-3m25s, each time with a fixed 300ms zero-jitter egress delay on eth0. No deploy, image bump, flag toggle or application config diff appears. An early reading that the delay had already been lifted is wrong — the detach was reversed before the alerts. Conclusion: latency-only event caused by that re-attached delay. Fix class is config_revert; confidence medium.

Still open. First, the ~900ms per-call gap between the client span (~1.21s) and the server span (~302ms) is roughly three times the applied delay and unexplained — possibly the same shaping hitting multiple packets or round trips, possibly independent client-side queuing or connection-pool pressure. Nothing measured it. Second, nobody confirmed whether the sidecar is still attached or whether the detach/re-attach pair belongs to a running experiment with a scheduled end; remediation choice hinges on that. Third, Redis was never inspected directly, so a coincident Redis-side slowdown cannot be formally excluded, and the absent cartservice span metrics remain a separate observability defect.

> Evidence `tr_9cd3122c33cf`:

```
<tool_result id="tr_9cd3122c33cf" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T03:32:45.583000+00:00..2026-08-26T03:47:45.583000+00:00">
service: checkoutservice
200 spans
  9ffbb3e24fe2703b productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
  9ffbb3e24fe2703b checkoutservice/hipstershop.CurrencyService/Convert 2.4ms
  9ffbb3e24fe2703b currencyservice/CurrencyService/Convert 0.0ms
```

> Evidence `tr_862cd9798521`:

```
<tool_result id="tr_862cd9798521" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T03:32:45.583000+00:00..2026-08-26T03:47:45.583000+00:00">
service: cartservice
2 changes
  2026-08-26T03:35:08.944167+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  2026-08-26T03:39:20.784753+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
```

