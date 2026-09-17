# Checkout stalls traced to cartservice restart loop after a Redis address change

## What we saw, and the dead ends

Pages arrived from frontend, loadgenerator and checkoutservice together; twelve services in the blast radius, entry point frontend, four unmeasured edges in the path. The first hour went into frontend and produced nothing usable.

The frontend change log came back completely empty, which closed both "frontend shipped something" and "a frontend rollback explains recovery" — but note the query was scoped to frontend alone at zero hops and the window ran forward from onset rather than backward, so that emptiness was weaker than it looked.

The error-rate metrics actively misled. Frontend's mean error ratio was essentially identical to baseline (~0.98 of it); only the shape changed, with roughly tripled deviation and peaks about four times the baseline maximum. Three bursts appeared, at about T-90m, T-40m and just before the time of interest — and the last was the smallest of the three, which briefly convinced us nothing new had happened. checkoutservice showed the same pattern at ~5x baseline mean with the latest change point again the smallest, plus four intervals with no traffic recorded at all. Neither series carried a downstream dimension, so neither could name or clear a dependency. cartservice's own error ratio was a third dead end: zero samples in both the incident and the preceding baseline window, denominator included, so the service emits no such series at all. Empty is not zero, and the tool's "no departure from baseline" verdict there was worthless.

> Evidence `tr_d585c580232e`:

```
<tool_result id="tr_d585c580232e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T05:04:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_d585c580232e>
```

> Evidence `tr_76f4343d79aa`:

```
<tool_result id="tr_76f4343d79aa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T03:34:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" template="error-ratio" baseline="2026-09-17T02:02:39.263784+00:00..2026-09-17T03:34:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=368 mean=0.05577 min=0 max=0.475 sd=0.1044
  baseline window: n=338 mean=0.05702 min=0 max=0.1195 sd=0.03842
```

> Evidence `tr_7fe30ea0e616`:

```
<tool_result id="tr_7fe30ea0e616" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T02:04:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" template="error-ratio" baseline="2026-09-16T23:02:39.263784+00:00..2026-09-17T02:04:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The pointers that held

Frontend logs broke the deadlock. Most lines were a generic code 14 UNAVAILABLE naming nothing, but at least one code 13 INTERNAL spelled out the cart-fetch step of checkout and wrapped an upstream Unavailable from a dial to 172.18.0.16:7070 that was actively refused. That closed DNS and service discovery (an address resolved and a connect was rejected), closed latency and saturation (immediate refusal, no deadline or resource codes), closed TLS and auth (rejection at the dial stage), and closed "frontend throws its own errors" — all retained frames were in the gRPC client receive path. Caveat: the downstream was identified only by address and operation, and this result was truncated to the oldest eight and newest thirty-two lines, so the minutes around T+0 were never returned.

checkoutservice logs looked healthy and that was the signal. The final three minutes were entirely info-level, with PlaceOrder entries arriving steadily, so the process was alive. But the payment-confirmation, email and queue-write markers that accompanied a healthy order earlier in the window never appeared. Orders entered and none completed; no line named a dependency.

Traces settled the hop. All ten sampled PlaceOrder traces shared one shape and terminated at CartService/GetCart with ERROR. No payment, shipping or email spans existed, so those stages were never reached. End-to-end time was 1.3–2.7ms with the failing child under a millisecond — failing fast, not hanging, which finally killed the slow-dependency reading. The preparation span was not itself flagged and had minimal self time, so checkoutservice's assembly logic was not the origin. Ten of ten identical ruled out intermittency, and both frontend spans reached checkoutservice cleanly.

> Evidence `tr_fc0c2989237e`:

```
<tool_result id="tr_fc0c2989237e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:34:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T03:35:13.654634+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-17T03:35:13.654704+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T03:35:13.654708+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T03:35:13.654710+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_f8f2ad4e7b47`:

