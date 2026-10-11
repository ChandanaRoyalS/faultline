# Frontend ad-slot errors after ad workload stops answering on its port

## Summary and sequence

Take T+0 as the moment the pages landed on frontend, frontend-proxy and ad; all offsets are from there. Nine services sat in the blast radius and severity was called critical, but the shape is narrow.

At roughly T-6m an automated platform actor updated ad's image reference to a service-specific hotfix build tag. One second before that entry, ad wrote a clean, sequenced gRPC-then-JVM shutdown and then emitted nothing at all for the rest of the window — no startup lines, no second shutdown. The replacement artifact never came up. Traces agree and date the behavioural cutoff slightly earlier: every sampled ad trace is a complete frontend→ad chain with an inbound GetAds server span, all starting before the stop, running roughly 1.6–10ms with none flagged errored; the last two before the cutoff are among the fastest, so this was an abrupt stop and not a slide into a timeout. After the cutoff there are no ad spans of any kind.

Frontend's errors are purely transport-level: gRPC status 14 UNAVAILABLE against a single peer at 172.18.0.19:9555, connection refused in the older lines and host unreachable in the newest, with no connection ever established. Frontend itself has no recorded changes in the window. Confidence medium. Fix class: rollback the ad image and confirm it starts.

> Evidence `tr_d0001383944f`:

```
<tool_result id="tr_d0001383944f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T10:23:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" radius="seed" hops="0">
service: ad
9 changes, ranked by suspicion
  #1  6m before onset  2026-10-08T10:16:56.186645+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  20m before onset  2026-10-08T10:03:09.156324+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_7ce8853c40b5`:

```
<tool_result id="tr_7ce8853c40b5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-08T09:53:20.725456+00:00  2026-10-08 09:53:20 - oteldemo.AdService - no baggage found in context trace_id=fbdd071ef50e2ce7192b89a9e493ebfd span_id=e4dfdd816c5bf414 trace_flags=01 
2026-10-08T09:53:20.726100+00:00  2026-10-08 09:53:20 - oteldemo.AdService - Non-targeted ad request received, preparing random response. trace_id=fbdd071ef50e2ce7192b89a9e493ebfd span_id=e4dfdd816c5bf414 trace_flags=01 
2026-10-08T09:53:21.841923+00:00  2026-10-08 09:53:21 - oteldemo.AdService - no baggage found in context trace_id=b2a5d1848c995eb32c2c53dd9658738a span_id=7d77b7f31ba90489 trace_flags=01 
2026-10-08T09:53:21.842123+00:00  2026-10-08 09:53:21 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=b2a5d1848c995eb32c2c53dd9658738a span_id=7d77b7f31ba90489 trace_flags=01 
```

> Evidence `tr_6b93e795e969`:

```
<tool_result id="tr_6b93e795e969" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00">
service: ad
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 764ba671da032223  root load-generator/user_get_ads  9.0ms  started 2026-10-08T10:06:51.599225+00:00  13 spans
  +0.0ms load-generator/user_get_ads 9.0ms [self 0.7ms]
```

> Evidence `tr_3384ab529d86`:

```
<tool_result id="tr_3384ab529d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-08T09:54:12.372346+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-08T09:54:12.370Z)
2026-10-08T09:54:12.372409+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-08T09:54:12.372412+00:00      at new Promise (<anonymous>) {
2026-10-08T09:54:12.372413+00:00    code: 14,
```

> Evidence `tr_877e05badcaa`:

```
<tool_result id="tr_877e05badcaa" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-07T10:23:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_877e05badcaa>
```

## Dead ends worth keeping

The memory-limit churn on ad. Eight of the nine recorded changes are four identical lower-then-restore pairs cycling for hours beforehand. It looks like a smoking gun until you check ordering: the last action before onset was a restore, so no lowered limit was in effect. Possibly a symptom of an odd controller, not the mechanism.

Ad's error ratio. Chased on the assumption ad was the origin. It averaged about 0.4% against 0.3% baseline, peaking under 2%, across a sparse series with 45 incident intervals carrying no traffic. A hard outage would drive the ratio toward 1.0 in traffic-bearing intervals. A service that has stopped existing produces no errors — it produces no data. Wrong instrument.

Everything else the evidence closed quickly: crash-looping (one orderly shutdown, no restart pairs); OOM or fatal exception (clean sequence, no stack trace); alive-but-degraded (a server-side stall still emits a long inbound span); DNS or discovery (the client resolved to a concrete IP and failed at the socket); TLS or auth (failure precedes any handshake); a slow downstream (UNAVAILABLE, not DEADLINE_EXCEEDED); a mesh-wide problem (every error names the same single peer); ingress or routing upstream of ad (pre-cutoff proxy→frontend→ad chains are intact and fast); and a frontend code defect (no application-level exception anywhere in its stream).

