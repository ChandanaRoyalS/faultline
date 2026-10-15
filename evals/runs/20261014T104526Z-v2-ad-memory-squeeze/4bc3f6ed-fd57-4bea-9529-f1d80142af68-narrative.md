# Frontend errors traced to a single unreachable gRPC peer on the ad path

## What the responder saw first

The page came from frontend and frontend-proxy. The first thing worth checking was whether the frontend was actually falling over, and it was not. Over the ~32 minute window the frontend's error ratio averaged 0.042 against a baseline mean of 0.025 — about 1.67x up, peaking at 0.093. That shape matters: it is elevated but nowhere near a total outage, and it never locked into a flat high state. It wobbled. The practical read from the responder's chair is that most request paths were fine and one class of path was failing, so the question was immediately "which dependency?" rather than "is the frontend broken?".

> Evidence `tr_45251a674f30`:

```
<tool_result id="tr_45251a674f30" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T10:20:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" template="error-ratio" baseline="2026-10-14T09:48:47.940458+00:00..2026-10-14T10:20:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.04223 min=0 max=0.09263 sd=0.03238
  baseline window: n=128 mean=0.0253 min=0 max=0.07841 sd=0.02475
```

## The frontend logs name exactly one peer

Frontend logs across the whole window are a single repeating story: gRPC UNAVAILABLE (code 14) against one address, 172.18.0.19 on port 9555. No other dependency appears anywhere in the error lines. The errors were already present at T+0 and were still arriving at the end of the window, with the embedded last-error timestamp advancing — so this was continuous, not a blip. The stack frames point at a Promise wrapper around an outbound call, not at frontend logic, which is what let us set aside an internal frontend defect early.

One detail that is not fully explained and should not be smoothed over: early in the window the socket error is ECONNREFUSED, and by roughly T+32m it has become EHOSTUNREACH. Refused means a host is up with nothing listening on that port. Unreachable means the host or the route to it is gone. A simple kill-and-restart loop on the callee explains the first but not cleanly the second. Whoever picks this up next should start there.

> Evidence `tr_7aa78830adfe`:

```
<tool_result id="tr_7aa78830adfe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T10:20:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T10:20:47.489024+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-14T10:20:33.363Z)
2026-10-14T10:20:47.489042+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-14T10:20:47.489043+00:00      at new Promise (<anonymous>) {
2026-10-14T10:20:47.489061+00:00    code: 14,
```

## Traces: a long, productive dead end

The trace sample (10 traces, 174 spans) was the biggest time sink and ultimately pointed the wrong way. It flagged product-catalog as the slow hop in four traces, contributing 28–40% of trace self-time in GetProduct calls, and product-reviews in two more, including one where the AI assistant response consumed 88% of trace self-time. Cart and checkout were explicitly clean — sub-millisecond to low-millisecond — with their flagged hops attributed to frontend call overhead or load-generator self-time.

None of that was the incident. It is ordinary latency texture, and chasing product-catalog burned effort. The genuinely informative result from the traces was a negative one: the ad hop does not appear in any trace at all. The trace analysis recorded this as "the ad service is not involved," which is the exactly wrong conclusion to draw from a span that is missing because the call never completed. A caller that cannot open a connection produces no callee span. Absence here is the symptom, not the exoneration. Read trace absence against the log evidence, not instead of it.

> Evidence `tr_04ece1c3b26b`:

```
<tool_result id="tr_04ece1c3b26b" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-14T10:20:46.664000+00:00..2026-10-14T10:52:45.387542+00:00">
service: frontend
10 trace(s) shown of 10 found, 174 spans; offsets are from each trace's root

trace ee991309c898101b  root load-generator/user_get_recommendations  30.9ms  started 2026-10-14T10:51:03.481854+00:00  25 spans
  +0.0ms load-generator/user_get_recommendations 30.9ms [self 0.7ms]
```

## Frontend change history: ruled out

The frontend change log over the preceding day shows only environment-variable churn: CART_ADDR set to cart:7071 and reverted twice, the second cycle completing about 2.3 h before onset. Net state at onset was CART_ADDR unset — its normal value — so nothing was left misconfigured. No deploys, no flag edits, no timeout or pool changes. All four edits came from platform-automation rather than a person. This was checked carefully and contributed nothing; record it so the next responder does not re-walk it.

> Evidence `tr_6db3d124a420`:

```
<tool_result id="tr_6db3d124a420" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T10:50:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" radius="seed" hops="0">
service: frontend
4 changes, ranked by suspicion
  #1  2.3h before onset  2026-10-14T08:32:57.576559+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  2.4h before onset  2026-10-14T08:24:32.568719+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

## The ad service change history

This is where the record turns. The ad service's change log contains seven entries, all from platform-automation, all resource-limit edits — no deploys, no scale-downs, no removals. An automated policy has been repeatedly clamping the service's memory limit to 144m and then restoring it: at least four cycles in the preceding hours (roughly 02:34/02:43, 07:31/07:42, 10:20/10:31, and then 10:45). The last clamp landed about five minutes before onset and the matching restore never arrived.

That sequence matches the symptom at the caller. A callee repeatedly killed for exceeding a tightened memory cap stops accepting on its port; the caller sees refused connections on a host that is otherwise present. Port 9555 is the ad service's conventional port, which is how 172.18.0.19 was attributed.

> Evidence `tr_e28af516e347`:

```
<tool_result id="tr_e28af516e347" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T10:50:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" radius="candidate_cause" hops="1">
service: ad
7 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T10:45:30.816718+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  19m before onset  2026-10-14T10:31:41.977071+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

