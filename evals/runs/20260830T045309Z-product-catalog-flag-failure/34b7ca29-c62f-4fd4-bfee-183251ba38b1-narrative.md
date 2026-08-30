# Partial GetProduct failures traced to an enabled 'fail' flag in the product catalog service

## What was visible first

The page named three services: frontend, loadgenerator, and productcatalogservice. Triage put seven services in the blast radius and flagged one edge as unmeasured. Nothing was hard-down. From the responder's chair the first honest reading was ambiguous: user-facing browse requests were failing some of the time, and the error signal was present at both ends of the frontend-to-catalog edge.

The metric view confirmed the shape but not the cause. Frontend's span error ratio moved between zero and roughly 10% across sixty sample points, bursty rather than a flat elevated floor. Productcatalogservice showed the same character from its own side, peaking near 11.1% with a minimum of zero across fifty-eight points, and its request denominator was non-zero at every point, so it was still serving traffic throughout. Two readings were ruled out immediately: this was not a total outage, and it was not a silent traffic drop.

> Evidence `tr_480192ce5c22`:

```
<tool_result id="tr_480192ce5c22" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1009 n=60
</tool_result:tr_480192ce5c22>
```

> Evidence `tr_342a27201f51`:

```
<tool_result id="tr_342a27201f51" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1111 n=58
</tool_result:tr_342a27201f51>
```

## The first dead end: looking for a change to roll back

The instinct was to find the change and revert it. Two separate passes over productcatalogservice's change history came back empty — no deploys, no config edits, no flag flips recorded. That result is worth reading carefully, because it is easy to over-interpret. Both dispatches actually covered only 04:46:45–05:01:45, the incident window itself, not the preceding hour that had been asked for. So what was genuinely established is narrow: nothing changed *during* the incident, and no rolling or staged change was still mutating the service while responders watched. What was *not* established is that nothing changed before it. The hour from roughly 03:56 to 04:46 was never queried, and neither was featureflagservice's own change log — which, in hindsight, is where the relevant record most likely sits.

Do not repeat the mistake of reading an empty change log as an exoneration of configuration. It was an exoneration of the fifteen minutes we happened to look at.

> Evidence `tr_d3e954d71c61`:

```
<tool_result id="tr_d3e954d71c61" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_d3e954d71c61>
```

> Evidence `tr_65b6677d9546`:

```
<tool_result id="tr_65b6677d9546" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_65b6677d9546>
```

## The second dead end: the catalog service's own logs

The obvious next move was to read the failing service's logs. The query returned zero lines — not zero error lines, zero lines of any level, across the full fifteen minutes. A healthy service still emits info-level chatter, so this was not a quiet-but-well server. The most likely explanation is a selector mismatch: the service is named productcatalogservice, while the query used the label value product-catalog-service. A logging or ingestion gap is the alternative.

The practical consequence is that server-side confirmation of the failure decision was never obtained from the failing process itself. Everything below rests on client-visible status and on trace structure. If you are picking this up again, fix the selector first; it is the cheapest outstanding action in the record.

> Evidence `tr_50e413e55ac4`:

```
<tool_result id="tr_50e413e55ac4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_50e413e55ac4>
```

## Where the signal actually was: frontend client logs

The frontend logs were the turning point. Every visible error line named exactly one downstream dependency — the product catalog service — and carried gRPC status 13, INTERNAL, with a server-supplied detail message attributing the failure to a deliberately enabled 'fail' feature flag on that dependency.

That single detail closed several doors at once. It was not a network problem: the call reached the peer, got an application-level answer, and carried response metadata; no timeout or unavailable status appeared anywhere. It was not a frontend bug: the stack frames sat entirely in the gRPC client's receive-status path, propagating a remote status rather than generating one. It was not a fan-out outage: no second dependency name appeared in any returned error line. And it was not transient — identical traces appeared near the window start around T+0 and again in a cluster near the end, meaning the condition was still live at the latest line returned.

One caveat the record should keep: the log tool truncated the middle of the window, returning only the oldest eight and newest thirty-two lines. The visible bursts are a lower bound on the tail. No true error count or rate can be derived from this evidence.

> Evidence `tr_7599424c4726`:

```
<tool_result id="tr_7599424c4726" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-08-30T04:53:24.335481+00:00  Error: 13 INTERNAL: Error: ProductCatalogService Fail Feature Flag Enabled
2026-08-30T04:53:24.335518+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-08-30T04:53:24.335522+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-08-30T04:53:24.335524+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Trace evidence and the structural corroboration

Traces made the mechanism legible without needing the server's logs. Every error-marked productcatalogservice span sat on hipstershop.ProductCatalogService/GetProduct. Not one ListProducts span was marked as an error, including the ones issued by recommendationservice, which calls only ListProducts and succeeded throughout.

The distinguishing structural detail: each failing GetProduct span had exactly one child, a productcatalogservice-issued FeatureFlagService/GetFlag call of roughly 1.0–1.7ms, itself not error-marked. Successful GetProduct spans had no such sibling. That child accounts for essentially all the extra latency on the error path — failures landed at 1.1–1.9ms while successes were overwhelmingly sub-0.1ms.

Those timings also killed the saturation hypothesis. Failures were fast, nowhere near any plausible deadline, and the slowest catalog-related spans in the window (a 14.7ms and a 10.4ms frontend GetProduct) both succeeded. Nor was a downstream service to blame: cartservice/redis, currencyservice, shippingservice, paymentservice and emailservice never appear beneath productcatalogservice, and where they show up in checkout traces they complete cleanly. Featureflagservice itself was not erroring — the GetFlag spans returned normally; the failure originates in the catalog service's own handling *after* consulting the flag state.

Callers were frontend (the large majority, browse traffic) and checkoutservice in one PlaceOrder chain, where the error propagated up and failed the order. Within single traces some GetProduct spans succeeded at ~0.0ms while a sibling failed, so selection is per-call, not per-instance.

> Evidence `tr_0794df107a9a`:

```
<tool_result id="tr_0794df107a9a" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
service: productcatalogservice
200 spans
  b6acb7cb182127cd productcatalogservice/hipstershop.ProductCatalogService/ListProducts 0.0ms
  b6acb7cb182127cd frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.8ms
  b6acb7cb182127cd frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.7ms
```

## Conclusion and fix class

The product catalog service is returning gRPC INTERNAL on a fraction of GetProduct calls because a failure-producing feature flag is enabled for that code path. The wrong value *is* the failure: the flag state instructs the service to fail requests it would otherwise serve. Blast radius matches that mechanism exactly — frontend browse traffic and one checkout chain error on the propagated status, ListProducts and recommendationservice are untouched, and both ends show partial, bursty error ratios in the 10–11% band.

Fix class is a configuration revert: turn the flag off. Do not roll back a deployment and do not restart anything; there is no bad artifact to remove and a restart will not change the flag state. Confidence is high.

> Evidence `tr_7599424c4726`:

```
<tool_result id="tr_7599424c4726" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-08-30T04:53:24.335481+00:00  Error: 13 INTERNAL: Error: ProductCatalogService Fail Feature Flag Enabled
2026-08-30T04:53:24.335518+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-08-30T04:53:24.335522+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-08-30T04:53:24.335524+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_0794df107a9a`:

```
<tool_result id="tr_0794df107a9a" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
service: productcatalogservice
200 spans
  b6acb7cb182127cd productcatalogservice/hipstershop.ProductCatalogService/ListProducts 0.0ms
  b6acb7cb182127cd frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.8ms
  b6acb7cb182127cd frontend/grpc.hipstershop.ProductCatalogService/GetProduct 2.7ms
```

> Evidence `tr_480192ce5c22`:

```
<tool_result id="tr_480192ce5c22" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1009 n=60
</tool_result:tr_480192ce5c22>
```

> Evidence `tr_342a27201f51`:

```
<tool_result id="tr_342a27201f51" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1111 n=58
</tool_result:tr_342a27201f51>
```

## Still open

The flag flip itself was never located. Neither change dispatch covered the hour before onset, and nobody queried featureflagservice's own change log, which is the most likely home for a record of a flag governing catalog behaviour. Who enabled it, when, and whether it was intentional testing or an accident all remain unsettled.

Why the error ratio sits at only 10–11% rather than near-total is unexplained. A service-wide flag would normally fail every GetProduct. The observed per-call selectivity suggests something probabilistic, scoped to particular product IDs, or evaluated per request — but the evidence does not distinguish among these, and the service's evaluation logic was never read.

Relatedly, why GetFlag appears as a child only on failing spans is unresolved. It may indicate a lazy consult on one branch, or it may be a sampling or instrumentation artifact.

The catalog service's logs remain unavailable, so no direct server-side confirmation of the flag decision exists. No latency percentiles or CPU/memory data were retrieved for either service; traces make saturation unlikely but it was never checked at the metric level. And of the seven services in the reported blast radius, only frontend, productcatalogservice and (through traces) checkoutservice were examined — whether the remainder are simple downstream victims or carry something independent was not tested. Finally, the true frontend error count is unknown because of log truncation.

> Evidence `tr_65b6677d9546`:

```
<tool_result id="tr_65b6677d9546" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_65b6677d9546>
```

> Evidence `tr_d3e954d71c61`:

```
<tool_result id="tr_d3e954d71c61" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
no changes recorded for productcatalogservice over this window
</tool_result:tr_d3e954d71c61>
```

> Evidence `tr_50e413e55ac4`:

```
<tool_result id="tr_50e413e55ac4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_50e413e55ac4>
```

> Evidence `tr_7599424c4726`:

```
<tool_result id="tr_7599424c4726" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-08-30T04:53:24.335481+00:00  Error: 13 INTERNAL: Error: ProductCatalogService Fail Feature Flag Enabled
2026-08-30T04:53:24.335518+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-08-30T04:53:24.335522+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-08-30T04:53:24.335524+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_342a27201f51`:

```
<tool_result id="tr_342a27201f51" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0.1111 n=58
</tool_result:tr_342a27201f51>
```

> Evidence `tr_480192ce5c22`:

```
<tool_result id="tr_480192ce5c22" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-30T04:46:45.583000+00:00..2026-08-30T05:01:45.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0.1009 n=60
</tool_result:tr_480192ce5c22>
```
