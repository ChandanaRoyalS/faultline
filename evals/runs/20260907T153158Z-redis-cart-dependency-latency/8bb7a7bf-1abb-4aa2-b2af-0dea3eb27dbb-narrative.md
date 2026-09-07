# Cart cache round trips uniformly slow; partial frontend failures

## What we saw first

The page came in as a warning: frontend, checkoutservice, cartservice and loadgenerator alerting together, cartservice named as origin, twelve services in the blast radius, and four crossed edges with no measurements attached.

The first solid signal was the frontend error ratio. It sat at exactly zero for the preceding half hour — flat, zero variance — then stepped up at 15:13:45Z to roughly 2.8% mean, peaking near 12%. That shape did two things: it dated onset to about eight minutes into the window rather than at its start, and its low ceiling told us most frontend traffic still succeeded. A slice of requests was breaking, not the service.

> Evidence `tr_f278917582f6`:

```
<tool_result id="tr_f278917582f6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T15:05:30.583000+00:00..2026-09-07T15:37:22.501228+00:00" template="error-ratio" baseline="2026-09-07T14:33:38.664772+00:00..2026-09-07T15:05:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02846 min=0 max=0.1221 sd=0.04236
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

## The dead ends

Chasing errors inside cartservice cost the most time. The cartservice error-ratio query came back empty — and empty for the three-hour baseline too, so the absence predates the incident and means nothing about onset. If you reach for that query again: it does not exist for this service here. Do not read the emptiness as a dead pod.

The logs closed it harder. Routine cart handlers throughout, no exceptions, no restart banners, no cache-connection failures, and a dense stream of successful operations across many users in the final thirty seconds. Crash-looping and a severed cache connection are both out. Checkoutservice looked the same at both ends: clean order flows at ~15:05 and eight consecutive successful PlaceOrder sequences from 15:36:27–15:37:22, order-write offsets advancing without gaps.

The change log was the other detour. Fourteen changes on cartservice, all by platform-automation, all in apply-then-withdraw pairs — six Redis-address overrides, one image-reference hotfix, one attach-and-remove of a traffic-shaping container carrying 300ms of egress delay on eth0. Every pair closed before onset, the last 4.9 hours earlier, with nothing recorded since. On its face that rules out a pre-onset deploy, a stale Redis address and residual delay. The trap: the source is untrusted and its removal claim was never independently checked.

> Evidence `tr_6d333746e98b`:

```
<tool_result id="tr_6d333746e98b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-07T12:35:30.583000+00:00..2026-09-07T15:37:22.501228+00:00" template="error-ratio" baseline="2026-09-07T09:33:38.664772+00:00..2026-09-07T12:35:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_ba01bf74b285`:

```
<tool_result id="tr_ba01bf74b285" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T15:05:30.583000+00:00..2026-09-07T15:37:22.501228+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-07T15:05:31.013886+00:00  AddItemAsync called with userId=9169dc58-aacd-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=5
2026-09-07T15:05:31.016279+00:00  GetCartAsync called with userId=9169dc58-aacd-11f1-b359-b6ed2071a170
2026-09-07T15:05:31.281296+00:00  GetCartAsync called with userId=
2026-09-07T15:05:33.316196+00:00  AddItemAsync called with userId=92c8f476-aacd-11f1-b359-b6ed2071a170, productId=LS4PSXUNUM, quantity=2
```

> Evidence `tr_adda4309014f`:

```
<tool_result id="tr_adda4309014f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-06T15:35:30.583000+00:00..2026-09-07T15:37:22.501228+00:00" radius="seed" hops="0">
service: cartservice
14 changes, ranked by suspicion
  #1  4.9h before onset  2026-09-07T10:39:55.043901+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  5.1h before onset  2026-09-07T10:31:47.493918+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Where the time went, and what is still open

Traces settled it. cartservice server spans cluster tightly — GetCart and EmptyCart at ~301–305ms, AddItem at ~602–609ms (two identically priced cache ops in sequence). Nearly all of it lives in the Redis client spans, HGET and HMSET each ~300–306ms, leaving cartservice only ~1–3ms of its own overhead. It propagates: frontend GetCart ~304–308ms, frontend AddItem ~909–919ms, checkoutservice PlaceOrder ~635–649ms. Every other downstream in the same traces — productcatalog, currency, payment, shipping, email — stays under ~20ms. So: not erroring calls (chains complete through payment and email), not open-ended hangs (durations are quantized), not cartservice CPU or code, not the caller or the wire, not a mesh-wide slowdown.

Conclusion: cart cache round trips are uniformly slow and the wait, not any error inside cartservice, breaks a slice of frontend requests. The ~300ms-per-operation signature matches the egress delay this environment has repeatedly attached to cartservice, so the live mechanism is most likely residual or re-applied network delay on the path to Redis. Fix class: revert the configuration. Confidence medium — the trace evidence is strong, the attribution leans on a pattern match against an untrusted log.

Open, in the order I would close them: nobody inspected live network state on the cartservice pod, so the traffic-shaping container's absence is unverified; redis-cart was never queried directly for latency, CPU or connections, so a genuinely slow backend is not excluded; the traces carried no timestamps or status codes and were truncated at 200 spans, so slow spans cannot be pinned to 15:13–15:36 or tied to errored requests; and both log queries elided their middles, including the whole 15:13–15:35 stretch, so the onset moment was never directly observed.

> Evidence `tr_e24f457d6c26`:

```
<tool_result id="tr_e24f457d6c26" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-07T14:05:30.583000+00:00..2026-09-07T15:37:22.501228+00:00">
service: cartservice
200 spans
  eae6009838d80fcb frontend/HTTP GET 307.4ms
  eae6009838d80fcb frontend/grpc.hipstershop.CartService/GetCart 306.3ms
  eae6009838d80fcb cartservice/hipstershop.CartService/GetCart 303.0ms
```

> Evidence `tr_2a3bfbd2d91d`:

```
<tool_result id="tr_2a3bfbd2d91d" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T15:05:30.583000+00:00..2026-09-07T15:37:22.501228+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-07T15:05:47.959824+00:00  {"message":"[PlaceOrder] user_id=\"9b7fb17c-aacd-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-07T15:05:47.959723388Z"}
2026-09-07T15:05:47.976571+00:00  {"message":"payment went through (transaction_id: 8fc6aa3a-159b-4999-ad08-6ca4ddb15236)","severity":"info","timestamp":"2026-09-07T15:05:47.976465638Z"}
2026-09-07T15:05:47.980924+00:00  {"message":"order confirmation email sent to \"jeff@example.com\"","severity":"info","timestamp":"2026-09-07T15:05:47.980836971Z"}
2026-09-07T15:05:47.981598+00:00  {"message":"Successful to write message. offset: 6704","severity":"info","timestamp":"2026-09-07T15:05:47.981509305Z"}
```

> Evidence `tr_adda4309014f`:

```
<tool_result id="tr_adda4309014f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-06T15:35:30.583000+00:00..2026-09-07T15:37:22.501228+00:00" radius="seed" hops="0">
service: cartservice
14 changes, ranked by suspicion
  #1  4.9h before onset  2026-09-07T10:39:55.043901+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  5.1h before onset  2026-09-07T10:31:47.493918+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

