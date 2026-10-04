# Frontend Unreachable Behind a Rewritten Resolver Setting

## What was visible, in order

The page came from frontend-proxy and load-generator. Nothing alerted on frontend itself — the service at the centre of this record never spoke, because it never spoke at all. Triage put the radius at three services from frontend-proxy, critical, with one edge crossed that carried no measurement.

The entry assumption — that frontend-proxy was broken, since it was the thing complaining — was reasonable and wrong. Its metrics showed one defined sample near a 0.905 error ratio, plus three intervals with no ratio at all: an empty denominator, meaning no calls recorded. Traffic did not merely sour, it vanished for stretches. But the preceding thirty-minute baseline held no samples whatsoever, so the apparent rise from zero is an artifact of an empty comparison period. The template's "no sustained departure" verdict should be read as insufficient data, not health. No request-rate counter, no 5xx-versus-503 split, no upstream connection-failure metric was ever retrieved.

Proxy logs contained only Envoy startup output, stamped around 08:48:51 — a start or restart late in the window. Startup ran all the way through the extension registry dump at info level with nothing fatal, so the binary and bootstrap are not the defect. The pod selector matched real stdout, so the missing access logs are a content gap, not a collection gap; and the access-log extensions are registered in the build, so "not compiled in" is not the explanation either.

> Evidence `tr_2635c8e1c2ef`:

```
<tool_result id="tr_2635c8e1c2ef" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00" template="error-ratio" baseline="2026-10-03T07:51:38.025922+00:00..2026-10-03T08:21:43.823556+00:00">
service: frontend-proxy
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="frontend-proxy"}[5m]))
  incident window: n=1 mean=0.9051 min=0.9051 max=0.9051 sd=0
  baseline window: no samples
```

> Evidence `tr_362c05685e3e`:

```
<tool_result id="tr_362c05685e3e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00">
selector: {namespace="astronomy-shop",pod=~"frontend-proxy-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.regex_engines: envoy.regex_engines.google_re2
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.tracers.opentelemetry.resource_detectors: envoy.tracers.opentelemetry.resource_detectors.dynatrace, envoy.tracers.opentelemetry.resource_detectors.environment, envoy.tracers.opentelemetry.resource_detectors.static_config
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.udp_packet_writer: envoy.udp_packet_writer.default, envoy.udp_packet_writer.gso
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.matching.network.custom_matchers: envoy.matching.custom_matchers.trie_matcher
```

## Three empty rooms, and the change record

Frontend was observed three ways and returned nothing three different ways. Metrics failed outright: the backend holds no span-derived series for this service because frontend sends no traces that become metrics — unavailable, not zero, and absent across the baseline too, so the gap is a property of the instrumentation rather than something that changed at onset. That whole query family is a dead end here; go to kubelet/cAdvisor or raw logs instead. Logs returned zero lines, flat across the window, so there is no burst and no volume signal to correlate against. Traces returned zero spans, inbound or outbound — which excludes every "frontend is up but struggling" story, since resolution errors, partial degradation, timeouts and inbound caller traffic would each leave spans behind.

The answer came from the change record. Four changes landed on frontend, all from the same automation actor, all within roughly three minutes of onset. The workload and its Service object were created about three minutes before onset — this is a fresh bring-up, not a mutation of a stable deployment. The two most recent, applied together about two minutes before onset, removed the cluster-default DNS policy and substituted an explicit configuration naming a single public resolver, 8.8.8.8. That resolver cannot answer for cluster-internal names.

Ruled out in the same record: no image or version bump, so no code deploy; no flag toggles; no human actor; nothing older than three minutes, so no slow-building edit; and the Service was created rather than modified, so routing is not implicated.

> Evidence `tr_a9a3db832182`:

```
<tool_result id="tr_a9a3db832182" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for frontend: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T07:51:38.025922+00:00..2026-10-03T08:21:43.823556+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for frontend: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_a9a3db832182>
```

> Evidence `tr_66fc0c934048`:

```
<tool_result id="tr_66fc0c934048" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="true" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00">
no log lines matched {namespace="astronomy-shop",pod=~"frontend-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} over this window
</tool_result:tr_66fc0c934048>
```

> Evidence `tr_2dcc48fc8659`:

```
<tool_result id="tr_2dcc48fc8659" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00">
no traces for frontend over this window
</tool_result:tr_2dcc48fc8659>
```

> Evidence `tr_929c50e7f8bf`:

```
<tool_result id="tr_929c50e7f8bf" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T08:51:43.823556+00:00..2026-10-03T08:51:49.621190+00:00" radius="candidate_cause" hops="1">
service: frontend
4 changes, ranked by suspicion
  #1  2m before onset  2026-10-03T08:49:31+00:00  platform-automation  container updated: dnsConfig changed
      None  ->  {"nameservers": ["8.8.8.8"]}
  #2  2m before onset  2026-10-03T08:49:31+00:00  platform-automation  container updated: dnsPolicy changed
```

## Conclusion and what is still open

The cause is a configuration value naming the wrong resolver: frontend can neither resolve nor reach any in-cluster dependency. Fix class is a config revert — restore the cluster-default DNS policy and drop the custom resolver block. frontend-proxy is the service that noticed, not the service that failed. Confidence is medium, deliberately.

Still open, and worth reading before trusting the above. First: no confirmation that frontend is actually Running and Ready — pod status, restart counts and exit reasons were never queried, and given the workload was created minutes before onset, a fresh deployment that simply failed to come up cannot be excluded. This is the most valuable next query. Second: the resolution-failure mechanism was never witnessed. Frontend emitted no outbound spans and the proxy returned no access logs or response flags, so the mechanism is inferred from the change record alone. Third: the Envoy restart at ~08:48:51 sits between the config edit and onset, and whether it is consequence, coincidence or contributor is unresolved.

Also unexamined: the two earlier changes in the set were truncated in the sample and never assessed on their own merits, and the single unmeasured edge was never dispatched against, so one dependency below frontend remains unchecked.

> Evidence `tr_929c50e7f8bf`:

```
<tool_result id="tr_929c50e7f8bf" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T08:51:43.823556+00:00..2026-10-03T08:51:49.621190+00:00" radius="candidate_cause" hops="1">
service: frontend
4 changes, ranked by suspicion
  #1  2m before onset  2026-10-03T08:49:31+00:00  platform-automation  container updated: dnsConfig changed
      None  ->  {"nameservers": ["8.8.8.8"]}
  #2  2m before onset  2026-10-03T08:49:31+00:00  platform-automation  container updated: dnsPolicy changed
```

> Evidence `tr_2dcc48fc8659`:

```
<tool_result id="tr_2dcc48fc8659" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00">
no traces for frontend over this window
</tool_result:tr_2dcc48fc8659>
```

> Evidence `tr_362c05685e3e`:

```
<tool_result id="tr_362c05685e3e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T08:21:43.823556+00:00..2026-10-03T08:51:49.621190+00:00">
selector: {namespace="astronomy-shop",pod=~"frontend-proxy-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.regex_engines: envoy.regex_engines.google_re2
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.tracers.opentelemetry.resource_detectors: envoy.tracers.opentelemetry.resource_detectors.dynatrace, envoy.tracers.opentelemetry.resource_detectors.environment, envoy.tracers.opentelemetry.resource_detectors.static_config
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.udp_packet_writer: envoy.udp_packet_writer.default, envoy.udp_packet_writer.gso
2026-10-03T08:48:51+00:00  [2026-10-03 08:48:51.179][15][info][main] [source/server/server.cc:440]   envoy.matching.network.custom_matchers: envoy.matching.custom_matchers.trie_matcher
```

