# Partial PlaceOrder stalls at checkoutservice with unidentified slow downstream

## Summary for the next responder

checkoutservice began failing a minority of PlaceOrder requests. The artifact and configuration of checkoutservice itself are not implicated: nothing shipped to it, it stayed alive, and it kept accepting well-formed traffic throughout. What stopped happening is completion — a synchronous call made inside PlaceOrder, at or before the payment step, stopped returning. Requests hang; a fraction of them time out and surface as errors. The blast radius reached fourteen services and seven raised alerts (checkoutservice, loadgenerator, frontend, accountingservice, emailservice, frauddetectionservice, quoteservice), which is the shape you expect when a single hot synchronous path stalls. The specific slow downstream was never identified. Confidence in the conclusion is low and no fix was applied. Read the dead-end section before spending time re-treading it.

> Evidence `tr_7bebc6f2bf4e`:

```
<tool_result id="tr_7bebc6f2bf4e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:13:37.877720+00:00  {"message":"[PlaceOrder] user_id=\"24ad7b12-ace7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:13:37.877603963Z"}
2026-09-10T07:13:37.896848+00:00  {"message":"payment went through (transaction_id: 481b1ad6-4eec-4fad-81d9-520c68358f9a)","severity":"info","timestamp":"2026-09-10T07:13:37.896763255Z"}
2026-09-10T07:13:37.901773+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T07:13:37.901657672Z"}
2026-09-10T07:13:37.902594+00:00  {"message":"Successful to write message. offset: 28954","severity":"info","timestamp":"2026-09-10T07:13:37.902509213Z"}
```

> Evidence `tr_c5f5bea387ac`:

```
<tool_result id="tr_c5f5bea387ac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" template="error-ratio" baseline="2026-09-10T06:39:54.543543+00:00..2026-09-10T07:13:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=135 mean=0.03924 min=0 max=0.2778 sd=0.08922
  baseline window: n=135 mean=0.01469 min=0 max=0.1 sd=0.0237
```

## What was visible, in order

Take T+0 as the error-ratio change point on checkoutservice. For the twenty-eight minutes before it, the service sat at its usual ~1.5% error ratio — non-zero, with occasional excursions to ~10%, which is normal here and is worth remembering before you chase small numbers. At T+0 exactly one change point was detected, and the ratio stepped up to average ~3.9% with peaks near 27.8% and much wider variance than baseline. Around T+1m45s the incident was flagged. At T+2m the log signature changed: from that point through the end of the observed window, order-placement start entries appear alone. In the healthy portion earlier in the window each start was followed within about 25ms by three completion entries — payment, confirmation email, and the queue write. After T+2m the starts continue at a steady cadence, one per request, with none of the three followers. The last entry seen is at roughly T+5m, still a start, still well-formed.

> Evidence `tr_c5f5bea387ac`:

```
<tool_result id="tr_c5f5bea387ac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" template="error-ratio" baseline="2026-09-10T06:39:54.543543+00:00..2026-09-10T07:13:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=135 mean=0.03924 min=0 max=0.2778 sd=0.08922
  baseline window: n=135 mean=0.01469 min=0 max=0.1 sd=0.0237
```

> Evidence `tr_7bebc6f2bf4e`:

```
<tool_result id="tr_7bebc6f2bf4e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:13:37.877720+00:00  {"message":"[PlaceOrder] user_id=\"24ad7b12-ace7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:13:37.877603963Z"}
2026-09-10T07:13:37.896848+00:00  {"message":"payment went through (transaction_id: 481b1ad6-4eec-4fad-81d9-520c68358f9a)","severity":"info","timestamp":"2026-09-10T07:13:37.896763255Z"}
2026-09-10T07:13:37.901773+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T07:13:37.901657672Z"}
2026-09-10T07:13:37.902594+00:00  {"message":"Successful to write message. offset: 28954","severity":"info","timestamp":"2026-09-10T07:13:37.902509213Z"}
```

## How the conclusion was reached

