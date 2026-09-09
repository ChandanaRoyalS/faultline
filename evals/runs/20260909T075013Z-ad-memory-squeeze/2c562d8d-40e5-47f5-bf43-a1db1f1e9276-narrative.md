# Frontend ad-panel gRPC calls failing UNAVAILABLE on unresolved adservice target

## What we saw first

Two alerts arrived together: frontend and loadgenerator. Blast radius was tallied at seven services and the severity was set critical, which framed the early minutes as a possible broad outage rather than a single broken edge. The starting point for the walk was frontend, because that is where the alert and the user-visible surface met. Nothing in the paging data told us which dependency was involved, and the loadgenerator alert was never separated from frontend's — it is still an open question whether it is purely a downstream echo or an independent signal.

## The metric that looked wrong and wasn't

The first substantive look was at frontend's error ratio over about a ninety-minute lookback. There is exactly one change point, about a minute before the reference time, where the ratio crosses the detection threshold and reaches roughly a tenth of all calls. That reads as a sharp late onset, and it is the reason the incident is timestamped where it is.

What that series could not do is more important than what it did. Across the whole incident window the mean error ratio sits at roughly half the baseline mean, and the peak is only modestly above the baseline peak — so in aggregate terms frontend was not behaving anomalously at all. Two hypotheses died here: a slow creeping degradation across the window (there is no upward drift before the change point) and an early-window regression such as a deploy near the start of the lookback (the only change point is late). A third died as a matter of instrumentation: the series carries only service and status-code labels, with no route or downstream peer dimension, so it can never tell you which dependency's call path carries the errors. Anyone reaching for this metric to do attribution will waste time.

> Evidence `tr_664069326583`:

```
<tool_result id="tr_664069326583" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T06:23:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" template="error-ratio" baseline="2026-09-09T04:51:17.799978+00:00..2026-09-09T06:23:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=368 mean=0.008195 min=0 max=0.133 sd=0.02472
  baseline window: n=368 mean=0.01496 min=0 max=0.1054 sd=0.02645
```

## Logs named the surface

Frontend's own logs are where the incident actually becomes legible. Errors begin roughly twenty-seven minutes ahead of the metric change point and are gRPC status code 14 UNAVAILABLE. The earliest retained lines describe a dropped connection and name no target, which is a trap — you cannot tell from them whether this is a transient network blip or something structural. By the end of the window, some twenty-nine minutes later, the same code 14 errors explicitly name a DNS name-resolution failure against the adservice gRPC target on port 9555.

Several things fell away on this evidence. Frontend is not failing in its own handlers: every retained error is a client-side status from the gRPC client call path, with frontend as the caller. The downstream is not up-and-rejecting — there is no application-level status such as a deadline or permission error, only UNAVAILABLE with resolution detail, meaning no response was ever received. It is not slowness on an established connection, because connections were never established. No dependency other than adservice is named anywhere in the retained lines. And it is not a blip: errors recur seconds apart from the start of the window to the end.

> Evidence `tr_71fa3376d57b`:

```
<tool_result id="tr_71fa3376d57b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T07:23:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-09T07:26:41.914627+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-09T07:26:41.914882+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-09T07:26:41.914887+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-09T07:26:41.914890+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Change logs: four services, four dead ends

We spent the change-history budget walking the neighbours, and all four came back negative in ways worth recording.

Frontend itself is change-quiet: no deploys, config edits, or flag toggles anywhere in a full day forward from onset. That kills the local-change theory in both directions — nothing triggered it and nothing remediated it.

Checkoutservice is likewise empty across the same day. Note the window shape: it begins at the onset timestamp and runs forward, so it does not cover the hour before onset. A change landing just before onset would sit outside the result. That caveat applies to all four queries.

Productcatalogservice has only platform-automation activity: a traffic-shaping container attached to the service's network namespace with a fixed 300ms delay and no jitter, then detached, twice — once the previous day and once beginning about 1.9h before onset and ending about 1.7h before. No deploy, no config mutation, no flag flip. Crucially the shaping was removed before onset, so the delay was not in force when the incident began; the relationship is proximity, not concurrency. An identical pair a day earlier shows this is a recurring automated pattern, not a one-off.

Cartservice has eighteen entries, all platform-automation, the earliest more than five hours after the window opens. They form matched update/revert pairs closing within eight to twelve minutes each: an image reference set and reverted, a REDIS_ADDR override to an alternate redis-cart port then reverted to unset, and a traffic-shaping attach then remove. The same three-part cycle repeats about 4h, 10-11h, and 13h before onset. The last change of any kind closed roughly four hours before onset and left the service on its original image, with REDIS_ADDR unset and no shaping in place. So the lingering-bad-image, lingering-bad-redis-address, and lingering-shaping theories are all closed by their own revert records.

The cumulative cost of these four queries is that the budget was exhausted before adservice — the one service the logs actually point at — was ever dispatched.

> Evidence `tr_d8e3a177e302`:

```
<tool_result id="tr_d8e3a177e302" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T07:53:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_d8e3a177e302>
```

> Evidence `tr_b6e5ce2f6564`:

```
<tool_result id="tr_b6e5ce2f6564" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-08T07:53:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_b6e5ce2f6564>
```

> Evidence `tr_8c54913ce706`:

```
<tool_result id="tr_8c54913ce706" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T07:53:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" radius="candidate_cause" hops="1">
service: productcatalogservice
4 changes, ranked by suspicion
  #1  1.7h before onset  2026-09-09T06:09:03.403533+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  1.9h before onset  2026-09-09T06:00:32.130376+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

