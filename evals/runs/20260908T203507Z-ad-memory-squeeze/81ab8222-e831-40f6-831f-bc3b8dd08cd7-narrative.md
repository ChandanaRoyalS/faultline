# Frontend shipping-quote RPCs refused at the target address

## What the responder saw first

The page came from two places at once: frontend and loadgenerator. That pairing usually means user-visible errors rather than a background job, and it set the initial framing — something on the browse/checkout path was returning 5xx to synthetic traffic.

The first thing worth knowing is that this was never a total outage. Frontend's aggregate error ratio roughly doubled, from a mean near 1.8% to about 3.2%, with incident-window peaks around 12.8% against a baseline that already excursed to about 5.9%. The overwhelming majority of requests still succeeded. A single change point landed at roughly T+30s relative to the declared onset reference, crossing the detection threshold at about 8.7%. So: a real, sharp shift, but a partial one. Anyone arriving expecting a dead frontend will waste time.

> Evidence `tr_054d0c4b99b1`:

```
<tool_result id="tr_054d0c4b99b1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" template="error-ratio" baseline="2026-09-08T19:36:05.387393+00:00..2026-09-08T20:08:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.03167 min=0 max=0.1277 sd=0.03319
  baseline window: n=129 mean=0.01772 min=0 max=0.05859 sd=0.02246
```

## The log line that decided the investigation

Frontend's own logs carried the answer earlier than the metrics change point suggested. At the earliest kept point in the window frontend emitted a gRPC client error, status 13 INTERNAL, describing a shipping-quote failure, wrapping a transport-level Unavailable from dialing a peer at 172.18.0.7 port 50050 — connection refused.

Three details in that one line each closed a door. First, a concrete IP and port were being dialed, so name resolution had already succeeded; this was not a discovery or DNS problem. Second, the failure was at the TCP connect step, not a deadline expiry, so the downstream was not merely slow or overloaded. Third, every stack frame sat in the Node gRPC client library call path, meaning frontend was propagating a remote status rather than throwing from its own handler logic.

Later in the window the shape changed: bare status 14 UNAVAILABLE with a detail that no connection was established, arriving in rapid bursts several within the same second. Same underlying condition, less wrapping. Nothing in the kept lines shows recovery across roughly a 28-minute span.

No UNAUTHENTICATED, PERMISSION_DENIED, or certificate errors appeared anywhere, which rules out a TLS or authorization rejection. And because the codes are gRPC codes on frontend's outbound calls, the failure sits on the frontend→backend hop, not at an ingress or load balancer in front of frontend.

> Evidence `tr_bf4e2b4d888f`:

