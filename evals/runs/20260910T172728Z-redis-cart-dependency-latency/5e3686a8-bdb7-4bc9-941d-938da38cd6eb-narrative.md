# Frontend and checkout errors traced to a failure flag on the product catalog service

## How this reads

All times in this record are offsets from T+0, which is the change point detected in frontend's span error ratio. The page that started the investigation arrived at roughly T+21m. The seed handed to the responder was cartservice, and the blast radius was recorded as twelve services at warning severity, with four edges crossed that had no measurements behind them. The short version, up front: cartservice was a bystander. The mechanism sat one hop further out, in productcatalogservice, which was answering calls with a deliberate failure setting turned on. Confidence in that is medium, and the reasons it is not higher are in the last two sections.

## What was visible, in order

The first thing on the screen was the alert set: cartservice, frontend, loadgenerator, checkoutservice. That grouping suggests a checkout path problem and biases you toward the cart, which is exactly the trap here.

Working the seed first: the change log for cartservice over the prior day held twenty entries, every one attributed to platform automation, and every one half of an apply/revert pair — an image reference moved to a hotfix tag and moved back, a Redis address pointed at a non-default port and pointed back, and a traffic-shaping container attached to the cart network namespace and then removed. The nearest change before the page was a revert around T-56m; the image revert was roughly T-93m. Nothing was left applied at onset, and no human actor appears anywhere in the window.

Cartservice's own log stream showed unbroken routine work — add-item, get-cart, empty-cart handlers, several distinct user ids per second — running right through T+23m, with no error, panic, startup-failure, or cache-connection entries.

Frontend is where the signal actually lived. Its span error ratio jumped from a near-zero baseline to roughly 2.5% mean with peaks near 11.7%, about 183x baseline, with a single change point at T+0. The pattern was partial and intermittent: the majority of calls kept succeeding and the ratio repeatedly fell back to zero.

Frontend logs closed the loop. In the retained newest segment, around T+7m, every gRPC client error is status 13 INTERNAL returned by ProductCatalogService, with detail text naming a deliberately enabled failure feature flag on that service. The connection succeeded and the callee answered with an application-level error — which is what an intermittent, partial error ratio at the caller looks like.

> Evidence `tr_c6e0ceabaa1a`:

```
<tool_result id="tr_c6e0ceabaa1a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T17:31:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" radius="seed" hops="0">
service: cartservice
20 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-10T16:14:13.047585+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.4h before onset  2026-09-10T16:05:18.222902+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_2fc9d5d0535e`:

```
<tool_result id="tr_2fc9d5d0535e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T17:01:02.589677+00:00  AddItemAsync called with userId=34317294-ad39-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=10
2026-09-10T17:01:02.592204+00:00  GetCartAsync called with userId=34317294-ad39-11f1-b359-b6ed2071a170
2026-09-10T17:01:03.369575+00:00  GetCartAsync called with userId=
2026-09-10T17:01:03.675850+00:00  AddItemAsync called with userId=34d78b7a-ad39-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=3
```

> Evidence `tr_4056f8558e66`:

```
<tool_result id="tr_4056f8558e66" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" template="error-ratio" baseline="2026-09-10T16:29:08.903374+00:00..2026-09-10T17:01:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02518 min=0 max=0.1168 sd=0.04063
  baseline window: n=128 mean=0.0001377 min=0 max=0.002629 sd=0.000575
```

> Evidence `tr_e7f975aa47de`:

```
<tool_result id="tr_e7f975aa47de" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:46:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T16:57:48.523675+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T16:57:48.523721+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T16:57:48.523730+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T16:57:48.523731+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Conclusion

The failing mechanism is inside productcatalogservice: a configuration value that should not have been set — a failure feature flag left enabled — and the wrongness of that value is what breaks requests. Frontend and checkoutservice alerted because they are callers on that path and the error propagated toward them. Cartservice alerted alongside them but shows no internal distress of its own.

Fix class is a config revert: turn the flag off on productcatalogservice.

> Evidence `tr_e7f975aa47de`:

```
<tool_result id="tr_e7f975aa47de" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:46:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T16:57:48.523675+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T16:57:48.523721+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T16:57:48.523730+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T16:57:48.523731+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_4056f8558e66`:

```
<tool_result id="tr_4056f8558e66" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" template="error-ratio" baseline="2026-09-10T16:29:08.903374+00:00..2026-09-10T17:01:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02518 min=0 max=0.1168 sd=0.04063
  baseline window: n=128 mean=0.0001377 min=0 max=0.002629 sd=0.000575
