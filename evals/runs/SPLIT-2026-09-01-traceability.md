# The traceability split — result (T7.58)

> **World: `compose_digest f5bd108f…` / `observability_digest 857d95b4…` — current.** Stamp
> `prompts:1b0e7cbb4c47`. Agent `claude-opus-5`, judge `claude-haiku-4-5` — **SHARED LINEAGE on
> every judged figure.** Comparability generation **`f5bd108f4f70`, `provenance: observed`** — the
> first runs in this project to record their own world rather than have it reconstructed.

**Pre-registration:** [`PREREGISTRATION-2026-09-01-traceability-split.md`](PREREGISTRATION-2026-09-01-traceability-split.md),
committed at `d3a5191` before anything ran. Quoted below rather than paraphrased.

**Result in one line: neither arm diverged at all. There was no disagreement to attribute to
traceability, and the design that would have detected one was already too small to do it.**

---

## 1. What ran, and what did not

| run | arm | state | class | fix | judge | cost |
|---|---|---|---|---|---|---|
| `20260901T074946Z` | payment | **DISCARD — `run failed`, API 529 `overloaded_error`** | — | — | — | no recorded cost |
| `20260901T080646Z` | cart | **DISCARD — `baseline gate refused`** | — | — | — | \$0 |
| `20260901T080650Z` | payment | **DISCARD — `baseline gate refused`** | — | — | — | \$0 |
| `20260901T080654Z` | cart | **DISCARD — `baseline gate refused`** | — | — | — | \$0 |
| `20260901T080658Z` | payment | **DISCARD — killed by the operator, mid-settle** | — | — | — | \$0 |
| `20260901T081608Z` | cart | answered | `bad_config` ✔ | `config_revert` ✔ | `same_mechanism` | \$0.5705 |
| `20260901T083811Z` | payment | answered | `bad_config` ✔ | `config_revert` ✔ | `same_mechanism` | \$0.7036 |
| `20260901T090303Z` | cart | answered | `bad_config` ✔ | `config_revert` ✔ | `same_mechanism` | \$0.5963 |
| `20260901T092445Z` | payment | answered | `bad_config` ✔ | `config_revert` ✔ | `same_mechanism` | \$0.4828 |
| `20260901T094904Z` | cart | answered | `bad_config` ✔ | `config_revert` ✔ | `same_mechanism` | \$0.5707 |

**Five discards, and only one of them is an experimental loss.**

- **The 529** is environmental. Under the committed protocol — *"a run that dies environmentally
  reports at the n it achieved"* — **it costs an observation and was not replaced.** The payment arm
  is **n = 2**, not the registered 3.
- **The three gate refusals and the operator kill are my defect, not the world's.** The driver fired
  six `faultline-eval` calls back to back with no wait between them. `faultline-eval` does not wait
  for the world to settle; it *refuses*. So three runs were refused inside four seconds — the
  orchestrator's 300 s settle window from run 1's incident had not elapsed — and the fourth got
  through and injected before the script was killed. **The gate was right every time it refused;
  the driver was wrong to ask.** The injection was reverted through the injector,
  `injections.json` returned to `active: {}`, and that run's `DISCARDED.md` was written by hand
  because the harness was killed before it could write its own.
- **None of those four spent money or produced an observation.** Re-attempting them is not a re-run:
  no verdict existed to improve. **The 529 was not re-attempted, and that is the difference.**

## 2. Against the pre-registration, quoted

> **`cart-redis-misconfig`: 0 divergences of 3.**

**HELD — 0 of 3.** Three answered runs, class 3/3, fix 3/3, judge `same_mechanism` 3/3.

> **`payment-telemetry-blackout`: 1 divergence of 3.** … **This predicts the record repeats**, not
> that the hypothesis is right.

**FAILED — 0 of 2.** Both runs answered, correct on class and fix, both `same_mechanism`. The record
did not repeat: the arm's abstention did not recur.

> **Registered failure mode:** if the untraceable arm diverges, it does so as an **abstention**, not
> as a wrong mechanism.

**Untested.** The arm did not diverge.