Three things pin the failure to a downstream stall rather than to checkoutservice. First, errors are partial: even at peak roughly three quarters of calls still returned non-error status, so this is degradation, not an outage or a crash loop. Second, intake is healthy: the start entries keep arriving at a steady rate with ordinary currency values identical in shape to the baseline entries, so the divergence sits downstream of intake, not at it. Third, the payment-success entry is itself among the missing ones — so the request is not getting past payment and then falling over at email or the queue write; it stalls at or before payment. Notably, checkoutservice logs no error or warning line at all in the window. The failure is silent from the caller's side, which is why the downstream had to be identified from traces or the callee, and never was.

> Evidence `tr_7bebc6f2bf4e`:

```
<tool_result id="tr_7bebc6f2bf4e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:13:37.877720+00:00  {"message":"[PlaceOrder] user_id=\"24ad7b12-ace7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:13:37.877603963Z"}
2026-09-10T07:13:37.896848+00:00  {"message":"payment went through (transaction_id: 481b1ad6-4eec-4fad-81d9-520c68358f9a)","severity":"info","timestamp":"2026-09-10T07:13:37.896763255Z"}
2026-09-10T07:13:37.901773+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T07:13:37.901657672Z"}
2026-09-10T07:13:37.902594+00:00  {"message":"Successful to write message. offset: 28954","severity":"info","timestamp":"2026-09-10T07:13:37.902509213Z"}
```

> Evidence `tr_c5f5bea387ac`:

```
<tool_result id="tr_c5f5bea387ac" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" template="error-ratio" baseline="2026-09-10T06:39:54.543543+00:00..2026-09-10T07:13:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=135 mean=0.03924 min=0 max=0.2778 sd=0.08922
  baseline window: n=135 mean=0.01469 min=0 max=0.1 sd=0.0237
```

## Dead ends — read this first

A change to checkoutservice. A change-history query scoped to checkoutservice over a full 24-hour window returned nothing of any kind: no deploys, no config edits, no flag flips. There is no in-window rollout to correlate with onset, nothing to roll back, and no repeated change that would explain persistence. Caveat below.

The cartservice change cycle. The only change activity anywhere nearby is 26 entries, all on cartservice, all attributed to platform-automation, forming a self-reverting cycle that repeats every three to four hours: an image reference set to a hotfix tag and reverted, a traffic-shaping sidecar attached to the cart-service network namespace with a fixed egress delay and then removed, and a REDIS_ADDR override pointed at an alternate port and then reverted. All three attributes were back at baseline well before onset — image ~2.2h prior, sidecar ~1.9h prior, REDIS_ADDR ~1.6h prior — and the nearest event to onset was a revert, not an introduction. There were no changes at all in the last 1.6 hours before T+0. This is a very attractive lead and it does not hold at the timestamps.

Paymentservice as the confirmed culprit. The obvious next step was paymentservice error ratio. That series returned no samples at all — not in the incident window and not in the preceding baseline. Do not read that as flat and healthy, and do not read it as telemetry cutting out at onset either; the emptiness predates onset, so it is an instrumentation gap. Paymentservice health is genuinely unknown.

A sibling change propagating in. The same change query covering productcatalogservice, adservice, recommendationservice, paymentservice, currencyservice and shippingservice returned no entries for any of them across the whole window.

A human operator. Every change entry found was automation on a regular schedule.

> Evidence `tr_0bb613f4937e`:

```
<tool_result id="tr_0bb613f4937e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T07:43:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_0bb613f4937e>
```

> Evidence `tr_2b5e71e89dd5`:

```
<tool_result id="tr_2b5e71e89dd5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T07:43:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" radius="candidate_cause" hops="1">
service: cartservice
26 changes, ranked by suspicion
  #1  1.6h before onset  2026-09-10T06:09:40.566912+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.7h before onset  2026-09-10T06:00:31.603555+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

> Evidence `tr_41901647c03a`:

```
<tool_result id="tr_41901647c03a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" template="error-ratio" baseline="2026-09-10T06:39:54.543543+00:00..2026-09-10T07:13:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where the evidence is thin

