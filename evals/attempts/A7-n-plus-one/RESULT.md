# A7 — N+1 regression in `product-catalog`, as a built image — RESULT

**Run 2026-09-23 05:46:16 → 06:08:12 UTC, \$0.** One run, `transcript.txt`. The image was built once
from the clone at 2.2.0 with `product-catalog-n-plus-one.patch` applied and reverted after the
build. The verdicts are the pre-registered definitions applied to the transcript and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **no** | Twenty-four quiet polls, 05:46:18–05:57:48; nothing reached `pending`. At minute twelve `product-catalog` read **0.00 % errors, p95 2 ms, 54.3 req/s** — against 9 ms and 5.8 req/s before |
| **DISTINCT** | not applicable | `BadDeployFault`'s mechanism by definition, as registered |
| **REVERTS** | **yes** | Recreated with the shipped image at 05:58:40; quiet throughout the ten minutes — **the first recreate on the fixed pipeline, and the rules saw it from the first flush and did not fire on the revert.** A6's defect is closed by measurement |
| **ADMISSIBLE** | **no** | Same mechanism as `bad_deploy`; cannot be a class. **And it does not page, so it is not a scenario either, as built** |

**Prediction scorecard.** PAGES: **wrong** — *"`ServiceHighLatency/product-catalog` within 8 min,
confidence high"*. It neither slowed on the rule's instrument nor errored under the 20 MB limit.
The registered fallback (*"if it errors rather than slows … the multiplier is not tuned to fix it
in this registration"*) does not apply; what happened is a third thing, and it is the finding.

## The regression ran, and it made the service look *faster*

The image was the patched one: `product-catalog`'s call rate went from 5.8 to **54.3 req/s**. That
is the N+1 itself — `getProductFromDB` goes through `otelsql`, so **each of the thirty re-reads per
product is a `CLIENT` span of its own**, ~48 extra spans a second at roughly a millisecond each.
And the rule's instrument is the p95 of *every non-internal span the service emits*:

```
histogram_quantile(0.95, sum by (service_name, le)
  (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m]))) > 250
```

Before the fault, that population was the service's `SERVER` spans and a handful of DB calls, p95
9 ms. During it, **nine of every ten spans were the regression's own one-millisecond DB reads**,
and the p95 fell to **2 ms**. The one span that got slow — the `ListProducts` `SERVER` span, now
carrying ~300 sequential queries — is 0.3 % of the population and cannot reach a 95th percentile
from there. **The N+1 regression diluted the instrument that was supposed to catch it, with the
spans it added.** Its callers felt it, faintly: `frontend-proxy` 46 → 57 ms, `load-generator`
47 → 61 ms, `frontend` 44 → 48 — the homepage is one call in thirty of the frontend's traffic and
a ~300 ms homepage moves its p95 by a few milliseconds.

A larger multiplier would not change this. It would make `ListProducts` slower *and* add more
cheap spans in the same proportion; the p95 of the mixture stays at the cheap spans' duration
until the server span is more than 5 % of the population, which an N+1 by construction never is.
**On this rule, an N+1 is invisible at any size.** That is a property of aggregating a service's
server and client spans into one histogram, and it is the same dilution A1 and A4b measured on
the error ratio, now on latency, and now caused by the fault itself.

## What it means

- **For the rules — Q90.** `ServiceHighLatency` mixes span kinds. Restricting it to
  `span_kind="SPAN_KIND_SERVER"` (what callers experience) would have put `product-catalog`'s p95
  where `ListProducts` actually was. That is a rule change; ADR-0042/the registration reserve it
  for its own registration, and this attempt is the measurement that motivates it. Not decided here.
- **For the catalog.** As registered, A7 yields no `bad_deploy` scenario: a fault the rules cannot
  see is not a scenario until the rule can. If Q90 is taken, this image is the ready-made
  latency-shaped `bad_deploy`, and the attempt is re-run under the new rule with a new
  registration.
- **For A6's defect.** This was the first `compose up -d <service>` since #459. The recreated
  container's counters were live at the first flush (54.3 req/s, 0.00 %) and the revert's recreate
  tripped nothing: **the pipeline now survives a recreate.**

## Owed

**One `ListProducts` span from Tempo** during 05:46–05:58, to put a number on how slow the server
span actually was under the regression. It does not change the verdict; it turns "~300 ms" from
arithmetic into a reading, and Q90's registration will want it.

## Timeline

| clock (UTC) | event |
|---|---|
| 05:45 | image built (43.6 s); clone restored |
| 05:46:16 | `up -d product-catalog` with the N+1 image; container recreated |
| 05:46:18–05:57:48 | 24 polls, all quiet |
| 05:57:50 | shape captured: 54.3 req/s, p95 **2 ms** (was 9), 0.00 % |
| 05:58:40 | `up -d product-catalog` with the shipped image — **REVERTS** |
| 06:08:12 | recovery window ends, quiet throughout |

**Scoreboard**: eight classes measured; A7 inadmissible and, as built, not a scenario; **A8 remains**,
the last that can add a class.
