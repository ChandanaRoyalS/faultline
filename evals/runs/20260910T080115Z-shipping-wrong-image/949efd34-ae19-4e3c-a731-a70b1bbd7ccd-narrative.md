# Partial checkout failures with no locally recorded cause

## What the record covers

Take T+0 as the start of the observation window we worked from; the alerts named checkoutservice, loadgenerator, and frontend, and the blast radius as drawn covered twelve services with four edges out of checkoutservice never measured at all. This record ends inconclusively. Read it for the order things were looked at and for the four dead ends, not for an answer — no evidence in hand names a failing mechanism, and the confidence in any story we could tell is low.

## First look: the error curve

The first thing visible was checkoutservice's own span-status error ratio. It sat near 1.4% through the opening minutes of the window, then stepped up around T+7m30s to a mean near 11%, roughly eightfold. A second crossing followed near T+28m. Two things about the shape mattered. It was bursty rather than a plateau — peaks near 29%, troughs returning to zero, with a standard deviation large relative to the mean. And the onset sat inside the window, so the first seven minutes were usable as a healthy comparison rather than something we had to guess at.

That curve ruled out several framings quickly. It was not baseline noise: the incident mean sat several baseline deviations above normal. It was not a total outage: the ratio never approached 1.0 and repeatedly returned to zero. It was not slow pre-existing drift that merely became noticeable: the change point was a step, with a quiet baseline immediately before it. And it was not a symptom belonging entirely to frontend or the gateway — the errors were recorded on checkoutservice's own spans, so checkout was genuinely participating.

> Evidence `tr_aeae36a96ac2`:

```
<tool_result id="tr_aeae36a96ac2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T07:34:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" template="error-ratio" baseline="2026-09-10T07:01:41.430286+00:00..2026-09-10T07:34:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=132 mean=0.1127 min=0 max=0.2857 sd=0.1216
  baseline window: n=132 mean=0.01379 min=0 max=0.1 sd=0.02516
```

## Second look: the service's own logs

With errors confirmed on checkoutservice's spans, the natural next move was to read its logs unfiltered across the whole window and expect a stack trace. There was none. Every line returned was info severity. No exceptions, no traceback text, no crash signature, and — importantly — no line naming an RPC target, a deadline, a status code, or a rejected field.

What the logs did show was a process that stayed alive. Early in the window a complete order pipeline appears end to end: order start, payment authorization with a transaction id, confirmation email, and a successful message write with an advancing offset. Order-start lines then continue at steady cadence to the last minute of the window, around T+33m. So the pod did not die, logging never stopped, and the service was demonstrably healthy at window start rather than already broken before we started watching.

One softer observation, and I flag it as weak: in the newest thirty or so lines, roughly T+30m onward, only order-start lines appear, with no accompanying payment-success, email-sent, or message-write lines. That is consistent with orders being entered and not completing. It is equally consistent with result truncation, since those later stages also log at info. Do not build on it.

The useful conclusion from this step is negative and worth keeping: span-status errors with no locally logged cause is the signature of a failure returned by, or waited on, something downstream. The culprit was never going to be readable off checkoutservice's log text. It has to come from traces or from peer-service logs.

> Evidence `tr_00b87ec6cc67`:

```
<tool_result id="tr_00b87ec6cc67" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:34:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:34:39.331053+00:00  {"message":"[PlaceOrder] user_id=\"148e75d0-acea-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:34:39.33095038Z"}
2026-09-10T07:34:39.334870+00:00  {"message":"[PlaceOrder] user_id=\"148ed408-acea-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:34:39.334745922Z"}
2026-09-10T07:34:39.351850+00:00  {"message":"payment went through (transaction_id: 51a2979a-b481-4aed-bf40-02e88a4078e4)","severity":"info","timestamp":"2026-09-10T07:34:39.351693339Z"}
2026-09-10T07:34:39.354483+00:00  {"message":"payment went through (transaction_id: 718ac2c1-9ce5-4d96-9ad7-e1f3161b132b)","severity":"info","timestamp":"2026-09-10T07:34:39.354391631Z"}
```

## Dead end one: the change log, queried twice, windowed wrong both times

Two separate change-history queries were run against checkoutservice. Both returned nothing at all — no deploys, no config edits, no flag flips. Both were also windowed from roughly T+30m forward, extending about twenty-four hours into the future, and both were scoped to the seed service with zero hops.

