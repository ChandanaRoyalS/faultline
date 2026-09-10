# Checkout completions stop while orders keep arriving

## What we were paged for

The page fired on frontend, loadgenerator and checkoutservice together, critical, with a blast radius eventually counted at twelve services. From the responder's chair the first impression was misleading: the alert text pointed at frontend, and frontend was where we spent the first several minutes. Nothing customer-visible looked like a hard outage — the great majority of requests were still succeeding — which made the severity feel wrong until the checkout log gap turned up. Four edges in the call graph between frontend and the eventual suspect are unmeasured, and that is worth remembering when reading anything below about ordering.

## Frontend first, and why it was a detour

We started at frontend because that is where the page pointed. The aggregate error ratio there did move, but modestly: roughly 1.0% to 1.2% mean against the prior baseline, about 1.25x. The interesting part was the shape, not the size — incident peaks near 30% against a baseline peak near 10%, with variance roughly doubled. Two change points were detected, the earlier at about T-11m and a second at about T-1m30s, both crossing the same threshold. That mattered for one reason: whatever started this was already underway before the moment we were paged, so the causal search window had to be pushed earlier. Two conclusions we had entertained died here. Frontend was not in a total outage — the mean stayed near 1%. And frontend was not cleanly masking a downstream problem either; its own errors were surfacing. But the query aggregated only by service name, with no downstream dimension, so it could not tell us which dependency was failing or in what order. No latency series came back at all. Frontend turned out to be a symptom: the caller timing out on a stalled path, not the origin.

> Evidence `tr_1791c8174aec`:

```
<tool_result id="tr_1791c8174aec" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T10:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" template="error-ratio" baseline="2026-09-10T08:01:43.872722+00:00..2026-09-10T10:03:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=489 mean=0.01198 min=0 max=0.3016 sd=0.04655
  baseline window: n=489 mean=0.009554 min=0 max=0.09867 sd=0.02323
```

## Ruling out change on the alerted services

Both change-history queries came back completely empty — no deploys, no config edits, no flag flips for frontend or for checkoutservice anywhere in a twenty-four hour window. This closed off the fastest remediation we had hoped for: there was nothing to roll back on either service, and no in-flight rollout to blame. One caveat on the frontend query specifically: the window it covered begins at the reference time and extends forward, so it is largely post-onset. Its emptiness rules out any remediation or rollback action on frontend after the fact, and it is consistent with there being no trigger, but it is not the pre-onset evidence we would have wanted. The checkoutservice window straddled onset properly and was still empty.

> Evidence `tr_3accd263f91b`:

```
<tool_result id="tr_3accd263f91b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T12:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_3accd263f91b>
```

> Evidence `tr_9dbf71894e33`:

```
<tool_result id="tr_9dbf71894e33" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T12:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_9dbf71894e33>
```

## The checkout log gap - the one piece that turned the investigation

This is the section to read if you read only one. Early in the log window, each order-entry line was followed within tens of milliseconds by three completion lines: payment, confirmation email, message-queue write. Late in the window, the order-entry lines continue at a steady cadence right through about T+2m — and the three completion lines are gone entirely. Not failing. Absent. There was no error or warn severity line anywhere near the page, no timeout or deadline text, no rejection, and no dependency named. That absence killed several hypotheses at once. checkoutservice had not crashed or restarted: entry lines kept arriving on schedule with no startup or panic output. It was not a validation or currency bug: orders in two currencies were accepted and logged identically with no rejection following. And it was not going to hand us the culprit's name, because it logs nothing about its downstream calls when they hang. The shape says requests are hanging inside a downstream call rather than failing fast. Important limitation: the result was truncated to the oldest eight and newest thirty-two lines of a roughly hour-long window, so we never actually saw the transition from healthy completion logging to entry-only logging. We inferred it from the two endpoints.

> Evidence `tr_924e7df4577b`:

```
<tool_result id="tr_924e7df4577b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T11:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T11:03:58.519055+00:00  {"message":"[PlaceOrder] user_id=\"526b6c42-ad07-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T11:03:58.518881333Z"}
2026-09-10T11:03:58.544187+00:00  {"message":"payment went through (transaction_id: d9076c01-43e8-4541-a5db-28b38f47f97e)","severity":"info","timestamp":"2026-09-10T11:03:58.544086875Z"}
2026-09-10T11:03:58.551296+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-10T11:03:58.551210541Z"}
2026-09-10T11:03:58.552851+00:00  {"message":"Successful to write message. offset: 30898","severity":"info","timestamp":"2026-09-10T11:03:58.552732666Z"}
```

## What the checkout metrics added

