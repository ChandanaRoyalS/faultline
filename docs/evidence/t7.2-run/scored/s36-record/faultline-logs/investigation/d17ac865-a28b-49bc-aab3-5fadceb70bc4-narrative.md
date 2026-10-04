# Silent front door: nginx-web-server reachable but emitting nothing

## What the alert said and what we saw first

The page came from nginx-web-server, the edge proxy and entry point for the social-network stack. Blast radius as scoped on arrival was four services, severity critical. The first instinct on an edge-proxy page is to look for a 5xx burst and name the upstream that caused it, so that is where the first dispatches went.

The immediate surprise was that there was nothing to look at. A trace query scoped to nginx-web-server across the full ~30-minute window spanning onset returned not one span. Not a degraded subset, not slow spans — zero. For a front door that normally carries continuous traffic, an empty trace result is itself the finding, and it closed off the plan of attributing the problem to a specific downstream call. Nothing could be implicated and nothing could be exonerated on trace evidence.

> Evidence `tr_77d8e6acee83`:

```
<tool_result id="tr_77d8e6acee83" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no traces for nginx-web-server over this window
</tool_result:tr_77d8e6acee83>
```

## The log path, and why it only half-counts

Around T+3m the log query came back the same way: a Loki query for the nginx frontend pods in the social-network namespace returned zero lines over the whole window. No access lines, no error lines, so no upstream names and no upstream status codes. Routine access logging alone should have produced thousands of lines; its total absence is not compatible with a healthy, serving, well-logged proxy.

Two caveats a future responder should carry forward. First, the selector matched on a pod-name regex rather than a namespace-wide or label-based selector, so a zero match is equally consistent with a selector miss. Second, the result came back carrying a truncation flag while also being empty, which is internally inconsistent and should lower trust in it further. The honest reading is: nginx-web-server is probably silent, but this query cannot distinguish silent from unqueried.

> Evidence `tr_b42ca415bd08`:

```
<tool_result id="tr_b42ca415bd08" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no log lines matched {namespace="social-network",pod=~"nginx-thrift-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_b42ca415bd08>
```

## Dead end: the metrics dispatches

Three separate metric dispatches were spent chasing error ratios — on nginx-web-server, on compose-post-service, and on home-timeline-service. All three came back empty, and all three were empty for the same structural reason: the error-ratio template reads span-derived metrics, and this Prometheus holds none for these services because they do not emit traces that get converted into metrics.

This is the trap worth flagging. The empty result is *unavailable*, not *measured zero*. It does not mean the services were error-free, it does not mean they were idle, and it does not mean traffic stopped. Crucially, the same absence is present in the pre-onset baseline window, so it predates the incident entirely and is a standing instrumentation condition rather than a symptom. Retrying or widening the time range on these templates will not help; the data was never stored. Status-code breakdowns and upstream latency profiles ride on the same missing pipeline, so neither can be recovered from this source — they would have to come from access logs or an nginx exporter.

> Evidence `tr_28928cb4f5ae`:

```
<tool_result id="tr_28928cb4f5ae" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T15:48:22.400834+00:00..2026-10-03T16:18:27.697074+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_28928cb4f5ae>
```

> Evidence `tr_e44cb5f7f0bc`:

```
<tool_result id="tr_e44cb5f7f0bc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for compose-post-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T15:48:22.400834+00:00..2026-10-03T16:18:27.697074+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for compose-post-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_e44cb5f7f0bc>
```

> Evidence `tr_5c01829f25f9`:

```
<tool_result id="tr_5c01829f25f9" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for home-timeline-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T15:48:22.400834+00:00..2026-10-03T16:18:27.697074+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for home-timeline-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_5c01829f25f9>
```

## Dead end: the change histories

Both change-log pulls looked promising and both turned out not to matter. For nginx-web-server, the only records in the 24-hour window were three creation events from the platform-automation actor roughly six minutes before onset: a ConfigMap, a Service, and the workload container, created within moments of each other. There were no updates, no patches, no redeploys, no routing flips — and, importantly, a quiet gap of about six minutes between the creation burst and onset with no activity at all. There is no last-minute edit to blame.

One nuance that cuts the other way: because the container record is a *first* creation rather than a replacement, there was no established steady state. A configuration wrong from first boot stays on the table even though a regression-against-a-previous-version does not.

compose-post-service told the same story: three changes, all at one moment roughly six minutes before onset, all from platform-automation, workload created fresh. No failure, rollback, restart or retry entries appear, so the change log does not show compose-post-service failing to come up — but neither does it confirm that it did. The change-log scope was per-service, so whether peer backends came up in the same burst was never established.

> Evidence `tr_71f8714f5626`:

```
<tool_result id="tr_71f8714f5626" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T16:48:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" radius="seed" hops="0">
service: nginx-web-server
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T16:41:29+00:00  platform-automation  container created: workload first created
  #2  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  config created: ConfigMap nginx-thrift created
  #3  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  config created: Service nginx-thrift created
```

