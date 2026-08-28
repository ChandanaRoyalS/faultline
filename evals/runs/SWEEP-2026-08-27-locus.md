# Dev sweep 5 — 2026-08-27, the return-to-locus instruction

The refined formulation T4.12's regressions decomposed, pre-registered in
[`PREREGISTRATION-2026-08-27-locus.md`](PREREGISTRATION-2026-08-27-locus.md) and committed
before any scenario ran.

**Result in one line: every registered condition met. Coverage 7/7, fault class 7/7, and the
primary endpoint moved in the registered direction on every scenario. The stamp is kept.**

Run before T7.1 because both baselines were measured against the current world and neither
survives a re-record.

| | dev sweep 3 | dev sweep 4 | **dev sweep 5** |
|---|---|---|---|
| stamp | `53fafe9c12bc` | `bf7605651ef2` *(rejected)* | **`1b0e7cbb4c47`** |
| instruction | none | silence → switch vantage | **silence → switch class, keep the subject** |
| budget | `changes` 8, others 4 | identical | identical |
| cost | $3.6889 | $3.5689 | **$3.8326** |
| judge cost | $0.2808 | $0.2942 | **$0.2571** |

Both baselines are live comparisons: S3 is this agent with no silence instruction, S4 is it with
the rejected one. Same world, same harness, same protocol, same budget. Holdout untouched.

## The three sweeps, per scenario

| scenario | S3 | S4 | **S5** | dispatches at the failing service, S3 → S4 → S5 |
|---|---|---|---|---|
| ad-memory-squeeze | `resource_exhaustion` ✔ | `resource_exhaustion` ✔ | **`resource_exhaustion` ✔** | 2 → 2 → **3** |
| cart-bad-image-tag | `bad_deploy` ✔ | **ABST** | **`bad_deploy` ✔** | 3 → **0** → **3** |
| cart-dependency-latency | `dependency_latency` ✔ | `dependency_latency` ✔ | **`dependency_latency` ✔** | 3 → 5 → **4** |
| cart-redis-misconfig | `bad_config` ✔ | **ABST** | **`bad_config` ✔** | 4 → **1** → **3** |
| frauddetection-memory-squeeze | `resource_exhaustion` ✔ | `resource_exhaustion` ✔ | **`resource_exhaustion` ✔** | 4 → 4 → **5** |
| product-catalog-flag-failure | **ABST** | `bad_config` ✔ | **`bad_config` ✔** | 6 → 3 → **5** |
| shipping-wrong-image | `bad_deploy` ✔ | **ABST** | **`bad_deploy` ✔** | 3 → **0** → **3** |

| | S3 | S4 | **S5** |
|---|---|---|---|
| **coverage** | 6 / 7 | 4 / 7 | **7 / 7** |
| fault class, of answered | 6 / 6 | 4 / 4 | **7 / 7** |
| class of fix, of answered | 5 / 6 | 3 / 4 | **6 / 7** |
| **failing-service dispatches, total** | 25 | 15 | **26** |
| **scenarios collapsed to ≤ 1 there** | 0 | **3** | **0** |
| distinct evidence classes at the failing service | 20 | 17 | **25** |
| judge `same_mechanism` | 6 / 6 | 4 / 4 | **6 / 7** |
| re-issues after silence | 4, in 3 runs | 2, in 2 runs | **2, in 2 runs** |
| runs exhausting a bound | 2 | 1 | **0** |
| tool calls, total | 58 | 50 | **47** |
| triage recall / precision | ~~0.91 / 0.54~~ **0.92 / 0.58** | ~~0.92 / 0.56~~ **0.92 / 0.59** | ~~0.90 / 0.54~~ **0.91 / 0.57** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_

| per fault class | n | S3 answered | S4 answered | **S5 answered** |
|---|---|---|---|---|
| `bad_config` | 2 | 1 / 1 | 1 / 1 | **2 / 2** |
| `bad_deploy` | 2 | 2 / 2 | 0 / 0 | **2 / 2** |
| `dependency_latency` | 1 | 1 / 1 | 1 / 1 | **1 / 1** |
| `resource_exhaustion` | 2 | 2 / 2 | 2 / 2 | **2 / 2** |

**S5 is the first sweep in this repository where every dev scenario was answered and every
answer was right.** It is also the cheapest in tool calls — 47 against S3's 58 — so this is not
"dispatch more and hope."

## The prediction ledger

