# Ads path failures at the frontend traced to a constrained ad service restarting in a loop

## What you would have seen first

Three pages arrived together: load-generator, frontend, frontend-proxy. Call that T+0. Frontend looked sick — error ratio around 8.7% against a baseline near 0.15%, roughly sixty-fold. Two details matter. It was partial: peak around 28.6%, minimum back to zero, so most requests kept succeeding; do not chase a hard-down service. And the first change point sits about twenty-two minutes before the top of the hour, well before T+0, with a second crossing near the window's close — so onset predates the page and the condition was still recurring at the end. Any midnight-job or date-rollover theory dies here. The metric was aggregated by service only: no per-route or per-dependency breakout, no latency series at all. Narrowing required traces.

Exactly one error trace appeared in the frontend sample. Root was a load-generator ads call; the only failing downstream span is frontend's gRPC client span for the ad service's GetAds, with the error marker propagating upward through the api route, the frontend GET span, proxy egress and ingress, and the load-generator client span. That chain is why three services paged for one failure. A sibling proxy ingress branch in the same trace succeeded — the proxy is carrying the status, not producing it. The failing span lasted about half a millisecond inside a ~7ms trace: a refusal, not a deadline. No child span beneath it, so no server-side ad span exists at all. Nobody answered.

> Evidence `tr_3c0f35f12602`:

```
<tool_result id="tr_3c0f35f12602" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T23:33:31.664000+00:00..2026-10-15T00:06:25.592976+00:00" template="error-ratio" baseline="2026-10-14T23:00:37.735024+00:00..2026-10-14T23:33:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=132 mean=0.08745 min=0 max=0.2855 sd=0.1065
  baseline window: n=132 mean=0.001468 min=0 max=0.01647 sd=0.004525
```

> Evidence `tr_beac0cf243e2`:

```
<tool_result id="tr_beac0cf243e2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T23:33:31.664000+00:00..2026-10-15T00:06:25.592976+00:00">
service: frontend
9 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 80805adb00465af7  root load-generator/user_checkout_multi  102.6ms  started 2026-10-15T00:02:29.525911+00:00  49 spans
  +0.0ms load-generator/user_checkout_multi 102.6ms [self 25.2ms]
```

## Dead ends worth keeping

The frontend change log was the obvious first pull and produced a tempting near-miss. All ten recorded changes in the preceding day were the same environment variable, CART_ADDR, toggled set/unset five times by platform-automation; the closest was a revert removing it about sixteen minutes before onset. Not the cause — the identical cycle had already run four times that day without incident, and there were no deploys, no image rollouts, no flag changes, no human actor. It was never tested against cart-path behaviour on the caller side, so it remains an unexplained loose end rather than a cleared one.

Other frontend paths were clean. Checkout completed fully in both sampled traces, including payment charge, cart empty, shipping quote and ship-order, currency convert and email confirmation. Product-catalog and its nested SQL queries carried no error markers. Recommendations completed end to end; its flagged hop was self-time, not an error. One non-error trace ran about 924ms, but the bulk was load-generator self-time near 618ms with the product-catalog portion around 207ms — slow and successful, a separate signal.

Frontend logs searched for the ad service's name returned nothing across the full window. The query ran cleanly and was not truncated, so this is a real absence: the frontend swallowed those refusals without logging. You cannot build a timeline from the caller side here.

> Evidence `tr_bce3621ae8b3`:

```
<tool_result id="tr_bce3621ae8b3" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-14T00:03:31.664000+00:00..2026-10-15T00:06:25.592976+00:00" radius="seed" hops="0">
service: frontend
10 changes, ranked by suspicion
  #1  16m before onset  2026-10-14T23:46:33.239475+00:00  platform-automation  environment reverted: CART_ADDR reverted on frontend
      CART_ADDR=cart:7071  ->  None
  #2  26m before onset  2026-10-14T23:37:07.263597+00:00  platform-automation  environment updated: CART_ADDR updated on frontend
```

> Evidence `tr_beac0cf243e2`:

