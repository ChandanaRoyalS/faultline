# Cart unreachable from frontend after an automated image reference update

## What the responder saw first

Paging started at the edge, not at the cause. Alerts fired on frontend-proxy and the load-generator; nothing paged for cart. Taking T0 as the moment the cart image reference was mutated by platform-automation, the first visible symptom lands within a minute and the first alert-worthy metric crossing about ninety seconds later.

The aggregate error ratio for frontend-proxy had been flat zero across the entire baseline hour — min, max and standard deviation all zero — then rose to roughly 6% mean in the incident window with a peak near 32%. frontend told the same story: zero baseline, a single change point at about T+1m30s, mean around 4.7%, peak near 32%. On both services the standard deviation exceeded the mean and the minimum returned to zero, so the signal was bursty rather than a clean step. That shape is worth remembering: it tempted an early read of load-correlated flapping, which turned out to be an artifact of partial traffic getting through while a dependency was absent.

> Evidence `tr_67e6575efc29`:

```
<tool_result id="tr_67e6575efc29" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T19:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T17:35:00.488554+00:00..2026-10-04T19:07:01.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=250 mean=0.06093 min=0 max=0.3235 sd=0.1079
  baseline window: n=12 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_0af772a00d1e`:

```
<tool_result id="tr_0af772a00d1e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T17:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T14:35:00.488554+00:00..2026-10-04T17:37:01.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=254 mean=0.04651 min=0 max=0.3178 sd=0.09913
  baseline window: n=14 mean=0 min=0 max=0 sd=0
```

## Following the error path down

frontend's logs collapsed the search quickly. Every retained error line was the same path: checkout's call to fetch the user cart returning gRPC code 13 INTERNAL wrapping an upstream Unavailable from cart. No other dependency — catalog, currency, payment — was named anywhere in the retained output.

The interesting detail is that the mode changed over the window. The earliest retained errors, around T+42s, are transport-level dial timeouts against a concrete cart IP and port: the name resolved, the endpoint simply did not accept the connection. By roughly T+10m to T+11m the errors are different — name resolution for cart returning zero addresses. Endpoints went unreachable first, then vanished from service discovery entirely.

> Evidence `tr_6cd2e801b1b2`:

```
<tool_result id="tr_6cd2e801b1b2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T19:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-04T20:12:18.147221+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 172.18.0.19:7070: i/o timeout"
2026-10-04T20:12:18.150284+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-04T20:12:18.150308+00:00      at new Promise (<anonymous>) {
2026-10-04T20:12:18.150313+00:00    code: 13,
```

## The cause

The cart change log over 24 hours contained exactly ten entries, all image reference updates or reverts, all by the same platform-automation actor. They pair up: an unset reference and a single cart hotfix tag, the same pair repeated five times. The pair adjacent to this incident sets the hotfix image at T0 and reverts it at about T+9m15s, bracketing the entire caller-side error window.

Cart's own metrics are the counter-intuitive part. Error ratio stayed near baseline — mean about 0.07%, max 1.2%, against a baseline of exactly zero across 122 samples, explicitly flagged as no sustained departure. But 24 incident-window samples had no defined value at all, versus zero such samples in the baseline. Cart was not erroring; cart was not serving. The absence of span traffic is the signal, and a responder scanning error-rate dashboards for a guilty service would have walked straight past it.

By about T+27m cart was logging a steady stream of normal cart-store operations across many user ids, consistent with the revert having taken effect.

> Evidence `tr_c1755292fd68`:

```
<tool_result id="tr_c1755292fd68" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-03T20:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" radius="outside_radius">
service: cart
10 changes, ranked by suspicion
  #1  16m before onset  2026-10-04T20:20:51.017159+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  25m before onset  2026-10-04T20:11:36.204570+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_54634ff874e2`:

```
<tool_result id="tr_54634ff874e2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T20:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T19:35:00.488554+00:00..2026-10-04T20:07:01.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=105 mean=0.0006655 min=0 max=0.0119 sd=0.002329
  baseline window: n=122 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_30aff810f573`:

```
<tool_result id="tr_30aff810f573" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-04T20:07:04.081009+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.081097+00:00        AddItemAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0, productId=OLJCESPC7Z, quantity=10
2026-10-04T20:07:04.082915+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.082942+00:00        GetCartAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0
```

## Dead ends and things that did not matter

Several lines of inquiry were opened and closed; keeping them is the point of this record.

Frontend as the originator. The change history for frontend was queried and came back completely empty — no deploys, no config edits, no flag events, no resource-limit edits. That closed frontend as a cause, but note the query window was mis-set: it started at the incident timestamp and ran forward 24h, so it never actually covered the hours before onset. The empty result is still useful (nothing landed during or after onset) but it is weaker than it first appeared. Separately, every frontend stack trace originated at the gRPC client boundary carrying an upstream status, which is a dependency report, not frontend logic breaking.

A pure service-discovery problem. Plausible given the zero-addresses lines, but the earliest errors show a resolved IP and port with a dial timeout. Addresses existed at onset; the zero-addresses condition is the later phase, not the trigger.

A slow or saturated cart being timed out. Also ruled out by the later phase — you cannot explain latency against a backend with no endpoints to dial.

Cart returning application errors. Never reached handler code; the Unavailable status sits at the connection and resolution layers.

Cart's backing store. The Valkey-backed cart store was logging successful reads and writes at both ends of the window, so store-side disruption did not persist and was not the mechanism.

A chronic pre-existing condition at either edge service. Both baselines were exactly zero with zero variance. Nothing was simply noticed late.

A human operator. All ten cart change entries are attributed to automation, not a person. And this was not a novel first rollout — the same tag had been applied and reverted four times roughly 11-12 hours earlier, in the same flapping pattern, with a long quiet gap in between. That earlier cluster did not correlate with the incident and consumed time before being set aside.

