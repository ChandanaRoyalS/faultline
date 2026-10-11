# Ad service goes dark after an image-reference update; frontend GetAds fails fast

## Summary

Pages fired on frontend and frontend-proxy. Blast radius was recorded as eight services, seven of the edges crossed were never directly measured. The chain we were able to substantiate is short: about five minutes before onset (T-5m) the running ad JVM logged a complete, orderly gRPC shutdown and then said nothing else for the rest of the window — no startup, no bind, no listen. One second after that shutdown line, platform-automation applied an image-reference update on ad pointing at an ad-hotfix build tag. Whatever that reference resolves to never came up and never served. Frontend traces show the downstream consequence: a single error chain that terminates at frontend's outbound gRPC call to ad GetAds, a childless leaf that fails in roughly a millisecond. Fix class is rollback of the ad image reference. Confidence medium — see the open items, which are substantial.

> Evidence `tr_ee1f8a8e0866`:

```
<tool_result id="tr_ee1f8a8e0866" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-04T20:28:07.772800+00:00  2026-10-04 20:28:07 - oteldemo.AdService - no baggage found in context trace_id=236a1b57cd0e7debf0459a3ef1e7b52e span_id=206fe7b02552305b trace_flags=01 
2026-10-04T20:28:07.772819+00:00  2026-10-04 20:28:07 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=236a1b57cd0e7debf0459a3ef1e7b52e span_id=206fe7b02552305b trace_flags=01 
2026-10-04T20:28:08.094946+00:00  2026-10-04 20:28:08 - oteldemo.AdService - no baggage found in context trace_id=6dd5b6641dac1c19295d3588d163e17c span_id=8bef5a70b010a7df trace_flags=01 
2026-10-04T20:28:08.094977+00:00  2026-10-04 20:28:08 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=6dd5b6641dac1c19295d3588d163e17c span_id=8bef5a70b010a7df trace_flags=01 
```

> Evidence `tr_451a0f2a493a`:

```
<tool_result id="tr_451a0f2a493a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-03T20:58:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" radius="candidate_cause" hops="1">
service: ad
9 changes, ranked by suspicion
  #1  5m before onset  2026-10-04T20:52:55.286143+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  8.9h before onset  2026-10-04T12:05:46.157637+00:00  platform-automation  image reverted: image reference reverted on ad
```

> Evidence `tr_a84d740b0da4`:

```
<tool_result id="tr_a84d740b0da4" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00">
service: frontend
10 trace(s) shown of 10 found, 188 spans; offsets are from each trace's root

trace 12cd2b2b6ff7f97b  root load-generator/user_get_product_reviews  33.6ms  started 2026-10-04T20:59:50.321967+00:00  11 spans
  +0.0ms load-generator/user_get_product_reviews 33.6ms [self 1.4ms]
```

## What was visible first, and why it was unhelpful

The first instinct with a frontend page is to look at frontend's own error rate. That was a dead end, and an actively misleading one. Over the half hour bracketing onset, frontend's aggregate errored-span ratio ran at roughly a quarter of its preceding baseline — down, not up — with no sustained departure flagged and a within-window peak below the baseline peak. If you arrive at this record and pull the same series, expect it to tell you nothing is wrong. The query aggregated by service name only, with no per-dependency breakdown, no request rate and no latency percentiles, so a single dependency failing inside a much larger volume of healthy calls is invisible to it. Do not treat a flat or improving aggregate ratio as exoneration of the fan-out.

> Evidence `tr_87e2365fa735`:

```
<tool_result id="tr_87e2365fa735" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" template="error-ratio" baseline="2026-10-04T19:55:53.775582+00:00..2026-10-04T20:28:01.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=129 mean=0.02416 min=0 max=0.1494 sd=0.04016
  baseline window: n=129 mean=0.09158 min=0 max=0.3178 sd=0.1236
```

## Dead end: looking for a frontend-side change

The change log was queried for frontend across a full day ending at window close and came back empty — no deploys, no config pushes, no flag flips. That closes the obvious 'revert the last frontend release' path, but it is worth noting the query covered only the seed service at zero hops. It said nothing about the six downstream dependencies, and for a while that gap was mistaken for a clean bill of health across the graph. The useful lesson: an empty change answer scoped to one service is not an empty change answer for the call tree.

> Evidence `tr_d029746e7b7d`:

```
<tool_result id="tr_d029746e7b7d" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-03T20:58:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_d029746e7b7d>
```

