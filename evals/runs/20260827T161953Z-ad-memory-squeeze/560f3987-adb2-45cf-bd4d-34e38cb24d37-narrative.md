# Frontend ad-path failures traced to an ad-service crash loop after a memory ceiling reduction

## What was visible, in order

Offsets run from T+0, the start of the shared evidence window; every query in this record stops at T+15m, and nothing past that was observed. The page came from frontend and loadgenerator, severity critical, seven services in reported blast radius with one unmeasured edge.

Frontend's error ratio came first and was usefully confusing: fifty-nine continuous sample points, so traffic never stopped, but the ratio wandered between zero and about ten and a third percent. Not an outage, not a flat baseline — a subset of requests failing while the rest of the site served fine. That alone said the break was on a path only some page loads take, but the query returned no latency percentiles and no per-dependency breakdown, so it could not name the edge.

Frontend logs fixed the failure class: repeated gRPC client errors, status 14 UNAVAILABLE, detail saying no connection established, running roughly T+6.5m through T+12.5m, with grpc-js client stack frames. Outbound calls failing at the transport layer, not local handler exceptions, not deadline-exceeded, not quota rejection. The critical limitation: not one line names a peer — no host, no address, empty metadata. Do not re-read them hoping a hostname appears.

Traces named the edge. Every error-marked span sat on frontend HTTP GET into frontend gRPC AdService/GetAds, in two shapes: some running about 2.50 seconds to what looks like a client timeout ceiling, others failing in well under a millisecond. That pair fits a peer alternately absent and actively refusing.

> Evidence `tr_c43cc564ad33`:

```
<tool_result id="tr_c43cc564ad33" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1034 n=59
</tool_result:tr_c43cc564ad33>
```

> Evidence `tr_1cfa39c19ffd`:

```
<tool_result id="tr_1cfa39c19ffd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-08-27T16:20:04.176346+00:00  Error: 14 UNAVAILABLE: No connection established
2026-08-27T16:20:04.176389+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-08-27T16:20:04.176394+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-08-27T16:20:04.176395+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_ecdb2f0db1da`:

```
<tool_result id="tr_ecdb2f0db1da" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
service: frontend
200 spans
  98a22b4146f4ec4e frontend/HTTP GET 11.5ms
  98a22b4146f4ec4e frontend/grpc.hipstershop.RecommendationService/ListRecommendations 6.8ms
  98a22b4146f4ec4e recommendationservice//hipstershop.RecommendationService/ListRecommendations 3.7ms
```

## Dead ends worth keeping

Checkout consumed real time and produced only exclusions. Two complete checkout traces ran frontend POST to gRPC PlaceOrder to checkoutservice in about twenty-two to twenty-four milliseconds, clean throughout. Inside checkout the largest child was the shipping-quote path at roughly nine milliseconds; cart, product catalog, currency, payment, ship-order, empty-cart, email and order-publish were each two milliseconds or less, none in error. That kills checkout as source, kills any checkout dependency propagating failure upward, and kills a degraded shared backend — catalog, cart and currency appear across many traces fast and clean. It also kills broad frontend saturation: most frontend spans were a few milliseconds and succeeded.

Frontend's change history was queried early, since frontend was the starting point, and came back empty — no deploys, no config pushes, no flag flips, and no change-plus-rollback pair. Caveat to carry: the window actually queried spans about fifteen minutes, not the full requested lookback, so anything older was never checked.

Ad-service error-rate metrics returned no series at all — not the error numerator and, decisively, not the unfiltered total-call denominator. That reads like a broken query but is not. It means the request/error telemetry has nothing left to give and the next question is whether the process was running at all.

> Evidence `tr_ecdb2f0db1da`:

```
<tool_result id="tr_ecdb2f0db1da" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
service: frontend
200 spans
  98a22b4146f4ec4e frontend/HTTP GET 11.5ms
  98a22b4146f4ec4e frontend/grpc.hipstershop.RecommendationService/ListRecommendations 6.8ms
  98a22b4146f4ec4e recommendationservice//hipstershop.RecommendationService/ListRecommendations 3.7ms
```