```
<tool_result id="tr_bf4e2b4d888f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-08T20:12:42.282121+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-08T20:12:42.282133+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-08T20:12:42.282134+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-08T20:12:42.282135+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Dead end: looking for the change

The obvious next move was the change log, and it produced nothing useful twice over.

The frontend query returned zero records of any kind — no deploys, no config edits, no flag flips, no dependency bumps. That legitimately eliminates an in-window frontend rollout, an in-window flag flip, and an in-window version bump as triggers, and it means a frontend rollback has no candidate target.

But the query had two limitations a later reader should not repeat. It was scoped to the seed service only, zero hops, so adservice, cartservice, checkoutservice, productcatalogservice and recommendationservice were simply not covered. More importantly, the window began at the onset reference and ran forward about 24 hours — it never looked backward. Any edit that landed before onset would be invisible to it, and that is precisely the class of edit this incident most plausibly involves.

A second query against checkoutservice plus its one-hop dependencies had the same forward-only window and also returned empty. That does rule out a concurrent deploy, a config edit, or a logged operator remediation on that path during the incident, and it means recovery or persistence cannot be attributed to any recorded intervention. It does not tell us what happened before.

> Evidence `tr_44b207d6043c`:

```
<tool_result id="tr_44b207d6043c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T20:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_44b207d6043c>
```

> Evidence `tr_a25b9fc77192`:

```
<tool_result id="tr_a25b9fc77192" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T20:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_a25b9fc77192>
```

## Dead end: checkoutservice and cartservice

With seven services in the blast radius it was reasonable to suspect the order path was broken. It was not.

checkoutservice logs across a roughly 62-minute window are entirely info-severity records of normal order flow — placement, payment, confirmation, downstream message write — completing successfully at both ends, including repeatedly through the final minute. No startup banners, no panics, no fatals, no restart markers. The message-write offsets advance monotonically by roughly 330 increments over the hour, which is what one continuously running process looks like, not a restart loop. Failed start, crash loop, unhandled panic, and total request rejection are all excluded.

One caveat worth recording: no bind or listen announcement appears in those lines, so the port checkoutservice actually listens on can be neither confirmed nor contradicted from this evidence. That gap matters given where the investigation landed.

cartservice was similarly healthy on logs — dense per-request handler entries at both window edges, the newest within seconds of window close, normal add/read/empty session shapes completing, no exceptions, timeouts, retries, or backend connection errors, no restart banners. It is not the origin of the user-visible errors.

The cartservice metrics query, however, was a genuine waste of a step. The error-ratio expression returned no samples at all — in the incident window and in the baseline window alike. The tempting reading, that cartservice went telemetry-dark at onset, is wrong: the baseline is equally empty, so the gap predates the incident and is an instrumentation or label-naming problem, not an onset symptom. Likewise, empty results are not the same as observed zero traffic; no flat-traffic conclusion can be drawn from a query that returned nothing. Nor did that query cover productcatalogservice, adservice, or recommendationservice, so the cross-service comparison it was meant to answer remains unanswered.

> Evidence `tr_f965864a3e76`:

```
<tool_result id="tr_f965864a3e76" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T19:38:15.754302+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-08T19:38:15.754145798Z"}
2026-09-08T19:38:15.756841+00:00  {"message":"Successful to write message. offset: 15765","severity":"info","timestamp":"2026-09-08T19:38:15.756709798Z"}
2026-09-08T19:38:19.604964+00:00  {"message":"[PlaceOrder] user_id=\"d69878f8-abbc-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T19:38:19.604729008Z"}
2026-09-08T19:38:19.954461+00:00  {"message":"payment went through (transaction_id: 20dc2821-617c-42ef-8501-0e4c1e88db37)","severity":"info","timestamp":"2026-09-08T19:38:19.954324883Z"}
```

> Evidence `tr_11494c4f1ae3`:

```
<tool_result id="tr_11494c4f1ae3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-08T20:08:17.383519+00:00  GetCartAsync called with userId=
2026-09-08T20:08:17.724531+00:00  AddItemAsync called with userId=08081bf6-abc1-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=10
2026-09-08T20:08:17.727152+00:00  GetCartAsync called with userId=08081bf6-abc1-11f1-b359-b6ed2071a170
2026-09-08T20:08:17.742492+00:00  AddItemAsync called with userId=08081bf6-abc1-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=5
```

> Evidence `tr_4262b1cb6929`:

```
<tool_result id="tr_4262b1cb6929" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" template="error-ratio" baseline="2026-09-08T19:36:05.387393+00:00..2026-09-08T20:08:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where it landed

The reading that survives all of the above: frontend is dialing the shipping-quote endpoint at an address where nothing is listening. Resolution works, the connect is refused, and the error is faithfully relayed up through frontend's client stack. Meanwhile the wider order path is intact — checkoutservice completes end-to-end orders through the last minute observed, cartservice serves normally — which is consistent with only frontend's leg of the call being misaddressed and with the error ratio rising only to about 12.8% rather than to totality.

The most likely cause is that the configured shipping-quote endpoint address or port frontend uses points at the wrong target. The wrong value is itself the failure; there is no separate broken component to find. Fix class is a config revert of that endpoint setting.

Confidence is medium, deliberately. Two things were never established.

> Evidence `tr_bf4e2b4d888f`:

```
<tool_result id="tr_bf4e2b4d888f" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-08T20:12:42.282121+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.7:50050: connect: connection refused"
2026-09-08T20:12:42.282133+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-08T20:12:42.282134+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-08T20:12:42.282135+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_f965864a3e76`:

