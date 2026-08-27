# Pre-registration — dev sweep 4, the evidence-class instruction

**Written and committed before any scenario of this sweep ran.** T4.8 set the precedent: a
prediction registered after the run is a description. Registered here are the scenarios that
should move, the ones that must not, and the outcome that falsifies the mechanism.

## The mechanism being tested

T4.11 measured why `product-catalog-flag-failure` abstains 5/5 under a fixed configuration
([`VARIANCE-2026-08-27-abstention.md`](VARIANCE-2026-08-27-abstention.md)). Not budget — it had
room in every run. The chain was:

1. Every plan dispatched logs at the failing service, whose stream ADR-0005 published at
   **0 lines/hour**.
2. The agent read the empty result as a **selector defect**, not as silence.
3. The follow-up round re-issued the same query — several plans call it "corrected logs pending".
4. `trace_query` was never called in any repeat, though four of that scenario's eight
   expected-evidence items sit on traces.
5. It reported the mechanism as unmeasured and abstained — correctly, given what it held.

**Claim under test: the abstention is caused by never changing evidence class after silence.**

## The change

One addition to `PLANNER_SYSTEM` — the planner owns dispatch and the follow-up round, which is
where the failure lives. It teaches the consequence ADR-0019's `empty`-is-not-error rule already
implies, and demotes the dispatch-count prior in the same breath. General form: no scenario, no
service, nothing that functions as an answer key. Guarded by
`test_the_evidence_class_instruction_names_no_answers`.

| | |
|---|---|
| stamp before | `faultline/0.0.1+prompts:53fafe9c12bc` |
| stamp after | `faultline/0.0.1+prompts:bf7605651ef2` |
| budget | **unchanged** — `changes` 8, others 4, 120k tokens, 600s, 2 rounds |
| baseline | **dev sweep 3** ([`SWEEP-2026-08-26-budget.md`](SWEEP-2026-08-26-budget.md)), same budget, same harness |

The budget is deliberately held at the T4.7 configuration so **the prompt is the only delta
against S3**. S3, not S2, is the comparison baseline.

## Registered predictions

### Should move

| scenario | S3 | predicted S4 | why |
|---|---|---|---|
| `product-catalog-flag-failure` | `unknown` **ABST** | **answers, `bad_config`** | The only reachability-blocked abstention in dev. If the mechanism is right, silence at the failing service's logs should push the planner to another vantage — a caller's logs or traces — both of which carry the flag. |

This is the whole prediction. One scenario, named in advance.

### Must not regress

All six S3 answers stay answered and stay correct:

`ad-memory-squeeze` (`resource_exhaustion`), `cart-bad-image-tag` (`bad_deploy`),
`cart-dependency-latency` (`dependency_latency`), `cart-redis-misconfig` (`bad_config`),
`frauddetection-memory-squeeze` (`resource_exhaustion`), `shipping-wrong-image` (`bad_deploy`).

**Floor: coverage ≥ 6/7, accuracy-of-answered 6/6.** Coverage below 6/7, or any answered
scenario returning a wrong class, is a regression and gets reported as one — an instruction
that buys one scenario by unsettling another has not been shown to be worth its stamp.

### The behavioural prediction, which is the sharper test

Independent of any coverage number, and checkable from the stored trajectories:

**No run in this sweep re-issues a question to a stream that returned empty in a prior round,
absent a material change (different service, different window, a selector justified by
something learned since).**

S3 and T4.11 both violate this. Coverage can move for reasons unrelated to the instruction —
T4.11 measured a 2.6× breadth spread on a scenario that answers, so a single sweep's coverage is
one draw. The re-issue count is a direct read of whether the instruction changed the behaviour it
names, and it is registered here as the primary endpoint.

## What falsifies the mechanism

1. **`product-catalog-flag-failure` abstains again while the trajectory shows the same shape** —
   logs dispatched at the failing service, empty, re-issued or abandoned, traces never called.
   The instruction reached the prompt and not the behaviour; the mechanism claim stands unproven
   and the stamp is not worth keeping.
2. **It abstains again having genuinely changed vantage** — traces called, or a caller's logs
   queried, and still no class. Then the mechanism claim in T4.11 is **wrong**: the evidence was
   reachable, the agent reached it, and something else is stopping it. This is the more
   informative failure and it should be said plainly rather than folded into "no effect".
3. **It answers, but the trajectory shows no evidence-class switch** — it got there by planning
   more widely, or by a lucky first dispatch. Coverage rose and the mechanism is **unconfirmed**;
   the correct report is "moved, cause not established", not a claim of success.

Outcome 3 is the one most likely to be misread as a win, so it is registered before the fact.

## What this sweep cannot show

n = 1 per scenario. T4.10 measured a 2.6× breadth spread and T4.11 a stable abstention, both on
single scenarios; neither licenses reading one sweep's per-scenario flip as a settled effect.
Holdout is untouched and stays untouched. Nothing here is evidence about `email-wrong-image` or
any other holdout abstention.
