# Front-door alert with no usable telemetry: an unresolved investigation

## What we were handed

The page came from nginx-web-server, the front door of the social-network namespace. Severity was set critical and the declared blast radius covered four services: nginx-web-server itself plus the three backends it fans out to — compose-post-service, home-timeline-service and user-timeline-service. Three of the edges between those services had never been measured before this incident, so there was no prior shape to compare against.

Read this record expecting disappointment. Ten dispatches went out; nine came back as tool failures rather than measurements, and the one that genuinely observed its window came back empty in a way that is ambiguous. Nothing below localises a failing mechanism. The value of this record is the map of which roads are closed and why.

## First look: traces from the front door

The first real question was the obvious one for a fan-out service: which of the three downstream edges carries error status or inflated duration? The trace store was queried for nginx-web-server across roughly the thirty minutes ending at the alert.

It returned nothing. Not zero error spans — zero spans of any kind for the service across the whole window. That closed the per-dependency comparison immediately: with no spans at the service level, there is no edge data to rank, and narrowing or widening a status or peer filter cannot help, because the emptiness is not a filter artifact.

Two readings were available and the evidence does not choose between them. Either the service stopped processing requests, or its spans never reach the store. Worth noting the window geometry: it runs from about T-30m to the alert, so almost all of the observed silence predates the page. A gap that is already present half an hour before onset looks more like a standing export gap than a sudden outage. It is not a brief blip either — the hole covers the entire half hour.

> Evidence `tr_3c7a09c7f07e`:

```
<tool_result id="tr_3c7a09c7f07e" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T04:42:35.717532+00:00..2026-10-03T05:12:41.347724+00:00">
no traces for nginx-web-server over this window
</tool_result:tr_3c7a09c7f07e>
```

## Metrics: four services, four structural dead ends

Error-ratio baselines were requested for all four services. All four failed, and they failed for the same reason, which turned out to be the single most useful negative result of the investigation: the error-ratio template reads span-derived metrics, and the metrics backend holds no span-derived series for any of these four services because none of them emit traces that get converted into metrics.

This is unavailable, not zero. Three tempting misreadings were explicitly set aside. It does not mean nginx-web-server was healthy and error-free. It does not mean compose-post-service suffered a traffic collapse. And it does not indicate a monitoring pipeline outage coincident with the incident, because the same emptiness covers the one-hour baseline window before onset just as completely as it covers onset itself.

The operational consequence for the next responder: do not re-run these. No choice of window, baseline or service spelling will make this metric family resolve for these four services. Request rate, status-code breakdown including 499s, and upstream latency all remain entirely unmeasured and must be pursued through logs or caller-side instrumentation.

This also corroborates the trace finding. If nginx-web-server emits no traces that become metrics, the empty trace window is comfortably explained as instrumentation coverage rather than as evidence of an outage.

> Evidence `tr_ecf722d4c88a`:

```
<tool_result id="tr_ecf722d4c88a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:42:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T04:12:30.087340+00:00..2026-10-03T04:42:35.717532+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_ecf722d4c88a>
```

> Evidence `tr_df4845357d16`:

```
<tool_result id="tr_df4845357d16" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for compose-post-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:12:30.087340+00:00..2026-10-03T04:12:35.717532+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for compose-post-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_df4845357d16>
```

> Evidence `tr_ff29c4182d6f`:

```
<tool_result id="tr_ff29c4182d6f" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for home-timeline-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:12:30.087340+00:00..2026-10-03T04:12:35.717532+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for home-timeline-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_ff29c4182d6f>
```

> Evidence `tr_0a142cfdc055`:

```
<tool_result id="tr_0a142cfdc055" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for user-timeline-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:12:30.087340+00:00..2026-10-03T04:12:35.717532+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for user-timeline-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_0a142cfdc055>
```

## Logs: one bad matcher cost us the decisive answer

The log query against nginx-web-server was the one dispatch that could have separated the candidate mechanisms. It never ran. The log backend rejected it with an HTTP 400 — a client-side bad request, with the pod label matcher regex and its escaping the likely culprit.

Three conclusions were ruled out here. The empty frame does not mean nginx logged no errors; nothing was ever retrieved. The log backend is not down — it answered at the application layer with a 400, which is what a reachable, parsing service does; a dead backend would have surfaced as a timeout, connection error or 5xx. And the time range was not the limiting factor, since explicit start and end nanosecond bounds were carried in the request and the rejection happened before they mattered.

This is the highest-value retry available. A corrected pod matcher against the same window answers, in one shot, what every other channel failed to answer: whether the process stalled, whether it lost its path to a backend, whether it ran out of space, or whether its configuration was wrong.

> Evidence `tr_ae542892c038`:

