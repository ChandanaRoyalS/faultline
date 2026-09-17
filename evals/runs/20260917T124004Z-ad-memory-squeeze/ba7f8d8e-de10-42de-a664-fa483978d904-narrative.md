# Frontend and load generator alerts traced to an ad-service restart loop under a lowered memory ceiling

## What was visible, and the dead ends

Two callers paged: frontend and loadgenerator. Severity was critical and the scored blast radius was seven services, which set the expectation of something broad. One triage edge was crossed unmeasured, so the map was known to be incomplete from the start.

Frontend itself looked almost fine, and chasing it cost the most time. Its change log over a full day ending just past the alert came back completely empty — no deploys, no config edits, no flag flips, and nothing after onset either, which also removed the possibility that someone worsened it mid-incident. Its error ratio rose from about 2.2% to 3.1% with peaks near 10% against a baseline max near 6%, but standard deviation was comparable to the mean and the comparison found no sustained departure. That query aggregated by service only, with no route dimension and no latency or throughput series, so it could never have answered whether damage was broad or confined.

The traces were the most convincing red herring. Ten traces, thirty-nine spans, all placing dominant latency in frontend's own self-time; the slowest three (57ms, 30ms, 29ms) were leaves with no downstream children at all. Downstream hops that did appear were fast — productcatalogservice sub-millisecond, cartservice with Redis children under 2ms — and no span was error-flagged. Two things defuse this. The returned traces clustered in the last forty seconds of the window rather than spanning it, so the sample never covered onset. And adservice appeared in none of the thirty-nine spans, which was logged as an exclusion but was actually the finding: calls that die at name resolution never produce a downstream server span. The sampler was showing surviving traffic. checkoutservice was also checked on the change side and its log was likewise empty.

> Evidence `tr_b43938a2e300`:

```
<tool_result id="tr_b43938a2e300" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T12:44:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_b43938a2e300>
```

> Evidence `tr_1d6249f884a0`:

```
<tool_result id="tr_1d6249f884a0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" template="error-ratio" baseline="2026-09-17T11:41:57.729963+00:00..2026-09-17T12:14:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=62 mean=0.03132 min=0 max=0.1047 sd=0.03583
  baseline window: n=124 mean=0.02159 min=0 max=0.0628 sd=0.02402
```

> Evidence `tr_403f04b700c7`:

```
<tool_result id="tr_403f04b700c7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00">
service: frontend
10 trace(s) shown of 10 found, 39 spans; offsets are from each trace's root

trace c6ed0b63ccdf2db9  root loadgenerator/HTTP GET  8.9ms  started 2026-09-17T12:44:33.936660+00:00  3 spans
  +0.0ms loadgenerator/HTTP GET 8.9ms [self 0.8ms]
```

> Evidence `tr_df0bb8bdcc13`:

```
<tool_result id="tr_df0bb8bdcc13" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T12:44:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_df0bb8bdcc13>
```

## The turn: frontend's own logs, then adservice

Frontend's log stream broke the stall. It carried repeated gRPC UNAVAILABLE (status 14) client errors from the grpc-js call path, naming exactly one target: adservice on port 9555 by DNS name. The late failures died at resolution of that name, before any socket attempt — fast failures, not DEADLINE_EXCEEDED, so this was never a timeout story. No other dependency host appeared in any returned line, retiring cart, checkout, product catalog, currency and recommendation. The newest lines sat around T+2m, seconds from the window's close, spaced a few seconds apart: still retrying, still failing.

adservice's own error-ratio metric was the next obvious move and was a near-miss. It returned no samples — but none in the baseline window either. Because the silence is uniform rather than starting at onset, the series simply never existed; the tool's "no sustained departure" verdict is vacuous here. An empty series is not a healthy series.

The log stream carried what the metrics could not. At roughly T-13m adservice was emitting normal ad-request handling with trace context. From about T-4m onward the stream contains nothing but JVM and OTel-agent startup banners — at least eleven distinct startups over five minutes, clustered within seconds at first then settling to about one per minute, the shape of a restart loop with backoff. Each cycle ends after the agent version banner: no listening line, no request handling, no readiness. The final record is another startup banner; the loop was still running when the data ended.

> Evidence `tr_88656a5dca3b`:

```
<tool_result id="tr_88656a5dca3b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T12:34:03.139221+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T12:34:03.139249+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T12:34:03.139251+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T12:34:03.139252+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_463656558d7e`:

