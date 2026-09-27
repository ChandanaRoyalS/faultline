# Shipping deployed with another service's image

## The scenario

| | |
|---|---|
| scenario | `v2-shipping-wrong-image` |
| fault class | **`bad_deploy`** |
| expected remediation | `rollback` |
| split | `dev` |
| injected at | `shipping` via `v2-shipping-wrong-image` |
| time to page | 4m05s |
| steady state captured | 300s |
| capture window | 2026-09-27T00:42:47+00:00 → 2026-09-27T01:02:53+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m05s |
| `t_revert` | T+9m05s |
| all clear | T+13m06s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m45s | `checkout` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+5m45s | `fraud-detection` | ServiceHighErrorRate | 1.0 min | joined later |
| T+7m45s | `accounting` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `email` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `payment` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `quote` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `shipping` | ServiceNoTraffic | 2.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="shipping"}` |

`logs/shipping.txt` — 60 lines.

## A look at the logs

From `logs/shipping.txt` (---- onset 2026-09-27T00:47:47+00:00 ----):

```
2026-09-27T00:47:51+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T00:47:52+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T00:47:53+00:00  [otel.javaagent 2026-09-27 00:47:53:606 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
2026-09-27T00:47:54+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T00:47:55+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T00:47:56+00:00  [otel.javaagent 2026-09-27 00:47:55:990 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
2026-09-27T00:47:57+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T00:47:58+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T00:47:58+00:00  [otel.javaagent 2026-09-27 00:47:58:602 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
2026-09-27T00:48:00+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar
2026-09-27T00:48:00+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-27T00:48:01+00:00  [otel.javaagent 2026-09-27 00:48:01:240 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 2.23.0
```

_39 further lines are in the bundle._

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

The page was one alert, `ServiceHighErrorRate` on **checkout**, 4m05s after the trouble started.

Checkout's error ratio had been zero. It was about 2% a minute in, 9% at two minutes, 21% at four,
and from five minutes it held at 24-26%. Its latency fell, from a p95 of about 35ms to about 22ms:
its orders were finishing sooner, which is what failing orders do. The storefront's error ratios
rose to about 5% and hovered there, frontend and frontend-proxy each touching the line and dropping
back, so neither paged. Browsing and the cart worked. Checking out did not.

About four minutes after the page, five services went quiet in the same minute: `ServiceNoTraffic`
on **shipping**, and on quote, payment, email and accounting. None of them had recorded an error.
Cart, the product catalog and currency kept their traffic. In between, fraud-detection raised a
one-minute `ServiceHighErrorRate` of its own: with orders gone it had almost no spans, and the
one it did make, its stream to the flag service closing on the server's routine ten-minute timeout,
was an error. Seven alerts by the fix, and none after it.

### What was checked

**Checkout's error traces.** Every failing order had the same shape. The cart read, the product
lookups and the currency conversions all succeeded. Then checkout's `HTTP POST` for the shipping
quote failed, with nothing beneath it, and `PlaceOrder` errored with `shipping quote failure:
failed POST to shipping service: Post "http://shipping:50050/get-quote": dial tcp: lookup shipping
on 127.0.0.11:53: no such host`. Nothing after the quote ran: no charge, no shipment, no email.

**The frontend's log,** which carries checkout's errors up to the storefront, gave the same failure
in two forms, alternating: `lookup shipping ... no such host`, and `dial tcp 172.18.0.23:50050:
connect: connection refused`. Sometimes the name `shipping` did not exist at all, and sometimes it
did and nothing was listening behind it. A service that is simply down gives one or the other. A
service that keeps coming up and going down gives both.

**Shipping itself.** No errors, no traces, and no traffic: its error ratio stayed at zero because
it answered nothing to fail. Shipping has never written a log line the tools can read, and now it
had a stream, and the stream was not shipping's. Seventeen times in nine minutes it logged exactly
three lines - `Picked up JAVA_TOOL_OPTIONS: -javaagent:/usr/src/app/opentelemetry-javaagent.jar`,
`OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes`, and the
OpenTelemetry Java agent announcing its version - and then nothing. Shipping is not a Java
service. The gaps between the starts grew from three seconds to about a minute, which is the
runtime backing off a container that keeps dying. Read on the container directly, each exit was
code 137 and marked as killed for memory, and its restart count climbed to 17. Its memory limit is
20M, sized for the small native binary shipping normally is; a Java virtual machine with an agent
attached cannot even finish starting in that.

**What changed.** One record, at the start: `image reference updated on shipping`, to
`ghcr.io/open-telemetry/demo:2.2.0-ad`. That is the ad service's image. The deploy had worked -
the image exists and the container started - and what it started was the wrong program. Nothing
else had changed: shipping's memory limit was what it had always been, and nothing had changed on
checkout, quote or anywhere else.

### Root cause

A deploy put the ad service's image into shipping's slot. The image resolved, so the deploy
succeeded and the container started, but what it ran was the ad service's Java process, which
cannot start inside shipping's 20M limit and was killed for memory before it could serve,
seventeen times, with the runtime backing off between attempts. Shipping never answered a request.
Every order failed at its shipping quote, after the cart, the catalog and currency had done their
parts. Nothing was wrong with shipping's limit or with any caller.

### Resolution

Shipping was rolled back to its own image, `2.2.0-shipping`. The container was recreated, started
cleanly, and did not restart again. Quotes, charges, confirmations and orders came back within a
minute of the fix, and the error ratios drained with their windows. Everything was quiet 4m01s
after the fix, and nothing fired during recovery.

Class of fix: **rollback**. A deploy was wrong and it was undone. Raising shipping's memory limit
would only have let the wrong program run, and restarting it was what the runtime had already been
doing, seventeen times.

### Detection notes

- Onset to first page: **4m05s**. Services on the page: **one**, checkout, which was not at fault.
  By the fix: **seven**, shipping among them.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** Checkout paged on its calls to
  shipping; shipping's only alert was the absence of traffic, four minutes later.
- Would the page alone have led you to the right service? **No, but one trace does.** Every failing
  order stops at the shipping quote.
- **"No such host" and "connection refused" alternating is a restart loop.** A service that is gone
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
