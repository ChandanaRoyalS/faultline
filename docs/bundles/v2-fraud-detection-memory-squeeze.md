# Fraud detection memory limit cut below what its JVM needs to run

## The scenario

| | |
|---|---|
| scenario | `v2-fraud-detection-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `fraud-detection` via `v2-fraud-detection-memory-squeeze` |
| time to page | 7m15s |
| steady state captured | 300s |
| capture window | 2026-09-27T13:27:34+00:00 → 2026-09-27T13:47:50+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+7m15s |
| `t_revert` | T+12m15s |
| all clear | T+13m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+7m00s | `fraud-detection` | ServiceNoTraffic | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="fraud-detection"}` |

`logs/fraud-detection.txt` — 284 lines.

## A look at the logs

From `logs/fraud-detection.txt` (---- onset 2026-09-27T13:32:34+00:00 ----):

```
2026-09-27T13:27:40+00:00  2026-09-27 13:27:40 - fraud-detection - Consumed record with orderId: 36a0bb04-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12078 trace_id=d5dbb18559507c1bc646ab69e93442f8 span_id=340d8f87d0091a5b trace_flags=01
2026-09-27T13:27:54+00:00  2026-09-27 13:27:54 - fraud-detection - Consumed record with orderId: 3eb34128-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12079 trace_id=73175facef0d78711edb4304c5765097 span_id=02a6d10e94ba4da7 trace_flags=01
2026-09-27T13:28:03+00:00  2026-09-27 13:28:03 - fraud-detection - Consumed record with orderId: 4448a0e7-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12080 trace_id=01650bbfcb750e2de0326633381d462c span_id=afa959624f22eeaf trace_flags=01
2026-09-27T13:28:03+00:00  2026-09-27 13:28:03 - fraud-detection - Consumed record with orderId: 446e438f-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12081 trace_id=f866f610ba6b24fb8063c5eee1ab7a32 span_id=7c7d5785d3b44e94 trace_flags=01
2026-09-27T13:28:18+00:00  2026-09-27 13:28:18 - fraud-detection - Consumed record with orderId: 4d3b629a-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12082 trace_id=4ec68be3a71414626ddef295a54356d7 span_id=f500c820905858ac trace_flags=01
2026-09-27T13:28:39+00:00  2026-09-27 13:28:39 - fraud-detection - Consumed record with orderId: 59691df4-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12083 trace_id=9b4bad9b448f0787d1759b55e1bf4266 span_id=bbd71418ffabe617 trace_flags=01
2026-09-27T13:28:39+00:00  2026-09-27 13:28:39 - fraud-detection - Consumed record with orderId: 59973b63-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12084 trace_id=3db80934e9ff2362f45bb7d0fbbd46df span_id=acd934fbfd045dc3 trace_flags=01
2026-09-27T13:28:42+00:00  2026-09-27 13:28:42 - fraud-detection - Consumed record with orderId: 5b98c6e5-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12085 trace_id=84933dd097278334021b3f876111914f span_id=2ec2acea784e1ba3 trace_flags=01
2026-09-27T13:29:09+00:00  2026-09-27 13:29:09 - fraud-detection - Consumed record with orderId: 6b9e44e9-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12086 trace_id=620ae58ad005cb14a9157f69cf2ad319 span_id=93a108cf39bb6842 trace_flags=01
2026-09-27T13:29:11+00:00  2026-09-27 13:29:11 - fraud-detection - Consumed record with orderId: 6cb6c4fb-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12087 trace_id=8e131b3f0137787b6ddd8741b1e820dd span_id=363836f423f225b5 trace_flags=01
2026-09-27T13:29:12+00:00  2026-09-27 13:29:12 - fraud-detection - Consumed record with orderId: 6d4559e5-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12088 trace_id=b06a013a13bac07efa8ca517fcab68eb span_id=1217ebf674f4eb50 trace_flags=01
2026-09-27T13:29:18+00:00  2026-09-27 13:29:18 - fraud-detection - Consumed record with orderId: 70edc087-ba77-11f1-8340-6ebe486271a3, and updated total count to: 12089 trace_id=3a49007a40dd069c37f9dabf6fd010c4 span_id=5785fa01d21733c9 trace_flags=01
```

_263 further lines are in the bundle._

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

One alert. `ServiceNoTraffic` on **fraud-detection**, 7m15s after the trouble started. Nothing
else fired for the entire incident, and nothing fired after the fix.

The store was perfect throughout. The frontend, frontend-proxy and the load generator recorded no
errors and no change in latency; checkout placed orders at its usual rate, payment charged them,
accounting recorded them at its usual 0.3 to 0.5 spans a second with its usual 90ms. Not one error
ratio on the world moved, apart from the flag readers' routine sliver. Orders were being placed,
charged, shipped, confirmed and booked the whole time.

What was missing was one consumer. Fraud-detection's span rate had been about 0.25 a second. It
was 0.14 a minute in, 0.06 at three, and nothing from four; from then on its error ratio and its
latency had no value at all. It had recorded nothing unusual before its numbers ran out: no error
of its own, no rise in latency.

This is the slowest page on this world and the smallest.

### What was checked

