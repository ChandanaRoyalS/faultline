# Pre-registration — the traceability split (T7.58)

**Committed before any run. Nothing below was written after seeing a result.**

The sole trigger for **Q2** (a synthesizer prompt change) and **Q3** (a warrant check in scoring).
Both were deferred pending exactly this measurement, and both become decidable together or not at
all.

---

## 1. The balance, checked before the design rather than after

**T7.41 died mid-sweep on credit exhaustion and reported at a truncated n. That must not happen
twice**, so the budget fixes the design rather than the design meeting the budget.

**What could be established:** a standard API key **cannot read a balance** — the organization
endpoint returns `401`. What could be established is that the key transacts: a 12-token liveness
probe succeeded for **\$0.000028**. So credit exists; the amount is not knowable from here, and the
stated **\~\$5.50** is the working figure.

**Measured per-run cost at the current stamp `prompts:1b0e7cbb4c47`**, from the run manifests:

| scenario | n at this stamp | mean | worst |
|---|---:|---:|---:|
| `cart-redis-misconfig` | 3 | \$0.6020 | \$0.6189 |
| `payment-telemetry-blackout` | 3 | \$0.5628 | \$0.6023 |

Judge: **\$0.0426/run** (T7.51, six runs for \$0.2555). All-in per run: **\$0.625 mean, \$0.662
worst**.

| design | worst-case cost | margin against \$5.50 |
|---|---:|---|
| **n = 4 per arm** (8 runs) | **\$5.29** | **\$0.21 — one third of a run.** A single discard truncates the experiment |
| **n = 3 per arm** (6 runs) | **\$3.97** | **\$1.53 — 2.3 runs of slack.** Two discards absorbed without truncation |

**Registered design: n = 3 per arm, 6 runs.** Chosen to fit with discard tolerance, which is the
difference the brief draws: *a design chosen to fit the budget is honest; a design truncated by the
budget is a smaller experiment reported as a larger one's remains.*

**The gate is not the constraint.** kafka **44.3%** against a **74.6%** threshold at
`--runs-remaining 6` (and 69.5% at 8). Money is.

## 2. What is being asked

T7.43 found two runs of the same agent disagreeing about **what counts as a demonstrated
mechanism**, and the looser one scored better. T7.51 and T7.52 bounded the finding — D5's abstention
is 1 of 3 rather than typical, and the label/mechanism gap is bidirectional and small — but neither
answered **whether the disagreement tracks the scenario's traceability or is variance.**

**The pair, as T7.43 proposed it.**

| arm | scenario | traceability |
|---|---|---|
| **untraceable** | `payment-telemetry-blackout` | the mechanism is a break in the **telemetry path**. The service is healthy and serving; what is broken is invisible to the capture set, so the mechanism cannot be traced through the evidence — it has to be inferred |
| **traceable** | `cart-redis-misconfig` | the mechanism is **named in the target's own logs** — connection refused against `redis-cart` on port 6380, dependency and port both |

Both are **dev**. This spends no holdout.

## 3. Primary endpoint, fixed now

Per arm, the **warrant-divergence count**: runs that are *not* (answered **and** judged
`same_mechanism`). Abstentions count as divergences; `adjacent` and `different` count as
divergences.

- **Hypothesis (H):** traceability drives the disagreement → the untraceable arm diverges and the
  traceable arm does not.
- **Null (N):** it is variance → both arms show the same spread.

## 4. Predictions, derived from the record

**`cart-redis-misconfig`: 0 divergences of 3.** Basis: **11 answered runs across the whole record,
fault class 11/11, judge `same_mechanism` 11/11, zero abstentions** — the strongest prior in the
catalog. **Stated with its limit: only 1 of those 11 ran on the current world** (`f5bd108f…`); the
rest are two and three worlds back, and T7.54 corrected this project for pooling across a world
move. The prior is context, not a control arm.

**`payment-telemetry-blackout`: 1 divergence of 3.** Basis: its three recorded runs are **all on the
current world** and read abstain / correct / correct, judged different / same / same — an observed
rate of exactly 1 in 3. **This predicts the record repeats**, not that the hypothesis is right.

**Registered failure mode:** if the untraceable arm diverges, it does so as an **abstention**, not as
a wrong mechanism — that is what T7.43 observed and what the arm's evidence shape implies.

## 5. What this n can and cannot distinguish — stated before spending

**It cannot establish the hypothesis.** Fisher's exact on 3 vs 3: even a **complete separation**
(3 divergences vs 0) gives one-sided **p = 0.05**, two-sided **p = 0.10**. Under this project's own
rule — no number without an interval, below-MDE deltas are "no measurable effect" — a complete
separation at this n is **suggestive, not established**. n = 4 per arm would give p = 0.014
one-sided on a complete separation, and n = 4 does not fit with discard tolerance.

**And a sharper admission: if both registered predictions hold exactly — 1 of 3 against 0 of 3 —
the experiment will not have distinguished H from N.** That table is p ≈ 0.4. **The outcome this
design predicts is an outcome that decides nothing**, and that is known now rather than discovered
in the report.

**What it can do, and why it is still worth \$4:**

1. **Falsify H cheaply.** H predicts spread in the untraceable arm. **If `payment-telemetry-blackout`
   returns 3 of 3 answered and `same_mechanism`, H has failed a prediction registered in advance** —
   and falsification does not need the power that confirmation needs, because the prediction was
   made first.
2. **Detect a complete separation** as a signal worth a larger experiment — reported as a signal,
   never as an effect.
3. **Add 3 current-world observations to each arm**, where the traceable arm currently has **one**.

**Three outcomes, and what each decides — registered now so no result gets read as more than it is:**

| result | reading | Q2 / Q3 |
|---|---|---|
| untraceable arm **0 of 3** | **H falsified.** The T7.43 disagreement is not traceability-driven at any rate this design could see | **Dropped**, not deferred — the way T7.45 dropped `MALLOC_ARENA_MAX` rather than deferring it forever |
| untraceable **≥ 2 of 3** and traceable **0 of 3** | **Signal, not effect.** Consistent with H and underpowered | **Kept**, with this as the argument for a powered experiment, and the power stated |
| anything else (including **1 vs 0**) | **Undecided.** Indistinguishable from variance | **Kept, and the register says the trigger has fired once without deciding** — a second identical run of this design would be worth nothing |

## 6. Protocol

- **6 runs, alternating arms** — `payment`, `cart`, `payment`, `cart`, `payment`, `cart` — so any
  drift in the world falls on both arms equally.
- Through **`faultline-eval`** with `--runs-remaining` counting **6 → 1**, which puts the runs under
  **T7.55's freeze path for its first real use**. Whether it behaves as designed, and the
  comparability generation it records, are reported as findings whichever way the experiment goes.
- Budget: the T4.7 bounds — `changes` 8, others 4, 120k tokens.
- **Every run judged.** The mechanism assessment is the measurement here, not an addendum: T7.44
  showed the class label cannot see warrant.
- **No re-runs to improve a number.** Discards recorded with their reason and never deleted. **A run
  that dies environmentally reports at the n it achieved** — but the \$1.53 of slack exists so that
  a discard costs an observation rather than the experiment.
- Agreement reported **three-way** (`same_mechanism` / `adjacent` / `different`), never collapsed;
  coverage and accuracy reported together; **n = 3 per arm is three observations, not a rate.**
