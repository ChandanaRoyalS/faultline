# Cart backend address change stalls checkout across twelve services

## What was visible, in order

Paging came from the customer edge: frontend, loadgenerator and checkoutservice within the same minute, twelve services in the blast radius, seed frontend, four unmeasured edges in the path. The frontend error ratio showed a flat-zero prior hour with zero variance, then a single step at T-2m to a window mean near 12% and a peak around 29%. That ruled out a chronic error floor, ruled out a total outage (most calls still succeeded), and pushed the search window earlier than the declared onset. checkoutservice showed the same shape one layer in: zero baseline, a step at T-1m30s, mean around 26%, worst interval two thirds erroring. Both series are steps rather than ramps, which argues for a discrete trigger rather than anything accumulating. Neither carried a per-callee dimension, so at that point nothing named a downstream. Traffic to checkout is thin enough that some intervals had no calls at all — the jumpiness of the ratio is an artifact of that and should not be read as intermittency in the cause.

> Evidence `tr_3f1feed564de`:

```
<tool_result id="tr_3f1feed564de" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T14:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" template="error-ratio" baseline="2026-09-06T13:48:26.901707+00:00..2026-09-06T14:50:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=32 mean=0.1225 min=0 max=0.2876 sd=0.1269
  baseline window: n=9 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_d1d89733797e`:

```
<tool_result id="tr_d1d89733797e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T14:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" template="error-ratio" baseline="2026-09-06T13:48:26.901707+00:00..2026-09-06T14:50:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=31 mean=0.2644 min=0 max=0.6667 sd=0.3133
  baseline window: n=7 mean=0 min=0 max=0 sd=0
```

## Dead ends worth keeping

First reflex was to ask what had shipped to checkoutservice. The change log came back empty. That genuinely rules out a rollout or repeated redeploy churning during the incident, and rules out anything landing afterwards to prolong it — but the query window began essentially at the declared onset, so it is silent on the hours that mattered, and it ran at radius zero, so no downstream was inspected at all. Time was lost treating that null as exoneration.

Second dead end: once cart was implicated, its error-ratio series returned no samples in the incident window and none in a three-hour baseline either. The key read is that the emptiness predates the incident by hours, so it indicates a missing or differently-named series, not a process that stopped emitting. No samples is not a zero ratio; this source can neither convict nor clear cart.

Still unresolved: checkoutservice logs show a silent stall — order-entry lines arriving steadily with none of the payment, email or message-write completions that accompanied every order earlier, and no error or warning line anywhere. A crash-looped callee should return a fast UNAVAILABLE, not a hang. Whether checkout blocks on cart with a long deadline or on one of the four unmeasured edges was never settled.

> Evidence `tr_fca1eb3b57e8`:

```
<tool_result id="tr_fca1eb3b57e8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-05T15:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_fca1eb3b57e8>
```

> Evidence `tr_1a10a670043f`:

```
<tool_result id="tr_1a10a670043f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-06T12:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" template="error-ratio" baseline="2026-09-06T09:48:26.901707+00:00..2026-09-06T12:50:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_504b18d22ae5`:

```
<tool_result id="tr_504b18d22ae5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T14:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-06T15:41:59.270649+00:00  {"message":"[PlaceOrder] user_id=\"7f3a50d6-aa09-11f1-83dd-26fccfc59db7\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-06T15:41:59.270534583Z"}
2026-09-06T15:41:59.289109+00:00  {"message":"payment went through (transaction_id: fa7d1f59-af8f-42e7-9b7c-cb65c297803f)","severity":"info","timestamp":"2026-09-06T15:41:59.289041083Z"}
2026-09-06T15:41:59.294430+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-06T15:41:59.294241Z"}
2026-09-06T15:41:59.295239+00:00  {"message":"Successful to write message. offset: 1328","severity":"info","timestamp":"2026-09-06T15:41:59.295182375Z"}
```

## Mechanism and cause

Frontend logs turned the investigation: every retained error came from the gRPC client stack, status 14 UNAVAILABLE with a no-connection detail and status 13 INTERNAL on the checkout path chaining to a refused TCP connection to the cart endpoint on port 7070. Refusal at dial time eliminated slow-upstream/deadline theories, name resolution (a concrete IP was resolved then refused), HTTP-layer 5xx, and auth or handshake rejection. Nothing was listening.

Cart logs explained why. From about T-42s to T+1m51s the process cycles through at least six crash-restarts: each attempts a Redis connection on port 6380, hangs ten to fifty seconds, then throws an unhandled exception out of the cart-store initialize path called from Main and dies. Startup-path frames mean it never reaches a serving state. That killed the memory-pressure, request-handler-bug, rolling-deploy and intermittent-flakiness theories, and made clear that restarting cart is not a fix — restarts are already happening and fail identically.

The change history shows one change in the preceding seven hours: an automated environment update at T-2m30s setting cart's Redis address to that endpoint. The same toggle had been applied and reverted at least three times earlier in the day; this application has no paired revert, so prior harmlessness does not transfer. No image change in over eight hours, no traffic-shaping sidecar attached at onset, no human actor. Fix class: revert the configuration. Open: nobody probed the Redis endpoint itself, so whether the port is wrong or the instance is simply down at a correct address remains unobserved, as does the interval between the edit and the first crash.

> Evidence `tr_b5edb21dc499`:

```
<tool_result id="tr_b5edb21dc499" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T14:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-06T15:48:00.330753+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-06T15:48:00.330793+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-06T15:48:00.330796+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-06T15:48:00.330797+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_abcd3dfe6600`:

```
<tool_result id="tr_abcd3dfe6600" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T12:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-06T13:08:17.306308+00:00  AddItemAsync called with userId=0694f0f6-a9f4-11f1-83dd-26fccfc59db7, productId=1YMWWN1N4O, quantity=5
2026-09-06T13:08:17.309298+00:00  GetCartAsync called with userId=0694f0f6-a9f4-11f1-83dd-26fccfc59db7
2026-09-06T13:08:18.103215+00:00  AddItemAsync called with userId=0711e516-a9f4-11f1-83dd-26fccfc59db7, productId=0PUK6V6EV0, quantity=5
2026-09-06T13:08:18.104455+00:00  GetCartAsync called with userId=0711e516-a9f4-11f1-83dd-26fccfc59db7
```

> Evidence `tr_df8db2306799`:

```
<tool_result id="tr_df8db2306799" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T15:50:30.583000+00:00..2026-09-06T15:52:34.264293+00:00" radius="candidate_cause" hops="1">
service: cartservice
28 changes, ranked by suspicion
  #1  2m before onset  2026-09-06T15:47:59.439115+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  7.8h before onset  2026-09-06T08:01:25.932667+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

