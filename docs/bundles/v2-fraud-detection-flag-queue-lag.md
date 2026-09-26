# A feature flag floods the orders queue, slows its consumer and breaks accounting

## The scenario

| | |
|---|---|
| scenario | `v2-fraud-detection-flag-queue-lag` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `fraud-detection` via `v2-fraud-detection-flag-queue-lag` |
| time to page | 4m00s |
| steady state captured | 300s |
| capture window | 2026-09-26T21:24:48+00:00 → 2026-09-26T21:41:49+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m00s |
| `t_revert` | T+9m00s |
| all clear | T+10m01s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m45s | `fraud-detection` | ServiceHighLatency | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="fraud-detection"}` |

`logs/fraud-detection.txt` — 456 lines.

## A look at the logs

From `logs/fraud-detection.txt` (---- onset 2026-09-26T21:29:48+00:00 ----):

```
2026-09-26T21:24:49+00:00  2026-09-26 21:24:49 - fraud-detection - Consumed record with orderId: b47bfe9c-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24117 trace_id=2323e79849cb73414378dec00d4bf735 span_id=c93816cbb32434ae trace_flags=01
2026-09-26T21:25:02+00:00  2026-09-26 21:25:02 - fraud-detection - Consumed record with orderId: bc4bbfab-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24118 trace_id=c2ccf72d6ebc550e5b8ebfe7e3998b35 span_id=d467cf1087866e86 trace_flags=01
2026-09-26T21:25:06+00:00  2026-09-26 21:25:06 - fraud-detection - Consumed record with orderId: be8feca0-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24119 trace_id=75d5409e57281dea8f10d779f34666e6 span_id=3cd64f8f33c8d331 trace_flags=01
2026-09-26T21:25:11+00:00  2026-09-26 21:25:11 - fraud-detection - Consumed record with orderId: c1344898-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24120 trace_id=17774e6a2819a92c14da9a232c400b4a span_id=98b5f666df0e96a6 trace_flags=01
2026-09-26T21:25:17+00:00  2026-09-26 21:25:17 - fraud-detection - Consumed record with orderId: c5508fe9-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24121 trace_id=1d3f14edc5179cbda6bbaf251e69c860 span_id=5ea0370b36c175eb trace_flags=01
2026-09-26T21:25:20+00:00  2026-09-26 21:25:20 - fraud-detection - Consumed record with orderId: c6cc906b-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24122 trace_id=3a0121216a335b8db409ead0909c72b8 span_id=f8528720478d647b trace_flags=01
2026-09-26T21:25:31+00:00  2026-09-26 21:25:31 - fraud-detection - Consumed record with orderId: cd40329f-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24123 trace_id=845e5c2e9ccc80471f535330d95b67a0 span_id=fad285171b0fcc7d trace_flags=01
2026-09-26T21:25:36+00:00  2026-09-26 21:25:36 - fraud-detection - Consumed record with orderId: d06dc8f4-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24124 trace_id=02291375a30696411ef720cc0139104b span_id=e1991568db9a8554 trace_flags=01
2026-09-26T21:25:40+00:00  2026-09-26 21:25:40 - fraud-detection - Consumed record with orderId: d29cbd2a-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24125 trace_id=37099e054c42497ce8321919e6fb0174 span_id=19ed998414f0b4df trace_flags=01
2026-09-26T21:25:41+00:00  2026-09-26 21:25:41 - fraud-detection - Consumed record with orderId: d36a5970-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24126 trace_id=a9ab3fc63afd337f790b9d82ef410b24 span_id=770bd99171fd1b92 trace_flags=01
2026-09-26T21:26:02+00:00  2026-09-26 21:26:02 - fraud-detection - Consumed record with orderId: dfcde858-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24127 trace_id=0e9aac11d4b553de6daaadc6bcab23ec span_id=372e3b9bffac2072 trace_flags=01
2026-09-26T21:26:07+00:00  2026-09-26 21:26:07 - fraud-detection - Consumed record with orderId: e2f62746-b9f0-11f1-a9d4-9e2f78f497c2, and updated total count to: 24128 trace_id=8ccef1bfa8f6d0804e3c3f5a246a68c1 span_id=62199507b049e9fc trace_flags=01
```

_435 further lines are in the bundle._

## The incident record

Written from the responder's chair, by someone who did not know the fault class
or that anything had been injected. This text is also corpus material, which is
why it never names the injector.

**It keeps its own clock.** The table above is measured from the injection, which
is the only origin the manifest records; a narrative's `T+` offsets are the
responder's own and start wherever that responder started counting — usually the
page, sometimes the injection, sometimes an event in the logs. The same moment can
therefore carry two different offsets on this page. The absolute timestamps in the
bundle are the tiebreak.

### What was observed

The page was one alert, `ServiceHighLatency` on **fraud-detection**, 4m00s after the trouble
started. Nothing else fired, then or later, and nothing fired after the fix.

Fraud-detection's p95 had been about 90ms. From the first minute it was about 1,380ms, and it held
there, flat. Its error ratio stayed at zero. Its rate of work changed shape too: it had been
reading a few records a minute, as fast as orders came in; from the first full minute it read
**exactly one a second**, sixty a minute, and did not move from that.

Nothing on the storefront or the order path changed. Checkout placed orders at its usual rate with
no errors and no added latency, and payment and email were normal. The one other service that
moved was **accounting**, the other consumer of the same Kafka topic: its span rate went from
about 0.45 a second to about 33, with no errors, and its latency fell, from about 90ms to about
2ms.

### What was checked

**Fraud-detection's traces, to see what the time was spent on.** Its work is two kinds of span:
`orders receive`, when it polls Kafka for a batch of records, and `orders process`, one for each
record it handles. The receive spans were fast. Every `orders process` span lasted about 1,003
milliseconds, and the trace tool showed two hundred of them in a single poll's trace. The p95 of
about 1,380ms is near the top of the latency histogram's bucket that a one-second span falls in. Nothing
inside the process span called anything: the second was spent in fraud-detection itself.

**Its log, which said why in its own words.** Before every record it logged `FeatureFlag
'kafkaQueueProblems' is enabled, sleeping 1 second`, and after it `Consumed record with orderId:
...`, sixty a minute, exactly. The order ids repeated: the same order was consumed over and over,
one a second, its running count climbing by one each time. Orders were arriving many times over.

**Whether Kafka or the producer was failing.** Neither was. Checkout's orders completed normally.
Accounting, reading the same topic without the sleep, was reading tens of records a second
without any slowdown, which is how fast the topic was being filled: each placed order was on it a hundred times
and more. The topic was healthy and far busier than the orders being placed.

**Accounting's log, because its traffic had jumped.** For every record it read it logged `Order
details: {...}` and then `fail: ... Order parsing failed:`, 700 to 2,400 times a minute. For the
duplicates the exception was `The instance of entity type 'OrderEntity' cannot be tracked because
another instance with the same key value for {'Id'} is already being tracked`: accounting was
refusing to save an order it already held. But the counts matched exactly from the first full
minute onwards: every order accounting read failed, the originals as well as the copies. From about
a minute after onset, accounting recorded nothing. Its spans showed no error and made no database
call, which is why its latency fell and why nothing about it paged. The failure was in its log and
nowhere else.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart. The log names a feature flag on one side of the topic. The duplicates on the other side
started at the same moment.

### Root cause

The `kafkaQueueProblems` feature flag was turned on in the flag service, and it acts on both sides
of the orders topic. Fraud-detection sleeps a second before each record, so it consumes one a
second, and checkout publishes every order a hundred extra times, so the consumer falls further
behind every second. Accounting, the topic's other consumer, received every duplicate. The
duplicates left its long-lived database session in a state where every save fails, so from about a
minute in it refused every order it read, silently. Kafka was healthy, and nothing was deployed or
reconfigured. The fault was the flag's value, and it left damage that outlasts it.

### Resolution

The flag was turned back off. Checkout stopped duplicating orders, and fraud-detection worked
through its backlog at once: 8,302 records in the minute after the fix, then back to its usual few
a minute, with the consumer group's lag at zero. Its latency alert cleared 1m01s after the fix.

**Accounting did not recover.** In the seventy seconds between the fix and its restart it read 104
records and refused all 104: a hundred duplicates of the last order still arriving, and four new
orders, each refused with `Unexpected entry.EntityState: Detached` from inside the save. Nothing
alerted. Accounting was restarted, and from then it recorded orders again, 4 to 10 a minute, with
no failures. The orders it refused while broken were read and committed, so they are not read
again: they are lost from accounting's records.

Class of fix: **config_revert**, for the flag, and **a restart of accounting**, which the page does
not ask for.

### Detection notes

- Onset to first page: **4m00s**. Services on the page: **one**, fraud-detection. By the fix:
  **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Partly.** Fraud-detection paged, and it is
  where the flag slows the work. The same flag was flooding the topic from checkout, and it broke
  accounting, which never paged.
- Would the page alone have led you to the right service? **To one of them.** The page and the log
  name the flag. Nothing on the page points at accounting, and accounting's damage is the part that
  outlasts the fix.
- **A consumer pinned at exactly one record a second is being paced, not overloaded.** A struggling
  consumer slows unevenly. A round number means something is deciding the pace.
- **The same order id consumed again and again means the topic is flooded, not that the consumer is
  retrying.** Here every placed order was on the topic a hundred times over.
- **A service can fail every record it handles and show no error at all.** Accounting's failures
  were caught in its own code and never reached a span. Its latency fell and its traffic rose, and
  its log was the only place the failure appeared.
- **A cleared page is not a clean world.** After the fix, check every service the flag touched, not
  only the one that paged. Accounting needed a restart that nothing asked for, and every order it
  refused in the meantime was lost.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-fraud-detection-flag-queue-lag/`](../../evals/scenarios/artifacts/dev/v2-fraud-detection-flag-queue-lag/) by `faultline-render`. [All bundles](README.md).
