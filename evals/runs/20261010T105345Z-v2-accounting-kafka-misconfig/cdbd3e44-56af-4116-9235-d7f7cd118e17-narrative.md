# Accounting consumer silent: broker bootstrap address pointed where nothing answers

## What was visible, in order

The page named one service, accounting, severity critical, with no graph neighbours attached and no unmeasured edges crossed. Take T+0 as the alert. The first move was accounting's span error ratio against a baseline half-hour, and it came back flat zero everywhere — no surge, no partial-failure fraction, no pre-onset ramp. Read naively, that says the service is fine. The signal was in the shape, not the values: 44 of 84 incident-window samples had no value at all, against zero such gaps in the baseline. An undefined ratio means an empty denominator, so for roughly half the window accounting emitted no spans. The same query produced 128 clean baseline samples, which rules out a broken query or scrape problem. This was not a service failing requests; it was a service gone quiet.

Logs then gave exactly one line, repeated: the consumer thread reporting its sole configured broker unreachable on a 9094 bootstrap endpoint, 1 of 1 down, at a near-constant 50–52ms cadence. A tight reconnect loop. The same consumer instance identifier persists from the oldest retained line to the newest, so nothing crashed or restarted. Traces showed ten traces across ~92 minutes, all rooted at the same consumer operation, latency concentrated almost entirely in root self-time (seconds to ~22s) while the receive child stayed at tens of milliseconds and the database child under ~3.2ms. Emission stopped after 10:53:45, about eight minutes before the alert. Change history recorded three entries, all from one automation actor, all touching the same broker-address variable: set ~30m before onset, reverted ~20m before, set again to the same 9094 value ~7m before.

> Evidence `tr_ff90f092fdaa`:

```
<tool_result id="tr_ff90f092fdaa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" template="error-ratio" baseline="2026-10-10T09:59:38.149317+00:00..2026-10-10T10:31:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=84 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_d190988c83d2`:

```
<tool_result id="tr_d190988c83d2" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" template="error-ratio" baseline="2026-10-10T09:59:38.149317+00:00..2026-10-10T10:31:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=84 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_d2b8c6f561f2`:

```
<tool_result id="tr_d2b8c6f561f2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-10T10:31:31.665812+00:00  %3|1791628291.665|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.717702+00:00  %3|1791628291.717|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.768935+00:00  %3|1791628291.768|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.820818+00:00  %3|1791628291.820|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
```

> Evidence `tr_e4d694deb0de`:

```
<tool_result id="tr_e4d694deb0de" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T09:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00">
service: accounting
10 trace(s) shown of 10 found, 30 spans; offsets are from each trace's root

trace b9c04094cf3098ac  root accounting/order-consumed  22428.8ms  started 2026-10-10T10:02:47.555545+00:00  3 spans
  +0.0ms accounting/order-consumed 22428.8ms [self 22371.5ms]
```

> Evidence `tr_0b8d07e94941`:

```
<tool_result id="tr_0b8d07e94941" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T11:01:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" radius="seed" hops="0">
service: accounting
3 changes, ranked by suspicion
  #1  7m before onset  2026-10-10T10:53:50.847194+00:00  platform-automation  environment updated: KAFKA_ADDR updated on accounting
      None  ->  KAFKA_ADDR=kafka:9094
  #2  20m before onset  2026-10-10T10:41:08.836169+00:00  platform-automation  environment reverted: KAFKA_ADDR reverted on accounting
```

## Dead ends worth keeping

The alert timestamp was a bad anchor and cost time. Nothing in accounting's data transitions at T+0 — the log error is already firing thirty minutes earlier, trace degradation is visible from ~10:02, and span emission ceases eight minutes before the page. Any theory of the form 'healthy, then abrupt cutoff at the alert' is unsupported.

The database was chased and cleared: postgresql children are under ~3.2ms against roots running thousands of milliseconds. Slow receive from the broker was chased and cleared too — the receive child is only 16–97ms and is entered very late, after the root has already burned seconds. A partial broker degradation (lost node, leader election, rebalance with capacity left) does not fit: the message reports the whole configured set down with one broker configured. A partial service degradation does not fit either: error ratio min and max are both zero. A split-behaviour story, where inbound serving stayed healthy while only the consumer path hung, died because there are no inbound server-rooted traces anywhere in the window to contrast against. And the empty trace tail is not a sampling artifact — the result returned 10 of 10, untruncated.

One anomaly turned out to matter: two traces at 10:41:10, ~8ms apart, completed in about 1ms end to end with a near-zero receive child. They land seconds after the 10:41:08 revert that unset the variable. The pipeline is healthy precisely when the override is absent.

> Evidence `tr_e4d694deb0de`:

```
<tool_result id="tr_e4d694deb0de" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T09:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00">
service: accounting
10 trace(s) shown of 10 found, 30 spans; offsets are from each trace's root

trace b9c04094cf3098ac  root accounting/order-consumed  22428.8ms  started 2026-10-10T10:02:47.555545+00:00  3 spans
  +0.0ms accounting/order-consumed 22428.8ms [self 22371.5ms]
```

> Evidence `tr_d2b8c6f561f2`:

```
<tool_result id="tr_d2b8c6f561f2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-10T10:31:31.665812+00:00  %3|1791628291.665|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.717702+00:00  %3|1791628291.717|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.768935+00:00  %3|1791628291.768|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.820818+00:00  %3|1791628291.820|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
```

> Evidence `tr_ff90f092fdaa`:

```
<tool_result id="tr_ff90f092fdaa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" template="error-ratio" baseline="2026-10-10T09:59:38.149317+00:00..2026-10-10T10:31:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=84 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

> Evidence `tr_0b8d07e94941`:

```
<tool_result id="tr_0b8d07e94941" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T11:01:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" radius="seed" hops="0">
service: accounting
3 changes, ranked by suspicion
  #1  7m before onset  2026-10-10T10:53:50.847194+00:00  platform-automation  environment updated: KAFKA_ADDR updated on accounting
      None  ->  KAFKA_ADDR=kafka:9094
  #2  20m before onset  2026-10-10T10:41:08.836169+00:00  platform-automation  environment reverted: KAFKA_ADDR reverted on accounting
```

## Conclusion and what remains unresolved

Accounting's broker bootstrap address was reconfigured to port 9094 and nothing is listening there. The process stays up while its consumer thread reconnects every ~50ms. Since accounting's entire traced surface is consumer-rooted, an unreachable broker means no messages arrive: roots balloon into seconds of self-time, throughput collapses to ten traces in 92 minutes, and emission stops — which the metrics see as the empty-denominator gap. Fix class: revert the configuration. Confidence medium, for the reasons below.

First and most important: nobody looked at the broker itself. It was never confirmed that a broker is listening and healthy on another port. If the broker is down everywhere, the configured port is incidental and this is a dependency outage, not a misconfiguration. That one unmade check separates two different incidents. Second, the relapse at 10:41:18 is unexplained — the revert held until 10:53:50, yet degradation resumed eight seconds after the two fast traces, which weakens the clean on/off correlation. Third, coverage gaps: no saturation, consumer-lag, queue-depth or absolute rate metrics were ever retrieved, so resource pressure inside accounting is unmeasured rather than excluded; the log window opens with the error already firing, so no clean pre-change state was observed; what actually fired the alert is unresolved; and whether other services share the same broker endpoint was never checked, which would discriminate between a per-service override and a broader outage.

> Evidence `tr_d2b8c6f561f2`:

```
<tool_result id="tr_d2b8c6f561f2" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" oldest_kept="8" newest_kept="32">
selector: {service="accounting"}
2026-10-10T10:31:31.665812+00:00  %3|1791628291.665|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.717702+00:00  %3|1791628291.717|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.768935+00:00  %3|1791628291.768|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
2026-10-10T10:31:31.820818+00:00  %3|1791628291.820|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down
```

> Evidence `tr_e4d694deb0de`:

```
<tool_result id="tr_e4d694deb0de" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-10-10T09:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00">
service: accounting
10 trace(s) shown of 10 found, 30 spans; offsets are from each trace's root

trace b9c04094cf3098ac  root accounting/order-consumed  22428.8ms  started 2026-10-10T10:02:47.555545+00:00  3 spans
  +0.0ms accounting/order-consumed 22428.8ms [self 22371.5ms]
```

> Evidence `tr_0b8d07e94941`:

```
<tool_result id="tr_0b8d07e94941" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-09T11:01:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" radius="seed" hops="0">
service: accounting
3 changes, ranked by suspicion
  #1  7m before onset  2026-10-10T10:53:50.847194+00:00  platform-automation  environment updated: KAFKA_ADDR updated on accounting
      None  ->  KAFKA_ADDR=kafka:9094
  #2  20m before onset  2026-10-10T10:41:08.836169+00:00  platform-automation  environment reverted: KAFKA_ADDR reverted on accounting
```

> Evidence `tr_ff90f092fdaa`:

```
<tool_result id="tr_ff90f092fdaa" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-10-10T10:31:31.664000+00:00..2026-10-10T11:03:25.178683+00:00" template="error-ratio" baseline="2026-10-10T09:59:38.149317+00:00..2026-10-10T10:31:31.664000+00:00">
service: accounting
metric: error-ratio
query: sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting",status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total{service_name="accounting"}[5m]))
  incident window: n=84 mean=0 min=0 max=0 sd=0
  baseline window: n=128 mean=0 min=0 max=0 sd=0
```

