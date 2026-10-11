# Ad service disappears from the network; frontend and proxy alert downstream

## What a responder saw first

Pages arrived for frontend, frontend-proxy and ad, severity critical, with nine services in the blast radius. The visible symptom was at the caller: frontend logging gRPC status 14 UNAVAILABLE against a single peer, 172.18.0.19 port 9555, repeating every two to eight seconds. The detail line said no connection could be established and the socket error was host-unreachable. That is the useful discriminator — the client never got a TCP session, so there was no server-side work to be slow and no listener actively refusing. The peer was simply not there. Note also that the embedded error timestamp inside those lines is roughly two minutes older than the log line carrying it; the client is replaying a cached last-connection-error rather than dialling afresh each time, so the repetition rate tells you nothing about retry cadence.

> Evidence `tr_fe847d5db367`:

```
<tool_result id="tr_fe847d5db367" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-30T03:47:36.459958+00:00  Error: 5 NOT_FOUND: Product Not Found: OLJCESPC7Z
2026-09-30T03:47:36.460038+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-09-30T03:47:36.460043+00:00      at new Promise (<anonymous>) {
2026-09-30T03:47:36.460046+00:00    code: 5,
```

## Ordering the evidence

Take T+0 as the last second of ad traffic. Up to T+0 the ad service's own log is boring in the way you want: alternating targeted and non-targeted ad request handling, routine 'no baggage in context' notices, steady cadence of roughly one request every few seconds, no warnings, no stack traces, no thinning that would suggest a degradation ramp. At T+0 the log records a JVM shutdown hook stopping the gRPC ads server, then a line confirming the server is down. After that, nothing. The stream ends there, and since these were the newest lines retained for a window extending past T+5m, the silence is real and not a retention or truncation artifact. At roughly T+0 plus one second the change log shows platform-automation moving ad's image reference from unset to a 2.2.0 ad hotfix tag. By T+5m the frontend errors described above are in full flow. The shape is: the running replica was taken down in an orderly fashion, and nothing healthy came up on that address to replace it.

> Evidence `tr_fb2d7b15b665`:

```
<tool_result id="tr_fb2d7b15b665" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-09-29T13:08:34.608144+00:00  2026-09-29 13:08:34 - oteldemo.AdService - no baggage found in context trace_id=3904007ed2adda381529e2db40a6cd14 span_id=7629233f6a1e0d84 trace_flags=01 
2026-09-29T13:08:34.608179+00:00  2026-09-29 13:08:34 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=3904007ed2adda381529e2db40a6cd14 span_id=7629233f6a1e0d84 trace_flags=01 
2026-09-29T13:08:37.540900+00:00  2026-09-29 13:08:37 - oteldemo.AdService - no baggage found in context trace_id=f6e76a25577ed49db9e8bd0b9356c430 span_id=eec689222f8ca4f4 trace_flags=01 
2026-09-29T13:08:37.540946+00:00  2026-09-29 13:08:37 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=f6e76a25577ed49db9e8bd0b9356c430 span_id=eec689222f8ca4f4 trace_flags=01 
```

> Evidence `tr_2ab1b562f262`:

```
<tool_result id="tr_2ab1b562f262" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:33:25.487646+00:00" radius="seed" hops="0">
service: ad
23 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T12:25:30.406454+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  15m before onset  2026-10-06T12:14:50.022229+00:00  platform-automation  image reverted: image reference reverted on ad
```

> Evidence `tr_fe847d5db367`:

```
<tool_result id="tr_fe847d5db367" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-30T03:47:36.459958+00:00  Error: 5 NOT_FOUND: Product Not Found: OLJCESPC7Z
2026-09-30T03:47:36.460038+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-09-30T03:47:36.460043+00:00      at new Promise (<anonymous>) {
2026-09-30T03:47:36.460046+00:00    code: 5,
```

## Dead end: the metrics for ad

Two separate attempts to get metric baselines for ad came back empty, and both times the emptiness was meaningless. The backend returned HTTP 400 Bad Request — the query was rejected before evaluation. It is very tempting, mid-incident, to read 'no series returned' as 'the target was gone, which confirms the theory.' Do not. A rejected request returns nothing whether or not the instance existed. The second attempt was supposed to substitute an availability or restart-count query shape; the result came back tagged with the same error-ratio template and the same 400, which means the alternative shape was never actually executed. Consequently there is no observation at all for ad's error rate, latency percentiles, heap or CPU through the onset window. One small positive: a 400 is generated by the server, so the metrics backend was up and processing requests — it was not itself unreachable. But that is the only thing those two results establish.

> Evidence `tr_361e4ee9a7d6`:

```
<tool_result id="tr_361e4ee9a7d6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-22T12:30:31.664000+00:00..2026-09-29T12:30:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_361e4ee9a7d6>
```

> Evidence `tr_8e12a5739107`:

```
<tool_result id="tr_8e12a5739107" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-22T12:30:31.664000+00:00..2026-09-29T12:30:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_8e12a5739107>
```

## Dead end: the trace sample

A trace query against frontend over the full seven-day window returned ten traces, nine displayed, two hundred spans, truncated — and all of them clustered in a three-minute pocket about half an hour before onset. None carried an error status. The call graph in them is exactly what you would expect: frontend into product-catalog GetProduct, cart AddItem and GetCart, AdService GetAds, checkout PlaceOrder, with checkout fanning out normally; every downstream hop completes in single-digit milliseconds. Where a slow hop was attributed, it was usually self-time in the load-generator root span. This sample does not contain the failing minute at all, so it cannot name a failing edge and cannot clear any dependency for the onset window. What it is good for is ruling out two things a responder might otherwise chase: the topology had not changed, and the failure was not a continuous week-long condition.

