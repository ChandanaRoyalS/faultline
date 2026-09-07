# Cart-dependent checkout paths failing behind a crash-looping cart service

## What the pager showed

Three services alerted at once: frontend, loadgenerator, and checkoutservice. Severity was called critical, with a stated blast radius of twelve services and four edges nobody had instrumentation for. The starting point handed to the responder was frontend, which is the natural place to look and — as it turned out — the wrong place to spend the first ten minutes.

The shape of the user-visible symptom mattered more than the alert list: this was never a total outage. Frontend's error ratio across the window averaged roughly 10% with peaks near a third, and checkoutservice averaged around 21% peaking near two thirds. Both series oscillated between fully clean and majority-failing intervals rather than stepping up to a plateau. That burstiness is what a partial dependency failure looks like when only some routes touch the broken thing.

> Evidence `tr_f16426d03d4c`:

```
<tool_result id="tr_f16426d03d4c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T07:32:29.646454+00:00..2026-09-07T09:04:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=246 mean=0.09948 min=0 max=0.3327 sd=0.1291
  baseline window: no samples
```

> Evidence `tr_2f263c1116b8`:

```
<tool_result id="tr_2f263c1116b8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T07:32:29.646454+00:00..2026-09-07T09:04:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=246 mean=0.2116 min=0 max=0.6667 sd=0.2984
  baseline window: no samples
```

## First moves, and what they cost

T+0 to T+5m went to the obvious question: what changed on frontend? Nothing. The change record for frontend over the full preceding day came back empty — no deploys, no config edits, no flag flips. That is a clean negative and worth keeping, because it forecloses the single most common explanation without further argument.

T+5m to T+12m went to metrics on both alerting services. Useful for shape, useless for attribution. The error-ratio queries aggregate only by service name: no dependency dimension, no route dimension, no latency component. They can tell you frontend is partially unhealthy; they cannot tell you which downstream is responsible. A responder who keeps drilling here will not find the answer. Worse, the tooling's automatic baseline comparison reported "no sustained departure" for both services — but the comparison window returned zero samples, so that verdict rests on nothing. The same trap applies to the reported move "from 0." Do not read either as reassurance.

> Evidence `tr_54e4c301005d`:

```
<tool_result id="tr_54e4c301005d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-06T10:34:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_54e4c301005d>
```

> Evidence `tr_f16426d03d4c`:

```
<tool_result id="tr_f16426d03d4c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T07:32:29.646454+00:00..2026-09-07T09:04:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=246 mean=0.09948 min=0 max=0.3327 sd=0.1291
  baseline window: no samples
```

> Evidence `tr_2f263c1116b8`:

```
<tool_result id="tr_2f263c1116b8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T07:32:29.646454+00:00..2026-09-07T09:04:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=246 mean=0.2116 min=0 max=0.6667 sd=0.2984
  baseline window: no samples
```

## The turn: reading frontend's logs instead of its metrics

Around T+15m the logs gave what the metrics could not. Frontend emits two error shapes: gRPC code 14 UNAVAILABLE with a no-connection-established detail, and code 13 INTERNAL whose detail names the failing operation outright — retrieving the user cart during checkout — wrapping an inner Unavailable from a dial to 172.18.0.8 on port 7070, the conventional cart port, refused at connect.

That detail settles several things at once. The address resolved and routed, so this is not a discovery problem. The connection was refused before any handshake, so it is not credentials or TLS. There is no DEADLINE_EXCEEDED anywhere, so it is not saturation or slowness — the socket never opens. And no other backend is named in any returned line; product catalog, currency, ads and recommendations are all absent from the error details. Frontend is the reporter here, not the origin: every line is a client-side status surfaced through the gRPC call stack.

> Evidence `tr_3ac75e3b3e96`:

