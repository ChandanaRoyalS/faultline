# Shipping path serving the wrong container artifact

## What we saw first

The page named checkoutservice as the origin, severity critical, at what this record treats as T+0. Within about three minutes five more services lit up together: accountingservice, emailservice, frauddetectionservice, quoteservice and shippingservice. Eleven services fell inside the declared blast radius. The shape of the alert set — a caller plus a shipping/quote pair plus three order-side consumers — was the only real signal at the start; nothing in the alert text distinguished a checkout problem from a downstream one.

Because checkoutservice was the named origin, that is where the first two hours of work went. In hindsight that was the wrong chair to sit in, but it was the reasonable one.

## The checkoutservice dead end

Three independent looks at checkoutservice all came back clean, and this is the part of the record worth keeping.

The change log for checkoutservice was empty across a window starting at onset and running roughly a day forward: no deploys, no config or flag edits, no dependency repointing, and no post-onset remediation. So the intuitive story — checkout shipped something bad and it broke at T+0 — was dead early.

The error-rate metric was more subtly misleading. Aggregate error ratio in the incident window was statistically indistinguishable from the two hours before it: mean moved about four percent, identical min and max, and slightly *lower* variance. A change point was reported, but it sat exactly on the first sample of the window, which makes it an artifact of where we drew the boundary rather than a transition. The series is spiky in both windows and hits the same peak in each, consistent with intervals where only a handful of calls were sampled. Note the limitation, because it bit us: the query aggregated by service name only, so there was no per-RPC-method or per-downstream-target breakdown, and no latency or request-rate series at all.

Logs told the same story from another angle. checkoutservice was still accepting and logging PlaceOrder calls at a steady cadence right through the end of the window, roughly one every few seconds, USD and CAD only. No error or warn lines, no named host:port targets, no field-rejection messages, no restart or shutdown banners. Two hypotheses died here — that checkout was logging downstream connection failures we could follow, and that checkout had crashed or stopped serving. But the result was truncated: only the oldest eight lines and newest thirty-two survived, so the interval containing onset itself was never actually observed. We were reading around the hole.

> Evidence `tr_efbc29cfaecc`:

```
<tool_result id="tr_efbc29cfaecc" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T14:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_efbc29cfaecc>
```

> Evidence `tr_3a6d36c988e6`:

```
<tool_result id="tr_3a6d36c988e6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T12:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" template="error-ratio" baseline="2026-09-10T10:37:51.489274+00:00..2026-09-10T12:42:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=500 mean=0.06405 min=0 max=0.6667 sd=0.1396
  baseline window: n=500 mean=0.06134 min=0 max=0.6667 sd=0.1869
```

> Evidence `tr_2f526671f154`:

```
<tool_result id="tr_2f526671f154" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T12:42:48.283541+00:00  {"message":"[PlaceOrder] user_id=\"20ddbf64-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:42:48.28345305Z"}
2026-09-10T12:42:59.969676+00:00  {"message":"[PlaceOrder] user_id=\"27d63a26-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:42:59.969509958Z"}
2026-09-10T12:43:02.502740+00:00  {"message":"[PlaceOrder] user_id=\"294cf87c-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:43:02.502420459Z"}
2026-09-10T12:43:13.324580+00:00  {"message":"[PlaceOrder] user_id=\"2fca5104-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:43:13.324473798Z"}
```

## The cartservice detour

cartservice looked promising for a while because its change history was busy — twenty entries, all from a single automation actor, no human or pipeline author anywhere. Three kinds of mutation appeared: a container image reference, a REDIS_ADDR environment override, and a traffic-shaping sidecar attached to the cart network namespace with a fixed egress delay. Each of these was tempting on its own; each was also matched by a revert.

The pairs repeat as four near-identical cycles spread over about a day. Every applied change has a corresponding undo, and the most recent revert of any kind completed roughly 1.9 hours before onset. The image override was live for about ten minutes per cycle, last ending ~2.6h before onset; the delay sidecar was removed ~2.2h before onset. So nothing on cartservice was in effect when the incident began, and there is nothing on cartservice to roll back. The whole branch closed.

One thing this query did not do: it covered cartservice only, so productcatalogservice was left unanswered here and had to be asked separately.

> Evidence `tr_c1d1e350769a`:

