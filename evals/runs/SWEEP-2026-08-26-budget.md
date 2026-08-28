# Dev sweep 3 — 2026-08-26, the `changes` bound raised

The manipulation that separates the confound
[HOLDOUT-2026-08-26.md](HOLDOUT-2026-08-26.md) left open: on holdout, abstention lined up exactly
with `changes`-budget exhaustion; on dev it did not. **Same stamp, same harness, same protocol —
one bound moved.**

| | dev sweep 2 | **dev sweep 3** |
|---|---|---|
| stamp | `prompts:53fafe9c12bc` | `prompts:53fafe9c12bc` — **identical** |
| `max_tool_calls_per_specialist` | 4 | 4 |
| **`per_specialist_tool_calls`** | — | **`{"changes": 8}`** |
| max tokens / wall clock / rounds | 120k / 600s / 2 | 120k / 600s / 2 |
| cost | $3.2676 · 305,145 tokens | **$3.6889 · 328,633 tokens** |
| judge cost | $0.2575 | **$0.2808** |

## Why 8, and why only `changes`

Read out of the stored trajectories of every budget-exhausted run in the record. All four
exhausted the **same** bound, and the pattern is identical:

| exhausted run | `changes` dispatches planned | target service's position | ran? |
|---|---|---|---|
| ad-memory-squeeze (S1, S2) | 6 | `adservice` = #5 | **no** |
| recommendation-memory-squeeze (holdout) | 6 | `recommendationservice` = #6 | **no** |
| email-wrong-image (holdout) | 5 | `emailservice` = #5 | **no** |
| cart-redis-misconfig (S2) | 4, + a 5th wanted in round 2 | `cartservice` = #4 | yes → answered |

**T3.4c made a dispatch name exactly one service** — correctly, because a comma-separated list
produced a PromQL selector that could not match anything. That multiplied the planner's
change-history needs by the size of the blast radius, and nobody moved the bound, which had been
set for a planner that could ask about several services in one dispatch.

The largest observed plan asked for **6**. `cart-redis-misconfig` wanted a seventh across two
rounds. **8** covers the largest plan plus a follow-up round's worth, and the dispatch-round bound
of 2 remains the structural governor. Only `changes` moved: raising every bound would change two
things and measure neither.

## The comparison, per scenario

| scenario | **S2** fault | S2 exhausted on | **S3** fault | S3 exhausted on | reading |
|---|---|---|---|---|---|
| ad-memory-squeeze | `unknown` **ABST** | **`changes` 4/4** | **`resource_exhaustion` ✔** | `metrics` 4/4 | **budget owned it** |
| cart-bad-image-tag | `bad_deploy` ✔ | — | `bad_deploy` ✔ | — | stable |
| cart-dependency-latency | `dependency_latency` ✔ | — | `dependency_latency` ✔ | `metrics` 4/4 | stable |
| cart-redis-misconfig | `bad_config` ✔ | **`changes` 4/4** | `bad_config` ✔ | — | stable; starvation removed |
| frauddetection-memory-squeeze | `resource_exhaustion` ✔ | — | `resource_exhaustion` ✔ | — | stable |
| product-catalog-flag-failure | `unknown` **ABST** | — | `unknown` **ABST** | — | **instruction owns it** |
| shipping-wrong-image | `unknown` **ABST** | — | `bad_deploy` ✔ | — | **neither — variance** |

| | S2 | S3 |
|---|---|---|
| fault class, of answered | 4 / 4 | **6 / 6** |
| **coverage** | 4 / 7 | **6 / 7** |
| class of fix, of answered | 3 / 4 | **5 / 6** |
| runs exhausting `changes` | **2** | **0** |
| runs exhausting anything | 2 | 2 (both `metrics`) |
| judge same_mechanism / different | 4 / 3 | **6 / 1** |
| triage recall / precision | ~~0.95 / 0.57~~ **0.95 / 0.60** | ~~0.91 / 0.54~~ **0.92 / 0.58** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_

