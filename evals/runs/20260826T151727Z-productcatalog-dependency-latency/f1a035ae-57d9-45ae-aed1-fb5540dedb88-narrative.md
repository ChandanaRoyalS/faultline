# Warning-severity slowdown across the storefront path with zero errors anywhere

## What the responder saw first

The page opens with five alerting services — frontend, loadgenerator, recommendationservice, checkoutservice, productcatalogservice — and a stated blast radius of twelve services and four edges with no measurement on them. Alerts landed roughly three and a half minutes after the moment that later turned out to matter (frontend first, then checkoutservice and productcatalogservice a few seconds behind at T+3m45s and T+4m). Severity was warning, not critical, and nothing was paging about failures. That combination — broad radius, mild severity, several tiers alerting nearly together — reads at first glance like a shared dependency degrading, which is roughly where the investigation ended up, but the first several steps did not know that.

## The first thing checked was the wrong thing

The instinct was to look for a release. The change log for frontend was queried over T-6m to T+9m and came back completely empty: no deploys, no config pushes, no flag flips, no rollbacks or remediation entries. The same query against recommendationservice came back equally empty. Two services deep into the alerting set and there was nothing to roll back. Both of these were dead ends, but useful ones — they closed the 'someone shipped something' framing for the two services people were most likely to suspect, and they redirected attention to infrastructure rather than application code. Note the boundary though: both queries started at T-6m. The preceding eleven minutes were never searched on either service, so a change landing earlier and surfacing late is still formally open.

> Evidence `tr_15483f6e5c7a`:

```
<tool_result id="tr_15483f6e5c7a" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_15483f6e5c7a>
```

> Evidence `tr_bba8cea8dd8d`:

```
<tool_result id="tr_bba8cea8dd8d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
no changes recorded for recommendationservice over this window
</tool_result:tr_bba8cea8dd8d>
```

## The one recorded act in the blast radius

The change log for productcatalogservice was not empty. It held exactly one entry, at what this record calls T+0: an automated actor (platform-automation) attached a traffic-shaping container to the service's network namespace, applying a fixed 300ms egress delay with zero jitter on eth0, where the prior state for that interface was no shaping at all. This is not a deploy, not a config push to the application, and not a flag — it is infrastructure sitting outside the process, altering the network path only. Two properties of it matter for prediction: the onset is sharp (nothing before T+0, everything after), and the penalty is flat, so any latency it causes should look like a uniform floor added per hop rather than a load-proportional curve or a queueing tail.

> Evidence `tr_83b838a8a03c`:

```
<tool_result id="tr_83b838a8a03c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
service: productcatalogservice
1 changes
  2026-08-26T15:17:32.553891+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_83b838a8a03c>
```

## Chasing errors, and finding none — repeatedly

A large fraction of the effort went into error signals, and all of it came back negative. Frontend's error ratio is flat zero across every sample point in the window, twice queried and twice confirmed. productcatalogservice's error ratio is likewise flat zero across sixty-one continuous points, spanning both sides of T+0 and both sides of the alert. Because these are ratios that resolved to a numeric zero rather than to nothing at all, the denominators were non-zero: both services were serving real traffic the whole time. That kills several plausible stories in one stroke. There was no error wave propagating up from the catalog to the edge. There were no hard downstream failures surfacing as frontend errors. There was no crash, restart, or drop-out — the series never gaps. And there was no retry amplification or circuit-breaker trip, since both need failed calls to feed on and there were none. The one thing all four of these queries did not deliver was any latency series at all. No p50, no p95, no duration histogram, for any service. That absence is the largest hole in the record.

> Evidence `tr_2920b63c56f2`:

```
<tool_result id="tr_2920b63c56f2" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=60
</tool_result:tr_2920b63c56f2>
```

> Evidence `tr_fd7f26d347d6`:

```
<tool_result id="tr_fd7f26d347d6" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_fd7f26d347d6>
```

> Evidence `tr_6e6c8fad1536`:

```
<tool_result id="tr_6e6c8fad1536" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_6e6c8fad1536>
```

> Evidence `tr_7a1e277eb041`:

```
<tool_result id="tr_7a1e277eb041" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_7a1e277eb041>
```

