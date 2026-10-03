# rate crash-loops on datastore connect; culprit datastore never observed

## What the alert looked like from the chair

The page arrived as a warning spanning ten services, with the alert set covering rate, reservation, and six mongodb-* backends (geo, profile, rate, recommendation, reservation, user). The entry point was rate, and three of the edges crossed during the walk were unmeasured — that detail turned out to matter more than it usually does, because most of the instrumentation I reached for in the first fifteen minutes gave me nothing usable.

The shape to hold in mind while reading the rest: exactly one query in this investigation returned real data. Everything else failed for structural or syntactic reasons, and several of those failures looked at first glance like meaningful negatives.

## The one signal that held: rate's own logs

At roughly T+3m I pulled rate's pod logs for the half hour around onset. This is the only evidence in the record that actually answers a question.

The pattern is unambiguous and repeats: the pod starts, reads its configuration successfully, logs the datastore URL it intends to use — mongodb-rate:27017, which is the correct endpoint — reports TLS as disabled, and then about twelve seconds later panics inside database initialization with an unreachable-servers error. Two full cycles are visible back to back within the window, beginning around the onset minute and again roughly a minute later, and the loop is still running at the window's edge.

The stack trace points at the database-init call reached from main. There are no request-handling lines, no gRPC-serving lines, nothing from any handler. The process never gets far enough to take traffic.

> Evidence `tr_88a01606ee27`:

```
<tool_result id="tr_88a01606ee27" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00">
selector: {namespace="hotel-reservation",pod=~"rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:38 > Initializing DB connection...
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:37 > Read database URL: mongodb-rate:27017
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:24 > Reading config...
2026-10-03T04:36:51+00:00  {"level":"info","time":"2026-10-03T04:36:51Z","message":"Tune: setGCPercent to 100"}
```

## What that one log ruled out

Four plausible stories died on this evidence, and it is worth recording them so nobody re-runs them:

rate is up but degraded under load — no. There are no request-level logs at all. It is not a running service returning errors; it is a process that never starts serving.

rate is misconfigured — no. Config loads cleanly and the expected datastore endpoint appears on every single attempt. The failure happens strictly after config load, at connect time.

A bug in rate's business logic — no. The trace is in startup, not in any handler path.

Pool exhaustion or query timeouts — no. There are zero timeout entries and zero pool-related entries. The failure is the initial connect, not a saturated or slow connection.

A transient blip that already cleared — no. At least two complete start-and-panic cycles run consecutively through the end of the window.

The texture of the failure is specific: a dial deadline expiring at connection establishment, with nothing in the query or pool layers. That points outward, at mongodb-rate, not inward at rate.

> Evidence `tr_88a01606ee27`:

```
<tool_result id="tr_88a01606ee27" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00">
selector: {namespace="hotel-reservation",pod=~"rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:38 > Initializing DB connection...
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:37 > Read database URL: mongodb-rate:27017
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:24 > Reading config...
2026-10-03T04:36:51+00:00  {"level":"info","time":"2026-10-03T04:36:51Z","message":"Tune: setGCPercent to 100"}
```

## Dead end one: mongodb-rate's logs were never read

The obvious next move was to hear from mongodb-rate directly. That query never executed. Loki returned HTTP 400 on the request — the pod selector used an escaped hyphen inside the regex alternation, which Loki rejected as malformed.

This is the single most important dead end in the record, for two reasons. First, the culprit's own voice is entirely absent from this investigation. Second, the empty payload is extremely easy to misread. It is not a zero-row response. It says nothing about whether mongodb-rate was logging, silent, crash-looping, or gone.

Two tempting inferences I explicitly refused: that mongodb-rate emitted no logs and was therefore absent (the error artifact is not evidence of silence), and that Loki or the log pipeline was broken (Loki answered with a 400, meaning it was reachable and processing — it rejected the query, not the connection). The time window was also not implicated; start and end were accepted into the URL and the rejection happened before range evaluation.

Fix for whoever picks this up: correct the pod selector and re-run. That one query likely resolves the whole incident.

> Evidence `tr_46428f62c4a4`:

```
<tool_result id="tr_46428f62c4a4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="[loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22hotel-reservation%22%2Cpod%3D~%22mongodb%5C-rate-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791000344440189696&end=1791002444440189696&limit=100">
query failed: [loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22hotel-reservation%22%2Cpod%3D~%22mongodb%5C-rate-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791000344440189696&end=1791002444440189696&limit=100
</tool_result:tr_46428f62c4a4>
```

## Dead end two: both metric baselines were structurally empty

I went to Prometheus for error ratio, latency, request volume, and saturation on both rate and mongodb-rate. Both came back with nothing, and both for the same reason: the error-ratio metric is derived from span telemetry, and this environment's Prometheus holds no such series for either service. They emit no traces that become metrics.

This is an availability gap, not a measurement. I want to be loud about it because the empty series looks exactly like a clean bill of health. It is not. For rate, the absence of a reported error ratio does not mean rate was erroring at zero. For mongodb-rate, the absence does not clear the database as a contributor.

A related trap: one might argue the empty result shows mongodb-rate was down during the window. It does not — the baseline window *before* onset is equally empty. A service that fell over at onset would show data beforehand. Uniform absence across both windows means the metric never existed.

Practical consequence: span-metric dashboards and alerts are inert for these two services. Their silence during the incident carries no information, and repeating this family of query will not produce data. Anything about connection saturation, cache pressure, or operation latency has to come from direct database telemetry, server logs, or from what callers observe.

> Evidence `tr_bfcbc09c5459`:

