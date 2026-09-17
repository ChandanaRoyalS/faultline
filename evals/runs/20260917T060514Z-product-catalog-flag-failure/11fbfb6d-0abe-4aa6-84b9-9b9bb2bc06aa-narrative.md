# Catalog lookups returning INTERNAL behind a feature flag

## What was visible, and the dead ends

The page named loadgenerator, frontend, and productcatalogservice at once, entry point frontend, seven services in radius, severity critical. Onset placed near 06:09; offsets below run from there.

The first instinct — confirm the surge in metrics — failed in a useful way. Both error-ratio baselines pointed the wrong direction. Frontend's aggregate error ratio fell from ~4.9% baseline mean to ~1.2% in the incident window, peak ~10% against a baseline peak of ~33%, with 129 samples in each window so no data gap. productcatalogservice was more emphatic: ~0.2% against a ~7% baseline, a factor of thirty the wrong way. Read literally, those two results close the incident. What matters for a later reader is that the metric is aggregate and unbroken by dependency, so a low-volume edge failing completely is invisible in it; and that only the error-ratio template came back — no latency percentiles, no CPU or memory — so the "is it slow" and "is it starved" halves were never actually measured. The elevated overnight ~7% belongs to the baseline window, not this incident.

Traces looked equally healthy: ten frontend-rooted traces, 94 spans, not one error status, roots 2.4ms to 26.0ms. The slowest was a 26.0ms checkout (PlaceOrder 24.2ms, shipping-quote path 8.6ms); the tool's nominated degrading hop at ~6.0ms is noise at this scale. Positively cleared and still clear: productcatalogservice is not slow (server spans ~0.0ms, the 0.9–3.4ms on frontend's client spans is frontend self time), cartservice and Redis are sub-millisecond, recommendationservice is not stalling downstream. Two caveats: no frontend→adservice span was sampled at all, so that edge is unsampled rather than cleared; and every returned trace clusters into 06:10:21–06:10:57 despite a window starting at 05:38.

adservice absorbed real attention and yielded nothing. Its change log holds four memory resource-limit adjustments by platform automation, two matched apply/revert pairs completing ~2.7h and ~1.9h before onset, the last being the revert — so no constraint was in force, and nothing landed within ~1.9h of onset. Its error-ratio series returned zero samples in both incident and baseline windows, so the series was never populated and the tool's "no sustained departure" verdict for it is vacuous.

> Evidence `tr_ab4785ce0d4c`:

```
<tool_result id="tr_ab4785ce0d4c" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" template="error-ratio" baseline="2026-09-17T05:06:31.886223+00:00..2026-09-17T05:38:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=129 mean=0.01152 min=0 max=0.1006 sd=0.02779
  baseline window: n=129 mean=0.04903 min=0 max=0.3296 sd=0.1037
```

> Evidence `tr_bb247e5cb0de`:

```
<tool_result id="tr_bb247e5cb0de" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-17T03:08:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" template="error-ratio" baseline="2026-09-17T00:06:31.886223+00:00..2026-09-17T03:08:45.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=729 mean=0.002109 min=0 max=0.1017 sd=0.01299
  baseline window: n=262 mean=0.06975 min=0 max=0.1875 sd=0.03368
```

> Evidence `tr_b8fd3c6f3d15`:

```
<tool_result id="tr_b8fd3c6f3d15" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00">
service: frontend
10 trace(s) shown of 10 found, 94 spans; offsets are from each trace's root

trace 533276e63cea43f2  root frontend/HTTP POST  26.0ms  started 2026-09-17T06:10:21.404010+00:00  48 spans
  +0.0ms frontend/HTTP POST 26.0ms [self 0.0ms]
```

> Evidence `tr_93af46dee0e9`:

```
<tool_result id="tr_93af46dee0e9" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-16T06:08:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" radius="candidate_cause" hops="1">
service: adservice
4 changes, ranked by suspicion
  #1  1.9h before onset  2026-09-17T04:12:03.153125+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
      memory=256m  ->  None
  #2  2.1h before onset  2026-09-17T04:02:25.341982+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
```

> Evidence `tr_2f7cde204b26`:

