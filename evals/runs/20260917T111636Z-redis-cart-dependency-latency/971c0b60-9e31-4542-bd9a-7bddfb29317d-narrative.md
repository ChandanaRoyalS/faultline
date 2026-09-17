# Cart store round-trips carrying a fixed ~300ms penalty; checkout pays it twice

## What was visible, in order

The page arrived with cartservice, checkoutservice, frontend and loadgenerator lit, warning severity, twelve services in the radius and four unmeasured edges. No error storm anywhere obvious. The first clean quantitative signal was checkoutservice's error ratio: flat zero across the whole preceding baseline, then lifting to ~1.1% mean with a ~6.7% peak, first crossing around T+10m and again around T+13m. That gave us a sharp onset boundary and a ceiling — under 7% means the great majority of checkouts still succeeded, so nothing downstream of checkout was hard-down.

Traces broke it open. In every sampled cartservice trace the backing-store child spans (HGET, HMSET) hold ~301–307ms of self time each while the cartservice gRPC handler above them contributes under a millisecond. The shape matters more than the size: durations cluster tightly against a ~300ms floor with no heavy tail, and end-to-end latency scales linearly with round-trip count — ~305ms for a single-HGET GetCart, ~610ms for AddItem's HGET+HMSET, ~665ms for checkout's GetCart+EmptyCart. Contention produces spread and a tail; a fixed per-operation cost on the path produces this staircase. Reads and writes are hit identically. From checkoutservice's side those two hops are ~600ms of a ~660ms request, while payment (1.6–3.0ms), currency (1–4ms), product catalog (0.6–4.8ms), shipping (1ms, GetQuote 10–20ms) and email (5–9ms) are all fast and boring.

> Evidence `tr_90d42a699f94`:

```
<tool_result id="tr_90d42a699f94" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T10:50:00.583000+00:00..2026-09-17T11:22:20.098684+00:00" template="error-ratio" baseline="2026-09-17T10:17:41.067316+00:00..2026-09-17T10:50:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=130 mean=0.01105 min=0 max=0.06731 sd=0.01966
  baseline window: n=130 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_3984cc69c503`:

```
<tool_result id="tr_3984cc69c503" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T10:20:00.583000+00:00..2026-09-17T11:22:20.098684+00:00">
service: cartservice
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace cdfa10e433b2ccd6  root frontend/HTTP GET  311.4ms  started 2026-09-17T11:21:16.170034+00:00  4 spans
  +0.0ms frontend/HTTP GET 311.4ms [self 1.3ms]
```

> Evidence `tr_17013007cead`:

```
<tool_result id="tr_17013007cead" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T10:50:00.583000+00:00..2026-09-17T11:22:20.098684+00:00">
service: checkoutservice
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 270e4928d5f9fa12  root frontend/HTTP POST  665.8ms  started 2026-09-17T11:21:37.232038+00:00  36 spans
  +0.0ms frontend/HTTP POST 665.8ms [self 0.9ms]
```

## Dead ends worth keeping

The cartservice error-ratio metric was our first instinct and is unusable: no samples in the incident window, but also none in the baseline. The series was already absent, so the silence does not correlate with onset and cannot separate errors from a traffic collapse. We never obtained a cartservice error rate, request rate or p95 from that source.

cartservice logs were the second instinct and also a dead end, though a productive one: no errors, no panics, no connection-refused, no startup output — only routine cart reads, adds and empties, dense and continuous to the end of the window. That rules out crash-restart, a lost store connection, and a hung service, and tells us the problem is invisible at application log level. The slice was truncated to the oldest 8 and newest 32 lines, so most of the window is unobserved.

checkoutservice logs had the same truncation and it hurt more: the returned lines skip the T+10m onset entirely, so no failing RPC or status code was ever named. What survives is still useful — the identical success path runs ~20–25ms per order at the head of the window and ~600–650ms at the tail, with queue offsets advancing consecutively throughout. Separately, checkoutservice's change log is completely empty for the 24h queried, so there is nothing to roll back there; note its window starts 11:20 the previous day and would miss an earlier-day crossing.

> Evidence `tr_235ca2bc63c4`:

```
<tool_result id="tr_235ca2bc63c4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T10:50:00.583000+00:00..2026-09-17T11:22:20.098684+00:00" template="error-ratio" baseline="2026-09-17T10:17:41.067316+00:00..2026-09-17T10:50:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_5f846f914e7b`:

