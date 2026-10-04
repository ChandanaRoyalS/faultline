# mongodb-rate: pod created, then stopped from outside within seconds

## What the page looked like

The page named a single service, mongodb-rate, at warning severity, with a blast radius of one and no upstream or downstream edge implicated. There was no graph anchor to start from — the datastore does not appear in the service topology that the tooling draws, so the usual "walk the callers" move was unavailable from the first minute. The practical consequence for the responder: everything below was reconstructed from the pod's own logs and the change log, because neither traces nor metrics existed for this service. If you pick this record up months later, start where we ended up starting: Loki, pod selector on the hotel-reservation namespace.

> Evidence `tr_596c016954c3`:

```
<tool_result id="tr_596c016954c3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T09:02:21.712780+00:00..2026-10-03T15:02:21.712780+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:02:21.712780+00:00..2026-10-03T09:02:21.712780+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_596c016954c3>
```

## Reconstructed order of events

Working backwards from the page (call it T+0), the whole story sits in a roughly twenty-second band about a minute and a half earlier. At about T-90s the platform automation created the workload for the first time — container, Service, two ConfigMaps, and a PersistentVolumeClaim. At about T-79s the storage engine opened cleanly: sub-second open, recovery timestamps established, journal recovery run to completion, no table-logging rewrites. Seconds later the process was shut down in an orderly, signal-driven way. At about T-77s the identical cycle repeated — same engine configuration string, byte for byte — and ended the same way. At roughly T-71s the process logged receipt of signal 15, attributed to kill(2) from pid 0/uid 0, then walked the full teardown: replication coordinator stepped down, listening sockets closed, unix socket file removed, storage engine, checkpoint, journal and session-sweeper threads shut down. Only three in-flight operations were interrupted, so the instance was carrying essentially no load when it was stopped. The log window we queried runs out shortly after the page, so there is no observation of whether a third startup followed.

> Evidence `tr_616998c15f26`:

```
<tool_result id="tr_616998c15f26" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T15:02:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" radius="seed" hops="0">
service: mongodb-rate
7 changes, ranked by suspicion
  #1  1m before onset  2026-10-03T15:01:10+00:00  platform-automation  container created: workload first created
  #2  1m before onset  2026-10-03T15:01:00+00:00  platform-automation  config updated: PersistentVolumeClaim rate-pvc changed
  #3  1m before onset  2026-10-03T15:01:00+00:00  platform-automation  config updated: PersistentVolumeClaim rate-pvc changed
```

> Evidence `tr_fcd9d6881852`:

```
<tool_result id="tr_fcd9d6881852" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" contains="WiredTiger">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "WiredTiger"
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.516+00:00"},"s":"I",  "c":"STORAGE",  "id":4366408, "ctx":"initandlisten","msg":"No table logging settings modifications are required for existing WiredTiger tables","attr":{"loggingEnabled":true}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.504+00:00"},"s":"I",  "c":"RECOVERY", "id":23987,   "ctx":"initandlisten","msg":"WiredTiger recoveryTimestamp","attr":{"recoveryTimestamp":{"$timestamp":{"t":0,"i":0}}}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.504+00:00"},"s":"I",  "c":"STORAGE",  "id":4795906, "ctx":"initandlisten","msg":"WiredTiger opened","attr":{"durationMillis":230}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.497+00:00"},"s":"I",  "c":"STORAGE",  "id":22430,   "ctx":"initandlisten","msg":"WiredTiger message","attr":{"message":"[1791039662:497413][36:0x7edb5191eac0], txn-recover: [WT_VERB_RECOVERY | WT_VERB_RECOVERY_PROGRESS] Set global oldest timestamp: (0, 0)"}}
```

> Evidence `tr_9948fd3a2026`:

```
<tool_result id="tr_9948fd3a2026" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22323,   "ctx":"SignalHandler","msg":"Finished shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22322,   "ctx":"SignalHandler","msg":"Shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
```

## What the change log said, and what it did not

All seven recorded changes to this service cluster into that same twenty-second span and all carry the platform-automation actor, not a human. The entries describe first-time creation rather than modification of something already running. The PersistentVolumeClaim (rate-pvc) was created and then updated twice inside about seven seconds — the only object touched after its initial create, which made it the natural first suspect. One of the two ConfigMaps carries a name that advertises deliberate failure-administration tooling aimed at this service, and it landed seconds before the container came up. Searching the full preceding 24 hours turned up nothing at all before that burst: no older edit, no drift, no scaling or replica-count action, no image roll.

