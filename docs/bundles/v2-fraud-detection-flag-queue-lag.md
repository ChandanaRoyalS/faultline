# A feature flag floods the orders queue, slows its consumer and breaks accounting

## The scenario

| | |
|---|---|
| scenario | `v2-fraud-detection-flag-queue-lag` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `fraud-detection` via `v2-fraud-detection-flag-queue-lag` |
| time to page | 4m15s |
| steady state captured | 300s |
| capture window | 2026-09-27T05:12:32+00:00 → 2026-09-27T05:29:48+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m15s |
| `t_revert` | T+9m15s |
| all clear | T+10m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m00s | `fraud-detection` | ServiceHighLatency | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="fraud-detection"}` |

`logs/fraud-detection.txt` — 448 lines.

## A look at the logs

From `logs/fraud-detection.txt` (---- onset 2026-09-27T05:17:32+00:00 ----):

```
2026-09-27T05:12:41+00:00  2026-09-27 05:12:41 - fraud-detection - Consumed record with orderId: 10c712e8-ba32-11f1-909d-1277e832278d, and updated total count to: 1243 trace_id=210ea6f1232a66527c36c5da1d340559 span_id=df58b11dd8b5486a trace_flags=01
2026-09-27T05:12:46+00:00  2026-09-27 05:12:46 - fraud-detection - Consumed record with orderId: 136cd210-ba32-11f1-909d-1277e832278d, and updated total count to: 1244 trace_id=0caa965551b474c63e5cb9bc19007add span_id=5f24f038774e9f1c trace_flags=01
2026-09-27T05:12:47+00:00  2026-09-27 05:12:47 - fraud-detection - Consumed record with orderId: 142ce65c-ba32-11f1-909d-1277e832278d, and updated total count to: 1245 trace_id=1a0bf70a5c8a4ea1d47e175429dadc3c span_id=8ab4e21315243427 trace_flags=01
2026-09-27T05:12:50+00:00  2026-09-27 05:12:50 - fraud-detection - Consumed record with orderId: 15f289ca-ba32-11f1-909d-1277e832278d, and updated total count to: 1246 trace_id=9efb1da688696deb6f2837280ae47445 span_id=dc0604e4f274baf4 trace_flags=01
2026-09-27T05:12:56+00:00  2026-09-27 05:12:56 - fraud-detection - Consumed record with orderId: 19ba586e-ba32-11f1-909d-1277e832278d, and updated total count to: 1247 trace_id=e1afdd985a2665939b4a70c7cfa1347f span_id=ce0516e5f300e2ad trace_flags=01
2026-09-27T05:13:03+00:00  2026-09-27 05:13:03 - fraud-detection - Consumed record with orderId: 1dfe6975-ba32-11f1-909d-1277e832278d, and updated total count to: 1248 trace_id=f3b776023ae40a2939fc85f1895796fb span_id=a91626f34171432f trace_flags=01
2026-09-27T05:13:14+00:00  2026-09-27 05:13:14 - fraud-detection - Consumed record with orderId: 24139f33-ba32-11f1-909d-1277e832278d, and updated total count to: 1249 trace_id=fa348969833755ea755535d3da9c7ead span_id=0154652a65bae287 trace_flags=01
2026-09-27T05:13:15+00:00  2026-09-27 05:13:15 - fraud-detection - Consumed record with orderId: 24d9fc29-ba32-11f1-909d-1277e832278d, and updated total count to: 1250 trace_id=7ff077de6e765d475b2efd56da5ce5af span_id=92c4aa8cec9511ee trace_flags=01
2026-09-27T05:13:16+00:00  2026-09-27 05:13:16 - fraud-detection - Consumed record with orderId: 2590b90e-ba32-11f1-909d-1277e832278d, and updated total count to: 1251 trace_id=c87ba2e89331c60b51c3696aeaee5723 span_id=de6e3ad72f3c4ebf trace_flags=01
2026-09-27T05:13:17+00:00  2026-09-27 05:13:17 - fraud-detection - Consumed record with orderId: 265235b1-ba32-11f1-909d-1277e832278d, and updated total count to: 1252 trace_id=fce27e0945a004b3141beefd4f85fc71 span_id=00aace0b8e6c1354 trace_flags=01
2026-09-27T05:13:49+00:00  2026-09-27 05:13:49 - fraud-detection - Consumed record with orderId: 393b19e1-ba32-11f1-909d-1277e832278d, and updated total count to: 1253 trace_id=42d812b6df41ab8d0d3a34bf7bef6e49 span_id=78b25f16e6d0a65f trace_flags=01
2026-09-27T05:13:51+00:00  2026-09-27 05:13:51 - fraud-detection - Consumed record with orderId: 3a094161-ba32-11f1-909d-1277e832278d, and updated total count to: 1254 trace_id=8f668ef96d54987ba5786efb2f810f91 span_id=02e6404def63b8bd trace_flags=01
```

_427 further lines are in the bundle._

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

The page was one alert, `ServiceHighLatency` on **fraud-detection**, 4m15s after the trouble
started. Nothing else fired, then or later, and nothing fired after the fix.

Fraud-detection's p95 had been about 90ms. From the first minute it was about 1,370ms, then
1,380ms, flat, until the fix. Its error ratio stayed under 1%, well below the line. Its rate of
work changed shape too: it had been reading a few records a minute, as fast as orders came in;
from the first minute it read **exactly one a second**, sixty a minute, and did not move from that.

Nothing on the storefront or the order path changed. Checkout placed orders at its usual rate with
no errors and no added latency, and payment and email were normal. The one other service that
moved was **accounting**, the other consumer of the same Kafka topic: its span rate went from
about 0.4 a second to between 16 and 25, with no errors, and its latency fell, from about 90ms to
about 2ms.

### What was checked

**Fraud-detection's traces, to see what the time was spent on.** Its work is two kinds of span:
`orders receive`, when it polls Kafka for a batch of records, and `orders process`, one for each
record it handles. The receive spans were fast. Every `orders process` span lasted about a second,
and a single poll's trace held about a hundred of them, one after another. The p95 of about
1,380ms is near the top of the latency histogram's bucket that a one-second span falls in. Nothing
inside the process span called anything: the second was spent in fraud-detection itself.

**Its log, which said why in its own words.** Before every record it logged `FeatureFlag
'kafkaQueueProblems' is enabled, sleeping 1 second`, and after it `Consumed record with orderId:
...`, up to sixty a minute, 551 sleeps in all and none before onset. The order ids repeated: the
first order after onset was consumed 101 times in a row, one a second, its running count climbing
by one each time, and the next one at least 99 times after it. Orders were arriving
many times over.

**Whether Kafka or the producer was failing.** Neither was. Checkout's orders completed normally.
Accounting, reading the same topic without the sleep, was reading records far faster than orders
were being placed, which is how fast the topic was being filled: each placed order was on it a
hundred and one times. The topic was healthy and far busier than the orders being placed.

**Accounting's log, because its traffic had jumped.** For the records it read it logged `Order
details: {...}` and then `fail: ... Order parsing failed:`, 302 to 1,010 times a minute and 6,566
times in all, where it had logged none in the five minutes before onset. For the duplicates the
exception was `The instance of entity type 'OrderEntity' cannot be tracked because another
instance with the same key value for {'Id'} is already being tracked`: accounting was refusing to
save an order it already held. But 66 of the failures, 2 to 10 a minute, about the rate orders
were being placed, were `Unexpected entry.EntityState: Detached` from inside the save: new orders
were being refused as well as copies. Its spans showed no error and made no database call, which
is why its latency fell and why nothing about it paged. The failure was in its log and nowhere
else.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart. The log names a feature flag on one side of the topic. The duplicates on the other side
started at the same moment.

### Root cause

The `kafkaQueueProblems` feature flag was turned on in the flag service, and it acts on both sides
of the orders topic. Fraud-detection sleeps a second before each record, so it consumes one a
second, and checkout publishes every order a hundred extra times, so the consumer falls further
behind every second. Accounting, the topic's other consumer, received every duplicate. The
duplicates left its long-lived database session in a state where saves fail, so it refused new
orders as well as the copies, silently. Kafka was healthy, and nothing was deployed or
reconfigured. The fault was the flag's value, and it left damage that outlasts it.

### Resolution

The flag was turned back off. Checkout stopped duplicating orders, and fraud-detection worked
through its backlog at once: about 6,500 records in the minute after the fix, then back to its
usual rate of about ten a minute, and its latency fell to about 2ms. Its latency alert cleared
1m01s after the fix.

**Accounting did not recover.** After the fix it logged six more `Order parsing failed`, each a new
order refused with `Unexpected entry.EntityState: Detached`. There were no copies left to refuse;
it was refusing real orders. Nothing alerted. Accounting was restarted about a minute after the
fix. The orders it refused while broken were read and committed, so they are not read again: they
are lost from accounting's records.

Class of fix: **config_revert**, for the flag, and **a restart of accounting**, which the page does
not ask for.

### Detection notes

- Onset to first page: **4m15s**. Services on the page: **one**, fraud-detection. By the fix:
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
  retrying.** Here every placed order was on the topic a hundred and one times.
- **A service can fail the records it handles and show no error at all.** Accounting's failures
  were caught in its own code and never reached a span. Its latency fell and its traffic rose, and
  its log was the only place the failure appeared.
- **A cleared page is not a clean world.** After the fix, check every service the flag touched, not
  only the one that paged. Accounting was still refusing new orders after the flag was off, needed
  a restart that nothing asked for, and every order it refused in the meantime was lost.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-fraud-detection-flag-queue-lag/`](../../evals/scenarios/artifacts/dev/v2-fraud-detection-flag-queue-lag/) by `faultline-render`. [All bundles](README.md).
