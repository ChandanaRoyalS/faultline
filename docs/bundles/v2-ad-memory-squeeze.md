# Ad service memory limit cut below what its JVM needs to run

## The scenario

| | |
|---|---|
| scenario | `v2-ad-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `ad` via `v2-ad-memory-squeeze` |
| time to page | 5m01s |
| steady state captured | 300s |
| capture window | 2026-09-27T12:34:52+00:00 → 2026-09-27T12:54:54+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+5m01s |
| `t_revert` | T+10m01s |
| all clear | T+13m02s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m45s | `frontend` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+4m45s | `frontend-proxy` | ServiceHighErrorRate | 8.0 min | **paged** |
| T+7m45s | `ad` | ServiceNoTraffic | 5.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="ad"}` |

`logs/ad.txt` — 240 lines.

## A look at the logs

From `logs/ad.txt` (---- onset 2026-09-27T12:39:52+00:00 ----):

```
2026-09-27T12:35:35+00:00  2026-09-27 12:35:35 - oteldemo.AdService - no baggage found in context trace_id=4d8b661cba4d7a0f21ae06f38653f188 span_id=fdd022e2c0ecb599 trace_flags=01
2026-09-27T12:35:35+00:00  2026-09-27 12:35:35 - oteldemo.AdService - Targeted ad request received for [books] trace_id=4d8b661cba4d7a0f21ae06f38653f188 span_id=fdd022e2c0ecb599 trace_flags=01
2026-09-27T12:35:41+00:00  2026-09-27 12:35:41 - oteldemo.AdService - no baggage found in context trace_id=c04360e251309f2cd6425b5d7b4d2ee7 span_id=b87ac6a78dcca38a trace_flags=01
2026-09-27T12:35:41+00:00  2026-09-27 12:35:41 - oteldemo.AdService - Non-targeted ad request received, preparing random response. trace_id=c04360e251309f2cd6425b5d7b4d2ee7 span_id=b87ac6a78dcca38a trace_flags=01
2026-09-27T12:35:51+00:00  2026-09-27 12:35:51 - oteldemo.AdService - no baggage found in context trace_id=697d6901916f8e05c7a1a62afda644a5 span_id=b97976fa36228001 trace_flags=01
2026-09-27T12:35:51+00:00  2026-09-27 12:35:51 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=697d6901916f8e05c7a1a62afda644a5 span_id=b97976fa36228001 trace_flags=01
2026-09-27T12:35:56+00:00  2026-09-27 12:35:56 - oteldemo.AdService - no baggage found in context trace_id=3ff8d1ce2ed0a54ab5326d009b150e86 span_id=b189decd3d5ceaa9 trace_flags=01
2026-09-27T12:35:56+00:00  2026-09-27 12:35:56 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=3ff8d1ce2ed0a54ab5326d009b150e86 span_id=b189decd3d5ceaa9 trace_flags=01
2026-09-27T12:36:01+00:00  2026-09-27 12:36:01 - oteldemo.AdService - no baggage found in context trace_id=a91df2d64a353f92b33238c35aa9b4c1 span_id=7cf293ace07dcd4f trace_flags=01
2026-09-27T12:36:01+00:00  2026-09-27 12:36:01 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=a91df2d64a353f92b33238c35aa9b4c1 span_id=7cf293ace07dcd4f trace_flags=01
2026-09-27T12:36:01+00:00  2026-09-27 12:36:01 - oteldemo.AdService - no baggage found in context trace_id=a903c555590316132348854595c660be span_id=9b09eee90ab724f1 trace_flags=01
2026-09-27T12:36:01+00:00  2026-09-27 12:36:01 - oteldemo.AdService - Non-targeted ad request received, preparing random response. trace_id=a903c555590316132348854595c660be span_id=9b09eee90ab724f1 trace_flags=01
```

_219 further lines are in the bundle._

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

The page was two alerts in the same moment, `ServiceHighErrorRate` on **frontend-proxy** and
**frontend**, 5m01s after the trouble started. Three minutes later `ServiceNoTraffic` fired on
**ad**. Three alerts on three services by the fix, and none after it.

The frontend's error ratio had been zero. It was 1.5% a minute in, 3.6% at two, 5.2% at three, and
it climbed on through the fault to 8.4% in the last minute before the fix; frontend-proxy's went
with it, 1.3% to 8.6%. The load generator's rose to 4.7% and stayed under the line. Nothing got
slower: the frontend's p95 sat at 40 to 46ms throughout, as it had. Checkout, cart, payment, the
catalog and recommendation recorded no errors and kept their usual rates. Pages, carts and orders
went on. What failed was the ad panel.

Ad's own numbers went from ordinary to nothing. Its call rate fell from about 0.45 spans a second
to 0.36 a minute in, 0.15 at three, 0.03 at four and nothing from five, and from then on its error
ratio and its latency had no value at all. It had recorded no error before the numbers ran out.

### What was checked

**The page names callers.** Frontend-proxy forwards what the frontend returns, and the load
generator is the synthetic shoppers counting their own failures. The frontend was the one service
making calls that failed, and the order path was not among them.