```
<tool_result id="tr_2f7cde204b26" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" template="error-ratio" baseline="2026-09-17T05:06:31.886223+00:00..2026-09-17T05:38:45.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## The log line that turned it (T+30m)

Frontend's own logs are the only mechanism-naming signal on the board. In the 06:10 portion of the window frontend repeatedly logs gRPC status 13 INTERNAL from the product catalog dependency, the detail text attributing the failure to a deliberately enabled 'fail' feature flag, recurring near 06:10:38 and 06:10:47 — sustained, not a blip.

The frames arise in the gRPC client status-receive callback, so frontend is reading a status handed to it by a remote peer: relaying, not originating. That structural detail moves the failing party to productcatalogservice and disposes of the alert's implication that frontend is broken. The status and detail also rule out a deadline or timeout (no such status appears) and any capacity or memory limit (no resource language in the returned lines).

A genuinely separate condition appeared earlier in the same window, ~05:54: a card-charging call failing with gRPC Unavailable on a refused TCP connection to a payment endpoint on port 50051. Different status, dependency and reason — not this incident, but worth knowing it happened.

Meanwhile productcatalogservice's own change history over a ~24-hour bracket returned empty — reachable and answering, so observed absence. No deploy correlates with onset, no config edit is recorded, and there is no change to roll back. That absence is consistent with the flag living in the separate FeatureFlagService visible in the trace tree.

> Evidence `tr_b041e95a699e`:

```
<tool_result id="tr_b041e95a699e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T05:54:48.108271+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-17T05:54:48.108295+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T05:54:48.108297+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T05:54:48.108298+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_41fdb1b0dad1`:

```
<tool_result id="tr_41fdb1b0dad1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T06:08:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_41fdb1b0dad1>
```

> Evidence `tr_b8fd3c6f3d15`:

```
<tool_result id="tr_b8fd3c6f3d15" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00">
service: frontend
10 trace(s) shown of 10 found, 94 spans; offsets are from each trace's root

trace 533276e63cea43f2  root frontend/HTTP POST  26.0ms  started 2026-09-17T06:10:21.404010+00:00  48 spans
  +0.0ms frontend/HTTP POST 26.0ms [self 0.0ms]
```

## Conclusion, fix, and open threads

productcatalogservice is the failing party: a feature flag governing its catalog lookups is set to a value that makes it return INTERNAL to callers, and the wrongness of that value is itself the failure. Frontend is a victim relaying it. Fix class is a configuration revert — flip the flag off. Do not restart and do not roll back a deploy; there is no recorded change to revert on the service, and nothing points at process or image state. Confidence: medium.

Three threads stay open. First and largest: the trace sample spans 06:10:21–06:10:57 with zero error spans across 94 spans, yet the flag-attributed errors are logged inside that same minute. Either the sampler misses the failing requests or the failing path is not the traced one. Unresolved, and the sole reason this is not filed at high confidence.

Second: productcatalogservice's logs were never actually read. The query used label value 'product-catalog-service' against a service named 'productcatalogservice'. The three-hour result was empty, but an empty answer under a mismatched selector proves nothing — window width was not the limiting factor, the label was. Re-run with the correct label; cheapest next step, and it would confirm or overturn the flag story from the callee side.

Third: where the flag lives, who set it and when are unestablished. No query was dispatched against the feature-flag service's own change history, so the 06:09 onset is not time-correlated to any recorded act.

> Evidence `tr_b041e95a699e`:

```
<tool_result id="tr_b041e95a699e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-17T05:54:48.108271+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-17T05:54:48.108295+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-17T05:54:48.108297+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-17T05:54:48.108298+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_b8fd3c6f3d15`:

```
<tool_result id="tr_b8fd3c6f3d15" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-17T05:38:45.583000+00:00..2026-09-17T06:10:59.279777+00:00">
service: frontend
10 trace(s) shown of 10 found, 94 spans; offsets are from each trace's root

trace 533276e63cea43f2  root frontend/HTTP POST  26.0ms  started 2026-09-17T06:10:21.404010+00:00  48 spans
  +0.0ms frontend/HTTP POST 26.0ms [self 0.0ms]
```

> Evidence `tr_e668a04490f1`:

```
<tool_result id="tr_e668a04490f1" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-09-17T03:08:45.583000+00:00..2026-09-17T06:10:59.279777+00:00">
no log lines matched {service="product-catalog-service"} over this window
</tool_result:tr_e668a04490f1>
```

> Evidence `tr_41fdb1b0dad1`:

```
<tool_result id="tr_41fdb1b0dad1" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-16T06:08:45.583000+00:00..2026-09-17T06:10:59.279777+00:00" radius="seed" hops="0">
no changes recorded for productcatalogservice over this window
</tool_result:tr_41fdb1b0dad1>
```

