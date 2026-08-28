# Dev sweep 6 — 2026-08-28, the benchmark re-founded on the world that exists

Pre-registered in [`PREREGISTRATION-2026-08-28-refound.md`](PREREGISTRATION-2026-08-28-refound.md),
committed before any scenario ran.

## S5 and S6 are not the same experiment

**They differ in the world, and only in the world.** The stamp is identical, the budget is
identical, the harness is identical. T7.1 moved `world.compose_digest` from `4a7690c6fdda…` to
`299d791c5e0d…` and re-recorded all twelve bundles against the result.

**Every comparison below crosses a world boundary.** It is not a comparison of agents — the agent
is byte-identical — and it cannot separate the world's effect from run-to-run variance, because
n = 1 per scenario on each side. Read it as *"does the benchmark still stand up on the world that
exists"*, never as *"the agent got better or worse"*.

| | dev sweep 5 (old world) | **dev sweep 6 (new world)** |
|---|---|---|
| stamp | `1b0e7cbb4c47` | **identical** |
| budget | `changes` 8, others 4, 120k, 600s, 2 rounds | **identical** |
| world | `4a7690c6fdda…` | **`299d791c5e0d…`** |
| scenarios scored | 7 | **6** (one discard) |
| cost | $3.8326 + $0.2808 judge | **$3.3650 + $0.2229 judge** |

## The two tables

| scenario | S5 — old world | **S6 — new world** | dispatches at the failing service | judge |
|---|---|---|---|---|
| ad-memory-squeeze | `resource_exhaustion` ✔ | **`resource_exhaustion` ✔** | 3 → 3 | same → same |
| cart-bad-image-tag | `bad_deploy` ✔ | **`bad_deploy` ✔** | 3 → 3 | different → **same** |
| cart-dependency-latency | `dependency_latency` ✔ | **`dependency_latency` ✔** | 4 → 4 | same → same |
| cart-redis-misconfig | `bad_config` ✔ | **`bad_config` ✔** | 3 → 3 | same → same |
| frauddetection-memory-squeeze | `resource_exhaustion` ✔ | **DISCARD** — no incident in 900s | 5 → — | same → — |
| product-catalog-flag-failure | `bad_config` ✔ | **`bad_config` ✔** | 5 → 6 | same → same |
| shipping-wrong-image | `bad_deploy` ✔ | **`unknown` ABSTAINED** | 3 → **0** | same → **different** |

| | S5 (old world) | **S6 (new world)** |
|---|---|---|
| scenarios scored | 7 | **6** |
| coverage | 7 / 7 | **5 / 6** |
| fault class, of answered | 7 / 7 | **5 / 5** |
| class of fix, of answered | 6 / 7 | **4 / 5** |
| judge `same_mechanism` | 6 / 7 | **5 / 6** |
| runs exhausting a bound | 0 | **0** |
| tool calls, total | 47 | **43** |

## The prediction failed, in two places

Registered: *all seven fault classes come back as S5 returned them, coverage 7/7*.

**No fault class changed** — every scenario that produced a class produced the same one, and every
one was correct. What failed is that two scenarios did not produce a comparable result at all.

## Movement 1: `shipping-wrong-image` abstained — **not traceable to the capture**

This is the scenario whose alert set changed most in the re-record (10 alerts → 8; frontend and
loadgenerator now alert **last** at T+6m30s rather than second), so the pre-registration flagged it
as the likeliest to move for capture reasons. **It moved, and the capture is not why.**

| | S5 | S6 |
|---|---|---|
| tool calls | 7 | 7 |
| services touched | `checkoutservice`, **`shippingservice`** | `checkoutservice`, **`cartservice`** |
| dispatches at `shippingservice` | **3** | **0** |
| verdict | `bad_deploy` ✔ | `unknown` |

Same budget, same number of calls. The difference is **which second service the planner chose** —
and `shippingservice` was in the blast radius both times, so nothing about the new capture removed
it from view. This is the failing-service dispatch collapse T4.12 identified as the predictor of
exactly this outcome, occurring here at n = 1. The verdict says so itself:

> "no dispatch touched shippingservice's logs, metrics, or change history at all… The failing
> component is localized with high confidence; the failing mechanism is not, and I decline to
> infer one from the shape of the error alone."

**Attribution: planner allocation, not the world.** T4.9 and T4.10 measured allocation as the least
stable thing in this system, and this is consistent with that rather than with the world change.

## Movement 2: `frauddetection-memory-squeeze` discarded — **possibly the world**

No incident reached one episode within **900s**. The baseline gate passed cleanly beforehand (15
services reporting, only `frontend-proxy` silent) and the fault injected, so this is a genuine
no-alert rather than a dirty world.

**It is outside anything previously recorded.** This scenario's onset has been measured at 469s
(old world) and 390s (new world), and its narrative already calls it the least stable figure in
the catalog — but 900s is well beyond both. It is also one of the three scenarios whose alert set
did **not** change, which the pre-registration named as the closest thing to a control.

**A mechanism exists and is not established.** T7.1 capped kafka's JVM heap at 400m, and
`frauddetectionservice` is a Kafka consumer whose alert is `ServiceNoTraffic` — a rule that fires
on a rate window emptying. A change to Kafka throughput would change when that window empties.
**That is a hypothesis with a plausible path, not a measurement**, and separating it from the
scenario's known instability needs repeats this sweep does not have.

## What did not move, which is the substantive result

**Five of six scenarios returned the same class, correctly, with the same dispatch count at the
failing service.** On triage the agreement is stronger still — but reading it requires removing a
confound first.

**The stored S5 triage figures were computed by a different scorer.** T7.3 fixed the blast-radius
exclusion to work per alert episode after S5 ran, so S5's manifests carry the old per-service
numbers and S6's carry the fixed ones. Comparing them directly would credit the world with a
scorer fix. Rescoring S5 under the current scorer, against its own old-world bundles:

| scenario | S5 rescored (old world) | S6 (new world) |
|---|---|---|
| ad-memory-squeeze | 1.00 / 0.43 | **1.00 / 0.43** |
| cart-bad-image-tag | 0.80 / 0.67 | **0.80 / 0.67** |
| cart-dependency-latency | 1.00 / 0.33 | **1.00 / 0.33** |
| cart-redis-misconfig | 0.80 / 0.67 | **0.80 / 0.67** |
| product-catalog-flag-failure | 1.00 / 0.43 | **1.00 / 0.43** |
| shipping-wrong-image | 0.75 / 0.50 | 0.75 / 0.60 |

**Five of six are identical to two decimal places.** The only triage movement is on the scenario
that abstained, and it is an artefact of that run predicting a smaller radius. **The world change
had no measurable effect on triage**, and the apparent improvement in the raw stored figures
(precision 0.54 → 0.57) is entirely T7.3's scorer fix.

## Cost

**$3.3650 agent + $0.2229 judge = $3.5879** for the six scored runs.

Two discards, neither re-run. `frauddetection-memory-squeeze` spent nothing — no model call was
made, because no incident ever formed. The earlier `ad-memory-squeeze` attempt died inside
`save()` on T7.9's missing column migration; **model calls were made and their cost is
unrecoverable**, because the write that failed is the one that would have recorded them. It is not
estimated here.

## What this sweep establishes, and what it does not

**Establishes:** the benchmark stands on the world that exists. Every scenario that produced a
verdict produced the same verdict as on the old world, and triage is unchanged on every scenario
that ran to completion.

**Does not establish:** the size of the world change's effect, or that either movement was caused
by it. n = 1 per scenario on each side, and T4.10 measured a 2.6× breadth spread on a single
scenario. One of the two movements traces to a known agent-side instability; the other has a
plausible world-side mechanism that this sweep cannot test.

**Holdout was not re-entered**, and nothing here licenses it.
