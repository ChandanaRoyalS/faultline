# Frontend ad-slot errors traced to an ad-service restart loop after an unreverted memory limit

## What we saw, in order

Two alerts opened the page: frontend and loadgenerator. Nothing else was paging, which already suggested something narrow.

The error-ratio series confirmed it. Frontend's error ratio was exactly zero across a 32-minute baseline — twenty samples, zero standard deviation. Then a single change point about two minutes before the alert, after which the ratio averaged roughly 2% with a peak near 9.6% and a minimum still touching zero. Abrupt, bursty, partial. Nine of every ten requests were still fine. That shape is one optional call in a composite page breaking, not a service falling over.

Traces contained exactly one error trace, and it was unambiguous: a frontend request toward AdService GetAds where a frontend-side tcp.connect span consumed about 3113ms of a 3119ms trace and carried the error. No adservice server span existed at all — the call never reached a listener. Successful AdService calls in the same window finished in single-digit milliseconds. Frontend's own logs agreed on mechanism: grpc-js client-side status 14 UNAVAILABLE, raised on the receive-status path, details describing a dropped or never-established connection, every stack frame inside the client library. But the payloads named no target service, host or method, so the attribution to adservice rests entirely on that one trace.

> Evidence `tr_f1cd77604556`:

```
<tool_result id="tr_f1cd77604556" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T08:27:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" template="error-ratio" baseline="2026-09-17T07:55:58.001872+00:00..2026-09-17T08:27:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=77 mean=0.02112 min=0 max=0.09607 sd=0.02975
  baseline window: n=20 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_51c35794df87`:

```
<tool_result id="tr_51c35794df87" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T08:27:45.583000+00:00..2026-09-17T08:59:33.164128+00:00">
service: frontend
20 trace(s) shown of 20 found, 110 spans; offsets are from each trace's root

trace a0ddde53e129b7ca  root frontend/HTTP GET  4.5ms  started 2026-09-17T08:38:53.515035+00:00  4 spans
  +0.0ms frontend/HTTP GET 4.5ms [self 0.6ms]
```

> Evidence `tr_5dbc89497852`:

```
<tool_result id="tr_5dbc89497852" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T08:27:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T08:47:33.394873+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T08:47:33.394923+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T08:47:33.394930+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T08:47:33.394932+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## The other end of the wire

adservice logs made it concrete. From roughly four minutes before onset the JVM emitted the same agent/VM boot banner triplet about a dozen times, with gaps lengthening from seconds to tens of seconds to about a minute — supervisor backoff on a container that keeps dying. No readiness or gRPC-server-started line appeared between attempts, so the process died at or before service initialisation. Around fifty minutes earlier the service had been serving normal ad requests, so this was a state change.

The change log supplied the trigger. Five adservice changes, all memory limit adjustments, all by platform-automation rather than a person. The one nearest onset lowered the limit to 256m seven seconds before the first failed boot and was never reverted — unlike two identical lower-then-revert cycles earlier the same morning. The absence of any OutOfMemoryError in stdout is consistent with this: the process is terminated externally before it can write a Java-level failure line.

Fix class: revert the configuration to the prior memory limit. Confidence medium.

> Evidence `tr_7e152c0bb12a`:

```
<tool_result id="tr_7e152c0bb12a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T07:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-17T08:05:37.182726+00:00  2026-09-17 08:05:37 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=c9db86c4466829606307d5d99717d564 span_id=12aa2d4e6718dc13 trace_flags=01 
2026-09-17T08:05:38.311868+00:00  2026-09-17 08:05:38 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=ab5c74fe628c9d4103746b9528c79692 span_id=dfcda3c46b3b2974 trace_flags=01 
2026-09-17T08:05:38.688536+00:00  2026-09-17 08:05:38 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=3bc1beb9486355f0915f5bc57765115c span_id=3377a2d61473e2de trace_flags=01 
2026-09-17T08:05:40.643202+00:00  2026-09-17 08:05:40 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=f65e88951d4aefa8376ac1b8055ae05e span_id=03d2e26e979a3451 trace_flags=01 
```

> Evidence `tr_7b7ab225733e`:

```
<tool_result id="tr_7b7ab225733e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T08:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" radius="candidate_cause" hops="1">
service: adservice
5 changes, ranked by suspicion
  #1  4m before onset  2026-09-17T08:53:39.022594+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  4.8h before onset  2026-09-17T04:12:03.153125+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