> Evidence `tr_eae1db565371`:

```
<tool_result id="tr_eae1db565371" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T07:53:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" radius="candidate_cause" hops="1">
service: cartservice
18 changes, ranked by suspicion
  #1  4.0h before onset  2026-09-09T03:55:06.229346+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  4.1h before onset  2026-09-09T03:47:20.263939+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## Where it landed

The conclusion is narrow and low-confidence: frontend's ad-panel calls are failing continuously because the adservice endpoint is not resolvable — either its pods or its DNS record are absent — so every ad call fails before a connection exists. That is consistent with all retained frontend log lines and contradicted by none of them.

What is not settled is why. Whether the endpoint is missing because instances crashed, a rollout failed, or the target address configured in frontend is simply wrong is unobserved, and we chose to report the class as unknown rather than guess. No fix class is proposed.

> Evidence `tr_71fa3376d57b`:

```
<tool_result id="tr_71fa3376d57b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T07:23:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-09T07:26:41.914627+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-09T07:26:41.914882+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-09T07:26:41.914887+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-09T07:26:41.914890+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Open threads for whoever picks this up

Start with adservice. It was never dispatched at all: its change log, its logs, its pod state and readiness at onset are entirely unobserved. That single query is likely to convert this record from low to high confidence.

Then reconcile the two clocks. Frontend log errors begin about twenty-seven minutes before the metric change point. Either these are two distinct events, or one ongoing failure whose aggregate footprint only crossed the threshold late. The metric's lack of route labels means it cannot settle this; span- or route-level data can.

Third, explain the magnitude. If an entire dependency is unreachable, why does frontend's aggregate error ratio peak near a tenth and average below baseline? The likely answers are that ad calls are a minority path or that the panel degrades gracefully, but neither was verified.

Fourth, decide whether loadgenerator's alert is downstream of frontend or independent.

Fifth, and this is the thread I would not skip: the same platform-automation cycle that repeatedly attached and reverted shaping and config on productcatalogservice and cartservice may also have touched adservice. If it did, this is a manufactured condition rather than an organic one, and the whole record reads differently.

> Evidence `tr_71fa3376d57b`:

```
<tool_result id="tr_71fa3376d57b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-09T07:23:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-09T07:26:41.914627+00:00  Error: 14 UNAVAILABLE: Connection dropped
2026-09-09T07:26:41.914882+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-09T07:26:41.914887+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-09T07:26:41.914890+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_664069326583`:

```
<tool_result id="tr_664069326583" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-09T06:23:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" template="error-ratio" baseline="2026-09-09T04:51:17.799978+00:00..2026-09-09T06:23:15.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=368 mean=0.008195 min=0 max=0.133 sd=0.02472
  baseline window: n=368 mean=0.01496 min=0 max=0.1054 sd=0.02645
```

> Evidence `tr_8c54913ce706`:

```
<tool_result id="tr_8c54913ce706" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T07:53:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" radius="candidate_cause" hops="1">
service: productcatalogservice
4 changes, ranked by suspicion
  #1  1.7h before onset  2026-09-09T06:09:03.403533+00:00  platform-automation  container removed: traffic-shaping container removed from product-catalog-service's network namespace
      eth0 delay=300ms jitter=0ms  ->  None
  #2  1.9h before onset  2026-09-09T06:00:32.130376+00:00  platform-automation  container created: traffic-shaping container attached to product-catalog-service's network namespace
```

> Evidence `tr_eae1db565371`:

```
<tool_result id="tr_eae1db565371" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-08T07:53:15.583000+00:00..2026-09-09T07:55:13.366022+00:00" radius="candidate_cause" hops="1">
service: cartservice
18 changes, ranked by suspicion
  #1  4.0h before onset  2026-09-09T03:55:06.229346+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  4.1h before onset  2026-09-09T03:47:20.263939+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

