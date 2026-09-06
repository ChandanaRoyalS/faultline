# Cart latency toll traced to a traffic-shaping attachment on cart's network namespace

## What was visible first, and the two dead ends

Four services alerted together: cartservice, checkoutservice, frontend and loadgenerator, severity warning, blast radius counted at twelve with four edges never measured. The instinct was to treat cartservice as broken. Its own logs said otherwise: routine cart add/get/empty handling at both ends of the window, no exceptions, no connection or timeout complaints toward its backing store, no startup banners. That eliminated crash-loop, image-pull failure and loss of connectivity to the cache in one pass. A minor lead — several late lookups carrying an empty user identifier — went nowhere; note it only so nobody spends twenty minutes on it. Caveat: only the oldest 8 and newest 32 lines were retained, so the interior of the window is unobserved.

The second dead end was metrics. The error-ratio query for cartservice returned nothing in the incident window — and nothing in the healthy baseline either. Emptiness predates onset, so it means the series was never populated (label or instrumentation mismatch), not that the service stopped serving. The result was flagged empty rather than truncated, so this is genuine absence. Consequence: request rate, latency, restart count and replica counts for cartservice were never measured at all, so concurrent saturation cannot be positively excluded.

> Evidence `tr_78352b904ff8`:

```
<tool_result id="tr_78352b904ff8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T07:25:00.583000+00:00..2026-09-06T07:57:05.540520+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-06T07:25:01.793368+00:00  AddItemAsync called with userId=12b33eb8-a9c4-11f1-83dd-26fccfc59db7, productId=OLJCESPC7Z, quantity=3
2026-09-06T07:25:01.795861+00:00  GetCartAsync called with userId=12b33eb8-a9c4-11f1-83dd-26fccfc59db7
2026-09-06T07:25:01.811878+00:00  AddItemAsync called with userId=12b33eb8-a9c4-11f1-83dd-26fccfc59db7, productId=LS4PSXUNUM, quantity=5
2026-09-06T07:25:01.813321+00:00  GetCartAsync called with userId=12b33eb8-a9c4-11f1-83dd-26fccfc59db7
```

> Evidence `tr_780df684e072`:

```
<tool_result id="tr_780df684e072" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T07:25:00.583000+00:00..2026-09-06T07:57:05.540520+00:00" template="error-ratio" baseline="2026-09-06T06:52:55.625480+00:00..2026-09-06T07:25:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Slow, not broken — and the timing that still doesn't fit

checkoutservice showed a real regression: a flat-zero baseline across 129 samples stepping to a mean around 0.17, peaking near two-thirds of calls failing, bursty and repeatedly returning to zero. One change point, not a ramp — so not slow saturation, and never hard-down. But it lands roughly eighteen minutes before the change we eventually blamed, and it is a service-level aggregate with no per-peer breakdown, so it cannot attribute anything on its own. This is the loosest thread in the record.

Checkout's logs pulled the other way. Every retained line is info severity and traces a complete order through payment, confirmation email and a message write with advancing offsets, still completing at the end of the window. What changed was duration: early orders ran about twenty milliseconds end to end, late ones about three seconds — roughly fifty times slower with no errors. That specifically killed the story a responder most wants: deadline-exceeded errors naming a peer. The newest lines cover a continuous minute at the tail and contain no error severity and no peer name. Same truncation caveat applies.

> Evidence `tr_01482d1a5f6a`:

```
<tool_result id="tr_01482d1a5f6a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T07:25:00.583000+00:00..2026-09-06T07:57:05.540520+00:00" template="error-ratio" baseline="2026-09-06T06:52:55.625480+00:00..2026-09-06T07:25:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.172 min=0 max=0.6667 sd=0.2807
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_0c326ffdbbb4`:

```
<tool_result id="tr_0c326ffdbbb4" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T07:25:00.583000+00:00..2026-09-06T07:57:05.540520+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-06T07:25:01.832006+00:00  {"message":"[PlaceOrder] user_id=\"12b33eb8-a9c4-11f1-83dd-26fccfc59db7\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-09-06T07:25:01.831900136Z"}
2026-09-06T07:25:01.850400+00:00  {"message":"payment went through (transaction_id: a556b20a-cb7c-4a19-bd56-e985b565ed2d)","severity":"info","timestamp":"2026-09-06T07:25:01.850255053Z"}
2026-09-06T07:25:01.855188+00:00  {"message":"order confirmation email sent to \"tobias@example.com\"","severity":"info","timestamp":"2026-09-06T07:25:01.855138136Z"}
2026-09-06T07:25:01.855955+00:00  {"message":"Successful to write message. offset: 1033","severity":"info","timestamp":"2026-09-06T07:25:01.855907428Z"}
```

## Where the shape showed, and the change that was still active

Traces made it legible. cartservice server spans are almost entirely their cache round trips with near-zero self time: GetCart 301–307ms as a single HGET; AddItem 601–617ms as HGET plus HMSET at ~300ms each. Reads and writes penalized identically, ruling out a one-direction persistence problem. No fast outliers anywhere — a constant toll, not variable load. Callers inherit it: PlaceOrder runs 2.44–2.48s with ~1.23s in the cart fetch and ~1.21s in EmptyCart, while every other checkout downstream sits under 25ms and is ruled out. Frontend paths carry the same penalty, so this is not checkout-specific. One unchased discrepancy: checkout's client spans measure ~1.21s against ~301ms server spans, leaving 300–900ms per call outside cart's server processing. Also note all three sampled PlaceOrder traces succeeded — latency inheritance is supported, failure correlation is not.

Change history held twenty-six entries, all from the same automation actor, in a repeating apply/revert cycle. Two attractive candidates fail on timing: a hotfix image tag applied ~22m before onset was reverted ~13m before, and a cache-address environment override was reverted ~1.3h before. Neither was in effect. What remained was a traffic-shaping container attached to cart-service's network namespace ~3 minutes before onset applying a fixed 300ms zero-jitter delay on eth0 — and unlike every earlier cycle, no matching removal was recorded. Confidence high; fix class is a configuration revert.

> Evidence `tr_fee4e8770864`:

```
<tool_result id="tr_fee4e8770864" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-06T07:10:00.583000+00:00..2026-09-06T07:57:05.540520+00:00">
service: cartservice
200 spans
  3ba76278f6298a09 cartservice/hipstershop.CartService/GetCart 301.3ms
  3ba76278f6298a09 cartservice/HGET 300.7ms
  6f51283a14a5d9ac frontend/HTTP POST 1518.8ms
```

> Evidence `tr_eafb0e1462b1`:

```
<tool_result id="tr_eafb0e1462b1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T07:55:00.583000+00:00..2026-09-06T07:57:05.540520+00:00" radius="seed" hops="0">
service: cartservice
26 changes, ranked by suspicion
  #1  3m before onset  2026-09-06T07:51:49.053789+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-06T07:41:11.315274+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

