# Frontend transport errors traced to an ad service restart loop under a tightened memory ceiling

## What was visible, in order

Alerts came from frontend and frontend-proxy; blast radius eight services. Frontend's own error ratio looked near-normal across the window, with a single late change point at T-2m rising to about 6.4% against a baseline max near 4.9% — a brief spike on a normal floor, and aggregated by service only, so it could not say which dependency went first. Frontend's logs were far more useful: unbroken gRPC status 14 UNAVAILABLE against one peer, 172.18.0.19:9555, connection refused in the oldest lines around T-5m, host unreachable by T+1m30s, with frontend itself alive and retrying throughout. Looking at the ad service closed it: a repeating JVM startup banner roughly every minute from T-5m onward, a fresh start two seconds after T+0, several cycles dying before the application init line, and no exception, no memory message, no shutdown line anywhere. The change log for ad showed three entries in 24h, all from the same automation, all memory-limit adjustments; the latest lowered the ceiling to 144m about five minutes before the loop began. Ad's error-ratio series showed 105 no-traffic intervals against 36 in baseline — repeated short gaps in serving, not one continuous outage.

> Evidence `tr_fb97dbf9e088`:

```
<tool_result id="tr_fb97dbf9e088" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" template="error-ratio" baseline="2026-10-14T06:34:54.296337+00:00..2026-10-14T07:06:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.01063 min=0 max=0.07758 sd=0.02355
  baseline window: n=128 mean=0.01241 min=0 max=0.04871 sd=0.01688
```

> Evidence `tr_ffbcb564ba8c`:

```
<tool_result id="tr_ffbcb564ba8c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T07:31:39.216586+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-14T07:31:39.213Z)
2026-10-14T07:31:39.216856+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-14T07:31:39.216872+00:00      at new Promise (<anonymous>) {
2026-10-14T07:31:39.216876+00:00    code: 14,
```

> Evidence `tr_760e30cba380`:

```
<tool_result id="tr_760e30cba380" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-14T07:07:11.469522+00:00  [otel.javaagent 2026-10-14 07:07:11:464 +0000] [OkHttp http://otel-collector:4318/...] ERROR io.opentelemetry.exporter.internal.http.HttpExporter - Failed to export metrics. The request could not be executed. Full error message: otel-collector
2026-10-14T07:07:11.470194+00:00  java.net.UnknownHostException: otel-collector
2026-10-14T07:07:11.473373+00:00  	at java.base/java.net.InetAddress$CachedLookup.get(Unknown Source)
2026-10-14T07:07:11.473398+00:00  	at java.base/java.net.InetAddress.getAllByName0(Unknown Source)
```

> Evidence `tr_09ba07093f8b`:

```
<tool_result id="tr_09ba07093f8b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T07:36:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" radius="candidate_cause" hops="1">
service: ad
3 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T07:31:23.973773+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  4.9h before onset  2026-10-14T02:43:03.380349+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_f35faa930f7a`:

```
<tool_result id="tr_f35faa930f7a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T01:36:46.664000+00:00..2026-10-14T07:36:46.664000+00:00" template="error-ratio" baseline="2026-10-13T19:36:46.664000+00:00..2026-10-14T01:36:46.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1195 mean=0.009602 min=0 max=0.3809 sd=0.04391
  baseline window: n=1405 mean=0.004485 min=0 max=0.04348 sd=0.006626
```

## Dead ends worth keeping

Frontend change history is the natural first stop and costs time: two automated environment edits to a cart address setting, the second reverting the first, both about three hours before onset, no deploys or flag changes at all. That query also ran at radius zero, so six direct dependencies were never checked for changes — widening it is what eventually surfaced ad. Frontend traces returned ten clean traces with no error spans and roots of 4–24ms, with the dominant hop varying by journey and sometimes sitting in the load generator itself; the sample clusters between T-3m and T-50s and covers nothing at or after T+0, so its apparent health proves nothing about the incident. Ad traces mislead hardest: ad server spans present, 180–200ms, never error-marked, with errors only on the load-generator and proxy ingress spans at their ~15s timeout, and a client-side wait shrinking from hundreds of seconds to a clean 9ms trace. That sample sits early and reads as a resolved backlog; it is not evidence ad was healthy. Finally, ad logged collector DNS export failures around T-30m — background exporter errors that do not kill the JVM — and its only metric change point sits 5.5 hours before the reference time. Neither is the cause.

