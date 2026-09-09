# Cart path slowdown: a fixed 300ms network delay on cart-service

## What was visible, in order

The page arrived as a warning-severity latency event starting at cartservice, blast radius twelve services. Cartservice alerted first; checkoutservice, frontend and loadgenerator followed about fifteen seconds later. That stagger is the first thing to read correctly — the three later alerts are waiters on the cart call path, not independent sources. Traces sampled just before onset carried the answer: across ten traces and 157 spans, every cart-related hop showed added delay clustered between roughly 300.4ms and 307.7ms, with almost no tail and almost no variance. The delay landed in two places — as self-time on the cartservice Redis leaf spans (HGET, HMSET), and again as a gap between callers' client spans opening and the cartservice server span starting. It stacked per round trip: a single frontend GetCart ran ~600ms, AddItem plus GetCart ~1.5s, checkout paths ~2.4s. Everything non-cart in the same traces — currency, product catalog, payment, shipping, email — finished in single-digit milliseconds. The change log then supplied the match: three minutes before onset, platform automation attached a traffic-shaping sidecar to cart-service's network namespace applying a fixed 300ms delay with zero jitter on eth0, still in place at onset with no matching removal.

> Evidence `tr_be586d4230a8`:

```
<tool_result id="tr_be586d4230a8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-08T18:18:15.583000+00:00..2026-09-08T21:20:35.275911+00:00">
service: cartservice
10 trace(s) shown of 10 found, 157 spans; offsets are from each trace's root

trace b0105919d1ba4d42  root cartservice/HGET  300.6ms  started 2026-09-08T21:17:07.773534+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

> Evidence `tr_3a9397b64997`:

```
<tool_result id="tr_3a9397b64997" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T21:18:15.583000+00:00..2026-09-08T21:20:35.275911+00:00" radius="seed" hops="0">
service: cartservice
17 changes, ranked by suspicion
  #1  3m before onset  2026-09-08T21:15:00.010101+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-08T21:04:24.096706+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

## The dead ends, which are the useful part

Saturation was the obvious first guess and does not survive: contention produces a heavy tail, and this distribution is flat to within a few milliseconds of a fixed value. Slow cartservice logic was ruled out — handler self-time is 0.2–0.8ms. A cold cache was ruled out because writes were penalised exactly as much as reads. A cartservice hotfix image tag rolled out ~22 minutes before onset is very tempting and is wrong: it was reverted ~13 minutes before onset, so the baseline image was running. A REDIS_ADDR override to port 6380 appears in the log but was applied and reverted roughly 2.5 hours before onset. Cartservice logs show only routine informational cart operations at a steady cadence straight through onset — no startup lines, no gaps, no connection or auth errors, and reads returning data just written, so no crash loop, no image-pull problem, and a reachable store. Frontend logs show gRPC 14 UNAVAILABLE bursts about twenty-two and fourteen minutes before onset, then nothing at all — no callee identifier, connection-establishment failures rather than deadlines, and inconsistent with a fixed 300ms delay. Treat those as a probable separate, earlier problem.

> Evidence `tr_be586d4230a8`:

```
<tool_result id="tr_be586d4230a8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-08T18:18:15.583000+00:00..2026-09-08T21:20:35.275911+00:00">
service: cartservice
10 trace(s) shown of 10 found, 157 spans; offsets are from each trace's root

trace b0105919d1ba4d42  root cartservice/HGET  300.6ms  started 2026-09-08T21:17:07.773534+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

> Evidence `tr_09b630f058ba`:

```
<tool_result id="tr_09b630f058ba" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T18:18:15.583000+00:00..2026-09-08T21:20:35.275911+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-08T18:18:15.590116+00:00  AddItemAsync called with userId=a8d9ddea-abb1-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=4
2026-09-08T18:18:15.592654+00:00  GetCartAsync called with userId=a8d9ddea-abb1-11f1-b359-b6ed2071a170
2026-09-08T18:18:17.248398+00:00  AddItemAsync called with userId=a9d77f5e-abb1-11f1-b359-b6ed2071a170, productId=OLJCESPC7Z, quantity=5
2026-09-08T18:18:17.250917+00:00  GetCartAsync called with userId=a9d77f5e-abb1-11f1-b359-b6ed2071a170
```

> Evidence `tr_9491d023980c`:

```
<tool_result id="tr_9491d023980c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:48:15.583000+00:00..2026-09-08T21:20:35.275911+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-08T20:56:33.716818+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-08T20:56:33.716865+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-08T20:56:33.716870+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-08T20:56:33.716872+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Conclusion, and what is still open

High confidence: a fixed, zero-jitter 300ms delay on cart-service's eth0, attached by platform automation three minutes before onset, is the cause. Every packet in and out of the pod pays it, additively per round trip, which is why checkout degraded roughly four times as much as a single cart read. Cartservice itself is healthy. Fix class: revert the configuration and detach the shaping sidecar. Still open: (1) two attempts to pull a cartservice error ratio returned completely empty in both incident and baseline windows — that is silence, not zero, a standing instrumentation gap, and no request-rate, p95, readiness or restart data was ever retrieved, so whether the latency became user-facing errors or only slow successes is unsettled; (2) the same attach/remove cycle recurs roughly three hours and 15.8 hours earlier, so it is unknown whether the automation self-removes the delay, or who scheduled it; (3) four edges were crossed unmeasured, with no direct evidence from redis-cart or checkoutservice, and three fragmented cart cache traces leave a small slice of the path without parent context.

> Evidence `tr_1651701e75b5`:

```
<tool_result id="tr_1651701e75b5" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T20:48:15.583000+00:00..2026-09-08T21:20:35.275911+00:00" template="error-ratio" baseline="2026-09-08T20:15:55.890089+00:00..2026-09-08T20:48:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_3a9397b64997`:

```
<tool_result id="tr_3a9397b64997" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T21:18:15.583000+00:00..2026-09-08T21:20:35.275911+00:00" radius="seed" hops="0">
service: cartservice
17 changes, ranked by suspicion
  #1  3m before onset  2026-09-08T21:15:00.010101+00:00  platform-automation  container created: traffic-shaping container attached to cart-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
  #2  13m before onset  2026-09-08T21:04:24.096706+00:00  platform-automation  image reverted: image reference reverted on cartservice
```

> Evidence `tr_be586d4230a8`:

```
<tool_result id="tr_be586d4230a8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-08T18:18:15.583000+00:00..2026-09-08T21:20:35.275911+00:00">
service: cartservice
10 trace(s) shown of 10 found, 157 spans; offsets are from each trace's root

trace b0105919d1ba4d42  root cartservice/HGET  300.6ms  started 2026-09-08T21:17:07.773534+00:00  3 spans, 3 unattached
  +0.0ms cartservice/HGET 300.6ms [self 0.0ms]
```

