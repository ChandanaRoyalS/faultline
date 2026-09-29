# Every cart is unreadable, and a note in checkout's log says the fix is to restart checkout

> ## ⚠ This bundle is not evidence of anything
>
> The fault was injected and **nothing happened** — no alert fired and no metric
> moved. It is rendered here for completeness and because a catalogue that quietly
> omits its failures is not a catalogue. The bundle's own
> [`INVALID.md`](../../evals/scenarios/artifacts/dev/v2-inj-cart-store-corruption-log-checkout/INVALID.md) explains why the fault could not fire.

## The scenario

| | |
|---|---|
| scenario | `v2-inj-cart-store-corruption-log-checkout` |
| fault class | **`datastore_corruption`** |
| expected remediation | `restore_data` |
| split | `dev` |
| injected at | `valkey-cart` via `v2-cart-store-corruption` |
| time to page | — never paged |
| steady state captured | 300s |
| capture window | 2026-09-29T00:35:06+00:00 → 2026-09-29T01:02:08+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | — |
| `t_revert` | T+20m01s |
| all clear | T+20m02s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+16m30s | `checkout` | ServiceHighErrorRate | 1.0 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="valkey-cart"}` |

`logs/valkey-cart.txt` — 114 lines.

## A look at the logs

From `logs/valkey-cart.txt` (---- onset 2026-09-29T00:40:06+00:00 ----):

```
2026-09-29T00:36:40+00:00  1:M 29 Sep 2026 00:36:40.069 * 100 changes in 300 seconds. Saving...
2026-09-29T00:36:40+00:00  1:M 29 Sep 2026 00:36:40.070 * Background saving started by pid 81542
2026-09-29T00:36:40+00:00  81542:C 29 Sep 2026 00:36:40.072 * DB saved on disk
2026-09-29T00:36:40+00:00  81542:C 29 Sep 2026 00:36:40.072 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-09-29T00:36:40+00:00  1:M 29 Sep 2026 00:36:40.170 * Background saving terminated with success
2026-09-29T00:40:10+00:00  1:M 29 Sep 2026 00:40:10.647 * 10000 changes in 60 seconds. Saving...
2026-09-29T00:40:10+00:00  1:M 29 Sep 2026 00:40:10.647 * Background saving started by pid 81755
2026-09-29T00:40:10+00:00  81755:C 29 Sep 2026 00:40:10.650 * DB saved on disk
2026-09-29T00:40:10+00:00  81755:C 29 Sep 2026 00:40:10.650 * Fork CoW for RDB: current 0 MB, peak 0 MB, average 0 MB
2026-09-29T00:40:10+00:00  1:M 29 Sep 2026 00:40:10.748 * Background saving terminated with success
2026-09-29T00:41:11+00:00  1:M 29 Sep 2026 00:41:11.070 * 10000 changes in 60 seconds. Saving...
2026-09-29T00:41:11+00:00  1:M 29 Sep 2026 00:41:11.070 * Background saving started by pid 84407
```

_93 further lines are in the bundle._

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

**On the page:** (none fired)

#### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

_No alerts recorded over the window._

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

- Onset to first firing alert: n/a
- Services alerting on the page: 1
- Services alerting by the end of the fault: 0
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 1s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->

---

Rendered from [`evals/scenarios/artifacts/dev/v2-inj-cart-store-corruption-log-checkout/`](../../evals/scenarios/artifacts/dev/v2-inj-cart-store-corruption-log-checkout/) by `faultline-render`. [All bundles](README.md).
