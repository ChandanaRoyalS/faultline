# Pre-registration — dev sweep 7, the benchmark re-founded again

**Written and committed before any scenario ran.**

## What this is, and what it is not

T7.28 moved the world and re-recorded every runnable bundle against it. **`compose_digest` moved
`299d791c5e0da43e…` → `f5bd108f4f70f460…`** and `observability_digest` `3d061a2793b1cd57…` →
`857d95b4d174ec43…`. Every published figure in this repository was measured before that move, and
carries a banner saying so. **The bounded world has no measurement at all.**

This repeats T7.10's shape after T7.1: the world moved, so the benchmark is re-founded on the world
that exists.

**This is not an experiment on the agent.** The stamp is unchanged at
`faultline/0.0.1+prompts:1b0e7cbb4c47` and the budget is unchanged at T4.7's — `changes` 8, others
4, 120k tokens, 600s, 2 rounds. **What moved is the world, and three specific things moved in it:**

| # | change | where |
|---|---|---|
| 1 | `MALLOC_ARENA_MAX=2` — glibc per-thread arenas capped | kafka |
| 2 | `maxmemory 12mb`, `maxmemory-policy allkeys-lru` — evicting rather than growing | redis-cart |
| 3 | `memory_limiter` (limit 450 MiB, spike 100), first in both pipelines | otel-col |

So the registered question is not "is the agent better" — nothing about the agent is different —
but:

> **What did the world change do to the results?**

S6 and this sweep are **not the same experiment**, and every comparison between them crosses a
world boundary. Any difference is attributable to the world, to run-to-run variance, or to both,
and this sweep cannot separate those two from each other. n = 1 per scenario on each side.

## How many scenarios are runnable: eight, not seven

The catalog changed, so the count is stated rather than assumed.

| | count | |
|---|---:|---|
| dev scenarios authored | 11 | |
| — with a recorded bundle | 10 | `ad-dependency-latency` has none |
| — bundle at the current `compose_digest f5bd108f…` | **8** | the sweep set |

**The three that are not runnable, and why — none of it new:**

- **`ad-dependency-latency`** — disqualified on measurement at T7.22. A leaf service has nowhere to
  put the delay; never recorded.
