# Dev sweep 4 — 2026-08-27, the evidence-class instruction

The experiment T4.11 named, with its mechanism registered in advance
([`PREREGISTRATION-2026-08-27-evidence.md`](PREREGISTRATION-2026-08-27-evidence.md), committed
before any scenario ran).

**Result in one line: the registered prediction hit, the registered mechanism was confirmed on
the trajectory, and the instruction is net harmful — coverage fell 6/7 → 4/7. It should not be
kept.**

| | dev sweep 3 | **dev sweep 4** |
|---|---|---|
| stamp | `prompts:53fafe9c12bc` | **`prompts:bf7605651ef2`** |
| budget | `changes` 8, others 4, 120k, 600s, 2 rounds | **identical** |
| delta | — | **one addition to `PLANNER_SYSTEM`, nothing else** |
| cost | $3.6889 · 328,633 tokens | **$3.5689 · 326,519 tokens** |
| judge cost | $0.2808 | **$0.2942** |

S3 is the baseline, not S2: S3 raised the `changes` bound and moved no prompt, so **the prompt is
the only delta here.** Holdout untouched.

## The comparison, per scenario

| scenario | S3 fault | S3 fix | **S4 fault** | S4 fix | dispatches at the failing service | judge S3 → S4 |
|---|---|---|---|---|---|---|
| ad-memory-squeeze | `resource_exhaustion` ✔ | `config_revert` ✔ | `resource_exhaustion` ✔ | `config_revert` ✔ | 2 → 2 | same → same |
| cart-bad-image-tag | `bad_deploy` ✔ | `rollback` ✔ | **`unknown` ABST** | — | **3 → 0** | same → **different** |
| cart-dependency-latency | `dependency_latency` ✔ | `config_revert` ✘ | `dependency_latency` ✔ | `config_revert` ✘ | 3 → 5 | same → same |
| cart-redis-misconfig | `bad_config` ✔ | `config_revert` ✔ | **`unknown` ABST** | — | **4 → 1** | same → **different** |
| frauddetection-memory-squeeze | `resource_exhaustion` ✔ | `config_revert` ✔ | `resource_exhaustion` ✔ | `config_revert` ✔ | 4 → 4 | same → same |
| product-catalog-flag-failure | `unknown` **ABST** | — | **`bad_config` ✔** | `config_revert` ✔ | 6 → 3 | different → **same** |
| shipping-wrong-image | `bad_deploy` ✔ | `rollback` ✔ | **`unknown` ABST** | — | **3 → 0** | same → **different** |

| | S3 | **S4** |
|---|---|---|
| **coverage** | **6 / 7** | **4 / 7** |
| fault class, of answered | 6 / 6 | 4 / 4 |
| class of fix, of answered | 5 / 6 | 3 / 4 |
| judge `same_mechanism` / `different` | 6 / 1 | **4 / 3** |
| triage recall / precision | 0.91 / 0.54 | 0.92 / 0.56 |
| runs exhausting a bound | 2 (both `metrics`) | 1 (`metrics`) |
| runs calling `trace_query` | 3 / 7 | **5 / 7** |
| tool calls, total | 58 | 50 |
| **re-issues after silence** | **4, in 3 runs** | **2, in 2 runs** |

| per fault class | n | S3 fault / answered | S3 abstained | **S4 fault / answered** | **S4 abstained** |
|---|---|---|---|---|---|
| `bad_config` | 2 | 1 / 1 | 1 | 1 / 1 | 1 |
| `bad_deploy` | 2 | **2 / 2** | 0 | **0 / 0** | **2** |
| `dependency_latency` | 1 | 1 / 1 | 0 | 1 / 1 | 0 |
| `resource_exhaustion` | 2 | 2 / 2 | 0 | 2 / 2 | 0 |

**Read the `bad_config` row against the per-scenario table above it.** The aggregate is identical
in both sweeps — one answered, one abstained — while the two scenarios **swapped places**.
`cart-redis-misconfig` answered in S3 and abstains in S4; `product-catalog-flag-failure` does the
reverse. A per-class table is required by house rule and is still not enough here: this row would
have reported "no change" for the single largest behavioural change in the sweep.

## The prediction ledger

| # | registered before the run | outcome |
|---|---|---|
| 1 | `product-catalog-flag-failure` **answers, `bad_config`** | **HIT.** `bad_config`, correct, `config_revert` correct, **high** confidence, judge `same_mechanism`, 6 dead ends closed and all four traps avoided. |
| 2 | The six S3 answers **stay answered and correct** | **FAILED — 3 violations.** `cart-bad-image-tag`, `cart-redis-misconfig` and `shipping-wrong-image` all fell to abstention. None returned a *wrong* class. |
| 3 | **Floor: coverage ≥ 6/7, accuracy-of-answered 6/6** | **FAILED.** Coverage 4/7. Accuracy-of-answered held at 4/4 — every answer given was right. |
| 4 | **Primary endpoint: no run re-issues a question to a stream that returned empty** | **FAILED, and improved.** 4 re-issues in 3 runs → **2 in 2 runs**. Both survivors are bare same-window PromQL re-asks (`cartservice`, `frauddetectionservice`). On the targeted scenario it went **2 → 0**. |

