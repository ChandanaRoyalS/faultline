# Ad backend crash-loop after a memory ceiling change, seen as frontend name-resolution failures

## What was visible first, and the dead ends

The page came from frontend and loadgenerator, severity critical, seven services in radius. That framing pointed at the storefront, and the first half of the investigation was spent learning it was wrong.

The first move was frontend's aggregate error ratio. It had gone down, not up: roughly a third to a half of its own two-hour baseline, with a lower in-window peak and no sustained departure flagged. That killed the frontend-wide surge theory, killed a total outage of any single high-traffic dependency, and killed the idea that this was a worsening continuation of an earlier pattern. The caveat to carry: the series is grouped only by service name, with no per-dependency and no per-route dimension and no latency at all, so it could never have ruled out a partial or route-scoped failure. Read it as "the aggregate did not move," not "frontend is fine."

Two change-history queries also came back empty. Frontend has no recorded deploy, config edit, or flag toggle at onset or after; checkoutservice likewise has none, so no in-window change there sustains anything. Both queries have a defect worth knowing: as executed they start at the incident timestamp and run forward about twenty-four hours, so they establish absence at and after onset, not in the lead-up. The checkoutservice call was scoped one hop and returned nothing about its neighbours.

> Evidence `tr_e05c7ecd11f7`:

```
<tool_result id="tr_e05c7ecd11f7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-10T13:10:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" template="error-ratio" baseline="2026-09-10T11:08:23.443984+00:00..2026-09-10T13:10:30.583000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="frontend"}[2m]))
  incident window: n=489 mean=0.01837 min=0 max=0.1154 sd=0.02868
  baseline window: n=489 mean=0.04565 min=0 max=0.3265 sd=0.09671
```

> Evidence `tr_fba95be7a9b8`:

```
<tool_result id="tr_fba95be7a9b8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T15:10:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_fba95be7a9b8>
```

> Evidence `tr_5c94d70e3097`:

```
<tool_result id="tr_5c94d70e3097" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-09T15:10:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" radius="candidate_cause" hops="1">
no changes recorded for checkoutservice over this window
</tool_result:tr_5c94d70e3097>
```

## The thread that held

Frontend's logs carried the first concrete lead. Around T+2m it repeatedly emitted gRPC code 14 UNAVAILABLE with a detail naming DNS name resolution failure for the adservice target on port 9555 — not a refused dial to a pod IP, not a deadline from a reachable server. The calls failed before any connection existed, so the ad backend never saw them. Stack frames sit in the gRPC client receiving a status on an outbound call, placing the problem upstream rather than in frontend logic.

The adservice change log was the turn. Eleven entries, all resource-limit edits on ad-service by the same automated actor, no human hand. Six lower-then-restore pairs across the prior seventeen hours — a loop that had run harmlessly all night. About three and a half minutes before T+0 it lowered the memory limit from uncapped to a 256m ceiling, and this one alone has no matching restore. No deploy, no image rollout, no DNS or routing change, no scaling action.

adservice's own stream confirmed the consequence. Lines kept arriving to the end of the window, so no collector blackout. From roughly T-3m the only output is a repeating three-line startup banner sequence: several starts within seconds, then restarts at about sixty-second spacing for five minutes — restart backoff. Request-handling lines appear only half an hour earlier. Not a hung process, not a single terminal exit, not a telemetry gap.

> Evidence `tr_12bd90c32996`:

```
<tool_result id="tr_12bd90c32996" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T13:10:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-09-10T13:18:24.059661+00:00  Error: 13 INTERNAL: failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing dial tcp 172.18.0.15:50051: connect: connection refused"
2026-09-10T13:18:24.059688+00:00      at Object.callErrorFromStatus (/app/node_modules/@grpc/grpc-js/build/src/call.js:31:26)
2026-09-10T13:18:24.059690+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client.js:189:52)
2026-09-10T13:18:24.059691+00:00      at Object.onReceiveStatus (/app/node_modules/@grpc/grpc-js/build/src/client-interceptors.js:365:141)
```

> Evidence `tr_83587b9c5868`:

