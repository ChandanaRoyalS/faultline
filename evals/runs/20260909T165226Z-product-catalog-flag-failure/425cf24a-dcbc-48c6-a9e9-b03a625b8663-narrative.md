# Partial catalog rejections behind a critical frontend alert

## What we saw, and the dead ends

The page arrived critical, blast radius seven services, entry point the frontend, with loadgenerator, frontend and productcatalogservice alerting together. One edge in the traversal was crossed unmeasured, so this is not a complete graph walk.

The first instinct — read frontend's aggregate error ratio and attribute it downstream — was a dead end and an actively misleading one. Frontend's error ratio in the window averaged about 1%, roughly a fifth of the preceding baseline, with a lower peak and no sustained departure flagged. Read literally it says frontend is healthier than usual. It is aggregated by service name only, with no per-peer breakdown, so it has no resolution for the question being asked. Do not use it to rule a dependency in or out.

Change history produced two more dead ends. Frontend's change log over the covering 24 hours was entirely empty — no rollouts, config edits, or scaling — which closed frontend rollback as a remediation path, since there is no rollback target. The catalog service's log held exactly two entries, both from platform-automation, both about a traffic-shaping container on the service's network namespace: created at 06:00:32Z applying a fixed 300ms egress delay, removed at 06:09:03Z. That looked promising until the arithmetic: about 10.8 hours before onset, active for roughly eight and a half minutes, not in effect when symptoms began. Recorded here precisely because it is the kind of entry that invites a responder to stop reading. What the catalog log did *not* contain — any deploy, version rollout, config edit, or flag change — was never reconciled with what the logs later showed.

A query for the catalog service's own logs returned zero lines across the full 32 minutes, not even routine output, and was explicitly empty rather than truncated. The selector used a hyphenated label value while the service is named without hyphens. It was never re-run corrected, so the service's own account is missing from this record.

> Evidence `tr_8241f2698d4b`:

```
<tool_result id="tr_8241f2698d4b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T16:25:15.583000+00:00..2026-09-09T16:57:49.770251+00:00" template="error-ratio" baseline="2026-09-09T15:52:41.395749+00:00..2026-09-09T16:25:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=131 mean=0.01011 min=0 max=0.08555 sd=0.02433
  baseline window: n=131 mean=0.05294 min=0 max=0.3064 sd=0.101
```

> Evidence `tr_37174b576e12`:

```
<tool_result id="tr_37174b576e12" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T16:55:15.583000+00:00..2026-09-09T16:57:49.770251+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_37174b576e12>
```

> Evidence `tr_3f43548041cd`:

```
<tool_result id="tr_3f43548041cd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:55:15.583000+00:00..2026-09-09T16:57:49.770251+00:00" radius="seed" hops="0">
service: productcatalogservice
2 changes, ranked by suspicion
  #1  10.8h before onset  2026-09-09T06:09:03.403533+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  10.9h before onset  2026-09-09T06:00:32.130376+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

> Evidence `tr_32613b039d16`:

```
<tool_result id="tr_32613b039d16" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-09T16:25:15.583000+00:00..2026-09-09T16:57:49.770251+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_32613b039d16>
```

## Where the signal actually was

Catalog-side metrics were the first evidence that held. Error ratio sat at exactly zero across the whole baseline half-hour — 131 samples, zero standard deviation — then went non-zero, mean near 1%, peak around 9%. So no chronic error floor that merely became visible. The single change point crossing 5% lands at 16:54:15Z, near the end of the window; with a 1% mean against a 9% peak, most buckets were still at or near zero. That killed both the idea of steady degradation from the window start and the idea of an outage — nine calls in ten succeeded. Note that only the error-ratio series came back; latency percentiles and CPU/memory for this service were never retrieved and cannot be answered from stored evidence.

Traces resolved the picture. One of ten sampled traces was errored, marked on the frontend client span for GetProduct and on the corresponding catalog server span for the same operation. ListProducts was clean everywhere, including inside the errored trace, so the recommendation-driven path was out. The errored server span completes in about 2.4ms (self ~0.3ms) inside a ~12.8ms trace, alongside healthy traces at 0.7–5ms — nowhere near a deadline, so these are fast rejections, not timeouts. Its only child, FeatureFlagService/GetFlag at ~2.1ms, carries no error status: the error is raised by the catalog service itself, not propagated upward. Worth flagging as a code-path hint: that outbound GetFlag child appears *only* under the errored call; the nine healthy GetProduct server spans are childless leaves. Coverage gap — all sampled traces fall in 16:56:27–16:56:50, nothing for 16:54–16:55, the minutes holding the change point.

> Evidence `tr_ff31c52b5213`:

```
<tool_result id="tr_ff31c52b5213" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T16:25:15.583000+00:00..2026-09-09T16:57:49.770251+00:00" template="error-ratio" baseline="2026-09-09T15:52:41.395749+00:00..2026-09-09T16:25:15.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=131 mean=0.01062 min=0 max=0.09036 sd=0.02586
  baseline window: n=131 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_d94a7b0bbf19`:

```
<tool_result id="tr_d94a7b0bbf19" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T16:10:15.583000+00:00..2026-09-09T16:57:49.770251+00:00">
service: productcatalogservice
10 trace(s) shown of 10 found, 55 spans; offsets are from each trace's root