```
<tool_result id="tr_3ac75e3b3e96" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-07T09:34:28.473327+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-07T09:34:28.473384+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-07T09:34:28.473388+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-07T09:34:28.473390+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Following the arrow to cartservice

At roughly T+20m the responder went to cartservice metrics and hit a dead end that looks alarming and is not. The error-ratio query returned nothing — for the incident window and for a baseline three hours earlier alike. Because the emptiness predates the incident by hours, it cannot be a symptom of it; the call-count series simply is not collected for this service. Equally, absence is not exoneration: it says nothing about serving health either way, and it carries no restart, availability, or memory signal at all. Whoever reads this next should not re-run that query expecting a different outcome.

The cart logs answered immediately, around T+25m. The process is in a startup loop: each attempt logs a Redis connection attempt against redis-cart, fails to connect, and terminates with an unhandled .NET ApplicationException raised from cart store initialization called directly from Main. The cycle repeats every fifteen to forty seconds and is continuous across the whole retained window, with identical lines at the oldest and newest ends and no successful startup anywhere between. The connection target recorded in the startup line is port 6380, not the Redis default.

That explains the refused TCP connect exactly: the failure happens during initialization, before the gRPC listener is ever bound, so there is no socket for frontend to reach. It also rules out the alternatives cleanly — no memory-pressure or abrupt-kill signature, no request-path frames, no bind or address-in-use error, and no partially-serving state.

> Evidence `tr_ff4e9f61c2f7`:

```
<tool_result id="tr_ff4e9f61c2f7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-07T07:34:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T04:32:29.646454+00:00..2026-09-07T07:34:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_7216e1f696a5`:

```
<tool_result id="tr_7216e1f696a5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T10:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-07T10:04:35.098721+00:00  Wasn't able to connect to redis
2026-09-07T10:04:35.201370+00:00  Unhandled exception. System.ApplicationException: Wasn't able to connect to redis
2026-09-07T10:04:35.201390+00:00     at cartservice.cartstore.RedisCartStore.EnsureRedisConnected() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 89
2026-09-07T10:04:35.201391+00:00     at cartservice.cartstore.RedisCartStore.InitializeAsync() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 62
```

## The change record and the older red herrings

Cartservice's change history is not empty: thirteen entries in twenty-four hours, every one attributed to platform-automation, with no human actor at all. The Redis address environment value pointing at the non-default port was applied and reverted repeatedly — at least five apply/revert pairs, three of them in the hour before onset. The nearest application lands about two minutes before onset, following a reverted state roughly twenty-seven minutes earlier, so onset sits on a transition rather than in steady state.

Two other change classes appear and both are dead ends worth recording. A cartservice image reference change roughly 17.7 hours before onset, reverted about an hour later — so no code change was in force. And a sidecar attaching fixed network delay to the cart network namespace, added ~17.4 hours before and explicitly removed ~17.2 hours before, therefore not present when this began. Also absent: any scaling, replica, resource-limit, or feature-flag change. If you are tempted by the delay sidecar because the story involves cart, check its removal timestamp first.

> Evidence `tr_8ffdd960ec9a`:

```
<tool_result id="tr_8ffdd960ec9a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-06T10:34:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" radius="candidate_cause" hops="1">
service: cartservice
13 changes, ranked by suspicion
  #1  2m before onset  2026-09-07T10:31:47.493918+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  27m before onset  2026-09-07T10:07:07.633670+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

## Conclusion and fix class

Cartservice is pointed at redis-cart on 6380. Nothing answers there, so the process fails store initialization in Main, throws, and dies before binding its listener — crash-looping continuously. With no serving instance, frontend's cart RPCs are refused at TCP connect and surface as code 14 and code 13 naming cart retrieval during checkout; checkoutservice fails on the same path. Only cart-dependent routes break, which is precisely why both callers show partial, bursty error ratios rather than a flat outage. The wrong port value is not a trigger for some deeper problem; it is the mechanism itself.

Fix class: revert the configuration value. Confidence high.

> Evidence `tr_7216e1f696a5`:

```
<tool_result id="tr_7216e1f696a5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T10:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-07T10:04:35.098721+00:00  Wasn't able to connect to redis
2026-09-07T10:04:35.201370+00:00  Unhandled exception. System.ApplicationException: Wasn't able to connect to redis
2026-09-07T10:04:35.201390+00:00     at cartservice.cartstore.RedisCartStore.EnsureRedisConnected() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 89
2026-09-07T10:04:35.201391+00:00     at cartservice.cartstore.RedisCartStore.InitializeAsync() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 62
```

> Evidence `tr_3ac75e3b3e96`:

```
<tool_result id="tr_3ac75e3b3e96" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-07T09:34:28.473327+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-07T09:34:28.473384+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-07T09:34:28.473388+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-07T09:34:28.473390+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_2f263c1116b8`:

```
<tool_result id="tr_2f263c1116b8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T07:32:29.646454+00:00..2026-09-07T09:04:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=246 mean=0.2116 min=0 max=0.6667 sd=0.2984
  baseline window: no samples
