# Checkout path failing at connection setup to the cart endpoint

## What we saw first

The page arrived pointed at the frontend: alerts on frontend, loadgenerator and checkoutservice, critical severity, a blast radius counted at twelve services. From the responder's chair this looked like an entry-point outage, and the first instinct was to treat frontend as the source.

That instinct was wrong, and it took most of the investigation to prove it. Frontend is the reporter. Nothing in its own behaviour turned out to be the story.

## The metric detour (T+3m to T+12m)

The first two substantive queries were error-ratio comparisons against the half hour preceding onset, one for frontend and one for checkoutservice. Both came back flat in the sense that matters: frontend moved from roughly 0.054 to 0.073 mean error ratio, about 1.36x, with no sustained departure flagged; checkoutservice moved from about 0.1125 to 0.1366, about 1.21x, also flagged as no sustained departure. In both series the standard deviation was on the order of the mean or twice it, and the maxima in the pre-onset window matched the maxima during the window. In other words the pre-onset period was not quiet, so it was a poor reference.

This was the first real dead end, and it cost time. The temptation was to read the flatness as "nothing is actually broken" or as "checkoutservice emits no error telemetry." Neither holds. The series were populated and live — 128 samples per window on the checkoutservice query — so the flat comparison reflects real data. What the flatness actually told us, in hindsight, is two things: the failure predates the window we chose as baseline, and it touches only a sub-path narrow enough to be swamped by aggregate traffic. Both queries aggregated by service name only, with no per-dependency dimension and no latency percentile, so they were structurally incapable of answering "which dependency turned first." If you are re-running this, break out by peer before you break out by time.

> Evidence `tr_d7e2241f381a`:

```
<tool_result id="tr_d7e2241f381a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" template="error-ratio" baseline="2026-09-07T05:04:00.717853+00:00..2026-09-07T05:35:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.07338 min=0 max=0.3265 sd=0.1185
  baseline window: n=128 mean=0.05395 min=0 max=0.3324 sd=0.112
```

> Evidence `tr_d3bf0de7c817`:

```
<tool_result id="tr_d3bf0de7c817" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" template="error-ratio" baseline="2026-09-07T05:04:00.717853+00:00..2026-09-07T05:35:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.1366 min=0 max=0.6667 sd=0.2547
  baseline window: n=128 mean=0.1125 min=0 max=0.6667 sd=0.2445
```

## The trace query that never ran (T+15m)

The obvious next move was span-level attribution on frontend requests. That query did not return an empty result — it failed outright, HTTP 503 from the trace backend. This is worth flagging clearly because it is easy to misread months later: a transport-level failure carries no information at all about whether error spans exist. Two hypotheses that briefly looked attractive here were both unsupported by this result: that traces existed and showed clean downstreams (implying a frontend-local problem), and that sampling had dropped the failing requests. Neither is evidenced; the query simply never completed.

The practical consequence was that the four unmeasured edges out of the checkout path — currencyservice, paymentservice, accountingservice — stayed unexaminable, and attribution had to come from logs. Note also that the query path itself being unhealthy is an observability-plane problem independent of the incident under investigation, and it should be tracked separately.

> Evidence `tr_f5a6ef9c0b22`:

```
<tool_result id="tr_f5a6ef9c0b22" tool="trace_query" trust="untrusted" source="jaeger" empty="true" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" error="HTTP Error 503: Service Unavailable">
query failed: HTTP Error 503: Service Unavailable
</tool_result:tr_f5a6ef9c0b22>
```

## The change-log queries, and why all three were useless

Three change-history queries were run: frontend, checkoutservice, productcatalogservice. All three returned nothing — no deploys, no config edits, no flag flips.

The honest reading is that these queries answered a question nobody asked. Every one of them started at the onset timestamp and ran forward roughly twenty-four hours. They therefore say nothing about the hours before onset, which is exactly the interval that matters. What they do legitimately rule out is post-onset activity: no frontend deploy re-triggered or prolonged anything, no rollback or remediation drove any observed recovery, no ongoing config churn explains intermittency, and the same for checkoutservice and productcatalogservice. The checkoutservice query was scoped at zero hops, so it says nothing about its dependencies either.

Keep this dead end visible. Three dispatches were spent, the windows were all mis-anchored the same way, and nobody caught it until the conclusion was being written.

> Evidence `tr_4db2c8ec3bc5`:

```
<tool_result id="tr_4db2c8ec3bc5" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-06T06:05:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_4db2c8ec3bc5>
```

> Evidence `tr_f8a264b7f48e`:

```
<tool_result id="tr_f8a264b7f48e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-06T06:05:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_f8a264b7f48e>
```

