# Payment service healthy, serving, and invisible in the traffic metric

## The scenario

| | |
|---|---|
| scenario | `payment-telemetry-blackout` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `paymentservice` via `payment-telemetry-blackout` |
| time to page | 6m16s |
| steady state captured | 300s |
| capture window | 2026-08-31T02:29:36+00:00 → 2026-08-31T02:48:54+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+6m16s |
| `t_revert` | T+11m16s |
| all clear | T+12m18s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+6m00s | `paymentservice` | ServiceNoTraffic | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="paymentservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/payment-service.txt` — 334 lines.

## A look at the logs

From `logs/payment-service.txt` (328 lines):

```
2026-08-31T02:34:37+00:00  npm notice
2026-08-31T02:34:37+00:00  npm notice New major version of npm available! 8.19.2 -> 12.0.2
2026-08-31T02:34:37+00:00  npm notice Changelog: <https://github.com/npm/cli/releases/tag/v12.0.2>
2026-08-31T02:34:37+00:00  npm notice Run `npm install -g npm@12.0.2` to update!
2026-08-31T02:34:37+00:00  npm notice
2026-08-31T02:34:37+00:00  npm ERR! path /usr/src/app
2026-08-31T02:34:37+00:00  npm ERR! command failed
2026-08-31T02:34:37+00:00  npm ERR! signal SIGTERM
2026-08-31T02:34:37+00:00  npm ERR! command sh -c -- node opentelemetry.js
2026-08-31T02:34:37+00:00
2026-08-31T02:34:37+00:00  npm ERR! A complete log of this run can be found in:
2026-08-31T02:34:37+00:00  npm ERR!     /home/node/.npm/_logs/2026-08-31T02_21_49_144Z-debug-0.log
```

_316 further lines are in the bundle._

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

<!-- NO ABSOLUTE TIMESTAMPS IN THE PROSE. Write "T+3m" or "about four minutes after
     the page", never "08:02:41". This file is read months later as a past incident,
     where the hour it happened means nothing - and a re-record would orphan every
     timestamp written here.

     `recorded_from` in the front matter above is the deliberate exception. It is
     absolute precisely so that it breaks when the recording changes: it pins this
     narrative to one recording, and a guard fails if they drift apart. Front matter
     is written to fail on a re-record; prose is written to survive one. Do not
     "fix" the inconsistency - see ARTIFACTS.md. -->

### What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

**On the page:** ServiceNoTraffic/paymentservice

#### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+6m16s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceNoTraffic | paymentservice | T-16s | 6.0m |

### What was checked

**Whether anything downstream of payment was failing.** Nothing was. Checkout's error ratio was
flat at zero for the whole window, and no error-rate or latency alert fired on any service. For a
service that had supposedly stopped serving, this was the wrong shape entirely - when payment is
genuinely unavailable, checkout is the first thing to break, and it had not.

**Whether checkout was still calling payment at all.** It was. Checkout's client spans to
paymentservice continued throughout and continued to return normally. That ruled out the
possibility that traffic had simply stopped arriving - somebody was still calling, and the calls
were being answered.

**Payment's own logs.** This is what settled it. The container logged `Charge request received.`
continuously through the entire window - 111 of them across the minutes the alert was firing,
carrying trace ids and card details as usual. A process that is down does not log; this one was
handling charges the whole time it was reported as serving none.

**Dead end: looking for a crash or a restart.** Container status, restart count and memory were all
checked first, because `ServiceNoTraffic` normally means something died. Nothing had. The container
had been up since the start of the window and showed no restarts and no memory pressure.

**Dead end: looking for the cascade.** Every previous `ServiceNoTraffic` on this system arrived with
company - a fan of alerts across the services that depend on the dead one. This one was alone, and
that was treated as suspicious rather than lucky.

**What named it:** the change history on paymentservice, which showed its OTLP trace exporter
endpoint had been changed to an address that does not answer.

### Root cause

The payment service's trace exporter was pointed at an address with nothing listening on it, so the
service stopped shipping spans. Nothing about the service itself changed: it kept accepting charges
and kept logging them. The traffic metric that `ServiceNoTraffic` watches is built from those spans,
so when the spans stopped the metric went to zero and the alert fired on a service that was working
normally the entire time. The outage was in the reporting path, not in the payment path.

### Resolution

The exporter endpoint was set back to the collector, and the traffic metric recovered within about a
minute of the service picking the setting up. **Class of fix: `config_revert`** - a setting was
returned to its previous value. Nothing was rolled back, restarted for its own sake, or resized; the
service had never been unhealthy.

### Detection notes

- Onset to first firing alert: 6m16s
- Services alerting on the page: 1
- Services alerting by the end of the fault: 1
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 1m02s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->

---

Rendered from [`evals/scenarios/artifacts/dev/payment-telemetry-blackout/`](../../evals/scenarios/artifacts/dev/payment-telemetry-blackout/) by `faultline-render`. [All bundles](README.md).
