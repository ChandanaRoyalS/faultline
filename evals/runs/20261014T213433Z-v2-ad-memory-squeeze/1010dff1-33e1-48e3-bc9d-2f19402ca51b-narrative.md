# Ad service restart loop surfacing as frontend gRPC UNAVAILABLE

## What was visible first

The page came from frontend and frontend-proxy, naming no downstream. Frontend's logs gave the shape within a few minutes: gRPC client errors, status 14 UNAVAILABLE, raised from the Next.js server bundle and surfacing as rejected promises. In the lines around the page the detail is a connect-level host-unreachable error against one address and port, 172.18.0.19:9555, with no connection ever established. The embedded last-error timestamps advance between samples (21:38:09, then 21:40:18), so these are fresh attempts failing repeatedly rather than one stale cached error.

That removed several readings immediately. Not frontend's own application logic: every error sampled is a transport status, with stack frames only at the client call site. Not a slow dependency hitting deadlines: there is no DEADLINE_EXCEEDED, the failure happens before a connection exists. Not name resolution: a concrete IP and port had already been resolved. And not broad: every alert-window error names the same single endpoint.

> Evidence `tr_54e3af93d73e`:

```
<tool_result id="tr_54e3af93d73e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:40:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T23:48:48.880349+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-07T23:48:48.881529+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T23:48:48.881546+00:00      at new Promise (<anonymous>) {
2026-10-07T23:48:48.881553+00:00    code: 14,
```

## The dead ends, in the order we hit them

Metrics were reached for first and wasted the most time. The error-ratio baseline for frontend returned empty with an HTTP 400 attached; the same template against ad did the same. These were rejections, not successful queries matching nothing. An empty payload from a rejected request is not evidence a service stopped emitting and cannot be used to date a cutoff. Twice the emptiness was briefly read as "ad went dark," and twice that was wrong. Neither query was ever repaired.

Traces were the subtler trap. Ten traces came back with no error spans at all across 117 spans, roots between ~4ms and ~67ms. Read naively, frontend looks healthy. But all ten start within a ~30-second band around 14:54 that day, hours before onset, despite a seven-day request. The sample misses the incident entirely. Check trace timestamps before trusting an all-green sample.

Frontend's change history looked like a lead and was not. All 16 changes are frontend environment-variable edits to one key by platform-automation, in set/revert pairs 6-10 minutes apart, repeating eight times over days. The last event before onset is a revert to baseline about an hour earlier, so the modified value was not in effect. No deploy, no release, no flag, no human actor. Background churn from a flapping reconciliation loop. Worth noting separately: UNAVAILABLE errors already exist at the oldest end of retention with a different detail, so that status alone is not new on frontend — only the unreachable-host mode is.

> Evidence `tr_5867cb77b5bf`:

```
<tool_result id="tr_5867cb77b5bf" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:40:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T21:40:31.664000+00:00..2026-10-07T21:40:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_5867cb77b5bf>
```

> Evidence `tr_ab9f73e6a1f0`:

```
<tool_result id="tr_ab9f73e6a1f0" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:40:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T21:40:31.664000+00:00..2026-10-07T21:40:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_ab9f73e6a1f0>
```

> Evidence `tr_df1f2335fc22`:

```
<tool_result id="tr_df1f2335fc22" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:40:31.664000+00:00">
service: frontend
10 trace(s) shown of 10 found, 117 spans; offsets are from each trace's root

trace 1ea7765c89e551a0  root load-generator/user_browse_product  23.6ms  started 2026-10-14T14:54:19.566259+00:00  10 spans
  +0.0ms load-generator/user_browse_product 23.6ms [self 2.3ms]
```

> Evidence `tr_80ad64f18b46`:

```
<tool_result id="tr_80ad64f18b46" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:42:32.839268+00:00" radius="seed" hops="0">
service: frontend
16 changes, ranked by suspicion
  #1  1.1h before onset  2026-10-14T20:36:20.363393+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  1.2h before onset  2026-10-14T20:27:28.512969+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

## Where it was, and what is still open

Following the endpoint led to ad. Its logs show four complete JVM cold starts at roughly 60-second spacing (~21:36:42, ~21:37:44, ~21:38:46, ~21:39:48), each reaching AdService startup and living about a minute. What is absent matters: no shutdown line, no stack trace, no fatal error dump, no bind failure, no in-process OutOfMemoryError. Only benign warnings. Each process stops mid-life and a new one begins — which rules out startup failure, an unhandled crash, a deploy or operator restart, and a one-off blip.

The trigger is in ad's change record: platform-automation lowered ad's memory limit to 144m at 21:34:38Z, five minutes before onset. The same lower/restore cycle recurs across the window, including three times in the preceding two hours, each restored. This one was not. All 33 changes are from the same automated actor; the only image changes are six days earlier and reverted; no scaling or config entries exist. Under that ceiling the JVM cannot stay resident and the container is terminated from outside; each teardown is what frontend's connect failures see. Fix class: revert the limit.

Open, and honestly so. The kill mechanism was never confirmed — exit codes, kernel and orchestrator events, and ad's working set against 144m were never retrieved. The 172.18.0.19:9555 to ad mapping is conventional, not evidenced. Six of the eight services in the blast radius were never dispatched to and both metric queries failed, so a broader shared cause with ad as one casualty is not excluded.

> Evidence `tr_03cb0064e103`:

```
<tool_result id="tr_03cb0064e103" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:40:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-07T21:41:03.461960+00:00  [otel.javaagent 2026-10-07 21:41:03:459 +0000] [OkHttp http://otel-collector:4318/...] ERROR io.opentelemetry.exporter.internal.http.HttpExporter - Failed to export metrics. The request could not be executed. Full error message: timeout
2026-10-07T21:41:03.462253+00:00  java.io.InterruptedIOException: timeout
2026-10-07T21:41:03.462765+00:00  	at okhttp3.internal.connection.RealCall.timeoutExit(RealCall.kt:461)
2026-10-07T21:41:03.462774+00:00  	at okhttp3.internal.connection.RealCall.callDone(RealCall.kt:423)
```

> Evidence `tr_6ddf31bc8b26`:

```
<tool_result id="tr_6ddf31bc8b26" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:42:32.839268+00:00" radius="candidate_cause" hops="1">
service: ad
33 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T21:34:38.294322+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  21m before onset  2026-10-14T21:19:15.053787+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_54e3af93d73e`:

```
<tool_result id="tr_54e3af93d73e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T21:40:31.664000+00:00..2026-10-14T21:40:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-07T23:48:48.880349+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-10-07T23:48:48.881529+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-07T23:48:48.881546+00:00      at new Promise (<anonymous>) {
2026-10-07T23:48:48.881553+00:00    code: 14,
```