> Evidence `tr_3d861d8a754e`:

```
<tool_result id="tr_3d861d8a754e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-06T06:05:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_3d861d8a754e>
```

## The log query that settled it (T+28m)

A plain label query against frontend's logs produced the one decisive piece of evidence. The gRPC errors on the checkout path name the cart service as the failing downstream, and the wrapped inner error is a refused TCP connection when dialing a concrete internal address on port 7070. Two error shapes recur: an UNAVAILABLE raised in frontend's own gRPC client with no connection ever established, and an INTERNAL returned by the checkout dependency whose details carry the same connection-refused cause underneath.

The shape of the error does a lot of eliminating on its own. These are connection-establishment failures, not response-level ones, so there is no deadline-exceeded anywhere and no application-generated 5xx — the calls never got a served response. Name resolution and routing both worked, because the dial reached a specific IP and port, which rules out DNS or service-discovery problems. A silent network filter would present as hangs; an active refusal means packets arrived and nothing was listening. The stack traces originate in the outbound client library, not in frontend's own handlers, which is what demotes frontend from suspect to witness. And the error details attribute the checkout failure specifically to retrieving the user cart, not to payment, shipping or product catalog.

The pattern is present both near the beginning of the queried window and near its end, roughly thirty-two minutes apart, so this was not a blip.

> Evidence `tr_450ceffdcf69`:

```
<tool_result id="tr_450ceffdcf69" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-07T05:35:46.495124+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-07T05:35:46.495184+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-07T05:35:46.495192+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-07T05:35:46.495197+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Where it landed

Nothing was listening on the cart service endpoint across essentially the whole queried window. That is consistent with the cartservice process being down or crash-looping. Fix class is a restart. Confidence is medium, not high, and the reason is the next section.

This also retroactively explains the metric detour: the failure predates the window we chose as a baseline, so both windows contained it, and it touches only the checkout sub-path, so the aggregates stayed bursty and flat.

> Evidence `tr_450ceffdcf69`:

```
<tool_result id="tr_450ceffdcf69" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-07T05:35:46.495124+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-07T05:35:46.495184+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-07T05:35:46.495192+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-07T05:35:46.495197+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_d7e2241f381a`:

```
<tool_result id="tr_d7e2241f381a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" template="error-ratio" baseline="2026-09-07T05:04:00.717853+00:00..2026-09-07T05:35:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.07338 min=0 max=0.3265 sd=0.1185
  baseline window: n=128 mean=0.05395 min=0 max=0.3324 sd=0.112
```

> Evidence `tr_d3bf0de7c817`:

```
<tool_result id="tr_d3bf0de7c817" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" template="error-ratio" baseline="2026-09-07T05:04:00.717853+00:00..2026-09-07T05:35:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.1366 min=0 max=0.6667 sd=0.2547
  baseline window: n=128 mean=0.1125 min=0 max=0.6667 sd=0.2445
```

## Open, and what to do differently

cartservice itself was never queried. Not once. Every dispatch went to frontend, checkoutservice or productcatalogservice. Its logs, restart and OOMKill counts, readiness state and change history would settle the cause in a single dispatch, and that is the first thing to do on a repeat.

Second, no change-log query covered the pre-onset period. Re-run at least one with the window anchored well before onset.

Third, an unresolved tension: if the cart path is hard-failing throughout, why is frontend's error ratio only around 7% with a peak near 33%? Either only a small fraction of traffic reaches the checkout path, or cartservice is flapping rather than fully down. Distinguishing those two matters for how the failure is classified, and neither current evidence nor the unavailable trace backend can separate them.

> Evidence `tr_450ceffdcf69`:

```
<tool_result id="tr_450ceffdcf69" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-07T05:35:46.495124+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-07T05:35:46.495184+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-07T05:35:46.495192+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-07T05:35:46.495197+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_d7e2241f381a`:

```
<tool_result id="tr_d7e2241f381a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" template="error-ratio" baseline="2026-09-07T05:04:00.717853+00:00..2026-09-07T05:35:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.07338 min=0 max=0.3265 sd=0.1185
  baseline window: n=128 mean=0.05395 min=0 max=0.3324 sd=0.112
```

> Evidence `tr_f5a6ef9c0b22`:

```
<tool_result id="tr_f5a6ef9c0b22" tool="trace_query" trust="untrusted" source="jaeger" empty="true" truncated="false" window="2026-09-07T05:35:45.583000+00:00..2026-09-07T06:07:30.448147+00:00" error="HTTP Error 503: Service Unavailable">
query failed: HTTP Error 503: Service Unavailable
</tool_result:tr_f5a6ef9c0b22>
```