**The frontend's error traces.** 125 over the fault, every one of them a storefront ad request:
`load-generator/GET` to `frontend-proxy/ingress` to `frontend/GET /api/data`, and beneath it
`frontend/grpc.oteldemo.AdService/GetAds` in error with no ad span beneath it. Under that call the
frontend's own client showed what it had tried: `dns.lookup` failing with `getaddrinfo ENOTFOUND
ad`, `tcp.connect` refused at ad's address, `tcp.connect` unreachable, over and over, some attempts
waiting eleven and fourteen seconds. The name came and went and the port was never open. Its log
said the same, `UNAVAILABLE`, 125 times, 2 to 16 a minute, with none in the five minutes before and
13 more in the five minutes after the fix as it found ad again.

**Ad itself, which is where it breaks open.** It produced no server span at all during the fault.
Its log ended its ordinary work two seconds before the trouble began - a targeted ad request,
answered - and one second after it began, the JVM was starting: `Picked up JAVA_TOOL_OPTIONS`, the
OpenJDK class-sharing warning, the OpenTelemetry agent announcing its version. Then, three or four
seconds later, the same three lines again. **Seventeen times** in ten minutes: eight starts in the
first 45 seconds, then gaps of 28 and 53 seconds, then once a minute. Eleven of those starts got as
far as `Ad service starting.` Not one reached `Ad service started, listening on 9555`. No line
explains a failure, because no JVM lived long enough to have an opinion about anything: no error, no
stack trace, no out-of-memory message from the JVM itself, no shutdown. A process that keeps
starting and never says why it stopped is a process being killed from outside, and a runtime backing
off between attempts is what the gaps are.

**Whether ad was idle or absent.** Its 51 JVM runtime series - heap by pool, threads, garbage
collection, CPU - did not stop at once to the eye: they held their last values for four minutes, the
store's lookback, and then vanished. No new instance's series appeared until after the fix. A
process that is merely idle keeps exporting them; these stopped at the moment the log says the
first kill came, and read on for four minutes after that only because the store serves a last value
forward. The series answer *whether*, the log answers *when*.

**Why ad never came back.** At rest ad was a JVM holding about 230MB in a 300M container: a heap
sized against that ceiling, 92MB of non-heap - the agent's instrumentation, the code cache - and
about 80MB the container held outside the JVM altogether. Seventeen restarts in a row, each dying
within seconds of loading the agent, is a JVM that cannot fit its own start-up into whatever it is
now allowed. Nothing about how much it needed had changed. What it was allowed had.

**What changed.** No deploy, no image change - it was running the same `2.2.0-ad` before and after
- no environment change, no flag. And one record, at the start, under ad's name: `memory limit
lowered on ad`, to `memory=144m`, from 300M. The JVM inside had sized itself for 300M and holds 230.
The record names the cause, and it is the only kind of change on this world that leaves a process's
image and configuration exactly as they were and kills it anyway.

**The flag readers' sliver.** A dead end. Recommendation, fraud-detection and flagd showed error
ratios under 2% for a few minutes at onset and again around nine minutes in, and had shown the same
before the trouble: the flag service's routine ten-minute stream reconnect. Nothing near a line.

### Root cause

The ad service container's memory limit was lowered from 300M to 144m, below the 230MB working set
of a JVM that had sized its heap against 300M, and below what a fresh JVM needs to load its
instrumentation agent and start at all. The kernel killed the running JVM within a second, the
restart policy brought it back, and every new JVM was killed again before it could listen -
seventeen times, with the runtime backing off to once a minute - so ad was absent for the whole
fault. The storefront's ad requests failed; nothing else changed, because nothing else calls ad.

### Resolution

The memory limit was restored to 300M. The next JVM start, twenty seconds after the fix, was the
first in ten minutes to reach `Ad service started, listening on 9555`, and it served its first ad
request just under two minutes later, as the frontend found it again; a new set of 51 runtime series
began with it. The frontend's error ratio drained with its window and its alert cleared two and a
half minutes after the fix; ad's no-traffic alert cleared with it. Everything was quiet 3m01s after
the fix, and nothing fired during recovery.

Class of fix: **config_revert**. The container's resource limit was wrong and it was set back.
Restarting ad was what the runtime had already been doing, seventeen times; rolling back its image
would have changed nothing, because the image was never the problem.

### Detection notes

- Onset to first page: **5m01s**. Services on the page: **two**, neither of them ad. By the fix:
  **three**, ad among them.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The frontend was loud; ad was silent,
  and its only alert was the absence of traffic, three minutes after the page.
- Would the page alone have led you to the right service? **No, but one trace does.** Every failing
  storefront request ends at a `GetAds` call with nothing beneath it, and the frontend's own
  connection attempts say the name resolves to nothing and the port is never open.
- **A truncated, repeating start-up is a process being killed from outside.** Seventeen JVM banners
  with nothing after them, at growing intervals, and no error anywhere: nothing inside the process
  decided to stop.
- **A killed process has no last words, so the cause is in what changed, not in what it said.** The
  change record names a memory limit; the log names nothing. The two together are the whole story.
- **Runtime series that stop do not stop at once.** They held their last values for four minutes
  before vanishing; the log dates the first kill to the first second. Read the stop time off the
  log, not off the series.
- **A JVM that cannot restart under a limit was sized for a bigger one.** The heap alone would have
  fitted; the agent, the code cache and what the container holds around the JVM would not. A
  memory squeeze on a JVM is a crash loop, not a slowdown.
- **A leaf's outage stays at the edge.** Ad is called only by the frontend, so the storefront paged
  and the order path never moved. This is the same page as a bad ad deploy; the change record and
  the log - a limit and a JVM that keeps starting, against an image and a JVM that shut down once -
  are what tell them apart.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-ad-memory-squeeze/`](../../evals/scenarios/artifacts/dev/v2-ad-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
