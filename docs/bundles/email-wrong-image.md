# Email service deployed with another service's image

## The scenario

| | |
|---|---|
| scenario | `email-wrong-image` |
| fault class | **`bad_deploy`** |
| expected remediation | `rollback` |
| split | `holdout` |
| injected at | `emailservice` via `email-wrong-image` |
| time to page | 4m16s |
| steady state captured | 300s |
| capture window | 2026-08-24T02:50:23+00:00 → 2026-08-24T03:07:39+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m16s |
| `t_revert` | T+9m16s |
| all clear | T+10m16s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m00s | `checkoutservice` | ServiceHighErrorRate | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |

`logs/email-service.txt` — 180 lines.

## A look at the logs

From `logs/email-service.txt` (174 lines):

```
2026-08-24T02:51:54+00:00  172.18.0.20 - - [24/Aug/2026:02:51:54 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0054
2026-08-24T02:51:59+00:00  172.18.0.20 - - [24/Aug/2026:02:51:59 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0019
2026-08-24T02:52:07+00:00  172.18.0.20 - - [24/Aug/2026:02:52:07 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0017
2026-08-24T02:52:16+00:00  172.18.0.20 - - [24/Aug/2026:02:52:16 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0017
2026-08-24T02:52:24+00:00  172.18.0.20 - - [24/Aug/2026:02:52:24 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0017
2026-08-24T02:52:27+00:00  172.18.0.20 - - [24/Aug/2026:02:52:27 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0018
2026-08-24T02:52:27+00:00  172.18.0.20 - - [24/Aug/2026:02:52:27 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0016
2026-08-24T02:52:38+00:00  172.18.0.20 - - [24/Aug/2026:02:52:38 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0019
2026-08-24T02:52:44+00:00  172.18.0.20 - - [24/Aug/2026:02:52:44 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0020
2026-08-24T02:52:45+00:00  172.18.0.20 - - [24/Aug/2026:02:52:45 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0017
2026-08-24T02:52:49+00:00  172.18.0.20 - - [24/Aug/2026:02:52:49 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0016
2026-08-24T02:52:51+00:00  172.18.0.20 - - [24/Aug/2026:02:52:51 +0000] "POST /send_order_confirmation HTTP/1.1" 200 - 0.0016
```

_162 further lines are in the bundle._

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

One alert: `ServiceHighErrorRate` on **checkoutservice**, 4m16s after onset. Nothing
else fired for the whole incident.

On the storefront, browsing, search and basket operations were normal. Checkout failed.

**emailservice never appeared in the alerting at any point** — not on error rate, not
on latency, not on traffic. The only evidence in the alert stream was one of its
callers failing.

### What was checked

**checkoutservice, named in the page.** Its own process was healthy, its configuration
unchanged, its resources fine. The errors were on one of its outbound calls.

**Which call was failing.** Order confirmation. checkout completes an order and then
hands off to emailservice; that hand-off was returning errors and taking the whole
checkout down with it.

**emailservice's logs, which contain the answer in plain text.** The service was
starting and dying repeatedly — eighteen attempts inside the fault window — and unlike a
process killed from outside, this one printed why every single time:

```
== Sinatra has ended his set (crowd applauds)
[core:warn] [pid 1] AH00111: Config variable ${QUOTE_SERVICE_PORT} is not defined
AH00526: Syntax error on line 5 of /etc/apache2/ports.conf: Port must be specified
```

Three things are wrong with that for a service called email. It is shutting down a Ruby
web framework, then starting Apache, and it is looking for a configuration variable
belonging to an entirely different service.

**What that pattern rules out.** A process that reads its configuration, objects to it,
and exits has got far enough to explain itself. Nothing external stopped it — no memory
ceiling, no scheduler, no dependency. It ran, disagreed with what it found, and quit.
That single distinction eliminates every resource-shaped explanation before any of them
is investigated.

**What changed on emailservice.** Its image reference. A deployment had pointed it at
the quote service's image. The container's environment is exactly what emailservice
needs and has nothing the quote service's code expects, so the process cannot configure
itself and exits on the first read.

### Root cause

A deployment put the wrong image on emailservice. The image resolved and pulled
cleanly, so the deploy reported success; what failed is what the container did next.

**The environment is correct for the service that belongs here and wrong for the image
that was deployed.** Read from the log line alone this looks like a missing
configuration variable, and the instinct is to go and define it. The variable is missing
because the wrong thing is asking for it, and defining it would make a service that
should not be running run slightly further.

### Resolution

The image reference was restored. emailservice came up on the next reconciliation and
checkout succeeded immediately. Everything was clear **60 seconds** after the fix —
nothing had to drain or reconnect, and the checkout path recovered as soon as its
dependency answered.

Class of fix: **rollback**. A deployment moved the service to the wrong artifact; the
fix was to put the previous one back.

### Detection notes

- Onset to first page: **4m16s**.
- Services alerting at the page: **1**. Over the whole incident: **1**, across 1 alert.
- Alerts that fired only during recovery: **none**.
- **The broken service never alerted.** No error rate, no latency, no absence of
  traffic. A container that cannot finish starting records nothing at all, and this one
  did not stay dead long enough in any single window to register as silent either. The
  entire signal was one caller failing.
- **Whether a failing process explains itself is the first thing to establish.** A
  process that prints a reason chose to stop; a process whose output ends mid-startup
  with no reason was stopped by something else. Those two have almost disjoint sets of
  causes, and the logs answer it immediately.
- **The logs named the cause outright** and cost nothing to check. The trap is not that
  the evidence is hidden; it is that the alerting points at a healthy service and the
  broken one is invisible, so reaching the logs at all requires following the
  dependency rather than the alert.
- Did the loudest service turn out to be the culprit? **No** — but it was the only
  service that alerted, so "loudest" and "only" were the same thing, and the culprit was
  one hop beyond it.

---

Rendered from [`evals/scenarios/artifacts/holdout/email-wrong-image/`](../../evals/scenarios/artifacts/holdout/email-wrong-image/) by `faultline-render`. [All bundles](README.md).
