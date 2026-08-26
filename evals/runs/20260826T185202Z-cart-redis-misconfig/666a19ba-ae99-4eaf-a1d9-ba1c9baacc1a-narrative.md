# Cart backing-store endpoint mismatch takes down every cart-touching request

## What was visible, in order

Frontend, loadgenerator and checkoutservice alerted together; the responder started at frontend. It was not a total outage — frontend's error ratio peaked near 30% and touched zero somewhere in the window, while checkoutservice peaked near 67%. Both metric results were min/max/count summaries with no per-timestamp values, so no onset curve was ever available; every timing claim here rests on logs and traces.

Frontend's error lines were monotonous and decisive: gRPC status code 14 UNAVAILABLE with a connection-not-established detail, every stack frame from the gRPC client library rather than frontend code. That rules out a slow-but-reachable downstream (no code 4 or 8 anywhere) and rules out an upstream answering 5xx. The transport never came up. But no line named a target host or method, and the result was truncated to the oldest 8 and newest 32 lines. The signature appears at roughly T-7m and again through the end of the window.

Traces supplied the name. Every errored path bottomed out at a CartService span — frontend's AddItem and GetCart, and checkoutservice's PlaceOrder inheriting its error from its own CartService/GetCart child. Two independent callers, one dependency. The errored spans were the fastest in the sample (~0.2–0.6ms), so this was fast-failing, not latency. Reads and writes both failed; catalog-only page loads succeeded, which plausibly explains the 30%/67% split, though traffic mix was never quantified.

> Evidence `tr_b8f9790f446f`:

```
<tool_result id="tr_b8f9790f446f" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.3023 n=60
</tool_result:tr_b8f9790f446f>
```

> Evidence `tr_b835f5876277`:

```
<tool_result id="tr_b835f5876277" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.6667 n=61
</tool_result:tr_b835f5876277>
```

> Evidence `tr_d4562c893caf`:

```
<tool_result id="tr_d4562c893caf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-08-26T18:44:52.889643+00:00  Error: 14 UNAVAILABLE: No connection established
2026-08-26T18:44:52.889692+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-08-26T18:44:52.889716+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-08-26T18:44:52.889718+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_3ac06548a0e2`:

```
<tool_result id="tr_3ac06548a0e2" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
service: frontend
200 spans
  3d77ab40090892f1 frontend/HTTP GET 1.0ms
  3d77ab40090892f1 frontend/grpc.hipstershop.ProductCatalogService/GetProduct 0.8ms
  3d77ab40090892f1 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

## Dead ends worth keeping

productcatalogservice was clean on both axes — sub-2ms error-free spans inside the very traces whose sibling cart calls failed, and an empty change history. recommendationservice was the largest downstream contributor to successful traces (3.7–11.8ms), which makes it look interesting on a flame graph; it never carried an error status and appeared only in successful traces. A red herring from reading duration instead of status. checkoutservice was a victim: its own order-preparation work completed clean and PlaceOrder inherited the error from below.

checkoutservice logs were genuinely misleading — not one non-info line, no gRPC codes, no named upstream. Early lines show the full four-step order sequence (accepted, payment, email, message write); late lines show only the accepted line, orders entering and stalling, several per minute, with the middle ~10 minutes truncated away. Attribution was simply unavailable from this service.

Change logs for frontend, checkoutservice and productcatalogservice all returned empty — no deploys, config edits, flag flips or rollbacks. All three queries ran from 18:44:45 onward, so the earlier interval was never examined for any service. cartservice metrics were queried twice as a span error ratio and returned no series at all; because the total-calls denominator was also unmatched, this was not 'zero errors' but 'no telemetry'. That absence was first read as a dead end and was actually a finding. Neither query touched process-level series.

> Evidence `tr_5412c29111b0`:

```
<tool_result id="tr_5412c29111b0" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_5412c29111b0>
```

> Evidence `tr_24583f3db529`:

```
<tool_result id="tr_24583f3db529" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-08-26T18:44:53.782204+00:00  {"message":"[PlaceOrder] user_id=\"3a1021e0-a17e-11f1-86d7-1e4ac5f08d0c\" user_currency=\"USD\"","severity":"info","timestamp":"2026-08-26T18:44:53.782102094Z"}
2026-08-26T18:44:53.798774+00:00  {"message":"payment went through (transaction_id: 19b16d6b-f051-48cc-8607-320545fb4021)","severity":"info","timestamp":"2026-08-26T18:44:53.798691261Z"}
2026-08-26T18:44:53.802982+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-08-26T18:44:53.802908927Z"}
2026-08-26T18:44:53.803829+00:00  {"message":"Successful to write message. offset: 12523","severity":"info","timestamp":"2026-08-26T18:44:53.803743802Z"}
```

> Evidence `tr_cd5057513981`:

```
<tool_result id="tr_cd5057513981" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_cd5057513981>
```

> Evidence `tr_e6243d067b7e`:

```
<tool_result id="tr_e6243d067b7e" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))' over this window
</tool_result:tr_e6243d067b7e>
```

## The cause, and what is still open

cartservice was serving normal cart traffic at ~T-8m. From ~T+5m to the end of the window it is in a startup crash loop: an outbound connection attempt to the Redis cart store, a 20–30 second hang, then an unhandled exception thrown from the store's connection-assurance and initialization path invoked directly from Main. The process dies before serving anything; a supervisor restarts it every 30–60 seconds. The target named in the attempt lines is redis-cart on port 6380, abortConnect off, TLS off. That explains the missing metrics, the code 14s, and checkout's silence. It is not a listener bind conflict, not a per-request bug, and not instant name-resolution failure — 20–30 seconds is timeout-shaped.

Exactly one change is recorded for cartservice: at T+0, platform-automation rewrote the Redis endpoint variable to redis-cart:6380. Not a deploy, not a flag flip, no competing changes. 6380 is not the conventional Redis port. Fix class is a configuration correction.

Open items, weakest first. Timing does not fully line up: frontend showed the identical code-14 signature at ~T-7m, before the change, and the change record explicitly cannot account for earlier symptoms — either something exists in the unqueried earlier interval or a separate cart failure preceded the loop. cartservice logs are truncated across the transition, so the moment it stopped serving is unestablished. Nobody queried Redis directly: if the store was intentionally moved to 6380 and is itself down, the fix belongs to the store, not the env var. The prior value of the variable is recorded as absent, so a literal revert has no target — the correct value must come from manifests or convention. And the blast radius named twelve services while four were investigated; whether other services share this endpoint configuration was never checked.

> Evidence `tr_86887693af88`:

```
<tool_result id="tr_86887693af88" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-08-26T18:44:45.958372+00:00  AddItemAsync called with userId=356a4558-a17e-11f1-86d7-1e4ac5f08d0c, productId=66VCHSJNUP, quantity=1
2026-08-26T18:44:45.960771+00:00  GetCartAsync called with userId=356a4558-a17e-11f1-86d7-1e4ac5f08d0c
2026-08-26T18:44:51.781467+00:00  GetCartAsync called with userId=
2026-08-26T18:44:51.877780+00:00  GetCartAsync called with userId=
```

> Evidence `tr_85fed96453d7`:

```
<tool_result id="tr_85fed96453d7" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T18:44:45.583000+00:00..2026-08-26T18:59:45.583000+00:00">
service: cartservice
1 changes
  2026-08-26T18:52:03.528328+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_85fed96453d7>
```
