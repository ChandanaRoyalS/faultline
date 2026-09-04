# Checkout failures traced to a refused cart backend connection

## What was visible, and in what order

T+0 is the earliest change point in the error-ratio series; the page did not arrive until roughly T+37m, so the first half hour is reconstruction. The page named frontend, loadgenerator and checkoutservice, and the instinct was to look for something that landed just before it. The metrics contradicted that immediately: frontend's error ratio ran about 4x its prior level (roughly 1.7% to 7.0%, peaks near 34%) and checkoutservice about 3.5x, both with a change point at T+0. The crossing near the page time is a recurrence, not an onset. Two other things the metrics settled early: the majority of requests kept succeeding, so this was never a hard outage; and the pre-onset baseline already contained excursions of the same peak height, so what changed was frequency, not severity. Frontend logs then showed a single repeating signature across the whole window — gRPC status 14 UNAVAILABLE with a detail stating no connection was established, surfaced through the client status path with empty metadata. Connect-time refusal, not an application error, not a deadline against a slow-but-reachable peer, not auth or TLS. What the logs would not give up was the target: no peer name, host:port, method or path appears in any line.

> Evidence `tr_e3eed71e136f`:

```
<tool_result id="tr_e3eed71e136f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-04T08:47:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" template="error-ratio" baseline="2026-09-04T07:45:25.952953+00:00..2026-09-04T08:47:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=249 mean=0.06964 min=0 max=0.3406 sd=0.1072
  baseline window: n=249 mean=0.01745 min=0 max=0.2775 sd=0.06067
```

> Evidence `tr_740bc3210ab8`:

```
<tool_result id="tr_740bc3210ab8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-04T08:47:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" template="error-ratio" baseline="2026-09-04T07:45:25.952953+00:00..2026-09-04T08:47:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=247 mean=0.115 min=0 max=0.6667 sd=0.244
  baseline window: n=249 mean=0.03314 min=0 max=0.6667 sd=0.1366
```

> Evidence `tr_4e849cc9d524`:

```
<tool_result id="tr_4e849cc9d524" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-04T09:17:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-04T09:17:31.405356+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-04T09:17:31.405404+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-04T09:17:31.405407+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-04T09:17:31.405408+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## The trace that carried it, and the one that did not

The obvious next move was to read the failing peer off frontend's spans. That query never ran — the tracing backend returned a 503. This was a transport failure of the query, not an empty match, so it says nothing about whether frontend spans exist or were clean. The consequence is real: frontend's other downstream edges were never examined, and some share of the UNAVAILABLE lines may point elsewhere. Traces scoped to checkoutservice did succeed. Roughly forty traces, two hundred spans, all identical in shape: frontend HTTP POST, frontend gRPC PlaceOrder, checkoutservice PlaceOrder, prepareOrderItemsAndShippingQuoteFromCart, then hipstershop.CartService/GetCart. GetCart is the deepest span reached, marked ERROR, with the error propagating up through checkoutservice and both frontend spans. Nothing beyond it is ever entered. Durations rule out a hang: GetCart completes in 0.3–2.5ms, the whole root in 1.3–10.7ms. The parent span carries no error of its own — the break is at the dependency boundary, not in checkout's preparation logic. Everything downstream of the cart lookup is therefore untested; do not read the silence of payment, shipping or catalog spans as health. checkoutservice's own logs agree it is a relay victim: steady info-level PlaceOrder entries through the tail, no errors or warnings, though per-order completion lines vanish from about T+35m.

> Evidence `tr_1bce9211df57`:

```
<tool_result id="tr_1bce9211df57" tool="trace_query" trust="untrusted" source="jaeger" empty="true" truncated="false" window="2026-09-04T08:17:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" error="HTTP Error 503: Service Unavailable">
query failed: HTTP Error 503: Service Unavailable
</tool_result:tr_1bce9211df57>
```

> Evidence `tr_6a2d28774230`:

```
<tool_result id="tr_6a2d28774230" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-04T09:17:30.583000+00:00..2026-09-04T09:49:35.213047+00:00">
service: checkoutservice
200 spans
  3732554fd0cf8fac frontend/HTTP POST 2.0ms ERROR
  3732554fd0cf8fac frontend/grpc.hipstershop.CheckoutService/PlaceOrder 1.8ms ERROR
  3732554fd0cf8fac checkoutservice/hipstershop.CheckoutService/PlaceOrder 0.8ms ERROR