```
<tool_result id="tr_5f846f914e7b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T10:50:00.583000+00:00..2026-09-17T11:22:20.098684+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T10:50:00.717715+00:00  GetCartAsync called with userId=
2026-09-17T10:50:01.169289+00:00  AddItemAsync called with userId=883f760a-b285-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=1
2026-09-17T10:50:01.171806+00:00  GetCartAsync called with userId=883f760a-b285-11f1-b359-b6ed2071a170
2026-09-17T10:50:01.181489+00:00  GetCartAsync called with userId=883f760a-b285-11f1-b359-b6ed2071a170
```

> Evidence `tr_b00c5e027670`:

```
<tool_result id="tr_b00c5e027670" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T10:50:00.583000+00:00..2026-09-17T11:22:20.098684+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T10:50:01.180302+00:00  {"message":"[PlaceOrder] user_id=\"883f760a-b285-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T10:50:01.180171264Z"}
2026-09-17T10:50:01.199455+00:00  {"message":"payment went through (transaction_id: 0a6f6412-ff9a-4316-b1df-313d555d2cbe)","severity":"info","timestamp":"2026-09-17T10:50:01.199361514Z"}
2026-09-17T10:50:01.204657+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-17T10:50:01.20456968Z"}
2026-09-17T10:50:01.205520+00:00  {"message":"Successful to write message. offset: 63399","severity":"info","timestamp":"2026-09-17T10:50:01.205438264Z"}
```

> Evidence `tr_c0db7cb47df3`:

```
<tool_result id="tr_c0db7cb47df3" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T11:20:00.583000+00:00..2026-09-17T11:22:20.098684+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_c0db7cb47df3>
```

## The change log, the conclusion, and what is still open

cartservice's change history has 14 entries, all attributed to platform-automation with no human actor. Three repeating patterns: an image reference set to a hotfix tag; a REDIS_ADDR override pointing the cart at a store endpoint on a non-default port; and a traffic-shaping container attached to the cart-service network namespace adding fixed egress delay on eth0. That third is an exact mechanical match for the ~300ms floor. But every apply has a matching revert minutes to ~10 minutes later; the last shaping removal is ~1.6h before onset, the last image revert ~1.9h, the most recent entry of any kind a REDIS_ADDR revert ~1.3h, and the hour before onset is empty. On the log's own terms all three are ruled out as standing config at onset.

Conclusion, medium confidence: every cart operation pays a fixed ~300ms penalty on the egress path to its backing store. cartservice is not erroring; checkoutservice is a victim that failed by waiting, with a small fraction of requests tipping over a client deadline. Fix class is a configuration revert of the cart-service egress delay.

Still open: (1) the contradiction above — the log says reverted, the traces at T+31m say live, so whether a cycle went unrecorded or a revert failed decides whether that revert is even an available lever; (2) nothing was gathered from the backing store itself — no metrics, logs or change history — so a genuine server-side ~300ms stall was excluded only by latency shape, never by direct observation; (3) the source of checkout's errors remains inferred, since no span carries error status and the log slice missed onset.

> Evidence `tr_8c23c4d6c8e8`:

```
<tool_result id="tr_8c23c4d6c8e8" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T11:20:00.583000+00:00..2026-09-17T11:22:20.098684+00:00" radius="seed" hops="0">
service: cartservice
14 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-17T10:03:07.534610+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.4h before onset  2026-09-17T09:54:19.071715+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_3984cc69c503`:

```
<tool_result id="tr_3984cc69c503" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T10:20:00.583000+00:00..2026-09-17T11:22:20.098684+00:00">
service: cartservice
10 trace(s) shown of 10 found, 130 spans; offsets are from each trace's root

trace cdfa10e433b2ccd6  root frontend/HTTP GET  311.4ms  started 2026-09-17T11:21:16.170034+00:00  4 spans
  +0.0ms frontend/HTTP GET 311.4ms [self 1.3ms]
```

> Evidence `tr_17013007cead`:

```
<tool_result id="tr_17013007cead" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-17T10:50:00.583000+00:00..2026-09-17T11:22:20.098684+00:00">
service: checkoutservice
5 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 270e4928d5f9fa12  root frontend/HTTP POST  665.8ms  started 2026-09-17T11:21:37.232038+00:00  36 spans
  +0.0ms frontend/HTTP POST 665.8ms [self 0.9ms]
```

