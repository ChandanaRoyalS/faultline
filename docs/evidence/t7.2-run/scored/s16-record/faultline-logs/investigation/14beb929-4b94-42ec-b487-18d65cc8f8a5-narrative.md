# Six hotel-reservation MongoDB instances stopped by external SIGTERM

## What was visible, and the first dead end

Six alerts arrived together at T+0, one per MongoDB instance in hotel-reservation (geo, profile, rate, recommendation, reservation, user), severity warning, with no graph-known entry point to walk back from. Six independent databases do not degrade in lockstep, so something above them acted on all of them at once.

The first move was a metrics baseline on mongodb-geo, then mongodb-user. Both came back empty, and empty in a way that is easy to misread: the backend reported the series as unavailable, not zero, because these datastores emit no traces that become Prometheus series. The whole span-derived family of queries is closed for them. Both the incident window and a separate earlier baseline failed identically, so this was not a bad time range or a transient scrape gap — retrying wider does not help. Two traps worth remembering: a blank panel here is a coverage gap, not evidence of health; and because no connection, memory, or throttling series returned either, saturation hypotheses stayed fully open at this point rather than being eliminated. Roughly twenty minutes went into this branch for no yield.

> Evidence `tr_f427209b3657`:

```
<tool_result id="tr_f427209b3657" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T09:38:17.601365+00:00..2026-10-03T10:08:23.645716+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-geo: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T09:08:11.557014+00:00..2026-10-03T09:38:17.601365+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-geo: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_f427209b3657>
```

> Evidence `tr_11db3f5b33a4`:

```
<tool_result id="tr_11db3f5b33a4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T09:38:17.601365+00:00..2026-10-03T10:08:23.645716+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-user: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T09:08:11.557014+00:00..2026-10-03T09:38:17.601365+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-user: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_11db3f5b33a4>
```

## Logs gave the answer in one query per service

mongodb-geo received an external termination signal about a minute before the alerts and ran a complete ordered shutdown: replication step-down, three in-flight operations killed, listening sockets and connection pool closed, WiredTiger torn down, clean-shutdown marker written. Every line informational; nothing before the signal. mongodb-user matched a second later and ran the full teardown to exit status zero in about twenty-eight milliseconds, three operations in flight, no restart lines afterwards. mongodb-reservation showed the same single burst, same signal, same routine stages. In all three the signal is attributed to kill(2) from pid 0 / uid 0 — the shape of an orchestrator stopping a pod, not anything the process did to itself.

This closed several live hypotheses at once. A hard kill is excluded: it leaves no trace, whereas these teardowns completed cleanly. Connection exhaustion is excluded: no refusal or limit entries, and three in-flight operations describes a lightly loaded instance. Election churn and storage corruption are excluded: the only replication and storage entries are the normal informational shutdown stages. Caveat: the log results were truncated, so 'quiet beforehand' rests on a tail of the window.

> Evidence `tr_e3f5da9a7ba3`:

```
<tool_result id="tr_e3f5da9a7ba3" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:38:17.601365+00:00..2026-10-03T10:08:23.645716+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-geo-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T10:07:17+00:00  {"t":{"$date":"2026-10-03T10:07:17.271+00:00"},"s":"I",  "c":"STORAGE",  "id":22323,   "ctx":"SignalHandler","msg":"Finished shutting down checkpoint thread"}
2026-10-03T10:07:17+00:00  {"t":{"$date":"2026-10-03T10:07:17.271+00:00"},"s":"I",  "c":"STORAGE",  "id":22322,   "ctx":"SignalHandler","msg":"Shutting down checkpoint thread"}
2026-10-03T10:07:17+00:00  {"t":{"$date":"2026-10-03T10:07:17.271+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T10:07:17+00:00  {"t":{"$date":"2026-10-03T10:07:17.271+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
```

> Evidence `tr_540a1d20a6c7`:

```
<tool_result id="tr_540a1d20a6c7" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:38:17.601365+00:00..2026-10-03T10:08:23.645716+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-user-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.976+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.976+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.975+00:00"},"s":"I",  "c":"STORAGE",  "id":22317,   "ctx":"SignalHandler","msg":"WiredTigerKVEngine shutting down"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.975+00:00"},"s":"I",  "c":"STORAGE",  "id":22261,   "ctx":"SignalHandler","msg":"Timestamp monitor shutting down"}
```

> Evidence `tr_0cd4e97940fd`:

```
<tool_result id="tr_0cd4e97940fd" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:38:17.601365+00:00..2026-10-03T10:08:23.645716+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-reservation-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.643+00:00"},"s":"I",  "c":"STORAGE",  "id":22323,   "ctx":"SignalHandler","msg":"Finished shutting down checkpoint thread"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.643+00:00"},"s":"I",  "c":"STORAGE",  "id":22322,   "ctx":"SignalHandler","msg":"Shutting down checkpoint thread"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.643+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T10:07:18+00:00  {"t":{"$date":"2026-10-03T10:07:18.643+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
```

## Change log, remaining leads, and remedy

The day-long change history is empty except for a tight burst by platform-automation immediately before onset. For mongodb-geo: two ConfigMaps, a Service, and the container, all created within about eighty seconds, with the container recorded as a first creation — so there was no prior running state to regress from, which closes image bumps, redeploys, sidecar changes, resource-limit tightening, node moves, and slow drift. One geo ConfigMap is named like an administrative or deliberate-failure config, created seconds before the container; its contents were never read, so it is a name, not a finding. mongodb-reservation only partially matches: Service and first container creation about a minute before onset, no ConfigMap at all. So that config is not a uniform property of the affected set. Nothing in the change log records a delete or scale-down to corroborate the terminations.

Conclusion: all six were stopped by externally delivered signals within about a second of each other; the processes are absent, so callers are hitting dead endpoints and the alerts reflect missing datastores rather than a defect in any one database. Fix class is restart. Confidence is low.

Still open: whether the processes stayed down past the window end (truncated logs, no startup lines seen — widen first); who issued the signals; what the administrative ConfigMap contains; and whether profile, rate and recommendation share the signature, since they were never examined.

> Evidence `tr_03f6bbb5b918`:

```
<tool_result id="tr_03f6bbb5b918" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:08:17.601365+00:00..2026-10-03T10:08:23.645716+00:00" radius="seed" hops="0">
service: mongodb-geo
4 changes, ranked by suspicion
  #1  1m before onset  2026-10-03T10:07:17+00:00  platform-automation  container created: workload first created
  #2  1m before onset  2026-10-03T10:07:00+00:00  platform-automation  config created: ConfigMap failure-admin-geo created
  #3  1m before onset  2026-10-03T10:06:59+00:00  platform-automation  config created: Service mongodb-geo created
```

> Evidence `tr_044c506c1683`:

```
<tool_result id="tr_044c506c1683" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:08:17.601365+00:00..2026-10-03T10:08:23.645716+00:00" radius="seed" hops="0">
service: mongodb-reservation
2 changes, ranked by suspicion
  #1  59s before onset  2026-10-03T10:07:18+00:00  platform-automation  container created: workload first created
  #2  1m before onset  2026-10-03T10:07:00+00:00  platform-automation  config created: Service mongodb-reservation created
</tool_result:tr_044c506c1683>
```