## Dead ends worth keeping

Frontend change history: empty. No deploys, config edits, or flag flips. Looking for a frontend rollback was reasonable and wrong — frontend noticed, it did not break.

Checkoutservice change history: also empty, including one hop out. Note the defect though — the window started at onset and ran forward, so it does not establish anything about the pre-onset period. The traces exonerated the checkout path independently (clean PlaceOrder at ~31ms), so the conclusion held, but do not lean on that empty result.

adservice metrics: a dead end of a different kind. The error-ratio query returned no samples in the incident window and none in the three-hour baseline either. The tempting read is "metrics stopped when the pod died," but the emptiness predates the incident by hours — the series simply is not collected. No samples is not a zero error ratio.

Also ruled out along the way: latency or deadline failures (the status is 14, not 4); auth and TLS rejections; cartservice, Redis, productcatalog, currency, payment and email, all returning in low single-digit milliseconds. And inside the checkout trace a frauddetectionservice span sits at ~+5017ms from the root while its parent publish span is 1.6ms — async queue consumption or clock skew, alarming in a waterfall view, not user-visible latency. Ignore it.

> Evidence `tr_8a9a5498eb41`:

```
<tool_result id="tr_8a9a5498eb41" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T08:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_8a9a5498eb41>
```

> Evidence `tr_fc2284852228`:

```
<tool_result id="tr_fc2284852228" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T08:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_fc2284852228>
```

> Evidence `tr_f69249aa4680`:

```
<tool_result id="tr_f69249aa4680" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T05:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" template="error-ratio" baseline="2026-09-17T02:55:58.001872+00:00..2026-09-17T05:57:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Open questions

No direct kill evidence was retrieved. Container-termination-reason, container_memory_working_set_bytes, and restart counters were never queried; the link from the 256m cap to the process death is inferred from a seven-second timing coincidence and the absence of a Java-level failure line. Pull those three first next time — one query would move this from medium to high.

One frontend UNAVAILABLE line sits about six minutes before the limit change and reports a dropped connection rather than a failure to connect. Unrelated blip, different dependency, or prior instability — unresolved. The log result was also truncated to the oldest 8 and newest 32 lines, so the interval containing the alert timestamp was never observed directly.

The automation has run this lower-then-revert cycle three times in one morning. Why this cycle's revert did not fire is unexplained and no owner was established, so a manual revert may be re-applied. Separately, whether 256m is too small under any load or only under current traffic was never determined — that decides between restoring the old limit and sizing a new one. Triage also reported one unmeasured edge crossed; which edge was never resolved.

> Evidence `tr_7e152c0bb12a`:

```
<tool_result id="tr_7e152c0bb12a" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T07:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-17T08:05:37.182726+00:00  2026-09-17 08:05:37 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=c9db86c4466829606307d5d99717d564 span_id=12aa2d4e6718dc13 trace_flags=01 
2026-09-17T08:05:38.311868+00:00  2026-09-17 08:05:38 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=ab5c74fe628c9d4103746b9528c79692 span_id=dfcda3c46b3b2974 trace_flags=01 
2026-09-17T08:05:38.688536+00:00  2026-09-17 08:05:38 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=3bc1beb9486355f0915f5bc57765115c span_id=3377a2d61473e2de trace_flags=01 
2026-09-17T08:05:40.643202+00:00  2026-09-17 08:05:40 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=f65e88951d4aefa8376ac1b8055ae05e span_id=03d2e26e979a3451 trace_flags=01 
```

> Evidence `tr_f69249aa4680`:

```
<tool_result id="tr_f69249aa4680" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T05:57:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" template="error-ratio" baseline="2026-09-17T02:55:58.001872+00:00..2026-09-17T05:57:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_5dbc89497852`:

```
<tool_result id="tr_5dbc89497852" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T08:27:45.583000+00:00..2026-09-17T08:59:33.164128+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T08:47:33.394873+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-17T08:47:33.394923+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T08:47:33.394930+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T08:47:33.394932+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

