# Shipping service deployed with another service's image

## The scenario

| | |
|---|---|
| scenario | `shipping-wrong-image` |
| fault class | **`bad_deploy`** |
| expected remediation | `rollback` |
| split | `dev` |
| injected at | `shippingservice` via `shipping-wrong-image` |
| time to page | 3m04s |
| steady state captured | 300s |
| capture window | 2026-09-09T05:24:31+00:00 → 2026-09-09T05:41:51+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m04s |
| `t_revert` | T+8m04s |
| all clear | T+10m20s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+2m45s | `checkoutservice` | ServiceHighErrorRate | 7.2 min | **paged** |
| T+5m15s | `loadgenerator` | ServiceHighErrorRate | 1.0 min | joined later |
| T+5m30s | `frontend` | ServiceHighErrorRate | 0.5 min | joined later |
| T+6m00s | `accountingservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m00s | `emailservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m00s | `frauddetectionservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m00s | `quoteservice` | ServiceNoTraffic | 2.2 min | joined later |
| T+6m00s | `shippingservice` | ServiceNoTraffic | 2.2 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="shippingservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/shipping-service.txt` — 337 lines.

## A look at the logs

From `logs/shipping-service.txt` (331 lines):

```
2026-09-09T05:29:35+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T05:29:35+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T05:29:35+00:00  [otel.javaagent 2026-09-09 05:29:35:573 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-09-09T05:29:40+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T05:29:41+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T05:29:41+00:00  [otel.javaagent 2026-09-09 05:29:41:323 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-09-09T05:29:45+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T05:29:46+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T05:29:46+00:00  [otel.javaagent 2026-09-09 05:29:46:357 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-09-09T05:29:51+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-09-09T05:29:51+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-09-09T05:29:51+00:00  [otel.javaagent 2026-09-09 05:29:51:904 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
```

_319 further lines are in the bundle._

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

The page was a single alert: `ServiceHighErrorRate` on **checkoutservice**, 3m04s after
onset. The fastest page this system has produced, and unusually it named a service one
hop from the problem rather than the edge.

**loadgenerator** crossed two and a half minutes later and **frontend** fifteen seconds after
that, both briefly. Then five services raised `ServiceNoTraffic` **together** at **T+6m00s** —
quoteservice, accountingservice, emailservice, frauddetectionservice and **shippingservice**.

**How far behind the edge alerts arrive is not stable.** Here it was two and a half minutes;
in the recording before this one frontend and loadgenerator never crossed at all; in earlier
ones they were four minutes behind. Dilution is the mechanism in every case — it is why checkout
alerts and the edge is slow to — but its size is a property of the run, not of the fault.

Eight alerts across eight services. On the storefront, browsing and basket operations
worked normally. Checkout failed every time.

### What was checked

**checkoutservice, named in the page.** Errors on its calls to shipping. Its own
process was healthy, its configuration unchanged, its other dependencies fine.

**shippingservice's logs.** The service was starting and dying, over and over. Fifteen
attempts inside the fault window, each one exactly three lines long — a JVM banner, a
class-loading warning, an instrumentation agent announcing its version — and then
nothing. The gaps between attempts lengthen from five seconds to a minute and stay
there, which is a supervisor backing off a container that will not stay up.

**And this is where a confident wrong answer is available.** A JVM that dies partway
through startup, repeatedly, on a lengthening backoff, saying nothing about why, is
exactly what a memory limit set below what the service needs looks like. The signature is
identical. The diagnosis writes itself and the obvious fix is to raise the ceiling.

**What the process never said.** Not one line explains a failure. That absence is
itself informative: a process that fails on its own configuration prints the reason,
because it got far enough to read the configuration and object to it. This one is being
stopped from outside before it reaches that point — killed, not failing.

**The logs from before onset, which is where it breaks open.** Up to 18:29:28 the
container is emitting Rust — structured request lines from the shipping implementation,
`ShipOrderRequest`, quote calculations, tracking IDs. From 18:29:33 it emits JVM startup
banners and nothing else. **The service changed language across the boundary.** No
resource limit does that. Whatever is running in that container is not the program that
was running five seconds earlier.

**What changed on shippingservice.** Its image reference. A deployment had pointed it at
a different service's image — one built on a JVM, where the previous image was a small
native binary. The new image needs several times the memory the old one did, and the
container ceiling was sized for the old one.

**The memory limit, which had not changed.** Its ceiling was the same value it had been
for weeks. Nothing had lowered it. A service does not begin exceeding a limit it has
lived comfortably inside unless something about the service changed.

### Root cause

A deployment put the wrong image on shippingservice. The image resolved and pulled
cleanly, so the deploy itself reported success; the failure is entirely in what the
container did afterwards. It could not start inside a memory ceiling sized for the
service that was supposed to be there.

The observable symptom belongs to resource exhaustion. The cause is a deployment, and
the two are separated by what changed: the image moved, the limit did not.

### Resolution

The image reference was restored. shippingservice came up on the next reconciliation and
checkout succeeded immediately. The no-traffic alerts cleared as those services resumed.
A brief `ServiceHighErrorRate` appeared on frontend fifteen seconds *after* the fix and
lasted half a minute — queued work draining through a path that had been failing.
Everything was clear 2m16s after the fix.

Class of fix: **rollback**. A deployment moved the service to the wrong artifact, and
the fix was to put the previous one back.

**Raising the memory limit would also have stopped the alert, and would have been
worse.** The container would have started, stayed up, and answered on the wrong
protocol — a service reporting healthy while every caller fails, which is harder to
diagnose than a container that cannot start.

### Detection notes

- Onset to first page: **3m04s**, the fastest on this system. A dependency whose failure
  is fatal to its caller pages quickly; one whose failure is tolerated does not.
- Services alerting at the page: **1**. Over the whole incident: **8**, across 8 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named the caller, not the edge and not the culprit.** checkoutservice fails
  outright when shipping is unavailable, so its error ratio crosses the threshold before
  the frontend's diluted one does. Being one hop from the fault made it the earliest and
  most specific signal available.
- **Dilution decides who alerts, and how much it is worth varies run to run.** checkout, which
  fails on every attempt, alerted at T+2m45s; frontend and the synthetic client, whose failures
  are one path out of many, crossed two and a half minutes later here, not at all in the previous
  recording, and nearly four minutes late in earlier ones. The same failure reaches the edge last
  and weakest — sometimes never — so a responder who waits for the storefront to look broken is
  choosing to start late or not at all.
- **A truncated, repeating startup names a symptom, not a cause.** A process stopped
  before it can explain itself is being killed from outside, and that is all the pattern
  says. It does not distinguish "the ceiling came down" from "the thing inside it got
  bigger", and those have opposite fixes.
- **What separated them was the log content before onset**, not the failure itself. The
  container was running one language and then another. A service whose runtime changes
  has been redeployed, whatever else is true — and no resource limit produces that.
  Where a substituted image happens to share a runtime with the original, this signal
  would not exist and the change history would be the only route.
- The strongest single question remained **"what changed on this service?"** Any
  investigation that stopped at the restart pattern would have shipped a fix that made
  the system quieter and worse.

---

Rendered from [`evals/scenarios/artifacts/dev/shipping-wrong-image/`](../../evals/scenarios/artifacts/dev/shipping-wrong-image/) by `faultline-render`. [All bundles](README.md).