## The trace sample that actually pointed somewhere

Ten frontend traces were sampled. Nine were clean and fast; end-to-end durations across the whole sample ran 4–47ms, so there was no latency incident to chase. Exactly one trace carried an error status: load-generator into frontend-proxy into frontend's /api/data route, terminating at frontend's client-side gRPC call to ad GetAds. That span has no server-side child from ad at all, and it fails in about a millisecond out of a 16.6ms trace, with the remainder being frontend self-time in the route handler after the failed call. A childless leaf failing in a millisecond is a connection-level refusal, not ad-side business logic and not a deadline. The same sample ruled out cart, product-catalog, checkout, payment, currency, shipping, email, quote, flagd and product-reviews as error sources, ruled out the proxy and frontend's own handling as latency contributors, and ruled out database spans — every one under about a millisecond. The slowest trace was an AI-assistant request whose budget went to product-reviews self-time and two outbound LLM chat calls; interesting, unrelated, and it absorbed attention for a while. One caveat that matters: all ten sampled traces started inside the final twenty seconds or so of a thirty-two minute window, so this sample characterises the end of the window only.

> Evidence `tr_a84d740b0da4`:

```
<tool_result id="tr_a84d740b0da4" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00">
service: frontend
10 trace(s) shown of 10 found, 188 spans; offsets are from each trace's root

trace 12cd2b2b6ff7f97b  root load-generator/user_get_product_reviews  33.6ms  started 2026-10-04T20:59:50.321967+00:00  11 spans
  +0.0ms load-generator/user_get_product_reviews 33.6ms [self 1.4ms]
```

## Dead end: ad's own metrics said ad was fine

With ad implicated by the traces, the natural move was to check ad's error ratio against baseline. It came back flat — low tenths of a percent, peaking near 1.4%, a mean roughly 1.6x baseline with the baseline standard deviation exceeding the shift, and an explicit finding of no sustained departure. The analysis built on that concluded ad was not the origin and that investigation should redirect upstream. That conclusion is wrong, and the reason is a window error: the query covered a six-hour span ending roughly eighteen hours before onset. It never looked at the incident at all. There is also a sampling-density mismatch between the two windows that makes the ratio approximate regardless. Nothing about pod restarts, container memory or CPU was returned — that part of the question is simply unanswered. If you inherit this, re-run the ad error ratio against the actual incident window before believing anything derived from it. Note also that a service which is not running emits no spans, so even a correctly-windowed ratio can look calm while the process is absent.

> Evidence `tr_a851199a2db8`:

```
<tool_result id="tr_a851199a2db8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-03T20:58:01.664000+00:00..2026-10-04T02:58:01.664000+00:00" template="error-ratio" baseline="2026-10-03T14:58:01.664000+00:00..2026-10-03T20:58:01.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1184 mean=0.003746 min=0 max=0.0137 sd=0.004758
  baseline window: n=136 mean=0.002304 min=0 max=0.01351 sd=0.004245
```

## Ad logs: the turn

The ad log stream was routine right up to T-5m20s or so — steady targeted and non-targeted ad request handling with trace context, no error-level entries. Then at T-5m7s the service logged shutdown initiated as the JVM terminated, followed about 23ms later by server shut down. That pair is the last ad output in the window. At onset the service was already silent, and it stayed silent through window close roughly two minutes after onset. The shutdown is orderly and self-logged to completion, which rules out an abrupt kill: no out-of-memory entries, no heap exhaustion, no panic or stack trace. It also rules out a restart that failed to re-bind a port, because there is no startup, bind or listen line anywhere after — there is no restart attempt logged at all. And it rules out a live-but-hung process: the silence is explained by the process being gone.

> Evidence `tr_ee1f8a8e0866`:

```
<tool_result id="tr_ee1f8a8e0866" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-04T20:28:07.772800+00:00  2026-10-04 20:28:07 - oteldemo.AdService - no baggage found in context trace_id=236a1b57cd0e7debf0459a3ef1e7b52e span_id=206fe7b02552305b trace_flags=01 
2026-10-04T20:28:07.772819+00:00  2026-10-04 20:28:07 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=236a1b57cd0e7debf0459a3ef1e7b52e span_id=206fe7b02552305b trace_flags=01 
2026-10-04T20:28:08.094946+00:00  2026-10-04 20:28:08 - oteldemo.AdService - no baggage found in context trace_id=6dd5b6641dac1c19295d3588d163e17c span_id=8bef5a70b010a7df trace_flags=01 
2026-10-04T20:28:08.094977+00:00  2026-10-04 20:28:08 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=6dd5b6641dac1c19295d3588d163e17c span_id=8bef5a70b010a7df trace_flags=01 
```