### The falsifiers, and which one fired

None of the three registered falsifiers fired. Falsifier 3 — *it answers but the trajectory shows
no evidence-class switch* — was registered as the outcome most likely to be misread as a win, and
it is worth showing why it does not apply. The winning trajectory, in order:

| seq | dispatch | result |
|---|---|---|
| 6 | `logql_query` @ `productcatalogservice` | **EMPTY** — the exact silence that blocked all five T4.11 repeats |
| — | *(no re-issue)* | T4.11 re-issued this same query at seq 15 |
| 9, 11, 13 | `change_history` @ `frontend`, `cartservice`, `adservice` | empty |
| **15** | **`change_history` @ `featureflagservice`** | **non-empty — the cause.** No T4.11 repeat ever made this dispatch |
| 23 | **`trace_query` @ `frontend`** | the trace tool, **never called once** in any T4.11 repeat |

The verdict names the scenario's own registered discriminator: every erroring chain carries a
client-side `GetFlag` call that is absent from the successful chains in the same window. **Hit
the silence, did not re-ask it, changed vantage, found the cause.** That is the registered
mechanism, executed.

## What the instruction actually did

It changed the behaviour it named. Re-issues fell, `trace_query` adoption rose 3/7 → 5/7, and
total tool calls fell 58 → 50 — fewer calls, more distinct evidence types. On the one scenario
whose failing service is genuinely mute, that is exactly right and it won the answer.

**And it pushed dispatch away from the failing service, which is wrong everywhere else.** The
column that predicts the outcome is dispatches at the service whose failure *is* the fault:

- Three regressions: **3 → 0**, **4 → 1**, **3 → 0**.
- Four non-regressions: 2 → 2, 3 → 5, 4 → 4, and 6 → 3 on the scenario where dispatching *away*
  is correct.

**Every regression is a scenario where target-service dispatches collapsed, and no scenario whose
target dispatches held regressed.** The three regressed runs all localized the *locus* correctly
and then failed to establish the *mechanism* — in their own words:

> "the mechanism at cartservice is unestablished, because the only cartservice dispatch was an
> error-ratio query that returned no series" — `cart-redis-misconfig`

> "no dispatch queried cartservice's logs, metrics, or changes at all" — `cart-bad-image-tag`

`cart-redis-misconfig` spent nine dispatches on `checkoutservice` ×5, `paymentservice` ×2,
`currencyservice` ×2 and **`cartservice` ×1**. It drifted outward across the blast radius. T4.10
measured this scenario answering **6/6** under the byte-identical budget, so a single abstention
here is not plausibly a draw from its variance.

The likely reading is that *"the caller's logs rather than the callee's"* is being taken as a
general push outward rather than as one option among several, and *"the low-prior tools are what
is left"* compounds it. **This is a hypothesis about why, at n=1 per scenario; the effect itself
is measured.**

Two things the instruction did **not** cost: no scenario returned a *wrong* class — every
regression is answer → abstention, never answer → error — and triage was unchanged
(0.91 → 0.92 recall, 0.54 → 0.56 precision), which is the closest thing here to a control.

## Recommendation

**Do not keep this stamp.** It buys one scenario and sells three. The pre-registration said an
instruction that unsettles another scenario has not been shown to be worth its stamp, and that is
what happened. `main` is unaffected — the PR carries the experiment and its negative result, and
not merging is the outcome rather than a deferral.

**What is worth keeping is the finding**, which is sharper than the instruction: the agent's
handling of silence is a real, movable lever, and the failing-service dispatch count is the thing
it moves. The obvious next experiment is a narrowed instruction that keeps *do not re-ask a silent
stream* and drops *change vantage point* — the first clause is what the winning trajectory needed
at seq 6, and the second is what emptied `cartservice` of dispatches. That is a separate stamp and
a separate sweep, recorded in PLAN.md rather than made here.

## What this sweep cannot show

n = 1 per scenario. T4.10 measured a 2.6× breadth spread on a single scenario, so any one
per-scenario flip is one draw — with the exception of `cart-redis-misconfig`, where T4.10's 6/6
prior makes the regression hard to attribute to variance. The four-scenario direction (one up,
three down) is consistent and the dispatch-count explanation fits all seven rows, but neither has
been repeated. Nothing here touches holdout, and the holdout figures now describe a superseded
pipeline (ADR-0023). Judge figures carry the shared-lineage violation as always.

**Total cost of T4.12: $3.5689 agent + $0.2942 judge = $3.8631.**