trace 3bd82efec927e065  root frontend/HTTP GET  2.6ms  started 2026-09-09T16:56:27.571057+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.6ms]
```

## What closed it, and what is still open

Frontend logs carry gRPC client errors naming ProductCatalogService as the failing peer, status 13 INTERNAL, with a details string generated by the catalog service attributing the failure to a deliberately enabled 'fail' feature flag on that service. The stack traces sit on the client-side status-receive path in Node grpc-js, so the frontend received and surfaced a server-returned status rather than failing the call itself. That eliminates the rest: no status 4 anywhere, so not a timeout; response metadata including content-type proves the connection was established and the peer replied, so not unreachability, DNS, refusal, or a mesh partition; every error line names the catalog service, so not another dependency; and not frontend code, nor an organic bug or resource condition needing a restart or scale-up. The wrong value is a flag whose enabled state is what breaks each affected request. Fix class: revert the configuration. Confidence high.

Three things remain open. No change record shows that flag being enabled — who flipped it, when, and in which system is unestablished, and that gap sits awkwardly against a change log that otherwise looked complete. The catalog service's own logs were never read, because the selector was wrong. And coverage of the onset minutes is inferential: the frontend log result was truncated to the oldest eight and newest thirty-two lines, so no line timestamped inside 16:54:00–16:56:59 is directly visible; identical errors appear around 16:52:35 and again at 16:57:31, 16:57:44 and 16:57:45, so the condition clearly spans the gap, but that span is inferred rather than read. Traces skip the same minutes.

> Evidence `tr_a4ba1bf91bf1`:

```
<tool_result id="tr_a4ba1bf91bf1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T16:10:15.583000+00:00..2026-09-09T16:57:49.770251+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-09T16:52:35.055312+00:00  Error: 13 INTERNAL: Error: ProductCatalogService Fail Feature Flag Enabled
2026-09-09T16:52:35.055361+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-09T16:52:35.055364+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-09T16:52:35.055365+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_d94a7b0bbf19`:

```
<tool_result id="tr_d94a7b0bbf19" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-09T16:10:15.583000+00:00..2026-09-09T16:57:49.770251+00:00">
service: productcatalogservice
10 trace(s) shown of 10 found, 55 spans; offsets are from each trace's root

trace 3bd82efec927e065  root frontend/HTTP GET  2.6ms  started 2026-09-09T16:56:27.571057+00:00  3 spans
  +0.0ms frontend/HTTP GET 2.6ms [self 0.6ms]
```

> Evidence `tr_3f43548041cd`:

```
<tool_result id="tr_3f43548041cd" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T16:55:15.583000+00:00..2026-09-09T16:57:49.770251+00:00" radius="seed" hops="0">
service: productcatalogservice
2 changes, ranked by suspicion
  #1  10.8h before onset  2026-09-09T06:09:03.403533+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  10.9h before onset  2026-09-09T06:00:32.130376+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