```
<tool_result id="tr_f965864a3e76" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T19:38:15.754302+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-08T19:38:15.754145798Z"}
2026-09-08T19:38:15.756841+00:00  {"message":"Successful to write message. offset: 15765","severity":"info","timestamp":"2026-09-08T19:38:15.756709798Z"}
2026-09-08T19:38:19.604964+00:00  {"message":"[PlaceOrder] user_id=\"d69878f8-abbc-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T19:38:19.604729008Z"}
2026-09-08T19:38:19.954461+00:00  {"message":"payment went through (transaction_id: 20dc2821-617c-42ef-8501-0e4c1e88db37)","severity":"info","timestamp":"2026-09-08T19:38:19.954324883Z"}
```

> Evidence `tr_11494c4f1ae3`:

```
<tool_result id="tr_11494c4f1ae3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-08T20:08:17.383519+00:00  GetCartAsync called with userId=
2026-09-08T20:08:17.724531+00:00  AddItemAsync called with userId=08081bf6-abc1-11f1-b359-b6ed2071a170, productId=0PUK6V6EV0, quantity=10
2026-09-08T20:08:17.727152+00:00  GetCartAsync called with userId=08081bf6-abc1-11f1-b359-b6ed2071a170
2026-09-08T20:08:17.742492+00:00  AddItemAsync called with userId=08081bf6-abc1-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=5
```

> Evidence `tr_054d0c4b99b1`:

```
<tool_result id="tr_054d0c4b99b1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" template="error-ratio" baseline="2026-09-08T19:36:05.387393+00:00..2026-09-08T20:08:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.03167 min=0 max=0.1277 sd=0.03319
  baseline window: n=129 mean=0.01772 min=0 max=0.05859 sd=0.02246
```

## Open questions for the next responder

First, the edit itself was never observed. Every change query ran forward from onset; nothing covered the hours before it. Re-run the change history with a window that starts well before onset and with a radius of at least one hop, and look specifically for an endpoint or port value on frontend's shipping-quote configuration.

Second, the shipping-quote service was never dispatched on directly. Its process state, the port it actually binds, and whether checkoutservice reaches it successfully on some different address are all unverified. If checkoutservice is calling the same backend and succeeding, that would confirm the address-mismatch reading outright; the absence of a bind announcement in checkoutservice's logs is why this was not settled here.

Third, two instrumentation gaps limited the investigation and should be fixed independently of this incident: cartservice has no usable call-count series under the queried label scheme, and frontend's error metrics carry only a service-level aggregation with no per-route or per-dependency breakdown and no latency series. Had frontend metrics been broken out by downstream, the shipping-quote leg would have been identifiable from metrics alone in the first minute.

> Evidence `tr_44b207d6043c`:

```
<tool_result id="tr_44b207d6043c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T20:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_44b207d6043c>
```

> Evidence `tr_a25b9fc77192`:

```
<tool_result id="tr_a25b9fc77192" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T20:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_a25b9fc77192>
```

> Evidence `tr_4262b1cb6929`:

```
<tool_result id="tr_4262b1cb6929" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" template="error-ratio" baseline="2026-09-08T19:36:05.387393+00:00..2026-09-08T20:08:15.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_054d0c4b99b1`:

```
<tool_result id="tr_054d0c4b99b1" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T20:08:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" template="error-ratio" baseline="2026-09-08T19:36:05.387393+00:00..2026-09-08T20:08:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.03167 min=0 max=0.1277 sd=0.03319
  baseline window: n=129 mean=0.01772 min=0 max=0.05859 sd=0.02246
```

> Evidence `tr_f965864a3e76`:

```
<tool_result id="tr_f965864a3e76" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T19:38:15.583000+00:00..2026-09-08T20:40:25.778607+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T19:38:15.754302+00:00  {"message":"order confirmation email sent to \"steve@example.com\"","severity":"info","timestamp":"2026-09-08T19:38:15.754145798Z"}
2026-09-08T19:38:15.756841+00:00  {"message":"Successful to write message. offset: 15765","severity":"info","timestamp":"2026-09-08T19:38:15.756709798Z"}
2026-09-08T19:38:19.604964+00:00  {"message":"[PlaceOrder] user_id=\"d69878f8-abbc-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T19:38:19.604729008Z"}
2026-09-08T19:38:19.954461+00:00  {"message":"payment went through (transaction_id: 20dc2821-617c-42ef-8501-0e4c1e88db37)","severity":"info","timestamp":"2026-09-08T19:38:19.954324883Z"}
```