**Whether anyone was missing it.** No one. Nothing calls fraud-detection: it reads orders off the
same Kafka topic accounting reads, and checkout publishes an order and moves on. So checkout had
no failed call to show, accounting kept consuming - 115 orders logged over the fault, 2 to 15 a
minute, exactly the orders checkout published - and the only trace of anything wrong was the
absence of fraud-detection's own consumer spans: not one `orders receive` or `orders process` in
the fault, against 108 orders published.

**Fraud-detection's log, which is where it breaks open.** Its last ordinary line came 23 seconds
before the trouble began - `Consumed record with orderId ...` - and eight seconds after it began,
the JVM was starting: `Picked up JAVA_TOOL_OPTIONS`, the OpenJDK class-sharing warning, the
OpenTelemetry agent announcing its version. Then, three seconds later, the same three lines again.
**Nineteen times** in twelve minutes: seven starts in the first 50 seconds, then the gaps growing
- 15, 29, 54 seconds - to once a minute. Not one reached the application's own start-up, and not
one consumed a record. No line explains a failure: no exception, no stack trace, no out-of-memory
message from the JVM, no shutdown. A process that keeps starting and never says why it stopped is
a process being killed from outside, and a runtime backing off between attempts is what the gaps
are.

**Whether it was idle or absent.** Its 51 JVM runtime series - heap by pool, threads, garbage
collection, CPU - held their last values for four minutes, the store's lookback, and then vanished,
and no new instance's series appeared before the fix. A process that is merely idle keeps exporting
them; these stopped when the log says the first kill came, and read on for four minutes only
because the store serves a last value forward. The series answer *whether*, the log answers *when*.

**Why it never came back.** At rest fraud-detection was a JVM holding about 256MB in a 500M
container: a heap capped at 122MB by its own settings, 100MB of non-heap - the agent's
instrumentation, the code cache - and about 90MB the container held outside the JVM altogether.
Nineteen restarts in a row, each dying within seconds of loading the agent, is a JVM that cannot
fit its own start-up into what it is now allowed. Nothing about how much it needed had changed.
What it was allowed had.

**What changed.** No deploy, no image change - the same `2.2.0-fraud-detection` before and after -
no environment change, no flag. And one record, at the start, under fraud-detection's name:
`memory limit lowered on fraud-detection`, to `memory=160m`, from 500M. The record names the
cause, and it is the only kind of change on this world that leaves a process's image and
configuration exactly as they were and kills it anyway.

**The flag readers' sliver.** A dead end. Fraud-detection's own error ratio had read 1.4 to 2.0% in
the four minutes before the trouble, and flagd's under 1% then and again six to ten minutes in: the
flag service's routine ten-minute stream reconnect, which every flag reader shows and none of them
pages on. The only error traces in the fault were three of those stream closes, on ad,
recommendation and product-reviews. Nothing near a line, and nothing to do with orders.

### Root cause

The fraud detection container's memory limit was lowered from 500M to 160m, below the 256MB
working set of its JVM and below what a fresh JVM needs to load its instrumentation agent and
start at all. The kernel killed the running JVM within seconds, the restart policy brought it
back, and every new JVM was killed again before it could consume - nineteen times, with the
runtime backing off to once a minute - so orders went unchecked for fraud for the whole fault.
Nothing calls fraud-detection, so nothing else noticed: the storefront, checkout and accounting
were untouched, and the orders it missed waited for it in Kafka.

### Resolution

The memory limit was restored to 500M. The next JVM start, 25 seconds after the fix, was the first
in twelve minutes to run, and three seconds after that it began working through the backlog: dozens
of `Consumed record` lines in a single second, 157 in the five minutes after the fix against 46 in a
normal five, its span rate at 0.5 to 0.7 a second against its usual 0.25, until it had caught up on
every order published while it was gone. Its no-traffic alert cleared within a minute of the fix,
and everything was quiet 1m01s after it. Nothing fired during recovery.

Class of fix: **config_revert**. The container's resource limit was wrong and it was set back.
Restarting fraud-detection was what the runtime had already been doing, nineteen times; rolling
back its image would have changed nothing, because the image was never the problem.

### Detection notes

- Onset to first page: **7m15s**, the no-traffic window draining. Services on the page: **one**,
  fraud-detection, the culprit. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one, and it was
  not loud: its only alert was silence.
- Would the page alone have led you to the right service? **Yes.** Nothing else was named, and
  nothing else was wrong.
- **A consumer that nobody calls dies silently.** No caller errors, no latency anywhere, no queue
  visible to the tools: the only sign is the consumer's own traffic going to nothing. The page for
  this fault is the absence of a service, and it arrives only when a window has drained.
- **A truncated, repeating start-up is a process being killed from outside.** Nineteen JVM
  banners with nothing after them, at growing intervals, and no error anywhere: nothing inside the
  process decided to stop.
- **A killed process has no last words, so the cause is in what changed, not in what it said.** The
  change record names a memory limit; the log names nothing. The two together are the whole story.
- **Runtime series that stop do not stop at once.** They held their last values for four minutes
  before vanishing; the log dates the first kill to the eighth second. Read the stop time off the
  log, not off the series.
- **A consumer's missed work is not lost work.** The orders it missed were still on the topic, and
  it consumed them all in the first seconds back. Its rate after the fix was twice its usual: the
  size of the backlog, not a second fault.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-fraud-detection-memory-squeeze/`](../../evals/scenarios/artifacts/dev/v2-fraud-detection-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