> Evidence `tr_ab2c2dafb187`:

```
<tool_result id="tr_ab2c2dafb187" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T16:48:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" radius="candidate_cause" hops="1">
service: compose-post-service
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  config created: ConfigMap compose-post-service created
  #2  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  config created: Service compose-post-service created
  #3  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  container created: workload first created
```

## Following the silence downstream

The last dispatch went to compose-post-service's logs on the theory that a downstream crash or connection failure would explain the edge going dark. It returned nothing: no lines of any level across the full window. No crash, no panic, no connection-failure message pointing at a database or cache, and no repeated startup sequences that would betray a restart loop.

The same selector caveat applies — pod-name regex, inconsistent truncation flag — so this empty result is provisional too. But read alongside the nginx silence it fits a simple shape: nothing is being forwarded to compose-post-service, so compose-post-service has nothing to say.

> Evidence `tr_bdff52fbd51f`:

```
<tool_result id="tr_bdff52fbd51f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no log lines matched {namespace="social-network",pod=~"compose-post-service-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_bdff52fbd51f>
```

## Where the investigation landed

The picture we converged on: nginx-web-server stopped doing work while remaining reachable. No logs, no spans, no error signal anywhere, no change landing between its creation and onset to explain a content-level regression, and a downstream that is equally quiet because nothing is reaching it. Total silence from the alerting entry service, with no errors recorded on any path, is the signature of a stopped process whose socket still accepts connections — callers hang until their deadlines rather than getting a refusal they could log.

Fix class: restart.

Confidence in this is low, and that should be stated plainly rather than softened. Every metric dispatch returned an unavailable series rather than a measurement, and both log queries used selectors that could have missed their targets on their own.

> Evidence `tr_b42ca415bd08`:

```
<tool_result id="tr_b42ca415bd08" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no log lines matched {namespace="social-network",pod=~"nginx-thrift-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_b42ca415bd08>
```

> Evidence `tr_77d8e6acee83`:

```
<tool_result id="tr_77d8e6acee83" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no traces for nginx-web-server over this window
</tool_result:tr_77d8e6acee83>
```

> Evidence `tr_71f8714f5626`:

```
<tool_result id="tr_71f8714f5626" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T16:48:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" radius="seed" hops="0">
service: nginx-web-server
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T16:41:29+00:00  platform-automation  container created: workload first created
  #2  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  config created: ConfigMap nginx-thrift created
  #3  6m before onset  2026-10-03T16:41:28+00:00  platform-automation  config created: Service nginx-thrift created
```

> Evidence `tr_bdff52fbd51f`:

```
<tool_result id="tr_bdff52fbd51f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no log lines matched {namespace="social-network",pod=~"compose-post-service-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_bdff52fbd51f>
```

> Evidence `tr_28928cb4f5ae`:

```
<tool_result id="tr_28928cb4f5ae" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T15:48:22.400834+00:00..2026-10-03T16:18:27.697074+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for nginx-web-server: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_28928cb4f5ae>
```

> Evidence `tr_e44cb5f7f0bc`:

```
<tool_result id="tr_e44cb5f7f0bc" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for compose-post-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T15:48:22.400834+00:00..2026-10-03T16:18:27.697074+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for compose-post-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_e44cb5f7f0bc>
```

> Evidence `tr_5c01829f25f9`:

```
<tool_result id="tr_5c01829f25f9" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for home-timeline-service: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T15:48:22.400834+00:00..2026-10-03T16:18:27.697074+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for home-timeline-service: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_5c01829f25f9>
```

## Open questions for whoever reads this next

Three things were never checked, and any one of them could overturn the conclusion.

Pod status and restart counts were never retrieved for the nginx frontend pods or for compose-post-service. From the dispatches we ran, a crash-loop or a never-ready pod is indistinguishable from a stopped-but-listening process. This is the cheapest gap to close and should be the first move next time.

Both log queries used pod-name regexes rather than a namespace label, and both returned an inconsistent truncation flag alongside an empty body. Re-query with a broader selector before treating the silence as real.

No caller-side evidence was gathered at all. Whether clients hang to their deadline or get an immediate connection error is precisely the distinction this conclusion rests on, and it was never established. If callers are seeing prompt refusals, the stopped-process reading is wrong and the investigation should restart from scheduling and readiness.

> Evidence `tr_b42ca415bd08`:

```
<tool_result id="tr_b42ca415bd08" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no log lines matched {namespace="social-network",pod=~"nginx-thrift-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_b42ca415bd08>
```

> Evidence `tr_bdff52fbd51f`:

```
<tool_result id="tr_bdff52fbd51f" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T16:18:27.697074+00:00..2026-10-03T16:48:32.993314+00:00">
no log lines matched {namespace="social-network",pod=~"compose-post-service-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_bdff52fbd51f>
```