> Evidence `tr_616998c15f26`:

```
<tool_result id="tr_616998c15f26" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T15:02:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" radius="seed" hops="0">
service: mongodb-rate
7 changes, ranked by suspicion
  #1  1m before onset  2026-10-03T15:01:10+00:00  platform-automation  container created: workload first created
  #2  1m before onset  2026-10-03T15:01:00+00:00  platform-automation  config updated: PersistentVolumeClaim rate-pvc changed
  #3  1m before onset  2026-10-03T15:01:00+00:00  platform-automation  config updated: PersistentVolumeClaim rate-pvc changed
```

## Dead ends worth keeping

Storage was the loudest-looking lead and it went nowhere. The PVC being rewritten twice reads like a volume problem, but both engine opens succeeded against the data path, read the journal and completed recovery — which cannot happen on an unmounted or unreadable volume. No salvage, no repair, no corruption markers; the closes wrote checkpoints cleanly. The engine configuration string was identical across both startups, so there was no storage-level config drift hiding behind the PVC edits.

Crash theories also failed. An out-of-memory kill or a segfault leaves no orderly teardown; what we have is a handled termination path with clean-shutdown marking, so the process did not die of its own accord. A separate pass filtering for ERROR-severity lines across the full half-hour window returned nothing — not one line, including around the stop. That empty answer cuts both ways: it rules out an error storm building over the preceding half hour and rules out a self-diagnosed fatal condition, but it is also why we never got an application-level statement of what hit it.

One timing argument we entertained and should flag as misleading: because the termination sits near the end of the queried window, it is tempting to say it post-dates onset and therefore cannot be the trigger. Given the page itself landed about a minute after, and given the broad log pull was marked truncated (quieter pre-event lines may exist and simply were not returned), that reasoning is weaker than it looks. Do not lean on it.

Finally, the metrics path is a dead end by construction, not by accident. Error-ratio, p95, request rate, and resource series all came back with nothing over both the incident window and the preceding baseline. This is an unavailable result, not a zero — the backend holds no span-derived series for this service because it emits no traces that become metrics. Re-running the same templates with a different range will not help, and nobody should read the blank chart as evidence the datastore was healthy.

> Evidence `tr_fcd9d6881852`:

```
<tool_result id="tr_fcd9d6881852" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" contains="WiredTiger">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "WiredTiger"
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.516+00:00"},"s":"I",  "c":"STORAGE",  "id":4366408, "ctx":"initandlisten","msg":"No table logging settings modifications are required for existing WiredTiger tables","attr":{"loggingEnabled":true}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.504+00:00"},"s":"I",  "c":"RECOVERY", "id":23987,   "ctx":"initandlisten","msg":"WiredTiger recoveryTimestamp","attr":{"recoveryTimestamp":{"$timestamp":{"t":0,"i":0}}}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.504+00:00"},"s":"I",  "c":"STORAGE",  "id":4795906, "ctx":"initandlisten","msg":"WiredTiger opened","attr":{"durationMillis":230}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.497+00:00"},"s":"I",  "c":"STORAGE",  "id":22430,   "ctx":"initandlisten","msg":"WiredTiger message","attr":{"message":"[1791039662:497413][36:0x7edb5191eac0], txn-recover: [WT_VERB_RECOVERY | WT_VERB_RECOVERY_PROGRESS] Set global oldest timestamp: (0, 0)"}}
```

> Evidence `tr_4d3c551d555b`:

```
<tool_result id="tr_4d3c551d555b" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" contains="ERROR">
no log lines matched {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "ERROR" over this window
</tool_result:tr_4d3c551d555b>
```

> Evidence `tr_9948fd3a2026`:

```
<tool_result id="tr_9948fd3a2026" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22323,   "ctx":"SignalHandler","msg":"Finished shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22322,   "ctx":"SignalHandler","msg":"Shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
```

> Evidence `tr_596c016954c3`:

```
<tool_result id="tr_596c016954c3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T09:02:21.712780+00:00..2026-10-03T15:02:21.712780+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:02:21.712780+00:00..2026-10-03T09:02:21.712780+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_596c016954c3>
```

## Where we landed

The best-supported reading is that mongodb-rate was stopped from outside, twice, within seconds of each fresh start, by an administered SIGTERM. The service itself logged no errors; its storage engine opened, recovered and checkpointed correctly every time. The mechanism is the process being stopped, not any value being wrong. Downstream, the datastore is absent from the topology while its socket and endpoint churn, which leaves callers in the hotel-reservation namespace without a rate datastore. The co-located ConfigMap named for failure administration is the obvious candidate for who sent the signal, but we never closed that loop. Confidence is low. The indicated remedy class is a restart.