A hard total outage. Mean error ratios of 4.7% and 6% with peaks around 32% mean the large majority of requests still succeeded throughout. Severity was high because checkout was affected, not because everything was down.

> Evidence `tr_bb55f0743c5a`:

```
<tool_result id="tr_bb55f0743c5a" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-03T20:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" radius="candidate_cause" hops="1">
no changes recorded for frontend over this window
</tool_result:tr_bb55f0743c5a>
```

> Evidence `tr_6cd2e801b1b2`:

```
<tool_result id="tr_6cd2e801b1b2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T19:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-04T20:12:18.147221+00:00  Error: 13 INTERNAL: cart failure: failed to get user cart during checkout: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 172.18.0.19:7070: i/o timeout"
2026-10-04T20:12:18.150284+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__00d48b27._.js:1:1906)
2026-10-04T20:12:18.150308+00:00      at new Promise (<anonymous>) {
2026-10-04T20:12:18.150313+00:00    code: 13,
```

> Evidence `tr_30aff810f573`:

```
<tool_result id="tr_30aff810f573" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-04T20:07:04.081009+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.081097+00:00        AddItemAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0, productId=OLJCESPC7Z, quantity=10
2026-10-04T20:07:04.082915+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.082942+00:00        GetCartAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0
```

> Evidence `tr_c1755292fd68`:

```
<tool_result id="tr_c1755292fd68" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-03T20:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" radius="outside_radius">
service: cart
10 changes, ranked by suspicion
  #1  16m before onset  2026-10-04T20:20:51.017159+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  25m before onset  2026-10-04T20:11:36.204570+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_67e6575efc29`:

```
<tool_result id="tr_67e6575efc29" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T19:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T17:35:00.488554+00:00..2026-10-04T19:07:01.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=250 mean=0.06093 min=0 max=0.3235 sd=0.1079
  baseline window: n=12 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_0af772a00d1e`:

```
<tool_result id="tr_0af772a00d1e" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T17:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T14:35:00.488554+00:00..2026-10-04T17:37:01.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=254 mean=0.04651 min=0 max=0.3178 sd=0.09913
  baseline window: n=14 mean=0 min=0 max=0 sd=0
```

## What remains unobserved

The link from image reference to endpoint loss is inferred from timing and caller symptoms, not observed directly. Cart's logs for the critical ten-minute span were truncated away — the query returned only the oldest 8 and newest 32 lines, and the period of interest falls entirely inside the dropped middle. So the artifact's actual behaviour (crash on start, failed readiness, kill) is unknown. The retained segments contain no error lines and end healthy, which partially but not fully closes the possibility of fatal logging at the moment things went dark.

No pod availability, restart count, or CPU/memory data was fetched for cart. Only the error-ratio template was evaluated. A memory kill or crash loop on the new image would look identical from the caller's seat, and that remains indistinguishable on the evidence gathered.

frontend-proxy shows a second threshold crossing at roughly T+23m30s, after the revert and after frontend's retained errors stop. No per-route or per-upstream dimension was available on the proxy metric — only the binary error filter, no status-code breakdown, no latency percentiles — so this crossing has no explanation. One edge in the dependency graph was never measured. If this recurs, start there.

> Evidence `tr_30aff810f573`:

```
<tool_result id="tr_30aff810f573" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-04T20:07:04.081009+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.081097+00:00        AddItemAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0, productId=OLJCESPC7Z, quantity=10
2026-10-04T20:07:04.082915+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.082942+00:00        GetCartAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0
```

> Evidence `tr_54634ff874e2`:

```
<tool_result id="tr_54634ff874e2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T20:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T19:35:00.488554+00:00..2026-10-04T20:07:01.664000+00:00">
service: cart
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="cart"}[5m]))
  incident window: n=105 mean=0.0006655 min=0 max=0.0119 sd=0.002329
  baseline window: n=122 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_67e6575efc29`:

```
<tool_result id="tr_67e6575efc29" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T19:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" template="error-ratio" baseline="2026-10-04T17:35:00.488554+00:00..2026-10-04T19:07:01.664000+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=250 mean=0.06093 min=0 max=0.3235 sd=0.1079
  baseline window: n=12 mean=0 min=0 max=0 sd=0
```

## Resolution and confidence

Resolution was a rollback: platform-automation reverted the image reference at about T+9m15s, and cart was serving normally by roughly T+27m. No responder action was required or recorded.

Confidence is medium. The bracketing of the caller-side error window by the update/revert pair is tight and the symptom chain is coherent, but the mechanism inside cart was never seen, and the recurring automation loop that produced this pair five times in a day is itself unexplained and is the real follow-up.

> Evidence `tr_c1755292fd68`:

```
<tool_result id="tr_c1755292fd68" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-03T20:37:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" radius="outside_radius">
service: cart
10 changes, ranked by suspicion
  #1  16m before onset  2026-10-04T20:20:51.017159+00:00  platform-automation  image reverted: image reference reverted on cart
      ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2  ->  None
  #2  25m before onset  2026-10-04T20:11:36.204570+00:00  platform-automation  image updated: image reference updated on cart
```

> Evidence `tr_30aff810f573`:

```
<tool_result id="tr_30aff810f573" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:07:01.664000+00:00..2026-10-04T20:39:02.839446+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart"}
2026-10-04T20:07:04.081009+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.081097+00:00        AddItemAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0, productId=OLJCESPC7Z, quantity=10
2026-10-04T20:07:04.082915+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-10-04T20:07:04.082942+00:00        GetCartAsync called with userId=2ae2df76-c02f-11f1-a7e5-d6e82b74dde0
```

