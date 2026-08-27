# Cart backing-store endpoint change silently breaks checkout and browse paths

## What was visible first, and what misled us

Three alerts arrived together — frontend, loadgenerator, checkoutservice — with a twelve-service blast radius and critical severity. That width read like an infrastructure event and shaped the first queries badly; almost all of it turned out to be propagation.

Frontend's error ratio came back non-zero and non-flat, swinging from zero to roughly 31.5%. That killed the comfortable stories: not a false-positive alert rule, not a hard outage, not a steady background rate. checkoutservice looked worse in ratio terms, peaking near two-thirds of calls failing while dipping to zero at points — on the incident path, not down, errors explicitly recorded rather than silently slow. Neither query returned latency percentiles or a per-dependency breakdown, so after two queries we knew the failure was partial and episodic and still had no idea where it started.

The first real dead end was the change log. We queried checkoutservice because it had the highest error ratio and got a completely empty result — no deploy, no config edit, no flag flip, and none in the five minutes after either, so no in-incident remediation was confounding the signal. Useful as a negative, but the query covered only that one service and only a fifteen-minute slice. The six synchronous dependencies and the earlier lookback were never checked. Widening it on the first pass would have found the real change two steps sooner.

The second dead end was checkoutservice's logs: no errors at all, every line informational, no dependency named as failing. Anyone grepping for ERROR would have cleared checkout. The signal was in absence — early in the window each order placement was followed within ~20ms by payment, confirmation-email and message-write lines; from ~17:23 onward only the placement lines remain, at unchanged cadence. Orders started and never finished, with no diagnostic at the break. That ruled out a checkout crash, an upstream traffic loss, and a currency-specific theory (USD and CAD stalled identically), but gave us no name to pivot on.

> Evidence `tr_b79e6df5609c`:

```
<tool_result id="tr_b79e6df5609c" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3152 n=58
</tool_result:tr_b79e6df5609c>
```

> Evidence `tr_e72cb9413005`:

```
<tool_result id="tr_e72cb9413005" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=59
</tool_result:tr_e72cb9413005>
```

> Evidence `tr_f851cf44f972`:

```
<tool_result id="tr_f851cf44f972" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_f851cf44f972>
```

> Evidence `tr_640d72847cfc`:

```
<tool_result id="tr_640d72847cfc" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T17:13:17.858221+00:00  {"message":"[PlaceOrder] user_id=\"98a5ebd8-a23a-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T17:13:17.858092591Z"}
2026-08-27T17:13:17.876450+00:00  {"message":"payment went through (transaction_id: c511a61d-0db7-41db-afcd-1ad98d36eec5)","severity":"info","timestamp":"2026-08-27T17:13:17.876359091Z"}
2026-08-27T17:13:17.881074+00:00  {"message":"order confirmation email sent to \"jack@example.com\"","severity":"info","timestamp":"2026-08-27T17:13:17.880946633Z"}
2026-08-27T17:13:17.881573+00:00  {"message":"Successful to write message. offset: 19565","severity":"info","timestamp":"2026-08-27T17:13:17.881457675Z"}
```

## The pivot: an edge with no far side

Traces gave us the direction. Failing requests came in two shapes: browse and cart requests where the frontend HTTP span's only child was an erroring client call to CartService (GetCart or AddItem); and checkout requests where frontend to PlaceOrder errored, checkoutservice's own PlaceOrder errored, its prepareOrderItemsAndShippingQuoteFromCart sibling completed cleanly, and the nested checkoutservice to CartService/GetCart client span errored.

That settled attribution. checkoutservice's error is inherited — a clean sibling and a single erroring descendant make it a propagator. Frontend is likewise a propagator: its spans errored only when they carried an erroring cart child, while catalog, ad and recommendation calls succeeded in the same window. That also disposed of the infrastructure-wide theory: failure was selective to one callee, reached from two independent callers.