```
<tool_result id="tr_83587b9c5868" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T15:10:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" radius="candidate_cause" hops="1">
service: adservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T15:07:02.849988+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  3.3h before onset  2026-09-10T11:52:34.805808+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

> Evidence `tr_45865e0db755`:

```
<tool_result id="tr_45865e0db755" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T14:40:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-10T14:40:33.598917+00:00  2026-09-10 14:40:33 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=7e3f9d7ebed219c674d9b76876e71379 span_id=6b185f7233c06ba1 trace_flags=01 
2026-09-10T14:40:48.284385+00:00  2026-09-10 14:40:48 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=c2a33ce8f1c9a09dfbe91d91aa386540 span_id=bbaa15102375489c trace_flags=01 
2026-09-10T14:40:49.969646+00:00  2026-09-10 14:40:49 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=d5e284bff3f47496d14cddeeb28c6b20 span_id=08fac63c4989cb47 trace_flags=01 
2026-09-10T14:40:56.654615+00:00  2026-09-10 14:40:56 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=899ff067ec4b845a952179e164d45e3b span_id=78858bfc5e88eddb trace_flags=01 
```

## Conclusion and what stayed open

An automated loop lowered the ad-service memory ceiling and did not put it back. The container began restarting immediately and never reached a serving state, so the Service carried no ready endpoints and frontend's ad calls failed at name resolution. Frontend is the service that noticed, not the one that broke. Remedy: restore the uncapped limit, and separately stop the loop, or it re-arms.

Open items. The kill was never observed directly — no termination reason, exit code, container events, or memory-usage series were retrieved; the mechanism is inferred from the edit timing plus the cadence. Pull container events next time, the stdout will not give it to you, as it holds no exception, panic, or shutdown text.

An attempt to corroborate via adservice's error-ratio metric returned no samples in either the incident or the baseline window, denominator included. The absence is symmetric, so it is an instrumentation gap, not a service going dark; that metric discriminates nothing here.

Finally, the payment-path entry about an hour and fifty minutes before onset — code 13 INTERNAL wrapping a refused dial on port 50051 — is a second, unrelated signature that was never explained; paymentservice was never examined. And the critical rating rests on a user-facing signal nobody measured, so the true blast radius remains unquantified.

> Evidence `tr_83587b9c5868`:

```
<tool_result id="tr_83587b9c5868" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-09T15:10:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" radius="candidate_cause" hops="1">
service: adservice
11 changes, ranked by suspicion
  #1  3m before onset  2026-09-10T15:07:02.849988+00:00  platform-automation  resource_limits updated: memory limit lowered on ad-service
      None  ->  memory=256m
  #2  3.3h before onset  2026-09-10T11:52:34.805808+00:00  platform-automation  resource_limits reverted: memory limit restored on ad-service
```

> Evidence `tr_45865e0db755`:

```
<tool_result id="tr_45865e0db755" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-10T14:40:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad-service"}
2026-09-10T14:40:33.598917+00:00  2026-09-10 14:40:33 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=7e3f9d7ebed219c674d9b76876e71379 span_id=6b185f7233c06ba1 trace_flags=01 
2026-09-10T14:40:48.284385+00:00  2026-09-10 14:40:48 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=c2a33ce8f1c9a09dfbe91d91aa386540 span_id=bbaa15102375489c trace_flags=01 
2026-09-10T14:40:49.969646+00:00  2026-09-10 14:40:49 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=d5e284bff3f47496d14cddeeb28c6b20 span_id=08fac63c4989cb47 trace_flags=01 
2026-09-10T14:40:56.654615+00:00  2026-09-10 14:40:56 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=899ff067ec4b845a952179e164d45e3b span_id=78858bfc5e88eddb trace_flags=01 
```

> Evidence `tr_182b1d3d5a80`:

```
<tool_result id="tr_182b1d3d5a80" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-10T14:40:30.583000+00:00..2026-09-10T15:12:37.722016+00:00" template="error-ratio" baseline="2026-09-10T14:08:23.443984+00:00..2026-09-10T14:40:30.583000+00:00">
service: adservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="adservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="adservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