```
<tool_result id="tr_ae542892c038" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-03T04:42:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="[loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22social-network%22%2Cpod%3D~%22nginx%5C-thrift-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791002474920822784&end=1791004394920822784&limit=100">
query failed: [loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22social-network%22%2Cpod%3D~%22nginx%5C-thrift-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791002474920822784&end=1791004394920822784&limit=100
</tool_result:tr_ae542892c038>
```

## Change history: the same failure four times

Change history was requested for all four services over the twenty-four hours ending at the alert. All four queries died identically — a parse error on an unterminated string partway through the response payload, at the same line and column each time. The response was truncated or malformed during serialisation; the backend never reported zero matching changes.

So the empty flags on these four results carry no weight at all. It would be a serious mistake to record that the change log is clean and exclude deploys, configuration edits or image/tag changes as the trigger. A change-driven cause remains fully open and entirely unexamined.

The repeatability of the error across four separate service names suggests the tool or its upstream data is currently emitting malformed output generally, not that one query was unlucky. A straight retry may reproduce it. Alternate sources worth reaching for: deployment pipeline records, image registry history, and the configuration repository's commit log.

> Evidence `tr_7c7136d87842`:

```
<tool_result id="tr_7c7136d87842" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T05:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="Unterminated string starting at: line 224 column 55 (char 9995)">
query failed: Unterminated string starting at: line 224 column 55 (char 9995)
</tool_result:tr_7c7136d87842>
```

> Evidence `tr_53f4cca39479`:

```
<tool_result id="tr_53f4cca39479" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T05:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="Unterminated string starting at: line 224 column 55 (char 9995)">
query failed: Unterminated string starting at: line 224 column 55 (char 9995)
</tool_result:tr_53f4cca39479>
```

> Evidence `tr_f3ae6788e684`:

```
<tool_result id="tr_f3ae6788e684" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T05:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="Unterminated string starting at: line 224 column 55 (char 9995)">
query failed: Unterminated string starting at: line 224 column 55 (char 9995)
</tool_result:tr_f3ae6788e684>
```

> Evidence `tr_06833e7a95d8`:

```
<tool_result id="tr_06833e7a95d8" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T05:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="Unterminated string starting at: line 224 column 55 (char 9995)">
query failed: Unterminated string starting at: line 224 column 55 (char 9995)
</tool_result:tr_06833e7a95d8>
```

## Where this stands

Not established. Confidence low. No fix class identified. No evidence gathered during this investigation points at a failing mechanism in any of the four services, and the one genuine observation we have is ambiguous between an outage and a telemetry gap — with the geometry of its window, and the metrics backend's own account of these services' instrumentation, both tilting toward the gap.

Three questions remain open, in priority order. First: what does nginx-web-server's own log say around the alert? Re-run the log query with a corrected pod matcher; this single answer is the discriminator. Second: did nginx-web-server emit traces earlier in the day? If it did, the empty half hour becomes incident evidence instead of an instrumentation artifact, and the first reading of the trace result gains weight. Third: what actually changed on any of the four services in the preceding day, and what signal fired the alert in the first place? We never established the latter, which in hindsight should have been question one.

> Evidence `tr_3c7a09c7f07e`:

```
<tool_result id="tr_3c7a09c7f07e" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T04:42:35.717532+00:00..2026-10-03T05:12:41.347724+00:00">
no traces for nginx-web-server over this window
</tool_result:tr_3c7a09c7f07e>
```

> Evidence `tr_ae542892c038`:

```
<tool_result id="tr_ae542892c038" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-03T04:42:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="[loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22social-network%22%2Cpod%3D~%22nginx%5C-thrift-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791002474920822784&end=1791004394920822784&limit=100">
query failed: [loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22social-network%22%2Cpod%3D~%22nginx%5C-thrift-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791002474920822784&end=1791004394920822784&limit=100
</tool_result:tr_ae542892c038>
```

## Notes for whoever picks this up

Two patterns here will recur and are worth internalising.

An errored query and an empty query look alike in a results table and mean opposite things. Four change-history failures and four metric failures all surfaced with empty payloads; none of them was a negative finding. Check for an error string before you write anything down as ruled out.

And a failure that is structural is worth more than a failure that is transient, because it tells you where not to spend the next hour. The metrics backend's explanation — these services do not feed the span-metrics path — permanently closes that route for this part of the topology, and that is a fact worth carrying into the next incident in this namespace rather than rediscovering.

> Evidence `tr_ecf722d4c88a`:

```
<tool_result id="tr_ecf722d4c88a" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:42:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T04:12:30.087340+00:00..2026-10-03T04:42:35.717532+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_ecf722d4c88a>
```

> Evidence `tr_53f4cca39479`:

```
<tool_result id="tr_53f4cca39479" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T05:12:35.717532+00:00..2026-10-03T05:12:41.347724+00:00" error="Unterminated string starting at: line 224 column 55 (char 9995)">
query failed: Unterminated string starting at: line 224 column 55 (char 9995)
</tool_result:tr_53f4cca39479>
```