```

> Evidence `tr_f16426d03d4c`:

```
<tool_result id="tr_f16426d03d4c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" template="error-ratio" baseline="2026-09-07T07:32:29.646454+00:00..2026-09-07T09:04:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=246 mean=0.09948 min=0 max=0.3327 sd=0.1291
  baseline window: no samples
```

> Evidence `tr_8ffdd960ec9a`:

```
<tool_result id="tr_8ffdd960ec9a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-06T10:34:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" radius="candidate_cause" hops="1">
service: cartservice
13 changes, ranked by suspicion
  #1  2m before onset  2026-09-07T10:31:47.493918+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  27m before onset  2026-09-07T10:07:07.633670+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

## Open threads for whoever reads this next

Three things were left unresolved and each could change the response.

First, a timeline contradiction that directly affects whether the fix will hold. The crash loop with target 6380 is observed running continuously from roughly T-30m onward, but the change record says that value was reverted around T-27m and only re-applied around T-2m. Both cannot be true of the running pods. Either the change log's state tracking is inaccurate, or reverts are being recorded without ever reaching the workload. If it is the latter, applying another revert will accomplish nothing and you will be back here.

Second, nobody ever measured redis-cart. No one checked which port it actually listens on, or whether it is healthy at all. That 6379 is the correct value is an inference from convention, not an observation. Confirm it before changing anything.

Third, the incident is older than the alert. Frontend was already emitting the same code-14 signature roughly an hour before onset, so the true start was never bounded and the alert threshold is probably tuned to catch only the loudest part of this. Nine of the twelve services in the stated blast radius were never probed, and all four unmeasured edges remain unmeasured.

> Evidence `tr_7216e1f696a5`:

```
<tool_result id="tr_7216e1f696a5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T10:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-07T10:04:35.098721+00:00  Wasn't able to connect to redis
2026-09-07T10:04:35.201370+00:00  Unhandled exception. System.ApplicationException: Wasn't able to connect to redis
2026-09-07T10:04:35.201390+00:00     at cartservice.cartstore.RedisCartStore.EnsureRedisConnected() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 89
2026-09-07T10:04:35.201391+00:00     at cartservice.cartstore.RedisCartStore.InitializeAsync() in /usr/src/app/src/cartstore/RedisCartStore.cs:line 62
```

> Evidence `tr_8ffdd960ec9a`:

```
<tool_result id="tr_8ffdd960ec9a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-06T10:34:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" radius="candidate_cause" hops="1">
service: cartservice
13 changes, ranked by suspicion
  #1  2m before onset  2026-09-07T10:31:47.493918+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
  #2  27m before onset  2026-09-07T10:07:07.633670+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_3ac75e3b3e96`:

```
<tool_result id="tr_3ac75e3b3e96" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T09:04:15.583000+00:00..2026-09-07T10:36:01.519546+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-07T09:34:28.473327+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-07T09:34:28.473384+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-07T09:34:28.473388+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-07T09:34:28.473390+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