```

## Dead ends, and why they are worth keeping

These consumed most of the investigation and none of them was the cause. Record them so the next responder spends the time elsewhere.

The cartservice hotfix image. Plausible on first read — a hotfix tag went live in the window. It was reverted roughly T-93m and was not in effect at onset.

The cartservice Redis address override. Also plausible; also paired with a revert, the last one around T-56m. A cache outage would additionally have surfaced as connection errors on the cart log stream, and did not.

Traffic shaping on the cart network namespace. Attached and removed; last removal roughly T-83m.

Cartservice as the origin. Its log stream is clean of error-severity output end to end. It was not crash-looping, not failing to start, and not cut off from its backing store.

Cartservice span metrics as an exoneration. This one is a genuine dead end rather than a ruled-out hypothesis: the error-ratio query returned no samples at all, in the incident window and in the preceding baseline alike. The series is simply absent for this service. That means you cannot read a spike from it, and equally you cannot read a traffic drop from it — the emptiness predates the incident and says nothing either way. Request rate, latency, and restart/readiness counts for the seed were never actually measured.

Checkoutservice changes. The change query came back empty, which at first looks like a clean exoneration. It is weaker than it appears: the query was scoped to the seed at zero hops, so callees were never examined, and its window started at the alert timestamp and ran forward, so the hours before onset — the interval the question was actually about — are uncovered.

The idea that degradation began at the start of the examined window. It did not; the only change point is at T+0, about nine minutes later, which is where any correlation search should anchor.

> Evidence `tr_c6e0ceabaa1a`:

```
<tool_result id="tr_c6e0ceabaa1a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T17:31:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" radius="seed" hops="0">
service: cartservice
20 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-10T16:14:13.047585+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.4h before onset  2026-09-10T16:05:18.222902+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_2fc9d5d0535e`:

```
<tool_result id="tr_2fc9d5d0535e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T17:01:02.589677+00:00  AddItemAsync called with userId=34317294-ad39-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=10
2026-09-10T17:01:02.592204+00:00  GetCartAsync called with userId=34317294-ad39-11f1-b359-b6ed2071a170
2026-09-10T17:01:03.369575+00:00  GetCartAsync called with userId=
2026-09-10T17:01:03.675850+00:00  AddItemAsync called with userId=34d78b7a-ad39-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=3
```

> Evidence `tr_ff732ad332a2`:

```
<tool_result id="tr_ff732ad332a2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" template="error-ratio" baseline="2026-09-10T16:29:08.903374+00:00..2026-09-10T17:01:00.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_c67453ea0428`:

```
<tool_result id="tr_c67453ea0428" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T17:31:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_c67453ea0428>
```

> Evidence `tr_4056f8558e66`:

```
<tool_result id="tr_4056f8558e66" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" template="error-ratio" baseline="2026-09-10T16:29:08.903374+00:00..2026-09-10T17:01:00.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=128 mean=0.02518 min=0 max=0.1168 sd=0.04063
  baseline window: n=128 mean=0.0001377 min=0 max=0.002629 sd=0.000575
```

## A second failure mode, unresolved

Around T-12m frontend logged a different failure entirely: a checkout charge-card call returning gRPC Unavailable because a TCP connection to a dependency on the payment path was refused. That is a transport-level failure against a different callee, and it is not the same thing as the catalog INTERNAL errors seen later. Its source service was never identified. Whether it recurred at the T+21m alert time — and therefore whether it, and not the catalog flag, is what actually paged checkoutservice — is unsettled.

> Evidence `tr_e7f975aa47de`:

```
<tool_result id="tr_e7f975aa47de" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:46:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T16:57:48.523675+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T16:57:48.523721+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T16:57:48.523730+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T16:57:48.523731+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

## Open questions for whoever picks this up

No dispatch ever touched productcatalogservice directly. Its change history, its logs, and its metrics are entirely unexamined. The flag is inferred solely from the detail text the callee returned, as seen by the caller. Which flag it is, who enabled it, and when, are all unknown; the T+0 change point comes from frontend metrics, not from any productcatalogservice change record.

Frontend emitted no log lines between T+7m and T+23m in the retained result, so there is no direct log evidence that the catalog failure was still the live mechanism at alert time. The elevated error ratio is the only bridge across that gap.

The cartservice log evidence is truncated — only the oldest eight and newest thirty-two lines were kept, leaving roughly T-9m to T+23m unviewed in the middle. The exoneration rests on the two ends of the stream.

Finally, the shape of the cartservice change history deserves a second look. Those apply/revert pairs recur on a roughly six-hour cadence, in bursts, all from platform automation. If the same automation also targets productcatalogservice, then the catalog flag is scheduled rather than accidental — and the correct remediation changes from reverting one value to disabling the schedule. Check that before declaring the revert sufficient.

> Evidence `tr_e7f975aa47de`:

```
<tool_result id="tr_e7f975aa47de" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T16:46:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T16:57:48.523675+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T16:57:48.523721+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T16:57:48.523730+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T16:57:48.523731+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_2fc9d5d0535e`:

```
<tool_result id="tr_2fc9d5d0535e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T17:01:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-10T17:01:02.589677+00:00  AddItemAsync called with userId=34317294-ad39-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=10
2026-09-10T17:01:02.592204+00:00  GetCartAsync called with userId=34317294-ad39-11f1-b359-b6ed2071a170
2026-09-10T17:01:03.369575+00:00  GetCartAsync called with userId=
2026-09-10T17:01:03.675850+00:00  AddItemAsync called with userId=34d78b7a-ad39-11f1-b359-b6ed2071a170, productId=1YMWWN1N4O, quantity=3
```

> Evidence `tr_c6e0ceabaa1a`:

```
<tool_result id="tr_c6e0ceabaa1a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T17:31:00.583000+00:00..2026-09-10T17:32:52.262626+00:00" radius="seed" hops="0">
service: cartservice
20 changes, ranked by suspicion
  #1  1.3h before onset  2026-09-10T16:14:13.047585+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.4h before onset  2026-09-10T16:05:18.222902+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

