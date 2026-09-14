# Pre-registration — Q53, does retrieval depth change a verdict?

**Written and committed before any run.** Governed by [ADR-0041](../../docs/adr/0041-deciding-a-change-to-the-retrieval-depth.md).

Four retrieval write-ups have measured whether a relevant document is **reachable**. None has
measured whether the model reads it and answers differently. T6.4 §5 named that limitation and it
has survived every measurement since.

**This is the first task in this repository that spends money to answer a retrieval question**, and
the first stage of it is designed to be killable for about twelve dollars.

---

## 1. What is already known, at $0

| | recall@3 | recall@5 |
|---|---:|---:|
| flag 0, `retrieval_k = 3` (production today) | **0.395** | 0.442 |
| flag 2 | 0.419 | **0.605** |

- **Raising `k` alone buys two queries of 43.** Flag 2 alone at `k = 3` buys one — inside ADR-0040
  clause 5's band, and Q52 measured that selecting among flags at `k = 3` is *worse* than not
  selecting (out-of-sample −0.0288). **Only the joint change is worth testing**, and that is what
  this registers.
- **Q52 established flag 2's `k = 5` margin is not a selection artefact**: 0.1628 in-sample against
  0.1545 out-of-sample, 95% surviving, selected on 733 of 1000 splits.
- **The token cost of `k = 5` is negligible and is now measured, not argued.** Over 269 recorded
  retrievals the rendered lines are a median of 321 characters each; two extra chunks at two
  retrieval sites is **~321 tokens per investigation, $0.0016** — 0.27% of a median run. Q53's row
  says a larger `k` "puts more retrieved text in front of the model on every investigation", and it
  does, and that is not a cost worth weighing. **The real risk is distraction**, which is precisely
  what a verdict comparison measures and a token count cannot.
- **What a run costs**, from 218 recorded trajectories with token counts:
  median **$0.597**, mean $0.588, p90 **$0.787**, max $1.049.

## 2. The change under test

`TEXT_NORMALISATION` 0 → **2** and `ContextSettings.retrieval_k` 3 → **5**, together. Neither alone.

## 3. The design

**Paired on the incident.** One injection, one incident, **two investigations** — one at
(flag 0, k = 3), one at (flag 2, k = 5). The pair shares a world state, an incident, an alert set
and a change log, so the only difference between the two verdicts is what retrieval handed the
model. World variance is the dominant noise source in this benchmark and pairing removes it
entirely; ten pairs this way are worth far more than twenty unpaired runs.

**Ten pairs, one per dev scenario**, taken in catalog order. No selection.

**Order is alternated**, arm-first on odd pairs and arm-second on even. A second investigation runs
against an incident that already carries a proposal from the first, and whether that matters is
unknown — T6.3's reject-loop re-investigates and found the driver needed the harness's own bounds
before it was comparable. Alternating does not remove an order effect; it stops one being confounded
with the arm.

### 3.1 What ten pairs can and cannot do

Registered as arithmetic, before any run. If the true rate at which a verdict changes is `p`, the
chance this pilot sees **at least one** change is `1 − (1−p)¹⁰`:

| true rate `p` | chance the pilot sees any change |
|---:|---:|
| 0.186 — the retrieval upper bound, 8 of 43 queries | **87%** |
| 0.10 | 65% |
| 0.05 | 40% |

So **ten pairs can falsify "this matters a lot" and cannot establish "this never matters."** It is
a kill switch, not a measurement, and no result from it will be reported as a rate.

### 3.2 The decision

- **0 of 10 verdicts differ** → Q53 closes. The effect is below the retrieval bound with 87%
  confidence, and the larger measurement is not funded. Flag 0 and `k = 3` stand.
- **1 or more differ** → the pilot has done its job and stops. It does **not** adopt anything: a
  changed verdict is not a better one, and `n = 10` cannot say which direction dominates. The next
  step is a registered measurement at 30–40 pairs, priced from this pilot's actual spend.

**Adoption is out of scope for this task entirely.** ADR-0041's rule is satisfied on the retrieval
side already; what is missing is evidence about verdicts, and one pilot does not supply it.

## 4. The budget, as a hard stop

- 20 investigations at the p90 of **$0.787** = **$15.74**.
- The harness discards about **16.7%** of runs (`outcome_of`'s own measurement), so ~24 runs to get
  20 scored: **$18.89**.
- **Hard ceiling: $25.00.** If spend reaches it, the run stops where it is and reports what it has,
  including the pairs it did not complete. A budget that is revised upward mid-task is not a budget.
- `budget_max_usd` stays at its per-incident 2.0. Nothing here raises a per-run cap.

## 5. Predictions

1. **At least one of the ten pairs produces a different `fault_class` or `remediation_class`.**
2. **No more than three do.** The retrieval bound is 18.6% and a reachable document is not a read
   one, so I expect the verdict rate to sit below the retrieval rate.
3. **Where a verdict changes, `k = 5` is right at least as often as `k = 3`.** Registered because
   the opposite is the outcome that would matter most: more context making the answer worse is the
   distraction risk, and it is the one thing this pilot could discover that would settle Q53 against
   the change outright.
4. **No pair differs only in `remediation_class`.** `baselines.py` records the class→remediation
   mapping as one-to-one across all eighteen scenarios, so remediation should move only when the
   class does. If one moves alone, that mapping has an exception nobody has found.
5. **Total spend is under $15.**
6. **At least 8 of the 10 pairs complete** — the discard rate is 16.7% and both halves of a pair
   must score for the pair to count.
7. **The `k = 5` arm's retrieved documents are a superset of the `k = 3` arm's in fewer than half
   the pairs.** Q48 established the two are *not* nested: each arm applies its own `LIMIT k` and
   `fuse` takes `limit=k`, so a deeper cut can reorder rather than extend. Listed because a reader
   will assume nesting and the record should say it does not hold.

## 6. What this cannot settle

- **Whether `k = 5` is better.** Ten pairs cannot. That is the 30–40 pair measurement, and this
  pilot exists to decide whether to pay for it.
- **Whether the change helps the agent on holdout scenarios.** Dev only. Every holdout entry is
  spent deliberately and none is spent on a pilot.
- **Whether flag 2 is right.** Q52 left it unconfirmed and unadoptable for want of held-out queries;
  that is unchanged, and this task adopts nothing.
- **Whether the floor is cleared.** If `k = 5` were adopted, a configuration measured at 0.605 would
  meet a 0.60 floor written at `k = 5` when production ran 3. ADR-0041 says what to do about that:
  **a floor met because the depth moved to meet it is not a floor that was cleared**, and it must be
  said in the same breath as any adoption.
