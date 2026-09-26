# A feature flag makes the email service keep every confirmation it sends

## The scenario

| | |
|---|---|
| scenario | `v2-email-flag-memory-leak` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `email` via `v2-email-flag-memory-leak` |
| time to page | 4m16s |
| steady state captured | 300s |
| capture window | 2026-09-26T23:25:38+00:00 → 2026-09-26T23:46:54+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m16s |
| `t_revert` | T+9m16s |
| all clear | T+14m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m00s | `email` | ServiceHighLatency | 10.0 min | **paged** |
| T+6m00s | `checkout` | ServiceHighLatency | 6.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="email"}` |

`logs/email.txt` — 491 lines.

## A look at the logs

From `logs/email.txt` (---- onset 2026-09-26T23:30:38+00:00 ----):

```
2026-09-26T23:25:46+00:00  Order confirmation email sent to: reed@example.com
2026-09-26T23:25:46+00:00  172.18.0.9 - - [26/Sep/2026:23:25:46 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0064
2026-09-26T23:25:54+00:00  Order confirmation email sent to: tobias@example.com
2026-09-26T23:25:54+00:00  172.18.0.9 - - [26/Sep/2026:23:25:54 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0036
2026-09-26T23:26:04+00:00  Order confirmation email sent to: tobias@example.com
2026-09-26T23:26:04+00:00  172.18.0.9 - - [26/Sep/2026:23:26:04 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0085
2026-09-26T23:26:24+00:00  Order confirmation email sent to: tobias@example.com
2026-09-26T23:26:24+00:00  172.18.0.9 - - [26/Sep/2026:23:26:24 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0128
2026-09-26T23:26:25+00:00  Order confirmation email sent to: jeff@example.com
2026-09-26T23:26:25+00:00  172.18.0.9 - - [26/Sep/2026:23:26:25 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0025
2026-09-26T23:26:33+00:00  Order confirmation email sent to: moore@example.com
2026-09-26T23:26:33+00:00  172.18.0.9 - - [26/Sep/2026:23:26:33 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0026
```

_470 further lines are in the bundle._

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

The page was one alert, `ServiceHighLatency` on **email**, 4m16s after the trouble started. A
minute and three quarters later `ServiceHighLatency` fired on **checkout** too. Nothing else fired,
then or later, and nothing fired after the fix.

Email's p95 had been 20 to 36ms. A minute in it was 345ms, at two minutes 680ms, and from four
minutes it held between about 870 and 960ms. Email raised no errors at all. Its span rate fell
from about 0.5 a second to about 0.22, so less than half of its usual work was being recorded.

Checkout's p95 followed it up, from about 31ms to 184ms at two minutes and 550 to 590ms from four
minutes on. Its error ratio rose too, to between 1.6% and 3.6%, under the line. Around them almost
nothing moved. Payment, accounting and fraud-detection kept their usual rates, so orders were
being placed, charged and recorded. The storefront slowed a little, frontend-proxy's p95 from about
43 to at most 86ms, and nobody else's error ratio moved.

### What was checked

**Email's traces, the service on the page.** Every order's confirmation went through
`email/POST /send_order_confirmation`, and almost all of its time was `send_email`'s own: 280 to
670ms of self-time in the traces read, with the template rendering beneath it done in a few
milliseconds and nothing else beneath it at all. Email was not waiting on anything. It was
spending the time itself, after the email's content was already rendered. Every one of those
requests answered 200.

**Email's log.** Its request log said the same in seconds: each confirmation that completed took
0.28 to 0.97 seconds, against 0.002 to 0.04 before. And between them, again and again, the server
started up: `== Sinatra (v4.2.1) has taken the stage on 6060 for production with backup from
Puma`, then Puma's start-up banner. It started **24 times** in a little over nine minutes, 0 to 4
times a minute, each time after one or two confirmations, from 13 seconds after the trouble began.
Before none of those starts did email log anything: no error, no stack trace, no shutdown message.
A process that stops on an error of its own says so. One that is killed from outside does not.

**Checkout's errors.** Each was the same call: checkout's `HTTP POST` to email, in error with
`EOF` after 100 to 480ms. Email had gone away in the middle of answering. In the same traces the
rest of the order had succeeded: the cart, the catalog, currency, the shipping quote, the charge,
emptying the cart and the shipment. Checkout does not fail an order when its confirmation fails, so
its errors stayed under the line and the orders went through. What checkout did do was wait: the
confirmation call comes before the order is published, and every order waited out email's
half-second or more, which is checkout's latency page. Confirmations sent fell from 6 to 10 a
minute to between 1 and 7.

**Whether email was short of memory.** The tools can't say. Email reports no runtime series and no
memory metric, so its memory is not in the telemetry. Read on the container directly, it stood at
**99.2 to 99.8% of its 100M limit** in the readings taken just before its restart count rose, and
lower after each start; the count went from 0 to 24. The runtime did not mark the exits as
out-of-memory kills and kept no event for them, so the kill is read from the memory and the
silence, not from a record. Before the trouble email had run for nearly five days without a
restart, at about half its limit.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, and
no change to email's memory limit. The restarts were the runtime's, not anyone's change. So a
service that had sat at half its limit for days was now filling it within one or two requests, and
each request was taking a hundred times longer inside email's own code. Nothing about the traffic
had changed: the same few confirmations a minute. What each confirmation cost had changed, and on
this world what changes a service's behaviour without a deploy is a feature flag.

### Root cause

The `emailMemoryLeak` feature flag was set to its `10000x` variant in the flag service. With it
set, the email service stops discarding the confirmations it has sent and pads each one's body to
ten thousand times its length, about 19MB an email. The service filled its 100M limit within one or
two confirmations, was killed and restarted, and did so again every few confirmations for as long
as the flag was set. Each confirmation it managed to send took a third of a second or more to
build, and every order waited for it. The limit had not changed and nothing was deployed. The fault
was the flag's value.

### Resolution

The flag was set back to off. The flag service picks up the change on its own, so nothing was
restarted or redeployed by hand. Email's last restart came six seconds before the fix, and none came
after it. The first confirmation after the fix took three milliseconds, and email's memory came back
to its resting level, about 47 to 50% of its limit, within two minutes. Confirmations went back to
4 to 11 a minute. Checkout's latency alert cleared about two and a half minutes after the fix and
email's about four and a half, as their windows drained. Everything was quiet 5m00s after the fix,
and nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back. Raising email's memory
limit would only have let it keep more.

### Detection notes

- Onset to first page: **4m16s**. Services on the page: **one**, email, the service whose code
  reads the flag. By the fix: **two**, with checkout waiting on it.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes.**
- Would the page alone have led you to the right service? **Yes, and not to what was wrong with
  it.** The page says slow. What was happening was a crash loop, and the page never says so.
- **A crash loop can page as latency and never as errors.** Email recorded no error span: a process
  that is killed leaves no span for the request it was serving. The failures showed up as the
  caller's `EOF`, as fewer spans, and as the server starting over and over in its log.
- **A killed process has no last words.** Start-up banners with nothing logged before them mean the
  process was stopped from outside. Look for the memory limit.
- **A limit that is suddenly too small, when nobody changed it, means the service grew.** Email had
  lived at half its limit for days. When it fills the limit in one or two requests with the same
  traffic, each request is costing more, and with nothing in change history, something changed what
  a request does without a deploy.
- **The caller's tolerance hides the victims.** Checkout completes the order when the confirmation
  fails, so its errors stayed under the line while confirmations went missing.

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-email-flag-memory-leak/`](../../evals/scenarios/artifacts/holdout/v2-email-flag-memory-leak/) by `faultline-render`. [All bundles](README.md).