```
<tool_result id="tr_c1d1e350769a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T14:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" radius="candidate_cause" hops="1">
service: cartservice
20 changes, ranked by suspicion
  #1  1.9h before onset  2026-09-10T12:45:53.653662+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  2.1h before onset  2026-09-10T12:37:19.842008+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## productcatalogservice: empty, and narrowly asked

The change history for productcatalogservice returned nothing — no deploys, no config edits, no dependency-endpoint changes, no post-onset remediation. That closes several hypotheses at one hop from the eventual cause.

Read the window before trusting the emptiness. It begins exactly at onset and runs about a day forward; it does not look backward. A change that landed earlier and was still in effect at T+0 would be invisible to this query. That is a real gap, not a formality.

> Evidence `tr_8760e94b17eb`:

```
<tool_result id="tr_8760e94b17eb" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T14:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8760e94b17eb>
```

## Where it actually was

shippingservice's change history is what turned the investigation. Fifteen changes, all from the same automation actor, arranged in a repeating cycle: a dependency-endpoint override applied then reverted, followed by an image reference update applied then reverted, recurring roughly every five to six hours across the day.

Two entries matter. First, an endpoint override pointing shippingservice's quote lookup at a non-existent host was set about 26 minutes before onset and reverted about 13 minutes before onset. That was the more attractive candidate on first read and it is ruled out on timing — the window closed before T+0, so it was not in effect. Second, and decisively: an image reference update landed at T-3m, repointing shippingservice at an adservice-tagged demo image, and unlike the three preceding cycles this one was never reverted. It was the only change in effect anywhere in the investigated radius at onset.

That reading makes the alert set coherent. A shippingservice pod running the adservice binary cannot serve the shipping RPCs — GetQuote and ShipOrder — which explains shippingservice and its quote dependency alerting together, and the order-side consumers (accounting, email, frauddetection) alerting about three minutes later. checkoutservice alerted first not because it was broken but because it is the caller that notices, which is consistent with its flat aggregate error ratio and its uninterrupted accepted-order logs.

Fix class is rollback: restore the correct shippingservice image reference. Confidence medium, for the reasons below.

> Evidence `tr_412929c4514d`:

```
<tool_result id="tr_412929c4514d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T14:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" radius="seed" hops="0">
service: shippingservice
15 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T14:39:44.841367+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-10T14:29:07.842064+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

> Evidence `tr_3a6d36c988e6`:

```
<tool_result id="tr_3a6d36c988e6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T12:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" template="error-ratio" baseline="2026-09-10T10:37:51.489274+00:00..2026-09-10T12:42:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=500 mean=0.06405 min=0 max=0.6667 sd=0.1396
  baseline window: n=500 mean=0.06134 min=0 max=0.6667 sd=0.1869
```

> Evidence `tr_2f526671f154`:

```
<tool_result id="tr_2f526671f154" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T12:42:48.283541+00:00  {"message":"[PlaceOrder] user_id=\"20ddbf64-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:42:48.28345305Z"}
2026-09-10T12:42:59.969676+00:00  {"message":"[PlaceOrder] user_id=\"27d63a26-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:42:59.969509958Z"}
2026-09-10T12:43:02.502740+00:00  {"message":"[PlaceOrder] user_id=\"294cf87c-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:43:02.502420459Z"}
2026-09-10T12:43:13.324580+00:00  {"message":"[PlaceOrder] user_id=\"2fca5104-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:43:13.324473798Z"}
```

## What a later responder should not assume is settled

The conclusion rests entirely on a change record. No metrics, logs, or traces were ever collected for shippingservice itself, so the wrong-artifact story has not been confirmed by observed shipping errors, crash-looping, or missing RPC handlers. Get that data before treating this record as closed.

The three earlier cycles applied the same anomalous image reference and were reverted. It is unsettled whether those earlier applications produced the same symptom signature — if they did, that is strong confirmation; if they passed unnoticed, the causal chain needs rethinking. Those cycles are free controls and nobody used them.

The user-visible symptom that fired the critical origin alert is still unexplained, because checkoutservice's aggregate error ratio did not move and the metric query returned no per-method, per-target, latency or request-rate breakdown.

Why accountingservice, emailservice, frauddetectionservice and quoteservice all alerted at the same instant is untested. A shared alert evaluation interval, an order-pipeline stall behind them, or a common cause upstream of all four remain distinguishable only with data not gathered.

Finally, five edges in the triage graph were never crossed, and only six services were queried. A cause outside that set is not excluded, and the productcatalogservice query looked only forward from onset.

> Evidence `tr_3a6d36c988e6`:

```
<tool_result id="tr_3a6d36c988e6" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T12:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" template="error-ratio" baseline="2026-09-10T10:37:51.489274+00:00..2026-09-10T12:42:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=500 mean=0.06405 min=0 max=0.6667 sd=0.1396
  baseline window: n=500 mean=0.06134 min=0 max=0.6667 sd=0.1869
```

> Evidence `tr_2f526671f154`:

```
<tool_result id="tr_2f526671f154" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T12:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T12:42:48.283541+00:00  {"message":"[PlaceOrder] user_id=\"20ddbf64-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:42:48.28345305Z"}
2026-09-10T12:42:59.969676+00:00  {"message":"[PlaceOrder] user_id=\"27d63a26-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:42:59.969509958Z"}
2026-09-10T12:43:02.502740+00:00  {"message":"[PlaceOrder] user_id=\"294cf87c-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:43:02.502420459Z"}
2026-09-10T12:43:13.324580+00:00  {"message":"[PlaceOrder] user_id=\"2fca5104-ad15-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T12:43:13.324473798Z"}
```

> Evidence `tr_8760e94b17eb`:

```
<tool_result id="tr_8760e94b17eb" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T14:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" radius="candidate_cause" hops="1">
no changes recorded for productcatalogservice over this window
</tool_result:tr_8760e94b17eb>
```

> Evidence `tr_412929c4514d`:

```
<tool_result id="tr_412929c4514d" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T14:42:45.583000+00:00..2026-09-10T14:47:39.676726+00:00" radius="seed" hops="0">
service: shippingservice
15 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T14:39:44.841367+00:00  platform-automation  image updated: image reference updated on shippingservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice
  #2  13m before onset  2026-09-10T14:29:07.842064+00:00  platform-automation  environment reverted: QUOTE_SERVICE_ADDR reverted on shippingservice
```