```
<tool_result id="tr_463656558d7e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" template="error-ratio" baseline="2026-09-17T11:41:57.729963+00:00..2026-09-17T12:14:00.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_23f4c239bab1`:

```
<tool_result id="tr_23f4c239bab1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-17T12:30:28.941234+00:00  2026-09-17 12:30:28 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=b4cc0abdc848425422de36bcc0bde054 span_id=f4f0e55b2ef85092 trace_flags=01 
2026-09-17T12:30:30.992907+00:00  2026-09-17 12:30:30 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=f6d377f7f6d699f66f8dd0dfee6100ee span_id=79d0c09504d3ac8a trace_flags=01 
2026-09-17T12:30:32.505810+00:00  2026-09-17 12:30:32 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=8e34e0732c66e52ede8ddcf9029593e0 span_id=d1faa3d46d053a68 trace_flags=01 
2026-09-17T12:30:33.030140+00:00  2026-09-17 12:30:33 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=489a3519266d26359379f9fb001b716a span_id=c3622fbbd0bea839 trace_flags=01 
```

## The cause, and what is still open

adservice's change log was the only non-empty one in the investigation: seven entries, all the same kind, all by platform-automation — container memory limit lowered to 256m, then reverted. That cycle had already run three times earlier the same day (roughly 9.4h, 8.7h and 3.8h before onset). The fourth lowering landed at T-3m with no matching revert, so at onset the service was under the 256m ceiling. The same log rules out a code deploy, a replica or autoscaler change, an intentional restart or drain, and — importantly, given the DNS-flavoured symptom — any service-discovery or endpoint configuration change. No human authored any of it.

Mechanism: the JVM-based ad service cannot live inside 256m, is killed during startup, restarts, and is killed again. The pod never reaches ready, so its endpoints stay absent and frontend's calls fail fast, latterly at name resolution. frontend and loadgenerator alerted only as callers noticing a missing dependency. Confidence high; the fix class is reverting the config.

Still open. No OOMKill or container termination reason was retrieved — memory exhaustion is inferred from the limit edit plus the pre-ready restart loop, not observed. Kubelet events and working-set-versus-limit metrics would settle it. Whether the lowering was reverted after the window closed, and whether adservice recovered, is unknown: the log window ends mid-loop and the service has no metric series at all. And one frontend UNAVAILABLE around T-10m carried a connection-dropped detail rather than a resolution failure, predating the restart loop; the middle of the log window was never returned, so earlier instability and the one unmeasured triage edge remain unexplained.

> Evidence `tr_157405b0e3e6`:

```
<tool_result id="tr_157405b0e3e6" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T12:44:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" radius="candidate_cause" hops="1">
service: adservice
7 changes, ranked by suspicion
  #1  3m before onset  2026-09-17T12:40:09.189012+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  3.7h before onset  2026-09-17T09:03:14.529343+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

> Evidence `tr_23f4c239bab1`:

```
<tool_result id="tr_23f4c239bab1" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-17T12:30:28.941234+00:00  2026-09-17 12:30:28 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=b4cc0abdc848425422de36bcc0bde054 span_id=f4f0e55b2ef85092 trace_flags=01 
2026-09-17T12:30:30.992907+00:00  2026-09-17 12:30:30 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=f6d377f7f6d699f66f8dd0dfee6100ee span_id=79d0c09504d3ac8a trace_flags=01 
2026-09-17T12:30:32.505810+00:00  2026-09-17 12:30:32 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=8e34e0732c66e52ede8ddcf9029593e0 span_id=d1faa3d46d053a68 trace_flags=01 
2026-09-17T12:30:33.030140+00:00  2026-09-17 12:30:33 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=489a3519266d26359379f9fb001b716a span_id=c3622fbbd0bea839 trace_flags=01 
```

> Evidence `tr_88656a5dca3b`:

```
<tool_result id="tr_88656a5dca3b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T12:34:03.139221+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T12:34:03.139249+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T12:34:03.139251+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T12:34:03.139252+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_463656558d7e`:

```
<tool_result id="tr_463656558d7e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T12:14:00.583000+00:00..2026-09-17T12:46:03.436037+00:00" template="error-ratio" baseline="2026-09-17T11:41:57.729963+00:00..2026-09-17T12:14:00.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

