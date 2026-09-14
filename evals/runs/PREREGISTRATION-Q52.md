# Pre-registration — Q52, and the confirmation that could not be built

**Written and committed before the cross-validation is run.**

Q49 measured seven `ts_rank_cd` normalisations against the 43-query golden set. Flag 2 reaches
`recall@5` **0.605** — the first configuration ever measured here that clears the registered 0.60
floor — and restores synthesizer recall to its pre-Q39 value. It was **not adopted**, because
choosing the best of six against the set that scored them is selection on the test set.

Q52 was registered to confirm it on a held-out draw. **That confirmation cannot be built, and the
reason is worth more than the confirmation would have been.**

**Cost: $0.00.** No model call. No new data of any kind.

---

## 1. Why the registered design is dead

The confirmation was to be planner-only, because planner labels are derived by code
(`planner_labels`, proved against all 21 committed labels) and therefore cannot be biased by
someone who already knows flag 2 wins.

Counted against the live harvest:

| | |
|---|---:|
| distinct non-holdout **planner** queries in existence | **31** |
| already spent on the golden set | **21** |
| available as held-out | **10** |
| …of which from one scenario (`shipping-quote-misconfig`) | **5** |

**One query in ten is 0.10.** Flag 2's advantage at `recall@3` — the metric ADR-0040 clause 2 says
decides — is **one query in 43, or 0.0233.** The instrument would be four times coarser than the
effect, on a sample half of which comes from a single scenario.

There are ~200 unused *synthesizer* queries, so the data exists; their labels are a judgement, and
the person available to make it already knows what the measurement is expected to show. That is the
one contamination the planner-only design was chosen to avoid.

**More planner queries require more investigations, which require model calls.** The supply of
mechanically-labellable evaluation data in this project is spent. That is a finding about the
benchmark rather than about retrieval, and nothing in the queue had anticipated it.

---

## 2. What is run instead, and what it is not

**Cross-validation over the existing 43.** Split the scored queries in half; choose the best flag
on one half by the deciding metric; measure that flag's advantage over flag 0 on the other half;
repeat and average.

**This is not confirmation and will not be reported as confirmation.** Every query in every half is
a query all six flags were already scored on. It answers one question only, and it is the question
Q52 exists for: **how much of flag 2's margin survives having been selected?** The gap between the
in-sample margin and the mean out-of-sample margin is the selection bias — measured, instead of
assumed away in either direction.

### 2.1 Parameters, fixed here

- **Splits: 1000. Seed: 20260914.** Both constants in `retrieval.py`, so the number in the
  write-up is reproducible by anyone who doubts it.
- **Candidates: flags 0, 1, 2, 4, 8, 16.** Flag 32 is excluded because it is provably identical to
  flag 0 — `fuse` reads positions and `rank/(rank+1)` is monotone — and a duplicate of the baseline
  would split the baseline's selection votes and inflate every other flag's frequency.
- **Halves are 21/22**, drawn without stratification. The golden set is already stratified by
  scenario and role; stratifying the split as well would make the halves more alike than two
  independent samples, which flatters the out-of-sample number.
- **Unanswerable queries are dropped before splitting**, not after. Rows contributing 0 to every
  flag in both halves shrink every margin by dilution rather than by selection.
- **Selection metric: `recall@3`**, ADR-0040 clause 2, tie-break `MRR@3`, then the lowest flag
  number so ties are deterministic rather than dictionary-ordered.
- **Reported at both `k`**, per ADR-0040 clause 3.

### 2.2 The decision rule

Flag 2 is adopted only if **both** hold:

1. It is selected on **more than half** of the 1000 splits at `k = 3`.
2. Its mean **out-of-sample** `recall@3` advantage over flag 0 exceeds **one query of the
   evaluation half** — `1/21 = 0.0476`.

Otherwise `TEXT_NORMALISATION` stays at 0 and the 0.605 stays on the record as measured,
unconfirmed, and explicitly not adopted.

**I expect this rule to reject flag 2**, and §3 says so as a prediction rather than leaving it to
be discovered. The bar is deliberately not lowered to fit: a rule written to admit the change it is
testing is not a rule, and this is the third measurement in a row where the registered rule points
away from a change I built.

---

## 3. Predictions

1. **Flag 2 is selected on a majority of splits at `k = 5`** — its margin there is seven queries
   of 43 and should dominate the noise.
2. **Flag 2 is *not* selected on a majority of splits at `k = 3`.** Its margin there is one query;
   on a 21-query half that is inside the resolution.
3. **The decision rule rejects flag 2**, on clause 2 at `k = 3`.
4. **Shrinkage at `k = 3` exceeds shrinkage at `k = 5`**, in absolute terms — a margin of one query
   is almost entirely selection, a margin of seven is mostly not.
5. **Out-of-sample advantage at `k = 5` stays above 0.10.** If the 0.605 is real at all, this is
   where it shows.
6. **At `k = 3` the out-of-sample advantage is within ±0.03 of zero** — indistinguishable from
   doing nothing.
7. **No flag other than 0 or 2 is selected on more than a fifth of splits at either `k`.**
8. **$0.00.**

---

## 4. What follows either way

**If flag 2 is rejected at `k = 3` and holds at `k = 5`** — which predictions 2, 3 and 5 together
expect — the finding is not about the flag. It is that **the configuration production runs cannot
tell these two pipelines apart, and the one that clears the floor is only distinguishable at a
depth production does not use.** The lever that would follow is `retrieval_k`, not the flag: one of
Q50's four candidates, and the only one that moves nothing stored.

That is a change with its own cost — a larger `k` puts more retrieved text in front of the model on
every investigation — and it is not made here, on the same argument that keeps flag 2 unadopted.

**If flag 2 survives both clauses**, it is adopted, the gate constants are recalibrated by the rule
`RETRIEVAL-2026-09-13-q39.md` §4.4 settled, and the 0.60 floor is cleared for the first time — with
the standing caveat that a cross-validated margin is a bound on optimism and not a held-out result.

**Either way Q52 closes** and a new row records what this task actually discovered: that the
benchmark's supply of unbiasably-labellable queries is exhausted, and that the next real
confirmation of anything in retrieval costs model calls.
