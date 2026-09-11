# Cart backend address left pointing at a non-serving port; cart listener never bound

## What was visible first, and what wasted time

Pages fired for frontend, loadgenerator and checkoutservice; the seed handed over was frontend, with twelve services in radius and four edges carrying no metric coverage.

The first two instincts both dead-ended. Frontend's change record is empty across a full 24 hours — no deploys, no config edits, no flag toggles, no later rollback — so no frontend-side trigger exists. Note the trap: that query was scoped to the seed with zero hops, so it says nothing about checkoutservice or the ten downstream services; reading it as "no changes anywhere" would have been wrong.

The error-ratio checks actively mislead. Frontend's aggregate error ratio during the window is about 2.5x *lower* than baseline. Checkoutservice sits near 8% against a 16% baseline, with standard deviation exceeding the mean and a floor at zero — the signature of a thin denominator, not a trend. Both are grouped by service name only, with no per-dependency dimension and no latency series, so neither can attribute anything. A responder who stops here concludes nothing is wrong.

> Evidence `tr_6a6a8616ae1e`:

```
<tool_result id="tr_6a6a8616ae1e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T06:03:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_6a6a8616ae1e>
```

> Evidence `tr_2847de2abd5a`:

```
<tool_result id="tr_2847de2abd5a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T05:33:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" template="error-ratio" baseline="2026-09-10T05:00:54.689618+00:00..2026-09-10T05:33:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.04109 min=0 max=0.3139 sd=0.09211
  baseline window: n=129 mean=0.102 min=0 max=0.342 sd=0.1189
```

> Evidence `tr_fbb2d5e02a05`:

```
<tool_result id="tr_fbb2d5e02a05" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T05:33:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" template="error-ratio" baseline="2026-09-10T05:00:54.689618+00:00..2026-09-10T05:33:00.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.07976 min=0 max=0.6667 sd=0.2033
  baseline window: n=129 mean=0.1579 min=0 max=0.6667 sd=0.2822
```

## Logs name the hop; checkout hides it

Frontend's log stream is dominated by grpc-js status 14 (no connection established), plus one decisive line: status 13 describing a cart failure fetching the user cart during checkout, caused by a transport dial to 172.18.0.8:7070 being refused. That closes several doors — refusal not timeout, so no deadline theory; a concrete resolved IP, so not DNS; stack frames ending in the client library, so not a frontend bug; only the cart path named, so not a broad multi-dependency outage. One unresolved oddity: the same status-14 errors already appear in the oldest retained lines, roughly 30 minutes before the change we ultimately blame.

Checkoutservice logs contain no error or warning lines at all, which is why it looked healthy. What changes is shape: early orders log start, payment, email and a message-write acknowledgement; from about T-2m only the order-start entries appear. Orders keep arriving through the end of the window, so the process is alive and accepting — the loss happens after entry, consistent with a call that never returns. Hung requests never land in the error bucket, which is exactly why the ratios looked better than baseline.

Two hops down it resolves. Cartservice started cleanly around T-30m against the standard Redis port and bound its listener on 7070. From about T-1m it is in a crash loop: each attempt dials port 6380, hangs 25–50 seconds, and dies with an unhandled ApplicationException from RedisCartStore.EnsureRedisConnected in Main — before the listener bind. Nothing on 7070 is exactly why callers see refusal. Ruled out here: port conflict (bind succeeds early, never reached later), memory kill (orderly managed traces), and any serving-path crash (stack terminates in Main).

> Evidence `tr_02a9dbc72d4c`:

```
<tool_result id="tr_02a9dbc72d4c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T05:33:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T05:33:04.966874+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-10T05:33:04.966917+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T05:33:04.966922+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T05:33:04.966924+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_d63cedf2f39f`:

```
<tool_result id="tr_d63cedf2f39f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T05:33:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T05:33:16.600737+00:00  {"message":"[PlaceOrder] user_id=\"1fb745e2-acd9-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T05:33:16.600648968Z"}
2026-09-10T05:33:16.630801+00:00  {"message":"payment went through (transaction_id: 87105779-33fa-4dcc-ae90-3be934c898f3)","severity":"info","timestamp":"2026-09-10T05:33:16.630634009Z"}
2026-09-10T05:33:16.663667+00:00  {"message":"order confirmation email sent to \"reed@example.com\"","severity":"info","timestamp":"2026-09-10T05:33:16.663537801Z"}
2026-09-10T05:33:16.667150+00:00  {"message":"Successful to write message. offset: 28145","severity":"info","timestamp":"2026-09-10T05:33:16.667034093Z"}
```

> Evidence `tr_5da85760ac8b`:

```
<tool_result id="tr_5da85760ac8b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T05:33:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T05:33:06.394128+00:00  Connecting to Redis: redis-cart:6379,ssl=false,allowAdmin=true,abortConnect=false
2026-09-10T05:33:06.933777+00:00  Successfully connected to Redis
2026-09-10T05:33:06.935087+00:00  Performing small test
2026-09-10T05:33:06.948984+00:00  Small test result: OK
```

## The change that stayed, and what is still open

Cartservice's change record holds 25 entries, all from platform-automation — no human actor, no flags. They repeat a six-hour cycle: image update, image revert, traffic-shaping attach, traffic-shaping remove, Redis address update, Redis address revert. In the final cycle the image was reverted ~T-29m and the 300ms traffic-shaping container removed ~T-10m, so both were inactive at onset; both are tempting and both are dead ends. The anomaly is the last step: at ~T-2m30s REDIS_ADDR was set to redis-cart:6380 and, unlike the four earlier occurrences which each reverted within eight to ten minutes, never reverted. The wrong port value is itself the mechanism. Fix class: revert the value.

Do not spend time on cartservice's error-ratio check — it returned no samples in the incident window *and* none in the baseline, so it is a telemetry coverage gap, not evidence of silence. It also covers neither restart counters nor memory.

Still open: redis-cart itself was never inspected, so whether nothing listens on 6380 or the backend is separately down is unestablished; why checkout truncates silently rather than logging a refusal; why frontend's UNAVAILABLE errors predate the config edit by roughly half an hour; and the change state of the ten other downstream services, never queried.

> Evidence `tr_374c3515f9cb`:

```
<tool_result id="tr_374c3515f9cb" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T06:03:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" radius="candidate_cause" hops="1">
service: cartservice
25 changes, ranked by suspicion
  #1  2m before onset  2026-09-10T06:00:31.603555+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  10m before onset  2026-09-10T05:52:06.554844+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

> Evidence `tr_48c5e62128bc`:

```
<tool_result id="tr_48c5e62128bc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T05:33:00.583000+00:00..2026-09-10T06:05:06.476382+00:00" template="error-ratio" baseline="2026-09-10T05:00:54.689618+00:00..2026-09-10T05:33:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

