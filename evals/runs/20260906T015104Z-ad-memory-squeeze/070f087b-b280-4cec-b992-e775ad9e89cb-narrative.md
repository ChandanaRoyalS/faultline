# Frontend Errors Traced to an Unreachable Ad Backend

## What was visible, in order

Frontend and loadgenerator paged together. The stated blast radius of seven services invited a broad connectivity theory that never held up.

Frontend was never down. Its error ratio averaged about 3.9% against a ~2.7% baseline in the preceding hour — roughly 1.4x, spiky rather than stepped, with standard deviation exceeding the mean in both windows and an incident-window peak (~0.34) indistinguishable from baseline. Two threshold crossings appeared, one sitting on the left edge of the window, meaning the elevated behaviour may have begun before the window opened.

Frontend logs showed Node.js gRPC client exceptions, status code 14 UNAVAILABLE, with a connection-never-established detail. Every stack frame sat in the grpc-js client and interceptor path. Outbound calls failing, not inbound logic. This ruled out an up-but-slow downstream (a deadline status looks different), and ruled out auth, TLS, or quota rejection (those carry different codes and populated metadata; these had empty metadata). It was not a transient blip either: identical lines bracketed both ends of the ~62-minute window. But the error objects named no target service or method, so attribution had to come from elsewhere. The log result was also truncated to the oldest 8 and newest 32 lines, so the suspected onset neighbourhood was never read directly.

Traces closed the gap. Exactly one failing outbound edge from frontend: AdService/GetAds, erroring at ~3.09s, with an errored frontend-side TCP connect child and no adservice server span anywhere in 200 sampled spans. The tight duration clustering points at a fixed client connect timeout, not variable server work. The error propagated up to the enclosing HTTP GET and the loadgenerator parent, which explains the second page.

> Evidence `tr_4c6a08670d5f`:

```
<tool_result id="tr_4c6a08670d5f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T00:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" template="error-ratio" baseline="2026-09-05T23:52:37.685883+00:00..2026-09-06T00:54:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=248 mean=0.03854 min=0 max=0.3374 sd=0.08422
  baseline window: n=248 mean=0.02724 min=0 max=0.3445 sd=0.07225
```

> Evidence `tr_00e747d11cb9`:

```
<tool_result id="tr_00e747d11cb9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T00:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-06T00:54:32.348254+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-06T00:54:32.348308+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-06T00:54:32.348311+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-06T00:54:32.348313+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_abbfdc44f8c6`:

```
<tool_result id="tr_abbfdc44f8c6" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-06T00:24:30.583000+00:00..2026-09-06T01:56:23.480117+00:00">
service: frontend
200 spans
  f2b64e51044ff596 checkoutservice/hipstershop.ShippingService/ShipOrder 0.8ms
  f2b64e51044ff596 shippingservice/hipstershop.ShippingService/ShipOrder 0.0ms
  f2b64e51044ff596 checkoutservice/hipstershop.CartService/EmptyCart 1.1ms
```

## Dead ends worth keeping

productcatalogservice was the obvious suspect by call volume. Its error ratio was exactly zero across 248 incident-window samples, identical to baseline — and a healthy zero, not a no-data zero, since the ratio evaluated to a defined value and therefore had a non-zero denominator. Every frontend GetProduct span had a matching sub-4ms server span.

cartservice's change history was the biggest time sink: twelve entries, all automated apply-and-revert pairs. A hotfix image was applied and reverted four times, the last revert ~59m before onset. A REDIS_ADDR override was added and removed, ending 30m before onset. Most temptingly, a traffic-shaping sidecar imposing a fixed 300ms egress delay was attached ~49m before onset and removed ~43m before. None of it was in effect at onset, and cart traces were clean — cartservice, its Redis calls, the whole checkout path, and recommendation/featureflag all completed error-free in single-digit milliseconds.

Frontend's own change log was empty for the full ~24h window, so there was nothing on frontend to roll back. Change queries for checkoutservice and recommendationservice also came back empty — but check the window before leaning on them: both started at the incident timestamp and ran forward, so they cover post-onset changes only and say nothing about the preceding hours.

> Evidence `tr_3c4f093b081e`:

```
<tool_result id="tr_3c4f093b081e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-06T00:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" template="error-ratio" baseline="2026-09-05T23:52:37.685883+00:00..2026-09-06T00:54:30.583000+00:00">
service: productcatalogservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="productcatalogservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="productcatalogservice"}[2m]))
  incident window: n=248 mean=0 min=0 max=0 sd=0
  baseline window: n=248 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_130ed30def5f`:

```
<tool_result id="tr_130ed30def5f" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T01:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" radius="candidate_cause" hops="1">
service: cartservice
12 changes, ranked by suspicion
  #1  30m before onset  2026-09-06T01:23:50.867384+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  35m before onset  2026-09-06T01:19:19.484680+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_4f143794a9b2`:

```
<tool_result id="tr_4f143794a9b2" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-05T01:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_4f143794a9b2>
```

## The change that lines up, and what is still open

adservice's change history held three entries, all automated, all adjustments to its memory cap. The latest lowered the cap to 256m about three minutes before onset, moving the service from no explicit limit to a capped state. The identical cap had been applied ~1.4h earlier and withdrawn ~1.3h earlier — a prior six-minute exposure. No deploys, no flag flips, no human operator.

The mechanism that fits: adservice was killed for running out of memory under a cap below its working set, leaving its listener intermittently absent, so frontend's connects failed at a fixed client timeout and the error surfaced to loadgenerator. Fix class is reverting that cap. Confidence medium, for three reasons.

First, no adservice-side telemetry was ever collected — no kill events, restart counts, memory metrics, or logs. The out-of-memory mechanism is inferred, not observed; collecting adservice pod events and memory usage is the cheapest way to settle it. Second, onset is not established: identical UNAVAILABLE errors appear about an hour before the cap was applied, and baseline error peaks match the incident window, so the ad edge may have been failing earlier. Third, why the automation repeatedly applies and withdraws this cap is unknown — a manual revert may simply be re-applied by the same loop.

> Evidence `tr_0815a617ef14`:

```
<tool_result id="tr_0815a617ef14" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-05T01:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" radius="candidate_cause" hops="1">
service: adservice
3 changes, ranked by suspicion
  #1  3m before onset  2026-09-06T01:51:08.951782+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  1.3h before onset  2026-09-06T00:38:09.946070+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

> Evidence `tr_abbfdc44f8c6`:

```
<tool_result id="tr_abbfdc44f8c6" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-09-06T00:24:30.583000+00:00..2026-09-06T01:56:23.480117+00:00">
service: frontend
200 spans
  f2b64e51044ff596 checkoutservice/hipstershop.ShippingService/ShipOrder 0.8ms
  f2b64e51044ff596 shippingservice/hipstershop.ShippingService/ShipOrder 0.0ms
  f2b64e51044ff596 checkoutservice/hipstershop.CartService/EmptyCart 1.1ms
```

> Evidence `tr_00e747d11cb9`:

```
<tool_result id="tr_00e747d11cb9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-06T00:54:30.583000+00:00..2026-09-06T01:56:23.480117+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-06T00:54:32.348254+00:00  Error: 14 UNAVAILABLE: No connection established
2026-09-06T00:54:32.348308+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-06T00:54:32.348311+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-06T00:54:32.348313+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

