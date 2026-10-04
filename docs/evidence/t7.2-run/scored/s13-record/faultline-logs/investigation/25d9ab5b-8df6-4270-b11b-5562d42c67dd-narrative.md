# Accounting order consumer rejecting writes with duplicate primary keys

## What was visible, in order

The page came from accounting itself — severity critical, blast radius one service, no graph path leading in. There was no upstream to walk back to, so the usual first instinct (find the caller that broke us) had nothing to work with. Call the alert T+0.

The pod logs answered fast. About thirty seconds before the page, the consumer threw an EF Core DbUpdateException wrapping a PostgreSQL unique-constraint violation, SQLSTATE 23505, on the primary key of the order table. The stack ran through the Npgsql batch-execute path, which matters: the connection was live and the server actively refused the row, so this was never a reachability problem. One and two seconds later the consumer logged ordinary order-processing records with full detail — the process was alive and still consuming, so no crash, no restart, no stalled ingestion.

Filtering the same logs on the SQL state showed the event was the tail of a series, not a one-off: roughly twenty-one exception events, about twenty of them packed into a three-second burst near T-1m30s, then a single trailing event a minute later. Every line named the same constraint on the same table — no schema-wide spread.

Traces confirmed the shape. Nineteen traces rooted at accounting's order-consumed operation, each with an identical flat three-span layout: consume root, one errored persist child, one broker-receive child. The errored span was a leaf; no span crossed into another service. The receive hop was consistently 5–12ms and never errored. Eighteen of nineteen failures completed in 44–250ms and still errored, so this was a rejection, not an expiry. The nineteen were distinct trace IDs arriving ~100–200ms apart — re-delivery, if happening, was arriving as fresh traces rather than an in-process retry loop. One outlier at the tail ran ~53s with ~15s in the persist span, consistent with pile-up at the end of the burst and not representative.

> Evidence `tr_d652adf5048e`:

