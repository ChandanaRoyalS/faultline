# Frontend user-facing failures traced to an unreachable adservice

## What was visible, in order

The page came from frontend and loadgenerator simultaneously, seven services in the blast radius, severity critical. No downstream was named, so the early work was guesswork about which edge out of frontend had broken.

Frontend's aggregate error ratio was checked first and actively misled: it averaged about 0.6 percent during the window against a 5.4 percent baseline in the prior hour, with variability also falling. Read naively the service looked healthier during the incident. It carried no per-dependency or per-endpoint breakdown, so it could not point anywhere. Do not let this metric talk you out of the incident — a service-level ratio can fall while one edge fails completely, because that path is a small share of call volume.

Frontend logs gave the first real signal: repeated Node.js gRPC client errors, status 14 UNAVAILABLE, detail indicating no connection could be established, raised in the @grpc/grpc-js receive-status path with empty response metadata. That is a client never reaching a server. It ruled out local business-logic errors, a slow-but-alive peer (code 14, not DEADLINE_EXCEEDED), auth/TLS/quota rejections, and frontend itself being down — it logged continuously throughout. What the logs never gave was a target: no service name, host, port, or method.

> Evidence `tr_53ecba761e7a`:

```
<tool_result id="tr_53ecba761e7a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-04T07:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" template="error-ratio" baseline="2026-09-04T06:48:03.973282+00:00..2026-09-04T07:50:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=248 mean=0.005981 min=0 max=0.09583 sd=0.02012
  baseline window: n=248 mean=0.05388 min=0 max=0.3641 sd=0.09675
```

> Evidence `tr_f63a4744e746`:

```
<tool_result id="tr_f63a4744e746" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-04T07:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-04T08:46:49.941594+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-04T08:46:49.941627+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-04T08:46:49.941628+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-04T08:46:49.941629+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## The dead ends

With no target named, productcatalogservice was picked as the plausible downstream and cost three dispatches, all of them empty in different ways.

Its traced error ratio was identically zero across 248 samples in the window and identically zero in the baseline, with a defined denominator throughout — so it was emitting spans, not silent. Note the ambiguity: flat zero is equally consistent with a healthy service and with error status never being recorded on its spans. Its change history returned nothing at all, but the window queried starts at 08:50 and runs forward, so it never covers the hours before onset. Its log query returned zero lines, total rather than selective absence, and the selector used a hyphenated name that does not match the service identifier in scope. Treat that log result as unusable rather than as evidence.

Frontend's own change history was likewise empty — no deploy, config edit, or flag flip registered, and none in the following 24 hours — with the same window caveat that it does not reach back before onset.

> Evidence `tr_6e861adb861e`:

```
<tool_result id="tr_6e861adb861e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-04T07:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" template="error-ratio" baseline="2026-09-04T06:48:03.973282+00:00..2026-09-04T07:50:00.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=248 mean=0 min=0 max=0 sd=0
  baseline window: n=248 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_d1ce6822c2ac`:

```
<tool_result id="tr_d1ce6822c2ac" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-03T08:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_d1ce6822c2ac>
```

> Evidence `tr_105258a8909e`:

```
<tool_result id="tr_105258a8909e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-03T08:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_105258a8909e>
```

## What broke it open, and what is still open

Widening the trace query back to 07:20 resolved it. Every erroring trace shows a frontend client span for AdService/GetAds ending in error at roughly 2.0 to 3.1 seconds with no adservice server span anywhere in the trace; in two of three, a child frontend tcp.connect span itself errors after about 3.08 seconds. The error propagates to the frontend HTTP parent and out to loadgenerator with matching durations. The same sample cleared every competing edge in one pass: productcatalogservice, cartservice with its Redis children, recommendationservice, and the full checkoutservice fan-out all show paired server spans and no errors. A saturated-but-reachable adservice does not fit, since that would still emit a server span; a trace-collection gap does not fit, since the errors are explicit and reach the user.

Conclusion: adservice is not accepting gRPC connections; frontend's GetAds calls hang at connect and fail with status 14, surfacing as user-facing failures. Confidence medium, indicated action a restart of adservice.

Still open. First, adservice itself was never investigated — logs, restart counts, saturation, change history all unexamined, so the mechanism is inferred entirely from the client side; start there. Second, onset is unpinned: frontend lines within the selector begin only around 08:46:49 and change windows start at 08:50. Third, why frontend's error ratio fell to a ninth of the prior hour is unexplained — sampling, traffic mix, or a distinct earlier problem before 07:50.

> Evidence `tr_767b14a37402`:

```
<tool_result id="tr_767b14a37402" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-04T07:20:00.583000+00:00..2026-09-04T08:51:57.192718+00:00">
service: frontend
200 spans
  5ebcb77b843bd346 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
  f0bc403e51dcae22 loadgenerator/HTTP GET 14.1ms
  f0bc403e51dcae22 loadgenerator/HTTP GET 13.1ms
```

> Evidence `tr_f63a4744e746`:

```
<tool_result id="tr_f63a4744e746" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-04T07:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-04T08:46:49.941594+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-04T08:46:49.941627+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-04T08:46:49.941628+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-04T08:46:49.941629+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_53ecba761e7a`:

```
<tool_result id="tr_53ecba761e7a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-04T07:50:00.583000+00:00..2026-09-04T08:51:57.192718+00:00" template="error-ratio" baseline="2026-09-04T06:48:03.973282+00:00..2026-09-04T07:50:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=248 mean=0.005981 min=0 max=0.09583 sd=0.02012
  baseline window: n=248 mean=0.05388 min=0 max=0.3641 sd=0.09675
```

