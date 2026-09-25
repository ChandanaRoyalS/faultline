# Cart service pointed at the wrong valkey port

> ## ⚠ This bundle is not evidence of anything
>
> The fault was injected and **nothing happened** — no alert fired and no metric
> moved. It is rendered here for completeness and because a catalogue that quietly
> omits its failures is not a catalogue. The bundle's own
> [`INVALID.md`](../../evals/scenarios/artifacts/dev/v2-cart-valkey-misconfig/INVALID.md) explains why the fault could not fire.

## The scenario

| | |
|---|---|
| scenario | `v2-cart-valkey-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `cart` via `v2-cart-valkey-misconfig` |
| time to page | 3m46s |
| steady state captured | 300s |
| capture window | 2026-09-24T23:36:56+00:00 → 2026-09-24T23:57:44+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m46s |
| `t_revert` | T+8m46s |
| all clear | T+13m48s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m45s | `checkout` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+3m45s | `frontend` | ServiceHighErrorRate | 10.0 min | **paged** |
| T+3m45s | `frontend-proxy` | ServiceHighErrorRate | 10.0 min | **paged** |
| T+3m45s | `load-generator` | ServiceHighErrorRate | 9.0 min | **paged** |
| T+5m45s | `fraud-detection` | ServiceHighErrorRate | 2.0 min | joined later |
| T+6m45s | `fraud-detection` | ServiceHighLatency | 1.0 min | joined later |
| T+7m45s | `accounting` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `currency` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `email` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `payment` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `quote` | ServiceNoTraffic | 2.0 min | joined later |
| T+7m45s | `shipping` | ServiceNoTraffic | 2.0 min | joined later |
| T+8m45s | `cart` | ServiceNoTraffic | 1.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="cart"}` |

`logs/cart.txt` — 506 lines.

## A look at the logs

From `logs/cart.txt` (500 lines):

```
2026-09-24T23:36:57+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-24T23:36:57+00:00        GetCartAsync called with userId=
2026-09-24T23:36:58+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-24T23:36:58+00:00        AddItemAsync called with userId=d5689812-b870-11f1-a811-5a2f3da10002, productId=1YMWWN1N4O, quantity=10
2026-09-24T23:36:58+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-24T23:36:58+00:00        GetCartAsync called with userId=d5689812-b870-11f1-a811-5a2f3da10002
2026-09-24T23:36:58+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-24T23:36:58+00:00        GetCartAsync called with userId=d5689812-b870-11f1-a811-5a2f3da10002
2026-09-24T23:36:58+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-24T23:36:58+00:00        EmptyCartAsync called with userId=d5689812-b870-11f1-a811-5a2f3da10002
2026-09-24T23:37:01+00:00  info: cart.cartstore.ValkeyCartStore[0]
2026-09-24T23:37:01+00:00        GetCartAsync called with userId=
```

_488 further lines are in the bundle._

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

**On the page:** ServiceHighErrorRate/checkout, ServiceHighErrorRate/frontend, ServiceHighErrorRate/load-generator, ServiceHighErrorRate/frontend-proxy

#### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+3m46s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighErrorRate | checkout | T-1s | 9.0m |
| **on the page** | ServiceHighErrorRate | frontend | T-1s | 10.0m |
| **on the page** | ServiceHighErrorRate | frontend-proxy | T-1s | 10.0m |
| **on the page** | ServiceHighErrorRate | load-generator | T-1s | 9.0m |
| later | ServiceHighErrorRate | fraud-detection | T+1m59s | 2.0m |
| later | ServiceHighLatency | fraud-detection | T+2m59s | 1.0m |
| later | ServiceNoTraffic | accounting | T+3m59s | 2.0m |
| later | ServiceNoTraffic | currency | T+3m59s | 2.0m |
| later | ServiceNoTraffic | email | T+3m59s | 2.0m |
| later | ServiceNoTraffic | payment | T+3m59s | 2.0m |
| later | ServiceNoTraffic | quote | T+3m59s | 2.0m |
| later | ServiceNoTraffic | shipping | T+3m59s | 2.0m |
| later | ServiceNoTraffic | cart | T+4m59s | 1.0m |

The page named 4 service(s). By the time the fault was removed 13 alert(s) had fired - 9 more than the responder saw when they started.

### What was checked

<!-- The signals a responder would reach for, in order, including the ones that turned
     out to be dead ends. Dead ends are valuable - they are what distinguishes a real
     investigation from a lookup. -->

### Root cause

<!-- One paragraph, plain language. -->

### Resolution

<!-- What fixed it, and what class of fix that is: rollback / restart / config_revert /
     scale. Must match the scenario's expected_remediation_class. -->

### Detection notes

- Onset to first firing alert: 3m46s
- Services alerting on the page: 4
- Services alerting by the end of the fault: 13
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 5m02s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->

---

Rendered from [`evals/scenarios/artifacts/dev/v2-cart-valkey-misconfig/`](../../evals/scenarios/artifacts/dev/v2-cart-valkey-misconfig/) by `faultline-render`. [All bundles](README.md).