> Evidence `tr_7944920ff440`:

```
<tool_result id="tr_7944920ff440" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00">
service: frontend
9 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 31914139a265fc9a  root load-generator/user_checkout_single  107.4ms  started 2026-10-06T11:53:27.895489+00:00  49 spans
  +0.0ms load-generator/user_checkout_single 107.4ms [self 37.2ms]
```

## Dead end: the deploy churn

The ad change history for the week is 23 entries, every one of them an image-reference change by the same automated actor, oscillating between setting a single hotfix tag and reverting it to unset. Thirteen of those flips happened in the three hours before onset, roughly one every ten to twenty minutes, the last about five minutes prior. This looks like a smoking gun until you notice that only one distinct image version appears across all 23 changes, and that a comparable burst of the same apply-and-revert pattern occurred roughly 39 to 50 hours earlier without this outcome. So the pre-onset change introduced no new code relative to prior healthy periods, the churn predates the incident, and 'a bad new release' is not supported. For the same reason, no configuration, environment-variable or flag mutation appears anywhere in the log for this service, and no human-initiated change appears either — it is all automation.

> Evidence `tr_2ab1b562f262`:

```
<tool_result id="tr_2ab1b562f262" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:33:25.487646+00:00" radius="seed" hops="0">
service: ad
23 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T12:25:30.406454+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  15m before onset  2026-10-06T12:14:50.022229+00:00  platform-automation  image reverted: image reference reverted on ad
```

## What we concluded

The ad service stopped existing on the network at T+0 and did not come back. Its teardown was orderly — a shutdown hook, not an abrupt crash, not an out-of-memory kill, not a panic — which is the signature of an externally driven stop such as a rollout or eviction. The deploy action one second later terminated the running replica and no healthy replacement appeared on that address, so the artifact that is supposed to be running is not running. The frontend and frontend-proxy alerts are caller-side propagation of the absent dependency, nothing more. Confidence is medium. The appropriate fix class is rollback: restore a known-good running replica rather than attempting to debug the image.

> Evidence `tr_fb2d7b15b665`:

```
<tool_result id="tr_fb2d7b15b665" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-09-29T13:08:34.608144+00:00  2026-09-29 13:08:34 - oteldemo.AdService - no baggage found in context trace_id=3904007ed2adda381529e2db40a6cd14 span_id=7629233f6a1e0d84 trace_flags=01 
2026-09-29T13:08:34.608179+00:00  2026-09-29 13:08:34 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=3904007ed2adda381529e2db40a6cd14 span_id=7629233f6a1e0d84 trace_flags=01 
2026-09-29T13:08:37.540900+00:00  2026-09-29 13:08:37 - oteldemo.AdService - no baggage found in context trace_id=f6e76a25577ed49db9e8bd0b9356c430 span_id=eec689222f8ca4f4 trace_flags=01 
2026-09-29T13:08:37.540946+00:00  2026-09-29 13:08:37 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=f6e76a25577ed49db9e8bd0b9356c430 span_id=eec689222f8ca4f4 trace_flags=01 
```

> Evidence `tr_2ab1b562f262`:

```
<tool_result id="tr_2ab1b562f262" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:33:25.487646+00:00" radius="seed" hops="0">
service: ad
23 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T12:25:30.406454+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  15m before onset  2026-10-06T12:14:50.022229+00:00  platform-automation  image reverted: image reference reverted on ad
```

> Evidence `tr_fe847d5db367`:

```
<tool_result id="tr_fe847d5db367" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-30T03:47:36.459958+00:00  Error: 5 NOT_FOUND: Product Not Found: OLJCESPC7Z
2026-09-30T03:47:36.460038+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-09-30T03:47:36.460043+00:00      at new Promise (<anonymous>) {
2026-09-30T03:47:36.460046+00:00    code: 5,
```

## Still open for the next responder

First and most important: did a replacement ad pod ever start? It could be crashlooping, stuck pulling the hotfix tag, or never scheduled at all, and we cannot distinguish these because no availability or restart metric was ever retrieved — both queries were rejected. Fixing the query path is the highest-value next step. Second, the attribution to ad rests on port convention plus the coincident shutdown; the frontend log names only an address and port, never a service name. Third, because the same tag was applied and reverted repeatedly earlier in the week without incident, the defect may well sit in the automation leaving zero replicas rather than in the image itself. If so, rolling back the tag alone will not prevent a recurrence.

> Evidence `tr_361e4ee9a7d6`:

```
<tool_result id="tr_361e4ee9a7d6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-22T12:30:31.664000+00:00..2026-09-29T12:30:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_361e4ee9a7d6>
```

> Evidence `tr_8e12a5739107`:

```
<tool_result id="tr_8e12a5739107" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-22T12:30:31.664000+00:00..2026-09-29T12:30:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_8e12a5739107>
```

> Evidence `tr_fe847d5db367`:

```
<tool_result id="tr_fe847d5db367" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:30:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-30T03:47:36.459958+00:00  Error: 5 NOT_FOUND: Product Not Found: OLJCESPC7Z
2026-09-30T03:47:36.460038+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__828d7226._.js:1:1058)
2026-09-30T03:47:36.460043+00:00      at new Promise (<anonymous>) {
2026-09-30T03:47:36.460046+00:00    code: 5,
```

> Evidence `tr_2ab1b562f262`:

```
<tool_result id="tr_2ab1b562f262" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-29T12:30:31.664000+00:00..2026-10-06T12:33:25.487646+00:00" radius="seed" hops="0">
service: ad
23 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T12:25:30.406454+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  15m before onset  2026-10-06T12:14:50.022229+00:00  platform-automation  image reverted: image reference reverted on ad
```

