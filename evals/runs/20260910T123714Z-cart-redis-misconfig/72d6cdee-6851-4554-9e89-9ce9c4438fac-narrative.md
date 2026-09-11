# Cart port misconfiguration stalls checkout across twelve services

## What we saw, and the two probes that wasted time

Pages arrived from frontend, loadgenerator, and checkoutservice at once; severity critical, blast radius twelve services. The seed was frontend, which was the wrong place to start.

First probe: the change log for frontend returned nothing at all. It did kill the in-incident theories (a rollout landing mid-incident, repeated rollback attempts), but note the window started at onset and ran forward a day, so it could never have shown a pre-onset change, and it examined zero downstream services.

Second probe was actively misleading. Frontend's aggregate error ratio during the incident was *lower* than baseline — roughly half — with high variance and similar maxima in both windows, meaning frontend error spikes are standing background noise here. Triaging on error rate alone would have closed the incident. The aggregate had no per-dependency or per-route breakdown and no latency series, so a hard failure on one path was invisible to it.

> Evidence `tr_5e24b32a9fc1`:

```
<tool_result id="tr_5e24b32a9fc1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T12:39:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_5e24b32a9fc1>
```

> Evidence `tr_0239c6cc38bd`:

```
<tool_result id="tr_0239c6cc38bd" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T12:09:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" template="error-ratio" baseline="2026-09-10T11:37:56.388771+00:00..2026-09-10T12:09:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.04145 min=0 max=0.3102 sd=0.09268
  baseline window: n=128 mean=0.08342 min=0 max=0.3216 sd=0.1154
```

## Logs named the hop, then the service that was never up

Frontend logs carried two signatures: gRPC 14 UNAVAILABLE with detail saying no connection was established, and gRPC 13 INTERNAL relayed from the checkout path wrapping a failure to fetch the user cart. Nested inside was the useful detail — a dial to 172.18.0.8:7070 refused at TCP connect. All stack frames sat in the gRPC client receive-status path, so frontend was relaying, not failing. That ruled out auth/validation/quota (would be 16, 7, 3, or 8), slowness (would be 4 DEADLINE_EXCEEDED), service discovery (a concrete IP was resolved and dialed), TLS (refusal precedes any handshake), and transience (same signature in oldest and newest lines).

Checkout looked healthy and that was the trap: no error or warning lines at all late in the window, steady info-severity PlaceOrder entries in both USD and CAD, no restart lines. The tell was structural — from about T-1m on, PlaceOrder starts had no matching payment-success or message-write completion. Orders accepted, quietly never finished. Two dead ends here: email-service HTTP 500s sit ~30 minutes earlier, are warnings, and the surrounding orders completed; and the currency theory died since USD and CAD stall identically.

Cart logs settled it. Repeated dial to redis-cart on port 6380, failure after 15-35s, unhandled exception from RedisCartStore.EnsureRedisConnected via Program.Main, restart every 30-50s, never reaching the gRPC listener. Hence the refusal on 7070. Cart was serving normally about three hours earlier, so this was a state change. Not silence, not a request-handling bug (no request frames), not an abrupt kill (each restart follows an orderly exception), not a command-level Redis error (no session ever established).

> Evidence `tr_cc66783452dd`:

```
<tool_result id="tr_cc66783452dd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:09:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T12:09:51.252584+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-10T12:09:51.252624+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T12:09:51.252627+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T12:09:51.252629+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_2d543d3e7bcc`:

```
<tool_result id="tr_2d543d3e7bcc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:09:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T12:09:51.276086+00:00  {"message":"[PlaceOrder] user_id=\"8676f9bc-ad10-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:09:51.27598176Z"}
2026-09-10T12:09:51.304008+00:00  {"message":"payment went through (transaction_id: 581b109f-fe21-4b21-b8d9-8f5e372ee11f)","severity":"info","timestamp":"2026-09-10T12:09:51.303945843Z"}
2026-09-10T12:09:51.313911+00:00  {"message":"failed to send order confirmation to \"jack@example.com\": failed POST to email service: expected 200, got 500","severity":"warning","timestamp":"2026-09-10T12:09:51.313689177Z"}
2026-09-10T12:09:51.315272+00:00  {"message":"Successful to write message. offset: 31351","severity":"info","timestamp":"2026-09-10T12:09:51.31515076Z"}
```

> Evidence `tr_fc5703a328a7`:

```
<tool_result id="tr_fc5703a328a7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T09:39:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T09:39:47.143453+00:00  GetCartAsync called with userId=
2026-09-10T09:39:51.085936+00:00  AddItemAsync called with userId=91f266e2-acfb-11f1-b359-b6ed2071a170, productId=6E92ZMYYFZ, quantity=5
2026-09-10T09:39:51.088766+00:00  GetCartAsync called with userId=91f266e2-acfb-11f1-b359-b6ed2071a170
2026-09-10T09:39:51.105157+00:00  AddItemAsync called with userId=91f266e2-acfb-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=2
```

## The change, the metric gap, and what is still open

Cart's change history — queried a full day back, unlike the frontend attempt — held nineteen entries, all from platform-automation, repeating a fixed six-step cycle four times over ~21 hours. The entry at T-2m set REDIS_ADDR to redis-cart on non-default port 6380, matching the crash-loop logs exactly. Two better-looking suspects cleared on timing: a cartservice hotfix image applied ~T-38m and reverted ~T-30m, so the pre-hotfix image was running at onset; and a traffic-shaping container attached ~T-19m and removed ~T-10m, so no added delay existed at onset — and a refusal is not a delay. No flag changes, no human actor. High confidence; fix class is a config revert.

One metric caveat for the next reader: cartservice has zero Prometheus samples in the incident window *and* in a baseline three hours earlier. An absence predating onset cannot be caused by it, so that gap is missing instrumentation or a name mismatch, not an outage — it settles nothing about cart request rate.

Still open. (1) Nobody read the redis-cart service definition; if 6380 is correct and redis-cart stopped listening, the fix becomes restarting redis-cart. Check before reverting. (2) Frontend shows the same UNAVAILABLE signature about twenty-eight minutes before the config edit, unexplained by this cause alone. (3) Only 3 of 12 affected services were examined and four unmeasured edges were crossed.

> Evidence `tr_90a970cde810`:

```
<tool_result id="tr_90a970cde810" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T12:39:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" radius="candidate_cause" hops="1">
service: cartservice
19 changes, ranked by suspicion
  #1  2m before onset  2026-09-10T12:37:19.842008+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  10m before onset  2026-09-10T12:29:28.926172+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

> Evidence `tr_114d3aa288a4`:

```
<tool_result id="tr_114d3aa288a4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T09:39:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" template="error-ratio" baseline="2026-09-10T06:37:56.388771+00:00..2026-09-10T09:39:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_cc66783452dd`:

```
<tool_result id="tr_cc66783452dd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:09:45.583000+00:00..2026-09-10T12:41:34.777229+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T12:09:51.252584+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-10T12:09:51.252624+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T12:09:51.252627+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T12:09:51.252629+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

