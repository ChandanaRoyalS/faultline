# Currency service starved of CPU quota, slowing every priced page

> ## ⚠ This bundle is not evidence of anything
>
> The fault was injected and **nothing happened** — no alert fired and no metric
> moved. It is rendered here for completeness and because a catalogue that quietly
> omits its failures is not a catalogue. The bundle's own
> [`INVALID.md`](../../evals/scenarios/artifacts/dev/currency-cpu-throttle/INVALID.md) explains why the fault could not fire.

## The scenario

| | |
|---|---|
| scenario | `currency-cpu-throttle` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `currencyservice` via `currency-cpu-throttle` |
| time to page | — never paged |
| steady state captured | 300s |
| capture window | 2026-08-23T09:41:17+00:00 → 2026-08-23T10:00:24+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | — |
| `t_revert` | T+12m03s |
| all clear | T+12m07s |

## What fired, and when

_No alert fired over the capture window._

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |

`logs/currency-service.txt` — 451 lines.

## A look at the logs

From `logs/currency-service.txt` (445 lines):

```
2026-08-23T09:41:18+00:00  Convert conversion successful
2026-08-23T09:41:18+00:00  Convert conversion successful
2026-08-23T09:41:26+00:00  Convert conversion successful
2026-08-23T09:41:26+00:00  Convert conversion successful
2026-08-23T09:41:26+00:00  Convert conversion successful
2026-08-23T09:41:26+00:00  Convert conversion successful
2026-08-23T09:41:34+00:00  Convert conversion successful
2026-08-23T09:41:34+00:00  Convert conversion successful
2026-08-23T09:41:34+00:00  Convert conversion successful
2026-08-23T09:41:34+00:00  Convert conversion successful
2026-08-23T09:41:34+00:00  Convert conversion successful
2026-08-23T09:41:37+00:00  Convert conversion successful
```

_433 further lines are in the bundle._

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

- Onset to first firing alert: ?
- Services alerting on the page: 1
- Services alerting by the end of the fault: 0
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 4s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->

---

Rendered from [`evals/scenarios/artifacts/dev/currency-cpu-throttle/`](../../evals/scenarios/artifacts/dev/currency-cpu-throttle/) by `faultline-render`. [All bundles](README.md).
