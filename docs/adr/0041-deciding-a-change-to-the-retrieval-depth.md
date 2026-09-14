# ADR-0041 — deciding a change to the retrieval depth itself

**Status:** accepted, 2026-09-14
**Task:** Q53. **Amends** [ADR-0040](0040-which-k-decides-a-retrieval-measurement.md) clause 2.

## Context

ADR-0040 clause 2 fixed the deciding metric for retrieval changes at `recall@3`, on a ground that
does not depend on any result: *"a measurement that decides on a configuration the system does not
run is measuring something else."* `ContextSettings.retrieval_k` is 3.

Q53 proposes changing `retrieval_k`. **The rule then eats itself**: the configuration the system
runs is what the change is about, so "decide at the depth production uses" names the old depth
before the change and the new one after it, and the same sentence gives two answers.

This is not hypothetical. The change Q53 wants to test is a joint one — `ts_rank_cd` normalisation
flag 2 together with `retrieval_k = 5` — because the two only work together:

| | recall@3 | recall@5 |
|---|---:|---:|
| flag 0 (standing) | 0.395 | 0.442 |
| flag 2 | 0.419 | **0.605** |

Raising `k` alone buys two queries of 43. Flag 2 alone, at `k = 3`, buys one — inside ADR-0040
clause 5's band, and Q52 measured that selecting among flags at `k = 3` is **worse than not
selecting** (out-of-sample −0.0288). Together they buy eight.

## Decision

**A change to `retrieval_k` is decided at the depth it proposes, and must additionally not regress
the depth it replaces.**

Concretely, for a change from `k = a` to `k = b`:

1. **It must win at `k = b`** — the depth production would run after the change — by more than one
   query of the evaluation set, ADR-0040 clause 5's resolution.
2. **It must not lose at `k = a`** by more than one query. Not "must also win": a change to the
   depth is allowed to be neutral at the depth it abandons, but it may not be a regression there,
   because a reader comparing against every figure published before it is reading `k = a`.
3. **Both are reported**, with all five partitions, as ADR-0040 clause 3 already requires.

## Why this construction and not the other two

Three rules were available and this is the most demanding of them:

- **Decide at the old `k` only.** Measures a configuration that will not exist after the change,
  which is precisely what ADR-0040 clause 2 forbids — applied to `retrieval_k` it forbids ever
  changing `retrieval_k` on evidence.
- **Decide at the new `k` only.** Weakest. Any depth increase raises recall mechanically, so a rule
  reading only the new depth approves almost any increase.
- **Both, as above.** Strictly stronger than either: it requires a real gain where the system will
  live *and* no loss where the record was written.

## The part a reader should be suspicious of

**I can see that the joint change satisfies this rule before it is run**, and saying so is the
point. Flag 2 at `k = 3` is 0.419 against 0.395 — one query, inside the band, so clause 2 is
satisfied as *not a regression*; and at `k = 5` it is 0.605 against 0.442, which clears clause 1.

That is a rule written by someone who knows the answer. The mitigations are the only ones
available and they are stated rather than assumed:

- The construction is the **most demanding** of the three, so choosing it cannot be the favourable
  choice.
- Neither clause is calibrated to the observed numbers. The threshold in both is `1/n`, which
  ADR-0040 clause 5 set before any of this, for an unrelated reason.
- **The rule does not decide Q53.** Retrieval recall is a *precondition* in Q53's registration, not
  its outcome. The outcome is whether a verdict changes, which no figure in this ADR bounds and
  which costs model calls to measure.

If a later reader concludes this ADR was reverse-engineered from a result, the honest response is
that it partly was, and that the queue row, the registration and this section all say so.

## Consequences

**ADR-0040 clause 2 stands unchanged for every retrieval change that is not a change to `k`.** This
ADR is narrow on purpose: it governs one parameter, the one clause 2 cannot speak about without
contradiction.

**The floor does not move.** `recall@5 ≥ 0.60`, `MRR ≥ 0.45`, still argued before any measurement.
If `retrieval_k` becomes 5, a configuration measured at 0.605 would clear the recall half — and
that is exactly the moment to reread ADR-0040 clause 4, which refuses to set a floor at a depth
whose number is already known. **A floor that becomes met because the depth moved to meet it is not
a floor that was cleared.** Whoever adopts `k = 5` should say so in the same breath.

**The CI gate keeps asserting both `k`.** If the depth changes, the gate's headline `k` changes with
it and the other stays, because the archive is full of figures at the old one.
