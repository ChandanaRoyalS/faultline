# Critical multi-service alert from the frontend proxy: ad investigated, cause not established

## What was visible, in order

The page arrived as a critical five-service event with the frontend proxy as the origin. frontend-proxy and load-generator alerted first; ad followed about a minute later. Three edges in the affected path had no measurement attached to them at all.

Every dispatched line of inquiry then targeted ad. Nothing was pulled for frontend-proxy or frontend, the two services that alerted first and sit upstream of ad. By the time that gap was noticed the budget had been spent proving ad looked fine.

Sampled traces through ad were clean: ten traces, no error-marked spans, ad server spans between roughly half a millisecond and twenty. The only children under ad were its own internal operations, so the theory that ad was blocking on a slow dependency had nothing to attach to. In the slowest trace (~103ms) the dominant self-time sat in the load-generator GET span at about 90%, with ad contributing a fifth of that. The traces push the problem upstream. Sampling was sparse and clustered, so this is suggestive rather than conclusive.

> Evidence `tr_cdaa32951ad4`:

```
<tool_result id="tr_cdaa32951ad4" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:14:31.664000+00:00">
service: ad
10 trace(s) shown of 10 found, 129 spans; offsets are from each trace's root

trace 7ace5a0f4a285065  root load-generator/user_get_ads  102.6ms  started 2026-10-13T16:49:22.573855+00:00  13 spans
  +0.0ms load-generator/user_get_ads 102.6ms [self 10.5ms]
```

## The log thread: a real anomaly, at the wrong layer

ad's logs opened clean and changed sharply near onset: repeated ERROR bursts from the telemetry agent's metrics exporter. Following the stack frames is what kept this from becoming the answer. Every frame belonged to the agent's background dispatch pool, none to ad's request-handling path. The failure was a name-resolution exception on the collector hostname, thrown during DNS lookup before any socket opened, which also rules out collector-side rejection, overload or TLS trouble.

A targeted follow-up tightened it. Every matching line named the collector host and only that host, arguing against a blanket resolver problem. The earliest match landed hours after the window opened, so this is a genuine onset rather than a truncation artifact. Entries recur in clustered per-minute bursts and continue into the final minutes before the window closes: intermittent and still active.

Caveat for the next reader: both log results were truncated to oldest and newest lines, leaving roughly seven days in the middle unobserved. The claim that no other hostname fails resolution rests only on surviving lines.

> Evidence `tr_cb5e1e5e4b95`:

```
<tool_result id="tr_cb5e1e5e4b95" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:14:31.664000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="ad"}
2026-10-07T16:23:33.332502+00:00  2026-10-07 16:23:33 - oteldemo.AdService - no baggage found in context trace_id=c7b3a1ffc4579d15a6dd3878c069ba66 span_id=4f72bef6871b4cbf trace_flags=01 
2026-10-07T16:23:33.332615+00:00  2026-10-07 16:23:33 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=c7b3a1ffc4579d15a6dd3878c069ba66 span_id=4f72bef6871b4cbf trace_flags=01 
2026-10-07T16:23:44.045488+00:00  2026-10-07 16:23:44 - oteldemo.AdService - no baggage found in context trace_id=f2998f97ebbc2e6fff8c6a166cb5e600 span_id=d8770040c34a2a47 trace_flags=01 
2026-10-07T16:23:44.045572+00:00  2026-10-07 16:23:44 - oteldemo.AdService - Targeted ad request received for [books] trace_id=f2998f97ebbc2e6fff8c6a166cb5e600 span_id=d8770040c34a2a47 trace_flags=01 
```

> Evidence `tr_bb7969af7d3e`:

```
<tool_result id="tr_bb7969af7d3e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:14:31.664000+00:00" oldest_kept="8" newest_kept="32" contains="UnknownHostException">
selector: {service="ad"} |= "UnknownHostException"
2026-10-07T20:28:01.399336+00:00  java.net.UnknownHostException: otel-collector
2026-10-07T20:29:01.342199+00:00  java.net.UnknownHostException: otel-collector
2026-10-07T20:30:01.671016+00:00  java.net.UnknownHostException: otel-collector
2026-10-07T20:31:00.975988+00:00  java.net.UnknownHostException: otel-collector
```

## Dead ends, conclusion, and what is still open

Two metric attempts against ad were both rejected with HTTP 400. This is the most important dead end because it is easy to misread: a 400 comes from a reachable, functioning backend and means the query template was malformed. It is not an empty result and says nothing about whether series exist. There is therefore no error-rate, latency, CPU or heap figure for ad anywhere in this record.

ad's change log held 26 entries over seven days, all from the same automation actor, all memory-limit or image toggles that were each reverted. The last revert restored baseline about 5.3 hours before onset, and nothing changed in the five hours preceding it. The memory-limit toggling looked promising early and consumed attention; it does not matter, because the constrained value was not in effect at onset.

The flag-service change query returned nothing, but its window started at onset and ran forward. The question asked, whether flags flipped before onset, was never answered. That is a template error, not a finding.

No cause is established; confidence is low and no fix class is identified. The resolution failure is the one real anomaly and most likely explains sparse telemetry from ad rather than why requests failed. Still open: re-run ad's metrics with a corrected template; re-run the flag query anchored behind onset; and investigate frontend-proxy and frontend, which alerted first and were never examined.

> Evidence `tr_f9025118037f`:

```
<tool_result id="tr_f9025118037f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:14:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T16:14:31.664000+00:00..2026-10-07T16:14:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_f9025118037f>
```

> Evidence `tr_e779ceaa0e52`:

```
<tool_result id="tr_e779ceaa0e52" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:14:31.664000+00:00" error="HTTP Error 400: Bad Request" template="error-ratio" baseline="2026-09-30T16:14:31.664000+00:00..2026-10-07T16:14:31.664000+00:00">
query failed: HTTP Error 400: Bad Request
</tool_result:tr_e779ceaa0e52>
```

> Evidence `tr_62dee350fb29`:

```
<tool_result id="tr_62dee350fb29" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:16:25.479517+00:00" radius="seed" hops="0">
service: ad
26 changes, ranked by suspicion
  #1  5.3h before onset  2026-10-14T10:56:31.199078+00:00  platform-automation  resource_limits reverted: memory limit restored on ad
      memory=144m  ->  None
  #2  5.5h before onset  2026-10-14T10:45:30.816718+00:00  platform-automation  resource_limits updated: memory limit lowered on ad
```

> Evidence `tr_feda815a3c5b`:

```
<tool_result id="tr_feda815a3c5b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-07T16:14:31.664000+00:00..2026-10-14T16:16:25.479517+00:00" radius="candidate_cause" hops="1">
no changes recorded for flagd over this window
</tool_result:tr_feda815a3c5b>
```