```
<tool_result id="tr_d652adf5048e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00">
selector: {namespace="astronomy-shop",pod=~"accounting-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T09:44:06+00:00           at Microsoft.EntityFrameworkCore.ChangeTracking.Internal.StateManager.SaveChanges(Boolean acceptAllChangesOnSuccess)
2026-10-03T09:44:06+00:00           at Npgsql.EntityFrameworkCore.PostgreSQL.Storage.Internal.NpgsqlExecutionStrategy.Execute[TState,TResult](TState state, Func`3 operation, Func`3 verifySucceeded)
2026-10-03T09:44:06+00:00           at Microsoft.EntityFrameworkCore.ChangeTracking.Internal.StateManager.<>c.<SaveChanges>b__114_0(DbContext _, ValueTuple`2 t)
2026-10-03T09:44:06+00:00           at Microsoft.EntityFrameworkCore.ChangeTracking.Internal.StateManager.SaveChanges(StateManager stateManager, Boolean acceptAllChangesOnSuccess)
```

> Evidence `tr_3a2a5fdbff47`:

```
<tool_result id="tr_3a2a5fdbff47" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00" contains="23505">
selector: {namespace="astronomy-shop",pod=~"accounting-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "23505"
2026-10-03T09:43:11+00:00            SqlState: 23505
2026-10-03T09:43:11+00:00         ---> Npgsql.PostgresException (0x80004005): 23505: duplicate key value violates unique constraint "order_pkey"
2026-10-03T09:43:11+00:00            SqlState: 23505
2026-10-03T09:43:11+00:00         ---> Npgsql.PostgresException (0x80004005): 23505: duplicate key value violates unique constraint "order_pkey"
```

> Evidence `tr_2b3aecdb27d3`:

```
<tool_result id="tr_2b3aecdb27d3" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00">
service: accounting
20 trace(s) shown of 20 found, 58 spans; offsets are from each trace's root

trace ad20841860c673a7  root accounting/order-consumed  130.8ms  started 2026-10-03T09:43:11.179093+00:00  3 spans
  +0.0ms accounting/order-consumed 130.8ms [self 75.6ms]
```

## Dead ends worth keeping

The metrics were the biggest time sink and the least useful artifact. Only the error-ratio series returned. The window held two defined samples, both around 0.317, and three intervals with no value at all — which for this query means no spans were recorded, not that errors were absent. The baseline window returned zero samples, so any framing of 'rose from zero' is an artifact of missing data, not an observed error-free prior state. The tool's own verdict of 'no sustained departure from baseline' should not be believed here; it reflects insufficient sampling. The metrics did usefully kill two ideas: accounting was not hard-down (roughly a third of calls errored where traffic existed), and there was no gradual climb of the kind a slow resource drain produces.

The change log was the other near-empty well, though its emptiness is itself the finding. Across a full twenty-four hours exactly one change touched accounting: a container creation attributed to platform-automation, about three minutes before onset, characterised as the workload being created for the first time. No deploy or release. No config or environment edit. No image or tag bump on an existing workload. No earlier change that could have been a latent trigger, and no second change, so no change-on-change interaction to reason about.

Other lines closed along the way: the database was not unreachable and the pool was not exhausted (the server returned a constraint error over a live connection); a schema migration or missing object was not at fault (the table and its constraint exist and are enforced); and nothing downstream of accounting was implicated (the errored span is a leaf and no other service appears in any trace).

> Evidence `tr_87ce6ad1d4f7`:

```
<tool_result id="tr_87ce6ad1d4f7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00" template="error-ratio" baseline="2026-10-03T08:44:27.224783+00:00..2026-10-03T09:14:38.697086+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=2 mean=0.3172 min=0.3172 max=0.3172 sd=3.925e-17
  baseline window: no samples
```

> Evidence `tr_079b4ae39041`:

```
<tool_result id="tr_079b4ae39041" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T09:44:38.697086+00:00..2026-10-03T09:44:50.169389+00:00" radius="seed" hops="0">
service: accounting
1 changes, ranked by suspicion
  #1  3m before onset  2026-10-03T09:41:25+00:00  platform-automation  container created: workload first created
</tool_result:tr_079b4ae39041>
```

> Evidence `tr_2b3aecdb27d3`:

```
<tool_result id="tr_2b3aecdb27d3" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="true" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00">
service: accounting
20 trace(s) shown of 20 found, 58 spans; offsets are from each trace's root

trace ad20841860c673a7  root accounting/order-consumed  130.8ms  started 2026-10-03T09:43:11.179093+00:00  3 spans
  +0.0ms accounting/order-consumed 130.8ms [self 75.6ms]
```

## Where it landed, and what is still open

Conclusion: accounting's order consumer cannot persist orders because the inserts duplicate rows that already exist, and PostgreSQL rejects them on the order table's primary key. The database is healthy, the broker hop is clean, and the failure begins and ends inside accounting's own EF Core/Npgsql write path. The dense burst of identical violations arriving as separate traces reads as the same order messages being re-delivered and re-inserted against a store that already holds those keys. The only change in a day — a first-time container creation three minutes earlier, from automation — fits a freshly created consumer replaying from an existing offset onto an already-populated table. The mechanism is the state of the store versus the messages being replayed. Fix class: restore the data state (reconcile the table against the replayed range, or advance the consumer past it).

Confidence is low. The story is coherent; the two pieces of evidence that would confirm it are both missing.

Still open, in priority order. First, the conflicting key values and the consumer offsets are not recoverable from the logs as currently configured — Npgsql's default redaction strips the detail — so we never directly confirmed that the same orders are being re-delivered. Go get this: lift the redaction in a controlled way, or read the consumer group offsets against the topic. Second, whether the order table was already populated before the new container was created — seeded, or surviving a prior workload — was never established, and that is the hinge of the entire explanation. Third, the metrics are too sparse to characterise onset: no baseline samples and gaps with zero traffic, so the true start time is unknown and we cannot say from metrics whether errors persist now. Note also that no dispatch examined the PostgreSQL instance or the broker directly, and both log result sets were truncated — so every 'nothing appears before X' statement in this record is suggestive, not conclusive.

> Evidence `tr_d652adf5048e`:

```
<tool_result id="tr_d652adf5048e" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00">
selector: {namespace="astronomy-shop",pod=~"accounting-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T09:44:06+00:00           at Microsoft.EntityFrameworkCore.ChangeTracking.Internal.StateManager.SaveChanges(Boolean acceptAllChangesOnSuccess)
2026-10-03T09:44:06+00:00           at Npgsql.EntityFrameworkCore.PostgreSQL.Storage.Internal.NpgsqlExecutionStrategy.Execute[TState,TResult](TState state, Func`3 operation, Func`3 verifySucceeded)
2026-10-03T09:44:06+00:00           at Microsoft.EntityFrameworkCore.ChangeTracking.Internal.StateManager.<>c.<SaveChanges>b__114_0(DbContext _, ValueTuple`2 t)
2026-10-03T09:44:06+00:00           at Microsoft.EntityFrameworkCore.ChangeTracking.Internal.StateManager.SaveChanges(StateManager stateManager, Boolean acceptAllChangesOnSuccess)
```

> Evidence `tr_3a2a5fdbff47`:

```
<tool_result id="tr_3a2a5fdbff47" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-03T09:14:38.697086+00:00..2026-10-03T09:44:50.169389+00:00" contains="23505">
selector: {namespace="astronomy-shop",pod=~"accounting-([a-z0-9]+-[a-z0-9]+|[0-9]+)"} |= "23505"
2026-10-03T09:43:11+00:00            SqlState: 23505
2026-10-03T09:43:11+00:00         ---> Npgsql.PostgresException (0x80004005): 23505: duplicate key value violates unique constraint "order_pkey"
2026-10-03T09:43:11+00:00            SqlState: 23505
2026-10-03T09:43:11+00:00         ---> Npgsql.PostgresException (0x80004005): 23505: duplicate key value violates unique constraint "order_pkey"
```

> Evidence `tr_079b4ae39041`:

```
<tool_result id="tr_079b4ae39041" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T09:44:38.697086+00:00..2026-10-03T09:44:50.169389+00:00" radius="seed" hops="0">
service: accounting
1 changes, ranked by suspicion
  #1  3m before onset  2026-10-03T09:41:25+00:00  platform-automation  container created: workload first created
</tool_result:tr_079b4ae39041>
```