## The ad-side evidence that does not actually cover the incident

Two ad-side investigations came back reassuring and should be read with care, because both were run over the six-hour pre-incident baseline (03:50–09:50), not over the incident window itself.

The metric comparison found the ad service serving traffic throughout, with an error ratio below baseline (0.004 vs 0.010) and undefined-sample gaps no more frequent than normal. The log pull found 40 lines of routine ad-request handling spanning nearly the full six hours, with no startup banner, no shutdown message, no crash signal.

Both are true and both describe a healthy service before the failure. Neither says anything about 10:20–10:52. The "ad service is fine" conclusion drawn from them is a window mismatch, and it nearly closed the investigation on the wrong note.

> Evidence `tr_48b01b06585b`:

```
<tool_result id="tr_48b01b06585b" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T03:50:46.664000+00:00..2026-10-14T09:50:46.664000+00:00" template="error-ratio" baseline="2026-10-13T21:50:46.664000+00:00..2026-10-14T03:50:46.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1361 mean=0.003992 min=0 max=0.02857 sd=0.00546
  baseline window: n=1204 mean=0.00965 min=0 max=0.3809 sd=0.0438
```

> Evidence `tr_9071767761cf`:

```
<tool_result id="tr_9071767761cf" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T03:50:46.664000+00:00..2026-10-14T09:50:46.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-14T03:50:50.271125+00:00  2026-10-14 03:50:50 - oteldemo.AdService - no baggage found in context trace_id=5418f9bd6ea904dd993449697cfc6d32 span_id=90d09317d25d036e trace_flags=01 
2026-10-14T03:50:50.271192+00:00  2026-10-14 03:50:50 - oteldemo.AdService - no baggage found in context trace_id=972f36ac2ac8e99ccc5a3de929d55d52 span_id=4395fe025dcd02d4 trace_flags=01 
2026-10-14T03:50:50.271522+00:00  2026-10-14 03:50:50 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=5418f9bd6ea904dd993449697cfc6d32 span_id=90d09317d25d036e trace_flags=01 
2026-10-14T03:50:50.271711+00:00  2026-10-14 03:50:50 - oteldemo.AdService - Targeted ad request received for [books] trace_id=972f36ac2ac8e99ccc5a3de929d55d52 span_id=4395fe025dcd02d4 trace_flags=01 
```

## Where it landed, and what is still open

Conclusion, held at medium confidence: the frontend is a victim. The automated memory-limit clamp on the ad service, applied ~5 minutes before onset and never restored, left the callee unable to stay up and accept connections; only ad-bearing request paths failed, which is why the frontend error ratio rose modestly rather than locking high. Fix class is a configuration revert — restore the limit the automation removed, and then address the policy that keeps cycling it.

Three things remain genuinely open:

1. No ad logs or metrics were gathered inside the actual incident window. Kill or restart events there would confirm the mechanism directly. Without them, the link from the 144m cap to the refused connections is inference, not observation. This is the single highest-value gap to close.

2. The mapping of 172.18.0.19:9555 to the ad service rests on port convention, not a verified service-to-address lookup. If that port belongs to a different workload in this environment, blame moves with it and the change-log correlation becomes a coincidence.

3. The ECONNREFUSED to EHOSTUNREACH escalation is unaccounted for. A memory-driven kill loop produces refusal. It does not obviously produce unreachability. Either something else happened later in the window, or the address was released entirely.

> Evidence `tr_7aa78830adfe`:

```
<tool_result id="tr_7aa78830adfe" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T10:20:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-14T10:20:47.489024+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect ECONNREFUSED 172.18.0.19:9555 (2026-10-14T10:20:33.363Z)
2026-10-14T10:20:47.489042+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-14T10:20:47.489043+00:00      at new Promise (<anonymous>) {
2026-10-14T10:20:47.489061+00:00    code: 14,
```

> Evidence `tr_e28af516e347`:

```
<tool_result id="tr_e28af516e347" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-13T10:50:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" radius="candidate_cause" hops="1">
service: ad
7 changes, ranked by suspicion
  #1  5m before onset  2026-10-14T10:45:30.816718+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  19m before onset  2026-10-14T10:31:41.977071+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

> Evidence `tr_45251a674f30`:

```
<tool_result id="tr_45251a674f30" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T10:20:46.664000+00:00..2026-10-14T10:52:45.387542+00:00" template="error-ratio" baseline="2026-10-14T09:48:47.940458+00:00..2026-10-14T10:20:46.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=128 mean=0.04223 min=0 max=0.09263 sd=0.03238
  baseline window: n=128 mean=0.0253 min=0 max=0.07841 sd=0.02475
```