> Evidence `tr_590efece6aa1`:

```
<tool_result id="tr_590efece6aa1" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T07:36:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" radius="seed" hops="0">
service: frontend
2 changes, ranked by suspicion
  #1  2.9h before onset  2026-10-14T04:43:01.757364+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  3.0h before onset  2026-10-14T04:34:34.057124+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_f930e0347ee7`:

```
<tool_result id="tr_f930e0347ee7" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00">
service: frontend
10 trace(s) shown of 10 found, 143 spans; offsets are from each trace's root

trace 162a7b4035bd6fb0  root load-generator/user_browse_product  5.7ms  started 2026-10-14T07:33:43.055292+00:00  10 spans
  +0.0ms load-generator/user_browse_product 5.7ms [self 0.6ms]
```

> Evidence `tr_0d4a40446fe8`:

```
<tool_result id="tr_0d4a40446fe8" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00">
service: ad
8 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 54ce8f3a11635502  root load-generator/user_get_ads  15009.1ms  started 2026-10-14T07:06:05.050510+00:00  28 spans
  +0.0ms load-generator/user_get_ads 15009.1ms [self 1.0ms]
```

## Mechanism, confidence, and what stayed open

Automation lowered ad's container memory limit to 144m; about five minutes later ad began a roughly one-minute restart loop, dying silently and often before application init. A process that stops without emitting anything, repeatedly, just after its ceiling was tightened, is being killed from outside for exceeding that ceiling rather than crashing from within. With ad's listener absent for most of each cycle, frontend's calls failed at connect time, and frontend's aggregate error ratio barely moved because one unavailable dependency is a small share of its traffic. Confidence high; fix class is reverting the limit change. Still open: no runtime or kernel kill event was retrieved, so the memory-kill step is inferred rather than observed; nothing on this board maps 172.18.0.19:9555 to the ad container — that rests on the port and on ad being the only service looping; and ad's actual memory usage against the 144m ceiling was never measured.

> Evidence `tr_09ba07093f8b`:

```
<tool_result id="tr_09ba07093f8b" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T07:36:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" radius="candidate_cause" hops="1">
service: ad
3 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T07:31:23.973773+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  4.9h before onset  2026-10-14T02:43:03.380349+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_760e30cba380`:

```
<tool_result id="tr_760e30cba380" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-14T07:07:11.469522+00:00  [otel.javaagent 2026-10-14 07:07:11:464 +0000] [OkHttp http://otel-collector:4318/...] ERROR io.opentelemetry.exporter.internal.http.HttpExporter - Failed to export metrics. The request could not be executed. Full error message: otel-collector
2026-10-14T07:07:11.470194+00:00  java.net.UnknownHostException: otel-collector
2026-10-14T07:07:11.473373+00:00  	at java.base/java.net.InetAddress$CachedLookup.get(Unknown Source)
2026-10-14T07:07:11.473398+00:00  	at java.base/java.net.InetAddress.getAllByName0(Unknown Source)
```

> Evidence `tr_ffbcb564ba8c`:

```
<tool_result id="tr_ffbcb564ba8c" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T07:06:46.664000+00:00..2026-10-14T07:38:39.031663+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T07:31:39.216586+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-14T07:31:39.213Z)
2026-10-14T07:31:39.216856+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-14T07:31:39.216872+00:00      at new Promise (<anonymous>) {
2026-10-14T07:31:39.216876+00:00    code: 14,
```