> Evidence `tr_9948fd3a2026`:

```
<tool_result id="tr_9948fd3a2026" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22323,   "ctx":"SignalHandler","msg":"Finished shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22322,   "ctx":"SignalHandler","msg":"Shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
```

> Evidence `tr_fcd9d6881852`:

```
<tool_result id="tr_fcd9d6881852" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" contains="WiredTiger">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "WiredTiger"
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.516+00:00"},"s":"I",  "c":"STORAGE",  "id":4366408, "ctx":"initandlisten","msg":"No table logging settings modifications are required for existing WiredTiger tables","attr":{"loggingEnabled":true}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.504+00:00"},"s":"I",  "c":"RECOVERY", "id":23987,   "ctx":"initandlisten","msg":"WiredTiger recoveryTimestamp","attr":{"recoveryTimestamp":{"$timestamp":{"t":0,"i":0}}}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.504+00:00"},"s":"I",  "c":"STORAGE",  "id":4795906, "ctx":"initandlisten","msg":"WiredTiger opened","attr":{"durationMillis":230}}
2026-10-03T15:01:02+00:00  {"t":{"$date":"2026-10-03T15:01:02.497+00:00"},"s":"I",  "c":"STORAGE",  "id":22430,   "ctx":"initandlisten","msg":"WiredTiger message","attr":{"message":"[1791039662:497413][36:0x7edb5191eac0], txn-recover: [WT_VERB_RECOVERY | WT_VERB_RECOVERY_PROGRESS] Set global oldest timestamp: (0, 0)"}}
```

> Evidence `tr_4d3c551d555b`:

```
<tool_result id="tr_4d3c551d555b" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" contains="ERROR">
no log lines matched {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "ERROR" over this window
</tool_result:tr_4d3c551d555b>
```

> Evidence `tr_616998c15f26`:

```
<tool_result id="tr_616998c15f26" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T15:02:21.712780+00:00..2026-10-03T15:02:30.027564+00:00" radius="seed" hops="0">
service: mongodb-rate
7 changes, ranked by suspicion
  #1  1m before onset  2026-10-03T15:01:10+00:00  platform-automation  container created: workload first created
  #2  1m before onset  2026-10-03T15:01:00+00:00  platform-automation  config updated: PersistentVolumeClaim rate-pvc changed
  #3  1m before onset  2026-10-03T15:01:00+00:00  platform-automation  config updated: PersistentVolumeClaim rate-pvc changed
```

## Still open — do these next time

Nobody pulled kubelet output or pod lifecycle events, so the source of the SIGTERM is unproven: it could be the administration ConfigMap, ordinary Kubernetes rescheduling during a first creation, or a liveness probe failing and the kubelet reaping the container. That is the single highest-value gap.

We also do not know whether the service stayed down after the last stop — the log window ends about a minute past the page with no later startup observed. Extend the window first thing.

No upstream metrics or logs were ever dispatched, so we cannot say which callers (the rate service being the obvious one) actually degraded, or whether they hung to their deadline versus failed fast.

And it remains unclear what signal the page itself fired on, given the metrics store holds no series for this service at all. Whatever fired it came from somewhere other than the place we looked.

> Evidence `tr_596c016954c3`:

```
<tool_result id="tr_596c016954c3" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T09:02:21.712780+00:00..2026-10-03T15:02:21.712780+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:02:21.712780+00:00..2026-10-03T09:02:21.712780+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_596c016954c3>
```

> Evidence `tr_9948fd3a2026`:

```
<tool_result id="tr_9948fd3a2026" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T14:32:21.712780+00:00..2026-10-03T15:02:30.027564+00:00">
selector: {namespace="hotel-reservation",pod=~"mongodb-rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22323,   "ctx":"SignalHandler","msg":"Finished shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22322,   "ctx":"SignalHandler","msg":"Shutting down checkpoint thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22319,   "ctx":"SignalHandler","msg":"Finished shutting down session sweeper thread"}
2026-10-03T15:01:10+00:00  {"t":{"$date":"2026-10-03T15:01:10.342+00:00"},"s":"I",  "c":"STORAGE",  "id":22318,   "ctx":"SignalHandler","msg":"Shutting down session sweeper thread"}
```