```
<tool_result id="tr_bfcbc09c5459" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for rate: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:34:12.324887+00:00..2026-10-03T04:06:49.415424+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for rate: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_bfcbc09c5459>
```

> Evidence `tr_f6ed97dbcbce`:

```
<tool_result id="tr_f6ed97dbcbce" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T03:34:12.324887+00:00..2026-10-03T04:06:49.415424+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for mongodb-rate: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_f6ed97dbcbce>
```

## Dead end three: every change-history query died the same way

I queried change history three times — for rate, for mongodb-rate, and for mongodb-reservation — and all three terminated with an identical parse error on a truncated response payload (an unterminated string at the same offset each time). This reads as a malformed or oversized response from the change-log source, not as a filter matching zero records.

So: no deployment, image, version, auth, storage, or config change in the preceding period has been observed for any of these services. The change hypothesis is fully open. I did not exclude it, and the record should not be read as excluding it. Excluding change requires evidence of no change, and I have none.

There is a second defect worth flagging. The window I used started at the incident timestamp and ran forward about twenty-four hours. Even if the queries had succeeded, they would have covered the wrong side of onset for the question being asked. Whoever retries should query *backwards* from onset, and should narrow the window or reduce the page size to avoid the truncated payload.

> Evidence `tr_4d406f3b84ac`:

```
<tool_result id="tr_4d406f3b84ac" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T04:36:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="Unterminated string starting at: line 226 column 17 (char 9998)">
query failed: Unterminated string starting at: line 226 column 17 (char 9998)
</tool_result:tr_4d406f3b84ac>
```

> Evidence `tr_1c9653913a48`:

```
<tool_result id="tr_1c9653913a48" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T04:36:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="Unterminated string starting at: line 226 column 17 (char 9998)">
query failed: Unterminated string starting at: line 226 column 17 (char 9998)
</tool_result:tr_1c9653913a48>
```

> Evidence `tr_c183cd3a076b`:

```
<tool_result id="tr_c183cd3a076b" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T04:36:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="Unterminated string starting at: line 226 column 17 (char 9998)">
query failed: Unterminated string starting at: line 226 column 17 (char 9998)
</tool_result:tr_c183cd3a076b>
```

## Where this landed, and with how much weight

The surviving mechanism consistent with the one good signal: mongodb-rate's process is stopped or otherwise not answering while its network identity still resolves, so rate's dial runs to its deadline and the process panics. Present-but-unserving, rather than anything wrong inside rate.

Confidence is low, and the reason is simple — this conclusion rests on a single log stream, read from the caller's side only. The remedy class is a restart of mongodb-rate.

I would not escalate this to a cluster-level story without more evidence, but I would not dismiss it either: five other mongodb-* services alerted alongside mongodb-rate, and I never checked whether they share the same failure.

> Evidence `tr_88a01606ee27`:

```
<tool_result id="tr_88a01606ee27" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00">
selector: {namespace="hotel-reservation",pod=~"rate-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:38 > Initializing DB connection...
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:37 > Read database URL: mongodb-rate:27017
2026-10-03T04:36:51+00:00  2026-10-03T04:36:51Z INF cmd/rate/main.go:24 > Reading config...
2026-10-03T04:36:51+00:00  {"level":"info","time":"2026-10-03T04:36:51Z","message":"Tune: setGCPercent to 100"}
```

## Open items for the next responder

Four things, roughly in the order I would do them.

One: re-run the mongodb-rate log query with a corrected pod selector. The answer is probably in there. What you are looking for distinguishes the remaining candidates — a silent mongod, one complaining it cannot reach anything, one refusing writes for lack of space, or no pod at all.

Two: check pod and container state for mongodb-rate at the infrastructure level. Running, CrashLoopBackOff, Pending, evicted? No such check was performed during this investigation at all, which in hindsight should have been the second thing I did rather than the thing I never did.

Three: retry change history for rate and mongodb-rate over a window that *precedes* onset, in smaller slices to dodge the truncation.

Four: compare the other alerting mongodb-* services. If they show the same connect-time failure from their callers, the cause sits above any single datastore and the restart remedy is wrong.

> Evidence `tr_46428f62c4a4`:

```
<tool_result id="tr_46428f62c4a4" tool="logql_query" trust="untrusted" source="loki" empty="true" truncated="false" window="2026-10-03T04:06:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="[loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22hotel-reservation%22%2Cpod%3D~%22mongodb%5C-rate-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791000344440189696&end=1791002444440189696&limit=100">
query failed: [loki_mcp] Error querying get_logs: 400 Client Error: Bad Request for url: http://loki.observe.svc.cluster.local:3100/loki/api/v1/query_range?query=%7Bnamespace%3D%22hotel-reservation%22%2Cpod%3D~%22mongodb%5C-rate-%28%5Ba-z0-9%5D%2B-%5Ba-z0-9%5D%2B%7C%5B0-9%5D%2B%29%22%7D&start=1791000344440189696&end=1791002444440189696&limit=100
</tool_result:tr_46428f62c4a4>
```

> Evidence `tr_4d406f3b84ac`:

```
<tool_result id="tr_4d406f3b84ac" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T04:36:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="Unterminated string starting at: line 226 column 17 (char 9998)">
query failed: Unterminated string starting at: line 226 column 17 (char 9998)
</tool_result:tr_4d406f3b84ac>
```

> Evidence `tr_1c9653913a48`:

```
<tool_result id="tr_1c9653913a48" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-10-02T04:36:49.415424+00:00..2026-10-03T04:39:26.505961+00:00" error="Unterminated string starting at: line 226 column 17 (char 9998)">
query failed: Unterminated string starting at: line 226 column 17 (char 9998)
</tool_result:tr_1c9653913a48>
```