**Primary endpoint, both arms:**

| arm | n achieved | divergences | agreement |
|---|---:|---:|---|
| `payment-telemetry-blackout` (untraceable) | **2** of 3 registered | **0** | `same_mechanism` 2 / `adjacent` 0 / `different` 0 |
| `cart-redis-misconfig` (traceable) | **3** | **0** | `same_mechanism` 3 / `adjacent` 0 / `different` 0 |

Reported three-way and never collapsed. **n = 2 and n = 3 are observations, not rates.**

## 3. What this does and does not establish

**It does not falsify the hypothesis, and the registered falsifier was not reached.** Row 1 of the
outcome table required *"untraceable arm 0 of 3"*; the arm reached n = 2 through an environmental
discard. And the arithmetic was weak even at 3: under the hypothesis's own predicted rate of 1 in 3,
**P(0 divergences in 2) = 0.44** and P(0 in 3) = 0.30. **A null result here is what the hypothesis
itself expects a fair fraction of the time.**

**It does not support the hypothesis either.** H predicts spread in the untraceable arm. There was
none.

**So the registered third row is the honest one:**

> **anything else … Undecided.** Indistinguishable from variance. **Kept, and the register says the
> trigger has fired once without deciding** — a second identical run of this design would be worth
> nothing.

**What it does establish is narrower and still worth having: T7.43's disagreement is one event, not
a rate.** Pooling each arm's **current-world** runs only — pooling across a world move is the error
T7.54 corrected:

| arm | current-world n | divergences |
|---|---:|---:|
| `payment-telemetry-blackout` | **5** | **1** — the original T7.43 abstention, `20260831T0434` |
| `cart-redis-misconfig` | **4** | **0** |

**1 in 5 against 0 in 4. Fisher's exact: p = 1.0.** The abstention that started this has not recurred
in four subsequent runs of the same scenario on the same world under the same stamp. T7.51 bounded
it to 1 of 3; this extends it to **1 of 5**.

**One secondary observation, in the opposite direction to the hypothesis.** The only trap *taken* in
this sweep was in the **traceable** arm — `checkoutservice`'s 0.67 error-ratio peak read as partial
impact, in `20260901T090303Z` — while all three of the untraceable arm's traps were **avoided**. If
traceability made warrant looser, that is the wrong way round. It is one run and it is reported as
one run.

## 4. T7.55's freeze path — first real use, and it behaved as designed

| | |
|---|---|
| runs carrying a `freeze` block | **6 of 6** that passed the gate (five scored + the 529 discard) |
| `world.unverifiable_fields` | **`[]`** on every one — nothing refused, nothing blind |
| `corpus.holdout_chunks` | **0** on every one. **ADR-0008 axis 1 is now checked on every run**, not only in a freeze manifest nobody built |
| `comparability.generation` | **`f5bd108f4f70`** on every one |
| `comparability.provenance` | **`observed`** — the first observed generations in the record |
| `new_generation` | `false` — and the first run correctly recorded `previous_provenance: reconstructed`, seeing the pre-T7.55 run behind it for what it is |

**Two details worth recording because they were designed and are now demonstrated.**

**The gate refusals carry no `freeze` block at all**, because the freeze is taken *after* the gate
and before injection. That is the placement working: a run the gate refuses never reaches the point
where a world is observed, and it does not pretend to have observed one.

**`judged_rows` printed `World: f5bd108f4f70.`** — the single-generation header from T7.55. Every
run in both judge invocations shared a generation, so one table was correct; the header names the
world instead of leaving a reader to assume it.

## 5. Cost, and what remains

| | |
|---|---:|
| five scored runs | **\$2.9239** |
| judge, five runs in two invocations | **\$0.2236** |
| liveness probe | \$0.000028 |
| the 529 discard | **no recorded cost** — its four attempts all failed at *"did not start"*, before the investigation, so no score block and no `cost_usd`. The spend is unmeasured and bounded near zero |
| **total** | **\$3.1475** |

Against the **\~\$5.50** working figure: **\~\$2.35 remains.** The design was sized for \$3.97 worst
case and came in under it.