```

> Evidence `tr_27a1865a306a`:

```
<tool_result id="tr_27a1865a306a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-04T09:17:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-04T09:17:31.413816+00:00  {"message":"[PlaceOrder] user_id=\"74f51300-a841-11f1-ae7b-9eef0fcf8acb\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-09-04T09:17:31.413617597Z"}
2026-09-04T09:17:31.436625+00:00  {"message":"payment went through (transaction_id: cf40ec79-9a75-4e12-8296-f7b0985149d9)","severity":"info","timestamp":"2026-09-04T09:17:31.436537347Z"}
2026-09-04T09:17:31.443319+00:00  {"message":"failed to send order confirmation to \"tobias@example.com\": failed POST to email service: expected 200, got 500","severity":"warning","timestamp":"2026-09-04T09:17:31.443256222Z"}
2026-09-04T09:17:31.444221+00:00  {"message":"Successful to write message. offset: 18783","severity":"info","timestamp":"2026-09-04T09:17:31.444150597Z"}
```

## Dead ends, conclusion, and what remains open

Email-service 500s appear near T+7m in checkoutservice's logs and are tempting, but those orders completed payment and message write, and the warnings are absent from the entire later tail. Noise. Change history for frontend and for checkoutservice both came back completely empty, which retires the bad-release, quiet-rollback and flag-flip stories for those two services and also means there is nothing to roll back on checkout. But note the defect in the frontend check: its window began at the page timestamp and ran forward a day, so it does not cover the hours before onset at all. The framing error — assuming the disturbance began at the page — is what cost that coverage, and it was the most expensive dead end of the walk. Conclusion: a sustained, fractional, connect-time refusal from one backend is most consistent with cartservice, or the cart store behind it, being unable to accept new connections. Remedy class is a restart of that component. Confidence is low, for a blunt reason: no dispatch ever queried cartservice. Its logs, metrics, restart history and change record are entirely unobserved, so the mechanism is inferred from the refusal pattern rather than measured. A pre-onset change on the cart path also remains possible and unchecked.

> Evidence `tr_27a1865a306a`:

```
<tool_result id="tr_27a1865a306a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-04T09:17:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-04T09:17:31.413816+00:00  {"message":"[PlaceOrder] user_id=\"74f51300-a841-11f1-ae7b-9eef0fcf8acb\" user_currency=\"CAD\"","severity":"info","timestamp":"2026-09-04T09:17:31.413617597Z"}
2026-09-04T09:17:31.436625+00:00  {"message":"payment went through (transaction_id: cf40ec79-9a75-4e12-8296-f7b0985149d9)","severity":"info","timestamp":"2026-09-04T09:17:31.436537347Z"}
2026-09-04T09:17:31.443319+00:00  {"message":"failed to send order confirmation to \"tobias@example.com\": failed POST to email service: expected 200, got 500","severity":"warning","timestamp":"2026-09-04T09:17:31.443256222Z"}
2026-09-04T09:17:31.444221+00:00  {"message":"Successful to write message. offset: 18783","severity":"info","timestamp":"2026-09-04T09:17:31.444150597Z"}
```

> Evidence `tr_87bb27270cc6`:

```
<tool_result id="tr_87bb27270cc6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-03T09:47:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_87bb27270cc6>
```

> Evidence `tr_679c97b448f4`:

```
<tool_result id="tr_679c97b448f4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-03T09:47:30.583000+00:00..2026-09-04T09:49:35.213047+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_679c97b448f4>
```