That combination makes the empty result almost worthless for the question that mattered. The window opens twenty-two minutes after the onset and runs the wrong direction. It never covers the hours before the step, and the zero-hop scope means no dependency's change history was consulted either.

What the empty result does legitimately establish is narrow: nothing landed on checkoutservice at or after the point where the window opens, so no post-onset change to the service itself is sustaining the behavior, and no unlogged remediation on checkoutservice explains any later recovery. It also confirms checkoutservice is a tracked entity in the change log rather than an unknown one — the tool answered cleanly instead of reporting no coverage — which means a re-query over the interval before onset should be productive. That re-query was never run. If you are picking this up, run it first.

> Evidence `tr_4b712b262c69`:

```
<tool_result id="tr_4b712b262c69" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T08:04:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_4b712b262c69>
```

> Evidence `tr_d96704f00c56`:

```
<tool_result id="tr_d96704f00c56" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T08:04:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_d96704f00c56>
```

## Dead end two: the single downstream probe returned nothing

Exactly one dependency was measured: cartservice, error ratio, same query shape as the one used on checkoutservice. It returned no samples — not in the incident window, and not in the preceding baseline window either.

The symmetry of that emptiness is the whole lesson. Because both windows are equally blank, the absence is best read as the series not existing for that service — no error-labelled call samples, or a label gap in instrumentation — rather than as a service that stopped reporting at onset. Specifically, this does not show cartservice crashing or losing scrape at T+7m30s, because the gap predates the window.

The trap here is treating a blank panel as a clean bill of health. It is not one. There is no measured step to compare against checkoutservice's, and no support for cartservice being the dependency whose errors propagated inward — but there is also no exclusion. And the probe covered cartservice alone. Productcatalog, shipping, email, ad, and recommendation were left entirely unmeasured, so the cross-dependency comparison that the log evidence pointed us toward was never actually performed.

> Evidence `tr_908f56a96829`:

```
<tool_result id="tr_908f56a96829" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T07:34:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" template="error-ratio" baseline="2026-09-10T07:01:41.430286+00:00..2026-09-10T07:34:30.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Where it stands and what to do next

The defensible statement is: checkoutservice began failing a bursty subset of requests at about T+7m30s, escalating again near T+28m; the failure is not in its own process; and the shape of the evidence points downstream, to a call that is either returning a failure or being waited on past a deadline. Which call, and which of those two it is, is not established.

Three gaps, in the order I would close them. First, re-query checkoutservice's change history over the hours before onset, backward from the step, not forward from the alert. Second, pull traces for the failing checkout spans, or the logs of its peers, to name the downstream call — checkoutservice's own logs will not tell you. Third, collect latency percentiles for checkoutservice and each dependency; without them, returned failures and timed-out waits look identical from where we sat, and the bursty on-off shape is compatible with both.

> Evidence `tr_aeae36a96ac2`:

```
<tool_result id="tr_aeae36a96ac2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T07:34:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" template="error-ratio" baseline="2026-09-10T07:01:41.430286+00:00..2026-09-10T07:34:30.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=132 mean=0.1127 min=0 max=0.2857 sd=0.1216
  baseline window: n=132 mean=0.01379 min=0 max=0.1 sd=0.02516
```

> Evidence `tr_00b87ec6cc67`:

```
<tool_result id="tr_00b87ec6cc67" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T07:34:30.583000+00:00..2026-09-10T08:07:19.735714+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T07:34:39.331053+00:00  {"message":"[PlaceOrder] user_id=\"148e75d0-acea-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:34:39.33095038Z"}
2026-09-10T07:34:39.334870+00:00  {"message":"[PlaceOrder] user_id=\"148ed408-acea-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T07:34:39.334745922Z"}
2026-09-10T07:34:39.351850+00:00  {"message":"payment went through (transaction_id: 51a2979a-b481-4aed-bf40-02e88a4078e4)","severity":"info","timestamp":"2026-09-10T07:34:39.351693339Z"}
2026-09-10T07:34:39.354483+00:00  {"message":"payment went through (transaction_id: 718ac2c1-9ce5-4d96-9ad7-e1f3161b132b)","severity":"info","timestamp":"2026-09-10T07:34:39.354391631Z"}
```