## The only positive symptom anyone actually measured

It came from logs, not metrics. recommendationservice's lines in the window are all INFO from the request server: the routine feature-flag/cache stub line and the ListRecommendations receive line, arriving steadily throughout. No errors, no warnings, no stack traces, no timeouts, and — importantly — no downstream service is named anywhere, so the logs do not point at the catalog on their own. What they do show is timing. The interval between the flag-stub line and the receive line on the same trace was roughly 1–2ms in the early samples near T-6m, and roughly 300ms in the late samples near T+6m to T+7m. Same shape of work, same flag state (the cache flag reports its disabled stub description identically early and late), same arrival cadence, three hundred milliseconds slower inside the request. That magnitude and that flatness are exactly what the shaping attachment predicts. It is also the entire empirical basis for the conclusion.

> Evidence `tr_280def5f89e6`:

```
<tool_result id="tr_280def5f89e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="recommendation-service"}
2026-08-26T15:11:01.296087+00:00  {"asctime": "2026-08-26 15:11:01,295", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "b265be6a3c512be4e19a36df3bd50dcc", "otelSpanID": "9e9bb1e06bedc5e4", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:01.297100+00:00  {"asctime": "2026-08-26 15:11:01,296", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "b265be6a3c512be4e19a36df3bd50dcc", "otelSpanID": "b8cfb0a8eac823e7", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', 'L9ECAV7KIM', '6E92ZMYYFZ', 'OLJCESPC7Z', 'LS4PSXUNUM']", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:02.560989+00:00  {"asctime": "2026-08-26 15:11:02,560", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "46b371d9e749b5b72b243515f56ee272", "otelSpanID": "44d5d625ec9a7d02", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:02.562130+00:00  {"asctime": "2026-08-26 15:11:02,561", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "46b371d9e749b5b72b243515f56ee272", "otelSpanID": "a4d6607fd3e1a3a9", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', '0PUK6V6EV0', '2ZYFJ3GM2N', '66VCHSJNUP', 'LS4PSXUNUM']", "otelServiceName": "recommendationservice"}
```

## Conclusion, and how firmly it should be held

The reading is that every call path traversing productcatalogservice now pays a near-constant ~300ms penalty per hop, and callers wait rather than fail — which is why twelve services look unwell at warning severity while not a single error is recorded anywhere. The mechanism is added wait time in a dependency call path, not a wrong value read by application code and not a mismatched artifact. Fix class is a revert of the shaping configuration. Confidence is medium, and the honest reason for that is that the 300ms step is inferred from two log lines on one trace, never measured as a latency distribution.

> Evidence `tr_83b838a8a03c`:

```
<tool_result id="tr_83b838a8a03c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
service: productcatalogservice
1 changes
  2026-08-26T15:17:32.553891+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
      None  ->  eth0 delay=300ms jitter=0ms
</tool_result:tr_83b838a8a03c>
```

> Evidence `tr_280def5f89e6`:

```
<tool_result id="tr_280def5f89e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="recommendation-service"}
2026-08-26T15:11:01.296087+00:00  {"asctime": "2026-08-26 15:11:01,295", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "b265be6a3c512be4e19a36df3bd50dcc", "otelSpanID": "9e9bb1e06bedc5e4", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:01.297100+00:00  {"asctime": "2026-08-26 15:11:01,296", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "b265be6a3c512be4e19a36df3bd50dcc", "otelSpanID": "b8cfb0a8eac823e7", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', 'L9ECAV7KIM', '6E92ZMYYFZ', 'OLJCESPC7Z', 'LS4PSXUNUM']", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:02.560989+00:00  {"asctime": "2026-08-26 15:11:02,560", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "46b371d9e749b5b72b243515f56ee272", "otelSpanID": "44d5d625ec9a7d02", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:02.562130+00:00  {"asctime": "2026-08-26 15:11:02,561", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "46b371d9e749b5b72b243515f56ee272", "otelSpanID": "a4d6607fd3e1a3a9", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', '0PUK6V6EV0', '2ZYFJ3GM2N', '66VCHSJNUP', 'LS4PSXUNUM']", "otelServiceName": "recommendationservice"}
```