```
<tool_result id="tr_beac0cf243e2" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-14T23:33:31.664000+00:00..2026-10-15T00:06:25.592976+00:00">
service: frontend
9 trace(s) shown of 10 found, 200 spans; offsets are from each trace's root

trace 80805adb00465af7  root load-generator/user_checkout_multi  102.6ms  started 2026-10-15T00:02:29.525911+00:00  49 spans
  +0.0ms load-generator/user_checkout_multi 102.6ms [self 25.2ms]
```

> Evidence `tr_c78b30efb093`:

```
<tool_result id="tr_c78b30efb093" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-14T23:33:31.664000+00:00..2026-10-15T00:06:25.592976+00:00" contains="AdService">
no log lines matched {service="frontend"} |= "AdService" over this window
</tool_result:tr_c78b30efb093>
```

## What the callee showed, and the change that explains it

The ad service's own error ratio is counterintuitive: incident mean ~0.0039 against baseline ~0.0040, no sustained departure. Requests it served failed at normal background rates. The real signal is twelve incident-window samples with no defined value against zero in baseline — intervals with no ad traffic at all. The signature is absent traffic, not failed traffic, which also excludes a gradual creep and a total failure (that would push the ratio toward 1.0; observed max ~0.016). Coverage gap: ad request rate and latency were never measured, so the gaps are inferred from undefined ratio samples, not a rate series.

Its logs close it. Early in the window it serves targeted ad requests normally. Then roughly T+1m to T+5m a JVM and container startup sequence repeats at least seven times in about four minutes, only some attempts reaching the application's 'service starting' line. No stack trace, no exception, no clean-shutdown message, no kill notice — the process dies silently from inside, which is what being killed from outside looks like. Logging itself was healthy throughout.

The ad change history holds seventeen resource-limit toggles by platform-automation, alternating a 144m memory ceiling with no limit. Eight prior lower/revert pairs across the day caused nothing. The seventeenth, about four minutes before onset, lowered the ceiling and never reverted. The ceiling persisting is the distinguishing factor, not the change type. Fix is to restore the limit — and to understand why the automation is flapping it, or the revert will be undone.

> Evidence `tr_bdafb4a5d489`:

```
<tool_result id="tr_bdafb4a5d489" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-14T23:33:31.664000+00:00..2026-10-15T00:06:25.592976+00:00" template="error-ratio" baseline="2026-10-14T23:00:37.735024+00:00..2026-10-14T23:33:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=120 mean=0.003902 min=0 max=0.01587 sd=0.005008
  baseline window: n=132 mean=0.003995 min=0 max=0.01176 sd=0.005011
```

> Evidence `tr_6785098d00e9`:

```
<tool_result id="tr_6785098d00e9" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-14T23:33:31.664000+00:00..2026-10-15T00:06:25.592976+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-14T23:33:39.541765+00:00  2026-10-14 23:33:39 - oteldemo.AdService - no baggage found in context trace_id=55209b04e634fdfd28d374268ffaa25d span_id=b5803dfdea52d30d trace_flags=01 
2026-10-14T23:33:39.542065+00:00  2026-10-14 23:33:39 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=55209b04e634fdfd28d374268ffaa25d span_id=b5803dfdea52d30d trace_flags=01 
2026-10-14T23:33:42.114339+00:00  2026-10-14 23:33:42 - oteldemo.AdService - no baggage found in context trace_id=3ff60be157d5b6f7dd7321fe969207d5 span_id=6fdbc133858bd061 trace_flags=01 
2026-10-14T23:33:42.114495+00:00  2026-10-14 23:33:42 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=3ff60be157d5b6f7dd7321fe969207d5 span_id=6fdbc133858bd061 trace_flags=01 
```

> Evidence `tr_8c7dc623349c`:

```
<tool_result id="tr_8c7dc623349c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-14T00:03:31.664000+00:00..2026-10-15T00:06:25.592976+00:00" radius="candidate_cause" hops="1">
service: ad
17 changes, ranked by suspicion
  #1  4m before onset  2026-10-14T23:58:50.761354+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
      None  ->  memory=144m
  #2  2.3h before onset  2026-10-14T21:46:48.395675+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
```

