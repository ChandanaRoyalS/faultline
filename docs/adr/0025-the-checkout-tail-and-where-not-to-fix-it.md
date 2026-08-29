# ADR-0025: The checkout-path latency tail is real, and the rule stays as it is

- **Status:** accepted
- **Date:** 2026-08-29
- **Task:** T7.14 (the rule that fires at rest)
- **Corrects:** T7.13's characterisation; the second half of `evalharness.gate`'s founding reading
- **Relates to:** ADR-0012 (alert thresholds), ADR-0014 (what a digest covers), ADR-0022 §3.1

## Context

`ServiceHighLatency` fires on a world at rest and the baseline gate refuses on it. T7.13 reported
this as a **degenerate histogram** — p95 pinned at the `+Inf` bucket because a sparse service
contributes too few samples — and proposed a min-sample guard on the rule.

**That diagnosis was wrong.** This ADR records what is actually happening, because the proposed
fix would have suppressed a true signal and falsified two recorded bundles.

## The measurement

`checkoutservice` at rest, `sum by(le) (rate(latency_bucket[2m]))`, ~136 observations in the
window — not a sample-starved series:

| bucket | cumulative | observations in bucket |
|---|---:|---:|
| ≤ 50ms | 93.08% | — |
| ≤ 1000ms | 94.62% | ~2 |
| ≤ 5000ms | 96.92% | ~3 |
| ≤ 10000ms | 98.46% | ~2 |
| > 15000ms | 100.00% | ~2 |

93% of checkouts finish inside 50ms. The rest are **genuinely slow requests**, some over fifteen
seconds, and they are real observations in real buckets.

The tail sits within a percentage point of 5%, which is exactly where the 95th percentile reads.
So p95 lands either at ~38ms or in the thousands depending on which side of 5% the tail fell that
minute, and the gap between those two answers is three orders of magnitude because the buckets up
there are 1000 → 5000 → 10000 → 15000 → ∞.

Twelve hours at 15s resolution, world at rest:

| service | median p95 | samples > 250ms | samples > 1000ms | sustained ≥ 3m |
|---|---:|---:|---:|---|
| `checkoutservice` | **37.8ms** | 295 / 2398 (12.3%) | 264 (11.0%) | yes |
| `frontend` | **42.3ms** | 127 / 2398 (5.3%) | 94 (3.9%) | yes |
| `loadgenerator` | **48.0ms** | 158 / 2398 (6.6%) | 115 (4.8%) | yes |
| all eleven others | 1.9 – 9.7ms | **0** | **0** | no |

Three services, all on the checkout path, and nothing else. **Their medians are their committed
baseline** — `evals/baselines/20260824T033742Z` records checkout at mean 38ms / max 39ms and
frontend at 42ms. The baseline is intact; a tail lives beside it.

The excursions are **episodes, not flutter**: two in twelve hours, lasting **3630s and 900s** —
12.6% of wall clock. The first began at `2026-08-29T01:43:03Z`, which is the `activeAt` recorded
on the firing alert T7.13 observed.

Everything observed now follows: it fires at rest because the tail is genuinely over 5%; it
cleared under T7.13's 50x load because the fast-path volume grew and pushed the tail back under
5%; it returned when load dropped; and the 45-minute committed baseline was recorded during a
tail-under-5% stretch.

## Where this has been misread before

Twice, and both readings are still cited as evidence somewhere in the repository:

- **T3.4's smoke** — *"the world already degraded (checkoutservice and frontend pinned at 15000ms
  p95, accountingservice at 0.000 req/s)"*, quoted in `evalharness.gate`'s docstring as part of
  why the gate exists. The `accountingservice` half was a real fault. The p95 half was this.
- **T7.13** — called it a starved histogram and proposed a min-sample guard. There were 136–209
  samples. A min-sample guard would not have suppressed a single one of these firings.

## Decision

### The rule is not changed

`ServiceHighLatency` reports a true condition: p95 above 250ms for three continuous minutes. It is
right. Three further reasons not to touch it:

1. **It would falsify recorded bundles.** `cart-dependency-latency` and
   `productcatalog-dependency-latency` both record `ServiceHighLatency/checkoutservice` in
   `alerts_over_window` as genuine fault evidence — 9 latency-alert entries across the catalog,
   all from those two scenarios. De-sensitising or exempting checkout would make that ground truth
   unreproducible, which is exactly ADR-0014's bar for a change that makes existing bundles false.
2. **A rule that lies at rest would be worth fixing; this one does not lie.** The premise for
   changing it does not hold.
3. **`compose/prometheus/alert-rules.yml` is not digest-locked** — `compose_digest` covers
   `world/docker-compose.yml`, `world-arm64.override.yml` and `telemetry.yml` only. So the change
   would be *cheap*, and that is the problem rather than the reassurance: **an alert-rule change
   would silently alter every future bundle's alert set with no digest to show it.** ADR-0014
   exists because "a bundle recorded before that edit and one recorded after describe different
   worlds and said they described the same one" — and the alert rules are outside its cover. That
   gap is recorded here and queued; it is not fixed by this task.

### The gate is not softened either

It still refuses. Refusing is correct: injecting during an excursion would put a pre-existing
`ServiceHighLatency/checkoutservice` into the scenario's blast radius, which is precisely what the
gate is for. The cost is that roughly one attempt in eight is refused and must be retried, on a
world whose median is its baseline. That is a retry, not a wrong number.

**A robust statistic was tried and rejected on measurement.** Replacing the gate's last-sample
read with a median over its 180s window changes the refusal rate from 11.3% to 11.1% — the
excursions are sustained, so there is nothing for a median to smooth. It is not the fix.

### What is changed: the gate records the window it already had

`_latest_by_service` fetched 180 seconds of p95 and discarded eleven of twelve samples. The gate
refused four times before this and stored one scalar each time, so **no recorded refusal can say
whether the world spiked or had been slow for an hour** — diagnosing them for this ADR meant going
to the live world, by which time those windows were gone.

The gate now records a `p95_excursions` entry per offending service: samples over ceiling, samples
in window, whether it was sustained, median and max. And when the service is one of the three with
a measured tail, the refusal says so — that the reading is real, that it is a real reason to
refuse, and that it is not evidence the world is degraded. Naming is not exemption.

## Consequences

- A refusal is diagnosable from the manifest instead of requiring a live probe.
- `KNOWN_TAIL_SERVICES` is a measured set of three. A latency excursion anywhere else gets no
  note, because a slow `cartservice` is a finding.
- **Open, not settled by this ADR: why the checkout path has a multi-second slow mode at all.**
  ~1.5% of checkouts exceed fifteen seconds on an idle world. That is a property of the world
  worth understanding — it did not appear in the 2026-08-24 baseline, and the world changed at
  T7.1 — but the correlation is a correlation and the pre-change series no longer exists to test
  it against.
- **Queued: bring the alert rules under a digest.** Their content is load-bearing for every
  bundle's `alerts_over_window` and no manifest field would show a change to them.