> Evidence `tr_55ed7a4f3bb9`:

```
<tool_result id="tr_55ed7a4f3bb9" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_55ed7a4f3bb9>
```

> Evidence `tr_d575d870c184`:

```
<tool_result id="tr_d575d870c184" tool="promql_query" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
no series matched 'sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))' over this window
</tool_result:tr_d575d870c184>
```

## The cause, and what remains unproven

Ad-service logs answered it. Healthy ad-request serving with trace context from T+0 to about T+35s; then from T+6.5m onward, nothing but repeated JVM and agent bootstrap triplets — tool-options pickup, OpenJDK class-sharing warning, OpenTelemetry javaagent banner — three times in the first thirty seconds and then at roughly one-minute cadence through T+13.5m. At least eleven bootstrap sequences, no gRPC serving activity, no ad requests. The process dies before or shortly after reaching the serving stage each time. Not a running server returning errors, not a single restart settling down. Change history shows one entry: platform automation lowered ad-service's container memory limit to 256m at about T+6m, four minutes before the page, by an automated actor rather than a person. Fix class is a revert of that limit.

What is not proven. No direct kill evidence exists — the returned lines contain no OutOfMemoryError, no GC pressure, no exit code or kill record; container restart reasons or kubelet events are needed to rule out a startup-probe failure or the agent itself failing under the new ceiling. The prior limit value is unrecorded, so whether 256m is merely tight or grossly insufficient for this JVM plus javaagent is unknown. The interval between healthy serving and the stable loop was truncated out, so onset and first failure mode are unobserved, as is everything after T+15m — persistence, self-recovery or remediation. Multi-service dispatches failed, so cartservice, checkoutservice, productcatalogservice and recommendationservice were only cleared indirectly by trace sampling; with seven services in blast radius and one unmeasured edge, collateral damage or a second concurrent failure cannot be excluded. The sub-millisecond versus 2.5-second GetAds failures were never reconciled against the restart cadence. Finally, whether the automation policy re-applies the limit after a manual revert is unknown — check that before closing.

> Evidence `tr_2ba33258cf6e`:

```
<tool_result id="tr_2ba33258cf6e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-08-27T16:13:47.517505+00:00  2026-08-27 16:13:47 - hipstershop.AdService - received ad request (context_words=[telescopes]) trace_id=482d8ae5e09e86a2dd73e4eb64a73eb2 span_id=6e39d782d389929e trace_flags=01
2026-08-27T16:13:56.986491+00:00  2026-08-27 16:13:56 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=018136a8a8923df8f2ae4cb74bc70823 span_id=d388623585f1be5f trace_flags=01
2026-08-27T16:14:04.008875+00:00  2026-08-27 16:14:04 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=425088f08bd8152adb7d1c25885783b1 span_id=33d71d68baca60a6 trace_flags=01
2026-08-27T16:14:11.604731+00:00  2026-08-27 16:14:11 - hipstershop.AdService - received ad request (context_words=[telescopes]) trace_id=3872bb9c1be023caa5a05f0ce7015cb2 span_id=0e1b32ec874e1b6a trace_flags=01
```

> Evidence `tr_8288272dd0bf`:

```
<tool_result id="tr_8288272dd0bf" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
service: adservice
1 changes
  2026-08-27T16:19:54.390096+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
</tool_result:tr_8288272dd0bf>
```

> Evidence `tr_ecdb2f0db1da`:

```
<tool_result id="tr_ecdb2f0db1da" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-27T16:13:45.583000+00:00..2026-08-27T16:28:45.583000+00:00">
service: frontend
200 spans
  98a22b4146f4ec4e frontend/HTTP GET 11.5ms
  98a22b4146f4ec4e frontend/grpc.hipstershop.RecommendationService/ListRecommendations 6.8ms
  98a22b4146f4ec4e recommendationservice//hipstershop.RecommendationService/ListRecommendations 3.7ms
```
