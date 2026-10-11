# Ad-path gRPC failures surfacing as frontend errors after ad instance stayed down

## What was visible first, and the dead ends

The page named frontend and frontend-proxy, severity critical, eight services in radius. Both alerted services turned out to be reporters, not sources.

First move was to quantify frontend damage. The error ratio averaged about 4.1%, peaking near 8.9%, minimum zero across 300 samples — bursty, not a plateau, and nowhere near a hard outage. Two traps: the comparison baseline returned no samples at all, so the tool's reassuring "no sustained departure" verdict was computed against nothing and should not talk you out of digging; and the query aggregated only by service_name, so it could not name a downstream or route. The low percentage misled in the other direction too — one product surface was entirely dead while the rest were healthy, which averages to a small number.

Second dead end: looking for a frontend change. The change log returned nothing for frontend — no deploys, config edits, toggles, or rollbacks. Worth recording honestly that this query was scoped to the seed service with zero dependency hops and its window began at onset and ran forward a day, so it never covered the hours before onset. "Frontend is not the culprit" is well supported, but by logs and traces, not by this empty result.

> Evidence `tr_a0db8337f966`:

```
<tool_result id="tr_a0db8337f966" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-06T08:53:31.664000+00:00..2026-10-06T10:55:27.781687+00:00" template="error-ratio" baseline="2026-10-06T06:51:35.546313+00:00..2026-10-06T08:53:31.664000+00:00">
service: frontend
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend"}[5m]))
  incident window: n=300 mean=0.04093 min=0 max=0.08921 sd=0.03179
  baseline window: no samples
```

> Evidence `tr_73b63a0cebf6`:

```
<tool_result id="tr_73b63a0cebf6" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-05T10:53:31.664000+00:00..2026-10-06T10:55:27.781687+00:00" radius="seed" hops="0">
no changes recorded for frontend over this window
</tool_result:tr_73b63a0cebf6>
```

## The turn: one peer, one signature, one missing span

Frontend logs were the pivot. Every error line in the window carried the same shape: gRPC status 14 UNAVAILABLE, transport-level connect failure (EHOSTUNREACH), against exactly one peer — 172.18.0.19:9555. Server-side Next.js frames, so real RPC calls. That one signature knocked out application logic (errors name a remote address), a downstream returning bad responses (no connection ever established), latency or pool exhaustion (host-unreachable at connect, not a deadline), name resolution (the target had already resolved to a concrete address), and any mesh-wide problem (only one peer appears anywhere). Errors were still flowing several per second at the last second queried, so nothing had self-healed. Critically, identical errors against the same peer were already present around T-51m — the alert marks a recurrence, not onset.

Traces named the edge. The only error-bearing trace is an ad fetch at about T-24m, where the frontend's AdService/GetAds client span is the deepest span and a childless leaf with no server-side ad span at all. It is sub-millisecond inside an ~11ms trace — immediate rejection, not timeout. Product-catalog, cart (with its Redis children) and recommendation chains all complete cleanly in the same sample; proxy spans are intact and merely inherit error status from below. Note the sample contains no traces after the alert time, so the post-alert signature is inferred by pattern from logs.

> Evidence `tr_9129eb349cc8`:

```
<tool_result id="tr_9129eb349cc8" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T09:53:31.664000+00:00..2026-10-06T10:55:27.781687+00:00" oldest_kept="8" newest_kept="32">
selector: {service="frontend"}
2026-10-06T10:02:02.398022+00:00  Error: 14 UNAVAILABLE: No connection established. Last error: connect EHOSTUNREACH 172.18.0.19:9555 (2026-10-06T10:02:02.393Z)
2026-10-06T10:02:02.398367+00:00      at <unknown> (.next/server/chunks/[root-of-the-server]__3ea42e2a._.js:1:531)
2026-10-06T10:02:02.398454+00:00      at new Promise (<anonymous>) {
2026-10-06T10:02:02.398456+00:00    code: 14,
```

> Evidence `tr_bead95082f1d`:

```
<tool_result id="tr_bead95082f1d" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-06T10:23:31.664000+00:00..2026-10-06T10:55:27.781687+00:00">
service: frontend
10 trace(s) shown of 10 found, 158 spans; offsets are from each trace's root

trace ab1218f00c287e69  root load-generator/user_browse_product  3.9ms  started 2026-10-06T10:23:49.744818+00:00  10 spans
  +0.0ms load-generator/user_browse_product 3.9ms [self 0.4ms]
```

## Ad: absence rather than failure, and the deploy cycling behind it

Ad's span-metrics series reads strangely and is worth slowing down for. In the six-hour comparison period the error ratio sat pegged at maximum across 272 samples with zero variance — already total failure before the window opened. From the alert boundary onward there are no samples at all: neither error spans nor total spans, ratio undefined for lack of a denominator. Both numerator and denominator come from the same counter and vanish together, which rules out a scrape artifact; and with no traffic there is nothing for retries to mask. The comparison period also held many undefined intervals, a hint of intermittency we did not read correctly at the time.

Ad's own logs settle it. Normal request handling through about T-6m with no error or exception lines, then two lines of orderly JVM-initiated gRPC server shutdown — a graceful path, not a crash, not an OOM kill, not a loop (only one shutdown, no restart banner). After that, silence across the alert point and through the end of the window.

The change log explains why it stayed down: seven image-reference changes on ad in the ~1.2 hours before onset, all attributed to platform automation, alternating every 11-13 minutes between an unset reference and a single hotfix tag — deployed versus not-deployed, never two code versions. The last entry is an update to that hotfix tag about five minutes before onset. The loop tore the running instance down and the hotfix artifact never came back up. Fix class: rollback.

Still open. Why the hotfix never started — no orchestrator or pod-event evidence was gathered, so image pull failure, a crash before the first log line, or the deploy never actually being applied all remain live. Whether 172.18.0.19:9555 is ad's current endpoint or a stale address from the prior instance; the peer was only ever an IP, never resolved to a name. And why identical ad-path failures already appear around T-51m and T-24m — the cycling plausibly explains it, but that correlation was never made directly.

> Evidence `tr_cf83f6da7194`:

```
<tool_result id="tr_cf83f6da7194" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-05T10:53:31.664000+00:00..2026-10-05T16:53:31.664000+00:00" template="error-ratio" baseline="2026-10-05T04:53:31.664000+00:00..2026-10-05T10:53:31.664000+00:00">
service: ad
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="ad"}[5m]))
  incident window: no samples
  baseline window: n=272 mean=1 min=1 max=1 sd=0
```

> Evidence `tr_049f5c41df79`:

```
<tool_result id="tr_049f5c41df79" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-06T10:23:31.664000+00:00..2026-10-06T10:55:27.781687+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-06T10:23:41.220417+00:00  2026-10-06 10:23:41 - oteldemo.AdService - no baggage found in context trace_id=d7e8d6ba7ffbee307f7790f6c1f20142 span_id=a2a0d0080c883086 trace_flags=01 
2026-10-06T10:23:41.222531+00:00  2026-10-06 10:23:41 - oteldemo.AdService - Targeted ad request received for [books] trace_id=d7e8d6ba7ffbee307f7790f6c1f20142 span_id=a2a0d0080c883086 trace_flags=01 
2026-10-06T10:23:47.042713+00:00  2026-10-06 10:23:47 - oteldemo.AdService - no baggage found in context trace_id=b17b0ceed76b7f00904e2c8d95ab5cf5 span_id=ff723542311e094a trace_flags=01 
2026-10-06T10:23:47.042866+00:00  2026-10-06 10:23:47 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=b17b0ceed76b7f00904e2c8d95ab5cf5 span_id=ff723542311e094a trace_flags=01 
```

> Evidence `tr_e6ff75165b3e`:

```
<tool_result id="tr_e6ff75165b3e" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-05T10:53:31.664000+00:00..2026-10-06T10:55:27.781687+00:00" radius="candidate_cause" hops="1">
service: ad
7 changes, ranked by suspicion
  #1  5m before onset  2026-10-06T10:47:53.143120+00:00  platform-automation  image updated: image reference updated on ad
      None  ->  ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2
  #2  17m before onset  2026-10-06T10:36:09.915832+00:00  platform-automation  image reverted: image reference reverted on ad
```