| per fault class | n | S2 fault / answered | S3 fault / answered | S3 abstained |
|---|---|---|---|---|
| `bad_config` | 2 | 1 / 1 | 1 / 1 | 1 |
| `bad_deploy` | 2 | 1 / 1 | **2 / 2** | 0 |
| `dependency_latency` | 1 | 1 / 1 | 1 / 1 | 0 |
| `resource_exhaustion` | 2 | 1 / 1 | **2 / 2** | 0 |

## The answer: mixed, and it decomposes

The task set three outcomes in advance. **All three occurred, one per scenario**, which is why
"mixed" here is a finding rather than a shrug.

**1. Budget owned one.** `ad-memory-squeeze` abstained in S2 while exhausted on `changes`, and
answered **correctly** in S3 with the bound raised. Its S2 verdict said so in its own words —
"with no observation of the failing mechanism … assigning a fault class here would be invention"
— and in S2 the dispatch that would have observed the mechanism was #5 of a plan cut off at 4.
**The taxonomy instruction was innocent for this one; the planner was starved.**

**2. The instruction owns one.** `product-catalog-flag-failure` abstained in S2 **and** S3, and
was **not exhausted on any bound in either run**. It had budget to spare both times and declined
anyway. Whatever is happening there is not starvation.

**3. One is neither.** `shipping-wrong-image` abstained in S2 and answered correctly in S3, and
was **not exhausted in either run**. The bound it never hit cannot explain the flip. That leaves
run-to-run variance, or the planner allocating differently when it knows it has more room — and
at n=1 per side those are indistinguishable.

**Starvation was real and is now gone: zero runs exhausted `changes` in S3, against two in S2.**
Coverage rose 4/7 → 6/7 and accuracy-of-answered held at 100%. But the bound simply moved to the
next binding constraint: two S3 runs exhausted **`metrics` 4/4**, and both still answered.

## First variance data, at n=2

Four scenarios answered in both sweeps, and **all four returned the identical class both times** —
`bad_deploy`, `dependency_latency`, `bad_config`, `resource_exhaustion`. **Zero flips among the
four.**

The one flip across all seven is `shipping-wrong-image`, abstain → correct.

**This is not clean repeat variance.** The two sweeps differ in one bound, so a scenario that
answered in both was not run twice under identical conditions. What can be said: under the same
prompts and contracts, with `changes` raised from 4 to 8, **no scenario that produced a class
produced a different class.** That is the first repeat observation this project has, and it is
one observation.

## Reported separately

| category | S2 | S3 |
|---|---|---|
| flagged (other) | 0 | 0 |
| specialists failed alone | 0 | 0 |
| contradiction firings | 0 | 0 (retired) |
| budget exhausted | 2 (`changes`) | 2 (`metrics`) |
| narrative refused | 0 | 0 |

## Discards

| run | scenario | reason | outcome |
|---|---|---|---|
| `20260826T182222Z` | cart-redis-misconfig | no incident reached 2 episodes in 900s | re-run `20260826T185202Z` |

**The cause was an operator action, not the product.** A stranded incident was resolved by hand
minutes before the sweep started, which left it **inside the orchestrator's 5-minute settle
window**. The next scenario's first firing alert correlated into that recently-resolved incident
and reopened it — into `OPEN`, since a hand-resolve sets no `state_before_resolution` — and every
subsequent alert joined it. Twenty-two events, one incident, none of them in `triaging`, so the
harness waited 900s for an incident that would never appear.

**The gap this exposes is real and is recorded, not fixed here.** The baseline gate refuses on
*non-terminal* incidents. A **recently-resolved** incident inside the settle window is invisible
to the gate and can capture a new run's alerts just as effectively. The sweep was restarted after
waiting the settle window out; the restarted run is the one in the table.

## Protocol

Gate before every injection · one driver · revert and confirmed recovery between scenarios ·
discard recorded and the sweep continued · same judge configuration and lineage label as dev
sweeps 1 and 2 · **holdout untouched.**