## What a later responder should close

Six things stayed open. First and most important: pull a duration histogram on productcatalogservice and frontend spanning T+0. A flat step confirms this; a ramp or a tail breaks it. Second, the log evidence is truncated — only the oldest eight and newest thirty-two lines survived, so roughly T-6m to T+6m is unobserved and nobody actually witnessed the onset. The step cannot be pinned to T+0 from logs alone. Third, the eleven minutes before T-6m were never queried on frontend or recommendationservice. Fourth, the roughly three-and-a-half-minute gap between T+0 and the alerts is plausible for a rate window but was never checked against the alert rule. Fifth, triage named twelve services and four unmeasured edges, and only three services were examined; checkoutservice alerted and was never dispatched to, along with seven others. Sixth, and this one governs whether reverting is safe to do unilaterally: nobody established whether the shaping attachment was a scheduled resilience experiment with an owner and a stop procedure, or an errant automation run. Finally, it was never shown that a 300ms floor alone accounts for warning-severity impact across twelve services — if something is amplifying it through fan-out or serial calls per request, that amplification was not measured.

> Evidence `tr_280def5f89e6`:

```
<tool_result id="tr_280def5f89e6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="recommendation-service"}
2026-08-26T15:11:01.296087+00:00  {"asctime": "2026-08-26 15:11:01,295", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "b265be6a3c512be4e19a36df3bd50dcc", "otelSpanID": "9e9bb1e06bedc5e4", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:01.297100+00:00  {"asctime": "2026-08-26 15:11:01,296", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "b265be6a3c512be4e19a36df3bd50dcc", "otelSpanID": "b8cfb0a8eac823e7", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', 'L9ECAV7KIM', '6E92ZMYYFZ', 'OLJCESPC7Z', 'LS4PSXUNUM']", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:02.560989+00:00  {"asctime": "2026-08-26 15:11:02,560", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 122, "otelTraceID": "46b371d9e749b5b72b243515f56ee272", "otelSpanID": "44d5d625ec9a7d02", "message": "name: \"recommendationCache\"\ndescription: \"stub: flags are disabled unless FAULTLINE_ENABLED_FLAGS names them\"\n", "otelServiceName": "recommendationservice"}
2026-08-26T15:11:02.562130+00:00  {"asctime": "2026-08-26 15:11:02,561", "levelname": "INFO", "name": "recommendationservice-server", "filename": "recommendation_server.py", "lineno": 46, "otelTraceID": "46b371d9e749b5b72b243515f56ee272", "otelSpanID": "a4d6607fd3e1a3a9", "message": "[Recv ListRecommendations] product_ids=['1YMWWN1N4O', '0PUK6V6EV0', '2ZYFJ3GM2N', '66VCHSJNUP', 'LS4PSXUNUM']", "otelServiceName": "recommendationservice"}
```

> Evidence `tr_7a1e277eb041`:

```
<tool_result id="tr_7a1e277eb041" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_7a1e277eb041>
```

> Evidence `tr_fd7f26d347d6`:

```
<tool_result id="tr_fd7f26d347d6" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=61
</tool_result:tr_fd7f26d347d6>
```

> Evidence `tr_2920b63c56f2`:

```
<tool_result id="tr_2920b63c56f2" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
1 series
  {service_name=frontend} min=0 max=0 n=60
</tool_result:tr_2920b63c56f2>
```

> Evidence `tr_6e6c8fad1536`:

```
<tool_result id="tr_6e6c8fad1536" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
1 series
  {service_name=productcatalogservice} min=0 max=0 n=61
</tool_result:tr_6e6c8fad1536>
```

> Evidence `tr_15483f6e5c7a`:

```
<tool_result id="tr_15483f6e5c7a" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
no changes recorded for frontend over this window
</tool_result:tr_15483f6e5c7a>
```

> Evidence `tr_bba8cea8dd8d`:

```
<tool_result id="tr_bba8cea8dd8d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T15:11:00.583000+00:00..2026-08-26T15:26:00.583000+00:00">
no changes recorded for recommendationservice over this window
</tool_result:tr_bba8cea8dd8d>
```