- **`currency-cpu-throttle`** and **`flag-service-crashloop`** — each carries an `INVALID.md` and an
  empty `alerts_over_window`. This is long-standing (PLAN.md records it at T7.1's re-record, "only
  ten of the twelve bundles are runnable"), **not** a T7.28 blockage. Their bundles still sit at
  `299d791c…` because T7.28 correctly declined to re-record something invalid.

**The eighth scenario is `shipping-quote-misconfig`**, which did not exist when S6 ran. T7.22
recorded it and T7.24 ran it once, outside any sweep, at this same stamp. It enters a sweep here for
the first time.

## The prediction: verdicts hold

The faults are the same faults; the world's three changes are memory and eviction bounds, not
changes to what any fault does. **Registered: all eight scenarios return the fault class they last
returned**, and coverage is **7/8 or better**.

| scenario | last returned | where |
|---|---|---|
| `ad-memory-squeeze` | `resource_exhaustion` ✔ | S6 |
| `cart-bad-image-tag` | `bad_deploy` ✔ | S6 |
| `cart-dependency-latency` | `dependency_latency` ✔ | S6 |
| `cart-redis-misconfig` | `bad_config` ✔ | S6 |
| `frauddetection-memory-squeeze` | `resource_exhaustion` ✔ | **S5** — S6 discarded it, and T7.11 established the discard was the host suspending, not the scenario |
| `product-catalog-flag-failure` | `bad_config` ✔ | S6 |
| `shipping-wrong-image` | **`unknown` ABSTAINED** | S6 — `bad_deploy` ✔ in S5 |
| `shipping-quote-misconfig` | `bad_config` ✔ | T7.24, n=1 |

**Two of these are registered as unsettled rather than predicted.** `shipping-wrong-image` abstained
in S6 for a reason S6 attributed to planner allocation, not the world; either outcome here is
consistent with that and neither confirms it. `frauddetection-memory-squeeze` has not completed a
sweep run since S5.

## What would surprise me, and where

### The four dev scenarios whose alert composition T7.28's reconciliation changed

Named from the stage-3 corrections table, not guessed. T7.28 corrected seven narratives; two are
holdout and one (`ad-memory-squeeze`, restart timing 18s → 3s) is not an alert-composition change.
**These four are:**

| scenario | what stage 3 found | expected effect on triage |
|---|---|---|
| `cart-dependency-latency` | narrative said the page named **two** services with frontend joining later; frontend was **at fire** — three at fire, checkoutservice at +15s | denominator grows; recall should hold, precision may move |
| `cart-redis-misconfig` | said the page named **one**; frontend was at fire — **two at fire**, checkoutservice at +15s | a wider page than the narrative described |
| `product-catalog-flag-failure` | said **three** services alerted and that a **fourth alert fired after the fix**; four services, and **the recovery-alert claim removed** — the new recording has no after-revert alert at all | T7.3's blast-radius exclusion has nothing to exclude here now |
| `shipping-quote-misconfig` | said **nothing else alerted**; **seven alerts across seven services**, the `ServiceNoTraffic` cascade | the largest change in the set; T7.24's triage precision of 0.17 (2/12) was measured against the *old* capture |

**Triage movement on these four is expected and traces to the capture, not to the agent.** Saying so
in advance is the point: it is arithmetic over a changed `alerts_over_window`, and reporting it as a
world effect would be wrong.

### The controls

**`cart-bad-image-tag`, `frauddetection-memory-squeeze` and `shipping-wrong-image` had no narrative
correction at all**, and `ad-memory-squeeze`'s was a restart timestamp rather than an alert. Those
four are the closest thing to a control: same fault, same alert composition, same agent. **Triage
movement there is run-to-run variance and will be reported as such.**

### These would surprise me

1. **Any fault class changing.** The world moved; the faults did not. A different class means either
   the re-record changed what a fault *does* — which stage 3's reconciliation should have caught —
   or the agent is less stable than six sweeps suggest.
2. **`shipping-quote-misconfig` abstaining or missing.** Its capture changed most, and it is the one
   scenario here with a single prior observation. An abstention would say T7.24's result was fragile
   to a capture difference rather than a property of the scenario.
3. **A triage change on one of the four controls.** Same fault, same alert set, same agent.
4. **Coverage below 7/8**, or **any run exhausting a bound**. Six sweeps have never exhausted one.
5. **A gate refusal traceable to the new bounds** — redis-cart evicting under `allkeys-lru` or the
   collector's `memory_limiter` dropping data — rather than to the known checkout stall.

**The falsifier for the headline claim** — "the verdicts hold across the world change" — is any
scenario returning a different fault class, or coverage below 7/8.

## The S6 rescore, registered in advance

T7.10 caught a confound where S5's stored figures had been computed by a pre-T7.3 scorer, so
comparing them to S6 would have credited the world with a scorer fix. **The same thing has happened
again.**

`src/evalharness/scoring.py` last changed at **T7.17 (2026-08-29 00:38)**. S6's runs are stamped
`20260828T072535Z` through `20260828T154652Z` — **all of them before that commit.** T7.17 added
`also_correct` / `correct_by_alternative`, and `cart-dependency-latency` carries
`also_correct_remediation: [config_revert]`.

**Registered expectation: rescoring S6 under the current scorer moves `cart-dependency-latency`'s
fix class from wrong to correct, taking S6's "class of fix, of answered" from 4/5 to 5/5.** If that
happens, the S6 column printed in this sweep's comparison is the rescored one, and the raw stored
figure is not compared to anything.

## The kafka observation, and a correction to its premise

T7.27 established that kafka's growth is glibc arena retention, not a JVM leak, and queued a
re-measure: **`MALLOC_ARENA_MAX=2` was shown to engage — 68 arena regions → 0 — but was explicitly
not shown to bound long-run growth**, which needs ~24h of uptime under the setting.

**The premise that it has been live for a day or more does not hold, and the measurement is
registered accordingly.** The container's memory is a property of the current process lifetime, and
a restart clears all of it:

```
kafka started      2026-08-29T22:12:26Z
sweep starts       2026-08-30T03:05Z      → uptime ~4h53m
```

So this is a **~5h → ~8h observation, not a 24h one.** It is recorded at the start of the sweep and
again at the end, passively, alongside the runs — no injection, no separate task.

**What it can settle:** whether the lever is still engaged after hours of uptime (arena regions
still 0), and the growth rate under the setting.

**What it cannot settle:** whether the setting bounds long-run growth. That question needs 24h and
this does not reach it. It will be reported as unsettled rather than answered.

**Start-of-sweep reading, for the record:**

| | value |
|---|---|
| uptime | ~4h53m |
| container | **1.399 GiB / 2 GiB — 69.95%** |
| cgroup `anon` | 1,462,681,600 |
| **64 MB arena regions** | **0** — the lever is still engaged |
| total mapped anon | 3,134 MB |

**A risk this creates, registered now:** the recorder's headroom guard refuses at 90%, and kafka is
at 69.95% before the sweep starts. If it crosses 90% mid-sweep the guard is doing its job, and any
resulting refusal is a world-state discard, not a scenario failure.

## Protocol

Full protocol per ADR-0022 §3, unchanged: **baseline gate before every injection**, inject,
correlate, investigate, revert, confirm recovery, score, judge. **Discard-and-continue** — a
discarded run is recorded with its reason and the sweep proceeds.

**T7.28's checkout policy is carried forward:** recycle `checkoutservice` at the **end** of each
scenario, so its 300s uptime requirement elapses during the inter-scenario settle. T7.23 measured
the stall taking hold in ~12 minutes, so waiting for a gate refusal and then applying ADR-0025's
remedy would cost a refused attempt, a restart and a 300s wait on most of eight scenarios.
`accountingservice` is checked before the first injection rather than discovered mid-sweep (T7.27).

## What this sweep cannot show

n = 1 per scenario. T4.10 measured a 2.6× breadth spread on a single scenario and T5.3's demo
produced a 1-in-7 abstention on a scenario with a 6/6 record, so **a single per-scenario difference
is not separable from variance.** What this can establish is whether the benchmark still stands up
on the bounded world, not a measurement of the world change's size.

**Holdout is not re-entered.** That is a separate decision needing its own argument under ADR-0022's
protocol, and the T4.15 addendum already records that the set should not be entered a fourth time
before it is re-authored or extended. Nothing here licenses one.