Two details mattered. Every erroring span was under eleven milliseconds, with the cart client spans at a fraction of a millisecond, while the slowest spans in the window were all clean — so this was fast-fail, and any saturation or timeout-threshold theory died. And no cartservice server span appeared anywhere in two hundred spans; the deepest error terminated at a caller-side client span. We were at the last measured hop before an edge we could not see across.

The cartservice metric query then returned no matching series at all for the window — not a zero, an absence, with both numerator and denominator empty. Worth being precise: a healthy service with no errors still emits a denominator and yields zero. An empty result is distinguishable, so this ruled out both a healthy cart and any hope of citing a cart error spike as the signature.

> Evidence `tr_9a4b89aba003`:

```
<tool_result id="tr_9a4b89aba003" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00">
service: frontend
200 spans
  0620e365541fd23b frontend/HTTP GET 0.6ms ERROR
  0620e365541fd23b frontend/grpc.hipstershop.CartService/GetCart 0.3ms ERROR
  e8267be989eb6d84 loadgenerator/HTTP GET 29.0ms
```

> Evidence `tr_10d2f7406063`:

```
<tool_result id="tr_10d2f7406063" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_10d2f7406063>
```

## Mechanism, the change, and what remains open

cartservice logs closed it. The process was in a startup crash loop: connect attempt to the Redis backing store, failure after roughly fifteen to forty-five seconds, then termination on an unhandled exception from RedisCartStore.EnsureRedisConnected via InitializeAsync in Main — at least six cycles between about 17:24:47 and 17:27:29. The exception fires during initialization, before gRPC serving begins, which explains the empty metric series exactly: no server, so no server span. It also ruled out a request-handler bug, since no GetCart or AddItem calls are logged at all during the failing period. The recorded target was redis-cart on port 6380, TLS disabled, plain connect timeout rather than refusal — so not an auth or handshake problem, and consistent with an unreachable endpoint. Around 17:13 the service had been serving normally.

The cartservice change log held exactly one entry: an environment variable update setting that backing-store address, applied at 17:20:38 by platform automation, with no recorded prior value. One entry meant unambiguous attribution and ruled out a new image, a flag toggle, and any purely organic explanation.

Open items a future responder should not assume away. Nobody verified what redis-cart is actually listening on — if the platform legitimately moved Redis to 6380, the break is on the Redis side and reverting to the unset default fixes nothing. The actor is unnamed automation, so a revert may be reconciled back. Onset timing is unreconciled: the change landed at 17:20:38, alerts fired at 17:23:15, first observed crash cycle at 17:24:47, and nobody measured whether errors preceded the first restart. Four unmeasured edges were crossed and only cartservice's was resolved, so a second concurrent failure in the twelve-service radius cannot be excluded. And the link between the cart call and checkout's missing payment, email and message-write stages is inferred from the trace shape, not directly measured — checkout's per-dependency outbound error rates were never queried. Fix class: revert the configuration.

> Evidence `tr_8e580206e03d`:

```
<tool_result id="tr_8e580206e03d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T17:13:17.831240+00:00  AddItemAsync called with userId=98a5ebd8-a23a-11f1-86d7-1e4ac5f08d0c, productId=OLJCESPC7Z, quantity=2
2026-08-27T17:13:17.833540+00:00  GetCartAsync called with userId=98a5ebd8-a23a-11f1-86d7-1e4ac5f08d0c
2026-08-27T17:13:17.850187+00:00  AddItemAsync called with userId=98a5ebd8-a23a-11f1-86d7-1e4ac5f08d0c, productId=9SIQT8TOJO, quantity=2
2026-08-27T17:13:17.851676+00:00  GetCartAsync called with userId=98a5ebd8-a23a-11f1-86d7-1e4ac5f08d0c
```

> Evidence `tr_1ae166a5f4b1`:

```
<tool_result id="tr_1ae166a5f4b1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T17:13:15.583000+00:00..2026-08-27T17:28:15.583000+00:00">
service: cartservice
1 changes
  2026-08-27T17:20:38.028589+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_1ae166a5f4b1>
```
