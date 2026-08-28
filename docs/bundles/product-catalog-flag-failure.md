# A feature flag turned on at the flag service makes product catalog fail one product

## The scenario

| | |
|---|---|
| scenario | `product-catalog-flag-failure` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `featureflagservice` via `product-catalog-flag-failure` |
| time to page | 4m04s |
| steady state captured | 300s |
| capture window | 2026-08-28T03:48:07+00:00 → 2026-08-28T04:05:45+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m04s |
| `t_revert` | T+9m04s |
| all clear | T+10m38s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m45s | `loadgenerator` | ServiceHighErrorRate | 6.8 min | **paged** |
| T+4m15s | `frontend` | ServiceHighErrorRate | 3.8 min | joined later |
| T+4m15s | `productcatalogservice` | ServiceHighErrorRate | 6.2 min | joined later |
| T+10m15s | `frontend` | ServiceHighErrorRate | 0.2 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="featureflagservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/feature-flag-service.txt` — 8 lines.

## A look at the logs

From `logs/feature-flag-service.txt` (2 lines):

```
2026-08-28T03:53:11+00:00  ffs-stub listening on :50053; enabled flags: productCatalogFailure
2026-08-28T04:02:15+00:00  ffs-stub listening on :50053; enabled flags: none
```


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

The page was a single alert: `ServiceHighErrorRate` on **loadgenerator**, 4m04s after
onset. Fifteen seconds later **frontend** and **productcatalogservice** joined it.

Three services alerted during the failure and the set never grew. A fourth alert fired
after the fix: frontend crossed the threshold again for about twelve seconds during
recovery, on a service that had already been alerting throughout.

On the storefront most product pages rendered normally. One did not — it returned an
error every time, while everything around it worked. Baskets, checkout and payment were
unaffected.

### What was checked

**productcatalogservice, which was the obvious place to look.** Unlike most incidents on
this system, the failing service was named in the alerting and was genuinely returning
errors from its own code. It was up, serving, and reporting a healthy call rate — the
errors were a fraction of its traffic, not all of it.

**Which requests were failing.** Not all catalog lookups. One product identifier failed
consistently; every other lookup succeeded. A partial failure with a stable boundary is
not resource pressure, not a dependency outage and not a network problem — all of those
degrade traffic in aggregate rather than singling out one input.

**What changed on productcatalogservice.** Nothing. Image unchanged, environment
unchanged, configuration unchanged, resource limits unchanged, dependencies healthy.
This is the dead end, and it is a convincing one, because the service really was
producing the errors. Everything about it looked correct because everything about it
*was* correct.

**Its dependencies.** The database and cache were fine and every other consumer of them
was unaffected.

**The service list.** This is where it turns. productcatalogservice consults a feature
flag service on each request. That service does not appear in the metrics at all — it
has no call-rate series, no latency series and no error series, under any spelling of
its name. There is no dashboard for it, and no alert can fire on it, because nothing
about it is recorded.

**The flag service's own configuration.** A flag had been enabled that instructs product
catalog to fail requests for a specific product. The service was doing exactly what it
was told.

### Root cause

A feature flag was switched on at the flag service, and productcatalogservice honoured
it by returning errors for one product. The failing service was working correctly; the
configuration that made it fail lived somewhere else entirely, in a component with no
telemetry of any kind.

The errors were real and were attributable to product catalog. The *cause* was not, and
no amount of investigating product catalog would have found it.

### Resolution

The flag was turned off. The next request for that product succeeded. Everything was
clear **1m34s** after the fix. Nothing had to restart, drain or reconnect — a flag flip
takes effect on the following request — and the remaining time is the alerting's own
rolling windows emptying rather than the system recovering.

Class of fix: **config_revert**. Nothing was deployed and there was no version to roll
back to; one configuration value was wrong and was set back.

### Detection notes

- Onset to first page: **4m04s**.
- Services alerting at the page: **1**. Over the whole incident: **3**, across 4 alerts.
- Alerts that fired only during recovery: **1** — frontend, about twelve seconds, after
  the fix had already gone in. It names a service that was genuinely part of the failure,
  which makes it harder to dismiss than a recovery alert on an uninvolved service.
- **The service that errors is not the service that is misconfigured.** This is the
  inverse of a failure where the broken service goes silent. Here the broken-looking
  service is healthy and correct, and the alerting points at it with complete accuracy
  and no useful information.
- **A partial failure with a stable boundary is a configuration signature.** Resource
  exhaustion, dependency latency and outages all degrade traffic in aggregate. One input
  failing consistently while every other input succeeds means something is deciding, and
  something that decides is configured.
- **The cause was in a component with no telemetry.** Nothing in the metrics stack could
  have surfaced it — not a dashboard, not an alert, not a trace attribute. The only route
  to it was knowing that product catalog consults it, and then going to look at
  something the observability stack does not know exists.
- Did the loudest service turn out to be the culprit? **No**, but for an unusual reason:
  the loudest service was loadgenerator as always, and the *second* loudest was the
  service actually producing the errors — which was still not the cause.

---

Rendered from [`evals/scenarios/artifacts/dev/product-catalog-flag-failure/`](../../evals/scenarios/artifacts/dev/product-catalog-flag-failure/) by `faultline-render`. [All bundles](README.md).