```
<tool_result id="tr_f8f2ad4e7b47" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:34:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-17T03:35:19.862677+00:00  {"message":"[PlaceOrder] user_id=\"ce6506f0-b248-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T03:35:19.86254021Z"}
2026-09-17T03:35:22.939956+00:00  {"message":"[PlaceOrder] user_id=\"7e5634cc-b248-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T03:35:22.93971792Z"}
2026-09-17T03:35:34.581204+00:00  {"message":"[PlaceOrder] user_id=\"d3a58f40-b248-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T03:35:34.58100955Z"}
2026-09-17T03:35:34.586163+00:00  {"message":"[PlaceOrder] user_id=\"d5a1947e-b248-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-17T03:35:34.586055675Z"}
```

> Evidence `tr_2560c191a511`:

```
<tool_result id="tr_2560c191a511" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T04:34:30.583000+00:00..2026-09-17T05:06:21.902216+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace f3ba38f0e44fd71e  root frontend/HTTP POST  1.6ms  started 2026-09-17T05:05:12.589010+00:00  5 spans
  +0.0ms frontend/HTTP POST 1.6ms [self 0.2ms]  ERROR
```

## The cause, and what is still open

cartservice logs supplied what its metrics could not. Early in the window it was serving GetCart and AddItem normally. By the last three minutes it was in a crash-restart loop: a Redis connect attempt at startup, a 20–40 second hang, then an unhandled ApplicationException out of RedisCartStore.EnsureRedisConnected via Program.Main, terminating the process — at least six cycles across roughly two and a half minutes. Because the exception escapes Main, the gRPC listener never binds, which is precisely why frontend's dial to :7070 was refused. The startup line named host redis-cart on port 6380. Not a resource kill (explicit connect failure and typed exception each cycle, no memory lines), not a request-handling bug (all frames pre-request), not auth or TLS (ssl disabled, generic connect failure after a long silence).

The change history for cartservice closed it: seven changes, all by the same platform-automation actor, all inside the ninety minutes before onset and nothing in the prior day. The nearest was an environment update about two minutes before onset setting the Redis address to a non-default port where no value had been set before. Two tempting alternatives died here: a hotfix image applied near T-90m was reverted minutes later, re-applied near T-40m and reverted again, so the pre-hotfix reference was running at onset; and an egress-delay sidecar attached near T-20m was removed about eleven minutes before onset. No change to the cache workload itself appears anywhere. Fix class is a config revert; confidence high.

Three things remain unresolved. Nobody confirmed which port redis-cart actually listens on — that 6380 is wrong is inferred from convention and from the connect failing. The frontend and checkoutservice bursts at T-90m and T-40m are equal or larger than the one at onset and predate the config change; the two hotfix windows and the delay window are a plausible but unverified explanation. And the cartservice log result was truncated across about two hours, so the first crash cycle could predate the config change, which would break the asserted ordering.

> Evidence `tr_6ee0e4f18ac5`:

```
<tool_result id="tr_6ee0e4f18ac5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T03:04:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-17T03:04:35.197875+00:00  GetCartAsync called with userId=
2026-09-17T03:04:35.997128+00:00  AddItemAsync called with userId=838bf584-b244-11f1-b359-b6ed2071a170, productId=L9ECAV7KIM, quantity=1
2026-09-17T03:04:35.999391+00:00  GetCartAsync called with userId=838bf584-b244-11f1-b359-b6ed2071a170
2026-09-17T03:04:36.013802+00:00  AddItemAsync called with userId=838bf584-b244-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=1
```

> Evidence `tr_22cb69f787cf`:

```
<tool_result id="tr_22cb69f787cf" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T05:04:30.583000+00:00..2026-09-17T05:06:21.902216+00:00" radius="candidate_cause" hops="1">
service: cartservice
7 changes, ranked by suspicion
  #1  2m before onset  2026-09-17T05:01:47.544727+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  11m before onset  2026-09-17T04:53:23.824994+00:00  platform-automation  container removed: traffic-shaping container removed from cart-service's network namespace
```

