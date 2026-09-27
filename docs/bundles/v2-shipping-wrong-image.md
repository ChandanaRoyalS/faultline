# Shipping deployed with another service's image

## The scenario

| | |
|---|---|
| scenario | `v2-shipping-wrong-image` |
| fault class | **`bad_deploy`** |
| expected remediation | `rollback` |
| split | `dev` |
| injected at | `shipping` via `v2-shipping-wrong-image` |
| time to page | 4m33s |
| steady state captured | 300s |
| capture window | 2026-09-27T06:45:26+00:00 → 2026-09-27T07:06:00+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m33s |
| `t_revert` | T+9m33s |
| all clear | T+13m34s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m15s | `checkout` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+7m15s | `accounting` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `email` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `fraud-detection` | ServiceNoTraffic | 1.0 min | joined later |
| T+7m15s | `payment` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `quote` | ServiceNoTraffic | 3.0 min | joined later |
| T+7m15s | `shipping` | ServiceNoTraffic | 3.0 min | joined later |
| T+10m15s | `fraud-detection` | ServiceHighErrorRate | 1.0 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="shipping"}` |

`logs/shipping.txt` — 63 lines.

## A look at the logs

From `logs/shipping.txt` (---- onset 2026-09-27T06:50:26+00:00 ----):

```
2026-09-27T06:50:29+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T06:50:29+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T06:50:29+00:00  [otel.javaagent 2026-09-27 06:50:29:888 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
2026-09-27T06:50:30+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T06:50:30+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T06:50:31+00:00  [otel.javaagent 2026-09-27 06:50:31:342 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
2026-09-27T06:50:32+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T06:50:32+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T06:50:33+00:00  [otel.javaagent 2026-09-27 06:50:32:998 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
2026-09-27T06:50:34+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T06:50:34+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T06:50:35+00:00  [otel.javaagent 2026-09-27 06:50:35:327 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
```

_42 further lines are in the bundle._

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

The page was one alert, `ServiceHighErrorRate` on **checkout**, 4m33s after the trouble started.

Checkout's error ratio had been zero. It was 5% at two minutes, 11% at three, 16% at four, and
from five minutes it held at 26-28%. Its latency fell, from a p95 of about 35ms to between 15 and
24ms: its orders were finishing sooner, which is what failing orders do. The storefront's error
ratios rose to 4-5% and hovered there, frontend-proxy touching the line once and dropping back, so
neither it nor the frontend paged. Browsing and the cart worked. Checking out did not.

About three minutes after the page, six services went quiet in the same minute:
`ServiceNoTraffic` on **shipping**, and on quote, payment, email, accounting and fraud-detection.
None of them had recorded an error. Cart, the product catalog and currency kept their traffic.
Fraud-detection's quiet lasted only a minute, and 42 seconds after the fix it raised a one-minute
`ServiceHighErrorRate` of its own. Seven alerts by the fix, and that one after it.

### What was checked

**Checkout's error traces.** Every failing order had the same shape. The cart read, the product
lookups and the currency conversions all succeeded. Then checkout's `HTTP POST` for the shipping
quote failed, with nothing beneath it, and `PlaceOrder` errored with `shipping quote failure:
failed POST to shipping service: Post "http://shipping:50050/get-quote": dial tcp: lookup shipping
on 127.0.0.11:53: no such host`. Nothing after the quote ran: no charge, no shipment, no email.

**The frontend's log,** which carries checkout's errors up to the storefront, gave the same failure
in two forms: `lookup shipping ... no such host`, 138 times, 6 to 18 a minute, and `connect:
connection refused`, 12 times. Mostly the name `shipping` did not exist at all, and sometimes it
did and nothing was listening behind it. A service that is simply down gives one or the other. A
service that keeps coming up and going down gives both.

**Shipping itself.** No errors, no traces, and no traffic: its error ratio stayed at zero because
it answered nothing to fail. Shipping has never written a log line the tools can read, and now it
had a stream, and the stream was not shipping's. Eighteen times in a little over nine minutes it
logged the same start -
`Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar`,
`OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes`, and the
OpenTelemetry Java agent announcing its version - and then nothing.
Shipping is not a Java service. The first start came three seconds in, and the gaps between them
grew from a second to about a minute and stayed there, which is the runtime backing off a
container that keeps dying. Its memory limit is 20M, sized for the small native binary shipping
normally is; a Java virtual machine with an agent attached cannot even finish starting in that.

**Fraud-detection's error alert.** A dead end. With orders gone it had gone quiet, and then its one
remaining span, its `flagd.evaluation.v1.Service/EventStream` stream to the flag service, was
ended by flagd with `stream closed due to server-side timeout`, the routine ten-minute reconnect.
That one span was an error, so fraud-detection read 100% errors on almost no traffic, with a p95
at the top of the histogram, 15 seconds; flagd's p95 went the same way for two minutes without
alerting. No order was involved, and the alert cleared as orders came back.

**What changed.** One record, at the start: `image reference updated on shipping`, to
`ghcr.io/open-telemetry/demo:2.2.0-ad`. That is the ad service's image. The deploy had worked -
the image exists and the container started - and what it started was the wrong program. Nothing
else had changed: shipping's memory limit was what it had always been, and nothing had changed on
checkout, quote or anywhere else.

### Root cause

A deploy put the ad service's image into shipping's slot. The image resolved, so the deploy
succeeded and the container started, but what it ran was the ad service's Java process, which
cannot start inside shipping's 20M limit and was killed for memory before it could serve,
eighteen times, with the runtime backing off between attempts. Shipping never answered a request.
Every order failed at its shipping quote, after the cart, the catalog and currency had done their
parts. Nothing was wrong with shipping's limit or with any caller.

### Resolution

Shipping was rolled back to its own image, `2.2.0-shipping`. The container was recreated and did
not start over again. The quiet services had traffic again within half a minute of the fix, and
the error ratios drained with their windows. Everything was quiet 4m01s after the fix. The one
alert that began during recovery was fraud-detection's stream-timeout error alert.

Class of fix: **rollback**. A deploy was wrong and it was undone. Raising shipping's memory limit
would only have let the wrong program run, and restarting it was what the runtime had already been
doing, eighteen times.

### Detection notes

- Onset to first page: **4m33s**. Services on the page: **one**, checkout, which was not at fault.
  By the fix: **seven**, shipping among them.
- Alerts that fired only during recovery: **one**, fraud-detection's `ServiceHighErrorRate`, a
  routine flag-stream timeout while its orders were still gone.
- Did the loudest service turn out to be the culprit? **No.** Checkout paged on its calls to
  shipping; shipping's only alert was the absence of traffic, three minutes later.
- Would the page alone have led you to the right service? **No, but one trace does.** Every failing
  order stops at the shipping quote.
- **"No such host" and "connection refused" together is a restart loop.** A service that is gone
  gives one; a service that is dying and starting over gives both.
- **A log in the wrong language is the whole story.** Shipping does not run Java. A stream that
  appears where there was none, and says `JAVA_TOOL_OPTIONS`, means something else is running in
  its place.
- **Killed for memory with an unchanged limit means the workload changed, not the limit.** This
  looks like a memory fault and is a deploy fault; the change record naming the image is what
  separates them, and rolling back is the fix, not raising the limit.
- **A single routine span can page a quiet service.** Fraud-detection's one-minute error alert was
  its flag-service stream timing out while orders were gone, not a second fault.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-shipping-wrong-image/`](../../evals/scenarios/artifacts/dev/v2-shipping-wrong-image/) by `faultline-render`. [All bundles](README.md).