> Evidence `tr_d0001383944f`:

```
<tool_result id="tr_d0001383944f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T10:23:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" radius="seed" hops="0">
service: ad
9 changes, ranked by suspicion
  #1  6m before onset  2026-10-08T10:16:56.186645+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  20m before onset  2026-10-08T10:03:09.156324+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_e5e86ff39423`:

```
<tool_result id="tr_e5e86ff39423" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" template="error-ratio" baseline="2026-10-08T09:21:15.671302+00:00..2026-10-08T09:53:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=84 mean=0.004062 min=0 max=0.01923 sd=0.005629
  baseline window: n=109 mean=0.003002 min=0 max=0.0122 sd=0.004635
```

> Evidence `tr_7ce8853c40b5`:

```
<tool_result id="tr_7ce8853c40b5" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-08T09:53:20.725456+00:00  2026-10-08 09:53:20 - oteldemo.AdService - no baggage found in context trace_id=fbdd071ef50e2ce7192b89a9e493ebfd span_id=e4dfdd816c5bf414 trace_flags=01 
2026-10-08T09:53:20.726100+00:00  2026-10-08 09:53:20 - oteldemo.AdService - Non-targeted ad request received, preparing random response. trace_id=fbdd071ef50e2ce7192b89a9e493ebfd span_id=e4dfdd816c5bf414 trace_flags=01 
2026-10-08T09:53:21.841923+00:00  2026-10-08 09:53:21 - oteldemo.AdService - no baggage found in context trace_id=b2a5d1848c995eb32c2c53dd9658738a span_id=7d77b7f31ba90489 trace_flags=01 
2026-10-08T09:53:21.842123+00:00  2026-10-08 09:53:21 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=b2a5d1848c995eb32c2c53dd9658738a span_id=7d77b7f31ba90489 trace_flags=01 
```

> Evidence `tr_3384ab529d86`:

```
<tool_result id="tr_3384ab529d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-08T09:54:12.372346+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-08T09:54:12.370Z)
2026-10-08T09:54:12.372409+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-08T09:54:12.372412+00:00      at new Promise (<anonymous>) {
2026-10-08T09:54:12.372413+00:00    code: 14,
```

> Evidence `tr_6b93e795e969`:

```
<tool_result id="tr_6b93e795e969" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00">
service: ad
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 764ba671da032223  root load-generator/user_get_ads  9.0ms  started 2026-10-08T10:06:51.599225+00:00  13 spans
  +0.0ms load-generator/user_get_ads 9.0ms [self 0.7ms]
```

## Open threads

The 172.18.0.19:9555 to ad mapping is inferred from port and timing only. Frontend logs name an IP and port, nothing else; no registry or container inventory was consulted. Do that first next time.

The timing does not fully close. Frontend was already logging identical UNAVAILABLE errors against that same peer about half an hour before the image update, while ad was demonstrably serving healthy traces in the minutes after. That overlap is unexplained and it weakens the clean onset story — the image update may be a change in failure mode rather than the start.

Why the replacement artifact never started is unknown. Pull failure, crash before first log line, and never scheduled are indistinguishable from what we have, and no CPU or memory utilisation metrics for ad were ever collected; no latency percentiles either, so tail degradation was never actually tested.

> Evidence `tr_3384ab529d86`:

```
<tool_result id="tr_3384ab529d86" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-08T09:54:12.372346+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-08T09:54:12.370Z)
2026-10-08T09:54:12.372409+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-08T09:54:12.372412+00:00      at new Promise (<anonymous>) {
2026-10-08T09:54:12.372413+00:00    code: 14,
```

> Evidence `tr_6b93e795e969`:

```
<tool_result id="tr_6b93e795e969" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00">
service: ad
10 trace(s) shown of 10 found, 132 spans; offsets are from each trace's root

trace 764ba671da032223  root load-generator/user_get_ads  9.0ms  started 2026-10-08T10:06:51.599225+00:00  13 spans
  +0.0ms load-generator/user_get_ads 9.0ms [self 0.7ms]
```

> Evidence `tr_e5e86ff39423`:

```
<tool_result id="tr_e5e86ff39423" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-08T09:53:16.664000+00:00..2026-10-08T10:25:17.656698+00:00" template="error-ratio" baseline="2026-10-08T09:21:15.671302+00:00..2026-10-08T09:53:16.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=84 mean=0.004062 min=0 max=0.01923 sd=0.005629
  baseline window: n=109 mean=0.003002 min=0 max=0.0122 sd=0.004635
```