checkoutservice's error ratio was flat zero across every sample in the comparison window, standard deviation zero, then became nonzero with a mean near 6.7% and peaks to about 67%. New onset, not a worsening of something chronic — which disposed of the idea that we were merely noticing a long-standing error floor because a threshold moved. The single sustained crossing lands at about T-1m15s. High variance against a modest mean is the signature of intermittent bursts with many clean intervals, not a smooth monotonic climb, so a gradual-degradation story does not fit the curve. We also had to correct an earlier working assumption that errors had been sustained above threshold since well before the page; only the one crossing was detected, though isolated sub-threshold samples before it are not excluded. Two gaps: the comparison baseline supplied was about thirty-two minutes, not the two hours we asked for, and no latency percentiles or in-flight request counts came back. The stall is therefore inferred from log structure, never measured.

> Evidence `tr_10a8d40cdea2`:

```
<tool_result id="tr_10a8d40cdea2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:33:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" template="error-ratio" baseline="2026-09-10T11:01:43.872722+00:00..2026-09-10T11:33:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.06697 min=0 max=0.6667 sd=0.1947
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

## Following the first missing completion line

With no dependency named in any log, the only pointer we had was ordering: the first of the three completion lines to go missing is the payment confirmation, which places the stall at or before the charge call. That reasoning is the entire basis for naming paymentservice, and it is thin. We pulled paymentservice's change history and found eight entries, all environment-variable edits by platform automation, all touching the same telemetry exporter endpoint setting and nothing else. They form four identical set-then-revert pairs about eleven to twelve minutes apart, recurring roughly every six hours — a scheduled job, not a human. The closest is a revert about 5.2 hours before onset, returning the setting to unset, which is the same state it held during every quiet interval before. The last five hours before onset are empty of change entirely. So: no deploy, no flag, no routing or timeout or credential edit, nothing left misconfigured, and nobody to interview. This was a dead end for cause, but a useful one — it means if paymentservice is the stalled dependency, it got there without a recorded change.

> Evidence `tr_e9920e3d9337`:

```
<tool_result id="tr_e9920e3d9337" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T12:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" radius="candidate_cause" hops="1">
service: paymentservice
8 changes, ranked by suspicion
  #1  5.2h before onset  2026-09-10T06:53:18.190056+00:00  platform-automation  environment reverted: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT reverted on paymentservice
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4317  ->  None
  #2  5.4h before onset  2026-09-10T06:41:59.548640+00:00  platform-automation  environment updated: OTEL_EXPORTER_OTLP_TRACES_ENDPOINT updated on paymentservice
```

## Where we landed, and how much to trust it

Working conclusion: checkoutservice requests are hanging rather than failing, on a downstream call at or before payment, and the bursty error ratios at both checkoutservice and frontend are deadlines expiring on stalled calls. Fix class is a restart of the stalled dependency. Confidence is low and should stay low. The reasons: no latency percentiles were returned for any service, so the stall itself was never measured; paymentservice was never queried for logs or metrics at all, so attribution to it rests entirely on which completion line went missing first; and cartservice, currencyservice and emailservice remain unexcluded. Two blind spots in the timeline are worth naming for whoever picks this up. The truncated checkout logs hid the healthy-to-stalled transition. And frontend's earlier change point, roughly eleven minutes before the page, predates every piece of evidence we examined — nobody ever explained it. If this recurs, get latency percentiles and pull paymentservice logs before doing anything else.

> Evidence `tr_10a8d40cdea2`:

```
<tool_result id="tr_10a8d40cdea2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T11:33:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" template="error-ratio" baseline="2026-09-10T11:01:43.872722+00:00..2026-09-10T11:33:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=129 mean=0.06697 min=0 max=0.6667 sd=0.1947
  baseline window: n=129 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_1791c8174aec`:

```
<tool_result id="tr_1791c8174aec" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T10:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" template="error-ratio" baseline="2026-09-10T08:01:43.872722+00:00..2026-09-10T10:03:45.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=489 mean=0.01198 min=0 max=0.3016 sd=0.04655
  baseline window: n=489 mean=0.009554 min=0 max=0.09867 sd=0.02323
```

> Evidence `tr_924e7df4577b`:

```
<tool_result id="tr_924e7df4577b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T11:03:45.583000+00:00..2026-09-10T12:05:47.293278+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-10T11:03:58.519055+00:00  {"message":"[PlaceOrder] user_id=\"526b6c42-ad07-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-10T11:03:58.518881333Z"}
2026-09-10T11:03:58.544187+00:00  {"message":"payment went through (transaction_id: d9076c01-43e8-4541-a5db-28b38f47f97e)","severity":"info","timestamp":"2026-09-10T11:03:58.544086875Z"}
2026-09-10T11:03:58.551296+00:00  {"message":"order confirmation email sent to \"bill@example.com\"","severity":"info","timestamp":"2026-09-10T11:03:58.551210541Z"}
2026-09-10T11:03:58.552851+00:00  {"message":"Successful to write message. offset: 30898","severity":"info","timestamp":"2026-09-10T11:03:58.552732666Z"}
```