| # | registered before the run | outcome |
|---|---|---|
| 1 | **Primary endpoint: no scenario's failing-service dispatch count collapses to 0 or 1** | **MET.** Zero collapses, against three in S4. The count rose on five of seven scenarios and the total went 15 → 26. |
| 2 | **Floor: coverage ≥ 6/7, accuracy-of-answered 100%** | **MET, and exceeded.** 7/7 coverage, 7/7 correct. |
| 3 | `product-catalog-flag-failure` **flips or holds S4's gain** | **MET.** `bad_config`, correct, `config_revert` correct, judge `same_mechanism`. |
| 4 | **The three S4 regressions must not recur** | **MET.** `cart-bad-image-tag`, `cart-redis-misconfig` and `shipping-wrong-image` all answered correctly, all with 3 dispatches at the failing service. |
| 5 | **Improvement on *both* baselines** | **MET.** Above S3's coverage *and* holding S4's gain — the condition T4.12 failed. |
| 6 | Secondary: re-issues ≤ S4's 2 in 2 runs | **MET, not eliminated.** 2 in 2 runs. One is `product-catalog-flag-failure` re-asking a silent change-history stream at its target; the instruction says not to and it did once. |

### The falsifiers, and why none fired

**Falsifier 4 was the one registered as most likely to be misread as a win**: coverage rising with
the failing-service dispatch counts unmoved, which would mean coverage moved for reasons unrelated
to the instruction — one draw from a spread T4.10 measured at 2.6×.

It did not fire, and the margin is not marginal. The counts moved on **five of seven** scenarios,
the total rose **73%** (15 → 26), and the two S4 regressions that had collapsed to zero both
returned to three. The registered endpoint and the outcome moved together on the same rows.

The sharper evidence is **distinct evidence classes at the failing service**, which is the second
half of the instruction stated as a number: 20 → 17 → **25**. Four scenarios reached one more
class at their target than they ever had before.

## Two trajectories that show the mechanism

**`cart-redis-misconfig`** — S4 spent one dispatch at `cartservice` and abstained; S3 spent four.

| dispatch | result |
|---|---|
| `change_history` @ `checkoutservice` | **empty** |
| *(not re-asked)* | S3 and S4 both re-issued a silent stream somewhere in this sweep |
| `promql`, `logql` @ `checkoutservice`, `promql`/`trace` @ `frontend` | the vantage half |
| **`change_history` @ `cartservice`** | **the config change — the answer** |
| `promql_query` @ `cartservice` | **empty** |
| **`logql_query` @ `cartservice`** | *different tool, same service* — the instruction, exactly |

**`product-catalog-flag-failure`** — the reachability case, and it exhausted **all four** evidence
classes at its target: `change_history` (empty), `promql`, `logql` (empty), and `trace_query`.
T4.11's five repeats never called `trace_query` on this scenario at all. It also re-asked
`change_history` at the target once, which is the one place this sweep disobeys its own
instruction.

## What did not improve

- **Triage was flat** — recall 0.91 → 0.90, precision 0.54 → 0.54. That is the control: the
  instruction changed how dispatches are spent, not what the blast radius looks like.
- **One judge disagreement.** `cart-bad-image-tag` returned the correct class and correct fix, and
  the judge scored its narrative `different` with 2 dead ends closed against 4 missed — its
  weakest row in any sweep. A right answer with a narrative the judge does not follow is worth
  saying out loud rather than rounding to a win.
- **Class of fix is 6/7, not 7/7.** `cart-dependency-latency` returned `config_revert` where the
  truth is a network-path fix — the same miss it has made in every sweep, unmoved by this stamp.
- **Cost rose** to $3.83, the highest of the three, on 47 tool calls rather than more.

## The decision, as registered

**The stamp is kept.** `faultline/0.0.1+prompts:1b0e7cbb4c47` is HEAD. The pre-registration fixed
this rule before the run: the record merges either way, the stamp stays only if it earned it
against the registered conditions, and reverts in the same PR if it did not. All six conditions
were met, so it stays — and had any failed, this section would read the other way with the same
files committed.

**Total cost: $3.8326 agent + $0.2571 judge = $4.0897.**

## What this sweep cannot show

n = 1 per scenario. T4.10 measured a 2.6× breadth spread on one scenario and T5.3's demo produced
a 1-in-7 abstention on a scenario with a 6/6 record, so no single per-scenario flip here is a
settled effect. What is stronger than any one row is the direction: seven scenarios moved the same
way on the registered endpoint, and the three that had collapsed under S4 all recovered.

Holdout is untouched and these figures say nothing about it. **The holdout numbers in
`docs/RESULTS.md` were measured under `53fafe9c12bc` and now describe a superseded pipeline again**
— ADR-0023's reporting obligation, discharged there.
