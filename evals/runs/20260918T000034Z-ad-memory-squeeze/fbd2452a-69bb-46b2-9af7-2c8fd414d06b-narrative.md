# Frontend outbound gRPC calls failing at name resolution

## What was visible first

The page arrived from frontend and loadgenerator together, scored critical across seven services with frontend as the entry point. The obvious first move was unhelpful: frontend's error ratio over the incident window was statistically indistinguishable from baseline - same sample count, mean slightly lower, overlapping spread, no sustained departure. That did useful negative work, excluding a crash-loop, a 5xx-producing rollout, and an upstream returning errors, since any of those would have lifted the error share. Continuous scraping also ruled out a missing-data artifact. Change history came back empty for frontend and for checkoutservice plus its one-hop dependencies - no deploy, config edit, or flag flip on record. Keep in mind both change queries started at onset and ran forward, never covering the hours before it; a change that landed earlier would be invisible to both.

> Evidence `tr_07cac1a6f03b`:

```
<tool_result id="tr_07cac1a6f03b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" template="error-ratio" baseline="2026-09-17T23:02:16.243517+00:00..2026-09-17T23:34:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02081 min=0 max=0.08201 sd=0.02682
  baseline window: n=128 mean=0.02477 min=0 max=0.07143 sd=0.02463
```

> Evidence `tr_0d596a098a6e`:

```
<tool_result id="tr_0d596a098a6e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-17T00:04:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_0d596a098a6e>
```

> Evidence `tr_b32f5f48a50c`:

```
<tool_result id="tr_b32f5f48a50c" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-17T00:04:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_b32f5f48a50c>
```

## Dead ends worth keeping

With errors flat, the theory became latency, and the traces produced a detailed answer that turned out not to matter. In the one checkout trace the cost sat in shipping-quote preparation out to quoteservice; GET traces accumulated in ListRecommendations. Productcatalog, currency, cart, payment, redis, email, frauddetection and accounting were all eliminated as sub-millisecond or trivially small, and frontend was not CPU-bound in its own handler. The checkoutservice edge, assumed uninstrumented, was in fact fully measured - so the unmeasured edge we crossed was not there. Two facts should have stopped this line sooner: the largest root was 35ms, not an incident-shaped population, and every sampled trace clustered in a nine-second band at the window's end with no coverage of onset. The one real hint was that the only ERROR spans were in the fastest trace returned, under a millisecond - errors here were fast, not slow. Separately, adservice and shippingservice error-ratio queries returned zero samples. The tempting read is that they dropped out at onset; the equally empty pre-onset baselines kill that - the gap is a standing instrumentation condition. Checkoutservice did return a series and was quiet, its only change point sitting hours before onset at a value already present in baseline.

> Evidence `tr_75360b5c1870`:

```
<tool_result id="tr_75360b5c1870" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00">
service: frontend
10 trace(s) shown of 10 found, 102 spans; offsets are from each trace's root

trace 2b4f4f2ff0fb5204  root frontend/HTTP GET  0.7ms  started 2026-09-18T00:06:05.293031+00:00  2 spans
  +0.0ms frontend/HTTP GET 0.7ms [self 0.2ms]  ERROR
```

> Evidence `tr_b44efcb05064`:

```
<tool_result id="tr_b44efcb05064" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" template="error-ratio" baseline="2026-09-17T23:02:16.243517+00:00..2026-09-17T23:34:15.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_51c9e78c8228`:

```
<tool_result id="tr_51c9e78c8228" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" template="error-ratio" baseline="2026-09-17T23:02:16.243517+00:00..2026-09-17T23:34:15.583000+00:00">
service: shippingservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="shippingservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="shippingservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_47b03673f532`:

```
<tool_result id="tr_47b03673f532" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T21:04:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" template="error-ratio" baseline="2026-09-17T18:02:16.243517+00:00..2026-09-17T21:04:15.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=728 mean=0.06047 min=0 max=0.6667 sd=0.1449
  baseline window: n=728 mean=0.06828 min=0 max=0.6667 sd=0.1631
```

## What broke, and what is still open

The logs answered it. Frontend's outbound gRPC calls were failing at DNS name resolution before any connection was established: code 14 UNAVAILABLE naming a resolution failure for the adservice target on 9555, and at the window's oldest kept line a code 13 wrapping an Unavailable dial error for a shipping-quote call, failing lookup against the container resolver at 127.0.0.11:53. Two distinct targets, the same pre-connect mode, points at the name-resolution layer frontend depends on rather than either backend's process health - the client never reached an address, so a down or handshake-rejecting adservice does not fit, and a single-dependency story does not cover two targets. Stack frames sat entirely in the grpc-js client path, not frontend business logic. No deadline-exceeded lines anywhere, which closes the latency theory and matches that sub-millisecond error trace. We classed this as a configuration problem - the target resolved is not resolvable - with a config revert as the fix, at low confidence. Open: we never tested whether this is a wrong target value in frontend's config or a problem in cluster DNS itself, since no resolver or registry evidence was gathered; the resolution errors predate the alert, so whether they are background noise or the alerting condition is unresolved; nothing covers the onset minute, as the log result dropped everything between its oldest and newest lines; and no latency series was ever returned for any service, so what the frontend alert actually fired on remains unestablished.

> Evidence `tr_eeb5c79271e6`:

```
<tool_result id="tr_eeb5c79271e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T23:34:16.018354+00:00  Error: 13 INTERNAL: shipping quote failure: failed to get shipping quote: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp: lookup shippingservice on 127.0.0.11:53: no such host"
2026-09-17T23:34:16.018366+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T23:34:16.018367+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T23:34:16.018368+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_75360b5c1870`:

```
<tool_result id="tr_75360b5c1870" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00">
service: frontend
10 trace(s) shown of 10 found, 102 spans; offsets are from each trace's root

trace 2b4f4f2ff0fb5204  root frontend/HTTP GET  0.7ms  started 2026-09-18T00:06:05.293031+00:00  2 spans
  +0.0ms frontend/HTTP GET 0.7ms [self 0.2ms]  ERROR
```

> Evidence `tr_07cac1a6f03b`:

```
<tool_result id="tr_07cac1a6f03b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T23:34:15.583000+00:00..2026-09-18T00:06:14.922483+00:00" template="error-ratio" baseline="2026-09-17T23:02:16.243517+00:00..2026-09-17T23:34:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02081 min=0 max=0.08201 sd=0.02682
  baseline window: n=128 mean=0.02477 min=0 max=0.07143 sd=0.02463
```

