# Cart backend crash loop from a rewritten Redis endpoint value

## What was visible, in order

Take T+0 as the first pages: loadgenerator, frontend and checkoutservice alerted within the same minute. Frontend's error ratio moved from clean to roughly 29.6% at peak; checkoutservice reached about two thirds of calls. Both series included zero-error samples in the same window, so this was a transition rather than a chronic condition, and neither service was fully down. Traces were the turn. Every sampled error chain bottomed out at the caller's own client span for CartService/GetCart or CartService/AddItem — sub-millisecond, errored, with no cartservice server span beneath it. The trace simply ended there. Checkout told the same story from a different caller: PlaceOrder errored, its non-cart child completed cleanly, and the deepest errored span was its outbound cart read. Catalog, ads and recommendations were clean in the same window, and browse paths were unaffected. The fast-fail shape killed any latency reading early.

> Evidence `tr_3eecb375044e`:

```
<tool_result id="tr_3eecb375044e" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.296 n=61
</tool_result:tr_3eecb375044e>
```

> Evidence `tr_50fb661719a5`:

```
<tool_result id="tr_50fb661719a5" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_50fb661719a5>
```

> Evidence `tr_2baa5034a48e`:

```
<tool_result id="tr_2baa5034a48e" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
service: frontend
200 spans
  ca4c74924cf18583 frontend/HTTP GET 12.7ms
  a1b0fc387a2874e6 frontend/HTTP GET 4.5ms
  a1b0fc387a2874e6 frontend/grpc.hipstershop.AdService/GetAds 3.6ms
```

## What the cart service and its change history showed

Cartservice logs around T-10m show normal cart operations. From roughly T+2m onward the pattern is a startup crash loop: a connection attempt naming host redis-cart on port 6380, a failure to connect, an unhandled ApplicationException through RedisCartStore.EnsureRedisConnected -> InitializeAsync -> Program.Main, then a fresh attempt about a second later. At least six cycles, still looping at the last line. No attempt succeeded; the stack frames run only through startup Redis initialization. Cartservice's change history for the window holds exactly one entry: at T-2m15s an automated platform pipeline applied an environment variable update setting the Redis address to that host and port — a config mutation, not an image rollout, not a scaling action, no competing changes, no human actor. The conventional port is 6379. The endpoint value is itself the failing mechanism: the address names a port nothing answers on. Remediation class is a revert of that value.

> Evidence `tr_18720a96077f`:

```
<tool_result id="tr_18720a96077f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-27T02:50:46.015262+00:00  AddItemAsync called with userId=1a293e54-a1c2-11f1-86d7-1e4ac5f08d0c, productId=1YMWWN1N4O, quantity=3
2026-08-27T02:50:46.017946+00:00  GetCartAsync called with userId=1a293e54-a1c2-11f1-86d7-1e4ac5f08d0c
2026-08-27T02:50:48.211673+00:00  AddItemAsync called with userId=1b7aa5b8-a1c2-11f1-86d7-1e4ac5f08d0c, productId=1YMWWN1N4O, quantity=2
2026-08-27T02:50:48.213430+00:00  GetCartAsync called with userId=1b7aa5b8-a1c2-11f1-86d7-1e4ac5f08d0c
```

> Evidence `tr_b2e8f499ff9f`:

```
<tool_result id="tr_b2e8f499ff9f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
service: cartservice
1 changes
  2026-08-27T02:58:30.569412+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_b2e8f499ff9f>
```

## Dead ends, and what the next responder inherits

Change history for frontend and for checkoutservice came back completely empty across the covered window — no deploys, config edits or scaling, and the window extends past onset so nothing was mid-rollout either. Both were natural first questions given both alerted; both produced nothing. Checkoutservice logs were pulled hoping to see a named downstream target in an error line and returned forty info-level lines and no errors; the oldest show complete order lifecycles through payment and confirmation, the newest show only placements, but the result was truncated in the middle so the absence of completions is not conclusive. Span-derived call metrics for cartservice returned no series at all; because the expression is a ratio, that could mean a missing numerator, a missing denominator, or a label-name mismatch — never resolved, and treating it as proof of the crash loop would be circular. Open items: nothing verified which port redis-cart actually listens on, so if Redis was legitimately moved the correction belongs on the Redis side or in ordering — check before reverting. The T-2m15s to T+2m interval is unobserved. Both change queries covered only about fifteen minutes, not the requested hour. Four unmeasured edges reported at triage were never covered. And what in the pipeline produced the value, and whether it will re-apply it after a manual revert, is unestablished.

> Evidence `tr_e9804b177039`:

```
<tool_result id="tr_e9804b177039" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_e9804b177039>
```

> Evidence `tr_9345fa6ac94f`:

```
<tool_result id="tr_9345fa6ac94f" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
no changes recorded for checkoutservice over this window
</tool_result:tr_9345fa6ac94f>
```

> Evidence `tr_cf8ef8c5f497`:

```
<tool_result id="tr_cf8ef8c5f497" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-27T02:50:51.590831+00:00  {"message":"[PlaceOrder] user_id=\"1d7a4544-a1c2-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-27T02:50:51.590741921Z"}
2026-08-27T02:50:51.607747+00:00  {"message":"payment went through (transaction_id: 2e71b7f8-50b8-4d62-a140-33bbaf383511)","severity":"info","timestamp":"2026-08-27T02:50:51.60766413Z"}
2026-08-27T02:50:51.612007+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-08-27T02:50:51.611878713Z"}
2026-08-27T02:50:51.612700+00:00  {"message":"Successful to write message. offset: 15169","severity":"info","timestamp":"2026-08-27T02:50:51.612620796Z"}
```

> Evidence `tr_f1c0cedec384`:

```
<tool_result id="tr_f1c0cedec384" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T02:50:45.583000+00:00..2026-08-27T03:05:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_f1c0cedec384>
```
