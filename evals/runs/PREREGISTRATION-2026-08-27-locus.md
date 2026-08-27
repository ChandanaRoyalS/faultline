# Pre-registration — dev sweep 5, the return-to-locus instruction

**Written and committed before any scenario of this sweep ran**, per T4.8's precedent and
exactly as T4.12 did it.

## Why now, before T7.1

T7.1 re-records the bundles, which moves the world. **Both of this experiment's baselines were
measured against the current world and neither survives a re-record** — S3
([`SWEEP-2026-08-26-budget.md`](SWEEP-2026-08-26-budget.md)) and S4
([`SWEEP-2026-08-27-evidence.md`](SWEEP-2026-08-27-evidence.md)). Run after T7.1 this would be a
one-armed experiment.

## The mechanism, decomposed by T4.12's regressions

T4.12 taught the planner that an empty stream is silence rather than a bad query. It won the one
scenario it targeted and cost three others, and the column that explained every row was
**dispatches at the service whose failure is the fault**: 3→0, 4→1, 3→0 on the three regressions,
holding on everything that did not regress.

The reading: **it taught switching vantage and never taught returning.** Having moved outward from
a silent stream, nothing brought the planner back to the service it had already localized. All
three regressed runs localized the *locus* correctly and then failed to establish the *mechanism*,
saying so themselves.

T5.3's demo added the other half of that picture. Its recorded run — at the **reverted** stamp,
with no such instruction in the prompt — localized to the failing service and then never
dispatched a change-history query there. **The tendency pre-exists the instruction**: one
occurrence in seven runs at baseline against three in seven under T4.12's wording.

## The change

One addition to `PLANNER_SYSTEM`, separating the two halves T4.12 fused. General form: no
scenario, service, or class names, guarded by `test_the_return_to_locus_instruction_names_no_answers`.

| | |
|---|---|
| stamp before | `faultline/0.0.1+prompts:53fafe9c12bc` |
| stamp after | `faultline/0.0.1+prompts:1b0e7cbb4c47` |
| budget | **unchanged** — `changes` 8, others 4, 120k tokens, 600s, 2 rounds |
| baselines | **S3** (`53fafe9c12bc`) and **S4** (`bf7605651ef2`), both at this budget |

The budget is held so **both baselines are live comparisons**: S3 is the same agent without any
silence instruction, S4 is the same agent with the rejected one. Same world, same harness, same
protocol.

## Registered predictions

### Primary endpoint: dispatches at the failing service

S4 measured this as the thing that predicts the outcome, so it is the endpoint rather than
coverage — which T4.10 measured as one draw from a 2.6× breadth spread.

**Registered: no scenario's failing-service dispatch count collapses to 0 or 1.** In S4 three did.
Stated as a floor rather than a direction because the count is small and noisy per scenario.

### Coverage

| | registered |
|---|---|
| **floor** | **coverage ≥ 6/7 — the S3 six are the floor**, and accuracy-of-answered stays at 100% |
| `product-catalog-flag-failure` | **should flip, or hold S4's gain** — it answered in S4 and abstained in S3 |
| the three S4 regressions | **must not recur**: `cart-bad-image-tag`, `cart-redis-misconfig`, `shipping-wrong-image` all answered in S3 |

**The registered success condition is improvement on *both* baselines**: ≥ S3's coverage *and*
S4's product-catalog gain retained. Beating one while losing the other is not a win — that is
what T4.12 did, and this instruction exists because of it.

### Secondary, checkable from the trajectories

Re-issues after silence should stay at or below S4's **2 in 2 runs** (S3: 4 in 3). This is
T4.12's registered endpoint, kept as a secondary here because that half of the wording survives
into this one.

## What falsifies it

1. **A failing-service dispatch count collapses again** (0 or 1) on any scenario. The
   "returning" half did not reach the behaviour, and the mechanism claim is unproven.
2. **Coverage below 6/7.** Whatever else moved, the instruction costs more than it buys, and the
   stamp reverts exactly as T4.12's did.
3. **Coverage ≥ 6/7 but `product-catalog-flag-failure` abstains again.** Then the two halves
   trade off rather than compose, and no single wording gets both — which is a finding about the
   approach, not just this stamp.
4. **The one most likely to be misread as a win: coverage rises with no change in the
   failing-service dispatch counts.** Then coverage moved for reasons unrelated to the
   instruction — one draw from a spread T4.10 measured at 2.6× — and the correct report is
   "moved, cause not established", not success. Registered before the fact because the primary
   endpoint exists precisely to catch it.

## The decision rule, fixed in advance

**Adopted as registered, exactly as T4.12 was.** The record merges either way: the sweep report,
this pre-registration, and every run directory stay regardless of outcome. **The stamp stays only
if it earned it against the conditions above, and reverts in the same PR if it did not.**

## What this sweep cannot show

n = 1 per scenario. T4.10 measured a 2.6× breadth spread and T5.3's demo produced a 1-in-7
abstention on a scenario with a 6/6 record, so no single per-scenario flip is a settled effect.
Holdout is untouched. Nothing here is evidence about `email-wrong-image` or any holdout scenario.