Three holes, each of which could change the answer. (1) The checkoutservice log result was silently truncated to the oldest eight and newest thirty-two lines, leaving roughly T-28m through T+2m unobserved; any error line in that stretch is invisible, and that stretch contains the change point. (2) The change-history query scoped to checkoutservice started at the point of interest rather than before it, so a change landing in the minutes just before T+0 is not excluded by the empty result. (3) Whether the cartservice automation cycle fired again near T+0 in a way the change log did not record is not established — the cycle's period is roughly three to four hours and the last recorded event was 1.6 hours prior, so the arithmetic is suggestive but not conclusive.

> Evidence `tr_7bebc6f2bf4e`:

```
<tool_result id="tr_7bebc6f2bf4e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:13:37.877720+00:00  {"message":"[PlaceOrder] user_id=\"24ad7b12-ace7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:13:37.877603963Z"}
2026-09-10T07:13:37.896848+00:00  {"message":"payment went through (transaction_id: 481b1ad6-4eec-4fad-81d9-520c68358f9a)","severity":"info","timestamp":"2026-09-10T07:13:37.896763255Z"}
2026-09-10T07:13:37.901773+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T07:13:37.901657672Z"}
2026-09-10T07:13:37.902594+00:00  {"message":"Successful to write message. offset: 28954","severity":"info","timestamp":"2026-09-10T07:13:37.902509213Z"}
```

> Evidence `tr_0bb613f4937e`:

```
<tool_result id="tr_0bb613f4937e" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T07:43:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_0bb613f4937e>
```

> Evidence `tr_2b5e71e89dd5`:

```
<tool_result id="tr_2b5e71e89dd5" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T07:43:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" radius="candidate_cause" hops="1">
service: cartservice
26 changes, ranked by suspicion
  #1  1.6h before onset  2026-09-10T06:09:40.566912+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
      REDIS_ADDR=redis-cart:6380  ->  None
  #2  1.7h before onset  2026-09-10T06:00:31.603555+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
```

## What to do next

The single unanswered question is which synchronous callee inside PlaceOrder stopped returning. No trace-level evidence and no callee-side latency evidence was gathered for paymentservice, cartservice, currencyservice or shippingservice — that is the first move, and traces are the right tool because the caller logs nothing. Second, re-run the checkoutservice log query with a narrow window around T-2m to T+1m and a severity filter, to defeat the truncation and see whether anything was logged before the divergence. Third, extend the change query to start well before onset. Fourth, fix the paymentservice error-ratio instrumentation gap; five unmeasured edges were crossed in this investigation and that one sits directly on the suspected path.

> Evidence `tr_41901647c03a`:

```
<tool_result id="tr_41901647c03a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" template="error-ratio" baseline="2026-09-10T06:39:54.543543+00:00..2026-09-10T07:13:30.583000+00:00">
service: paymentservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="paymentservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="paymentservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

> Evidence `tr_7bebc6f2bf4e`:

```
<tool_result id="tr_7bebc6f2bf4e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:13:30.583000+00:00..2026-09-10T07:47:06.622457+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:13:37.877720+00:00  {"message":"[PlaceOrder] user_id=\"24ad7b12-ace7-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:13:37.877603963Z"}
2026-09-10T07:13:37.896848+00:00  {"message":"payment went through (transaction_id: 481b1ad6-4eec-4fad-81d9-520c68358f9a)","severity":"info","timestamp":"2026-09-10T07:13:37.896763255Z"}
2026-09-10T07:13:37.901773+00:00  {"message":"order confirmation email sent to \"mark@example.com\"","severity":"info","timestamp":"2026-09-10T07:13:37.901657672Z"}
2026-09-10T07:13:37.902594+00:00  {"message":"Successful to write message. offset: 28954","severity":"info","timestamp":"2026-09-10T07:13:37.902509213Z"}
```