## The change record on ad

Nine changes landed on ad in the roughly ten hours before onset, every one of them an image-reference update or revert, all attributed to platform-automation. No config pushes, no flag flips, no human-initiated entries. The pattern is a flapping one — the same hotfix tag applied and reverted repeatedly, five applies against four reverts, across about nine hours — which reads like a reconciliation or rollout controller oscillating rather than a series of deliberate releases. After the last revert the service sat quiet on the pre-hotfix reference for nearly nine hours. Then the apply landed at T-5m, one second after the running JVM logged its shutdown. Worth recording: the hotfix artifact is not novel. It had already been applied and running during several earlier intervals the same day, so 'brand new code shipped for the first time' is not the story. What changed is the combination of that reference with current conditions, and the fact that this time nothing replaced the process that stopped.

> Evidence `tr_451a0f2a493a`:

```
<tool_result id="tr_451a0f2a493a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-03T20:58:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" radius="candidate_cause" hops="1">
service: ad
9 changes, ranked by suspicion
  #1  5m before onset  2026-10-04T20:52:55.286143+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  8.9h before onset  2026-10-04T12:05:46.157637+00:00  platform-automation  image reverted: image reference reverted on ad
```

## Still open

Three gaps, in rough order of how much they would have shortened this. First, no pod or container-state evidence was gathered at all. An image that cannot be pulled, a container that starts and dies repeatedly, and a workload that was never scheduled all produce exactly this signature — process gone, no logs, connection refused at the caller. Those were never distinguished, and distinguishing them is the first thing the next responder should do. Second, the ad metrics conclusion rests on a window that misses the incident by about eighteen hours; treat its 'ad is not the origin' finding as void until re-run. Third, two things remain unaccounted for: the roughly five-minute gap between ad's shutdown and symptom onset, and the breadth of the recorded eight-service blast radius, which the single error path we found does not explain. Either the trace sample (confined to the last twenty seconds of the window) missed other failing paths, or the radius figure is counting services that were merely adjacent rather than affected.

> Evidence `tr_a851199a2db8`:

```
<tool_result id="tr_a851199a2db8" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-03T20:58:01.664000+00:00..2026-10-04T02:58:01.664000+00:00" template="error-ratio" baseline="2026-10-03T14:58:01.664000+00:00..2026-10-03T20:58:01.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: n=1184 mean=0.003746 min=0 max=0.0137 sd=0.004758
  baseline window: n=136 mean=0.002304 min=0 max=0.01351 sd=0.004245
```

> Evidence `tr_a84d740b0da4`:

```
<tool_result id="tr_a84d740b0da4" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00">
service: frontend
10 trace(s) shown of 10 found, 188 spans; offsets are from each trace's root

trace 12cd2b2b6ff7f97b  root load-generator/user_get_product_reviews  33.6ms  started 2026-10-04T20:59:50.321967+00:00  11 spans
  +0.0ms load-generator/user_get_product_reviews 33.6ms [self 1.4ms]
```

> Evidence `tr_ee1f8a8e0866`:

```
<tool_result id="tr_ee1f8a8e0866" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-04T20:28:01.664000+00:00..2026-10-04T21:00:09.552418+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-04T20:28:07.772800+00:00  2026-10-04 20:28:07 - oteldemo.AdService - no baggage found in context trace_id=236a1b57cd0e7debf0459a3ef1e7b52e span_id=206fe7b02552305b trace_flags=01 
2026-10-04T20:28:07.772819+00:00  2026-10-04 20:28:07 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=236a1b57cd0e7debf0459a3ef1e7b52e span_id=206fe7b02552305b trace_flags=01 
2026-10-04T20:28:08.094946+00:00  2026-10-04 20:28:08 - oteldemo.AdService - no baggage found in context trace_id=6dd5b6641dac1c19295d3588d163e17c span_id=8bef5a70b010a7df trace_flags=01 
2026-10-04T20:28:08.094977+00:00  2026-10-04 20:28:08 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=6dd5b6641dac1c19295d3588d163e17c span_id=8bef5a70b010a7df trace_flags=01 
```

