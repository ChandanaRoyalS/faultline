# Pre-registration — Q39, the text arm that matches nothing

**Written and committed before the fix is written and before any query is re-scored.**

`RETRIEVAL-2026-09-12-t6.4.md` published this repository's first retrieval figures and labelled
every one of them **one-armed**. The reason is `PgVectorPastIncidentStore.search`: its full-text
arm is built with `plainto_tsquery`, which ANDs every lexeme, and **all 43 golden queries match
zero rows on it**. `fuse()` then performs reciprocal-rank fusion over one list and reports nothing
unusual. The pipeline has been dense-only since T2.4b and `RRF_K = 60` has been a fusion constant
over a single arm.

Q39 is the repair. It is registered on its own rather than under T6.4's §2.4 because §2.4
registered *that a follow-up would happen*, not what it predicts — and a measurement with nothing
to be wrong about is not a measurement. This one carries more weight than T6.4's did, not less:
it is the before/after that T6.4's published numbers will be read against, and it is the first
before/after this repository has been able to compute for retrieval at all.

**Cost: $0.00.** Embeddings are local, recall and MRR are arithmetic, and nothing here authors a
document. **Any model call in this task is a defect**, on T6.2's rule and T6.4's precedent.

---

## 1. What was already measured, before this was written

Three facts were established offline — against Postgres 16.13 and the 211 chunks the 40 authored
runbooks produce — **before** this document was written. They are mechanical properties of a SQL
predicate, of the same kind already published in §2 of the T6.4 results, and none of them is a
retrieval-quality number. They are recorded here because they change what Q39 is.

**1.1 — `plainto_tsquery` matches nothing, confirmed again.** 0 of 43 golden queries match any
chunk. This reproduces the published finding on the authored half of the corpus.

**1.2 — `websearch_to_tsquery` is not a candidate, and Q39's row is wrong to name it as one.**
It matches **0 of 43** as well. On 21 of the 43 queries it produces a tsquery byte-identical to
`plainto_tsquery`'s; on the other 22 it differs only in how it treats hyphenated compounds, which
it renders as phrase constraints (`'change-log' <-> 'chang' <-> 'log'`) rather than conjuncts —
**more** restrictive, not less. The top-level operator is `&` in every one of the 43. Q39's row
says the two candidates *"behave differently on this corpus"*; they behave identically in the only
respect that matters, and this document supersedes that sentence.

So **there is one candidate, not two**, and the interesting question moved.

**1.3 — an OR-joined `to_tsquery` matches 43 of 43, and matches a great deal.** Per query, of 211
chunks: min 29, p25 57, **median 174**, p75 209, max 211. Twenty-two of the 43 match more than
half the corpus and one matches all of it.

That last figure is the finding that shapes every prediction below. The arm does not become a
filter; it becomes a **ranking problem**, with `ts_rank_cd` ordering a nearly unfiltered set and
`LIMIT k` taking the top of it. Whether that helps is exactly what is unknown.

**Limits of this probe, stated rather than left implied**: the 50 narrative chunks were not
loaded, so these counts are over the 211 authored chunks and not the 261 the store holds. No
embeddings were computed, no fusion was run, and nothing was scored. It establishes what the text
arm *can* reach, and says nothing about whether reaching it is good.

---

## 2. The change

`PgVectorPastIncidentStore.search`'s text arm moves from `plainto_tsquery('english', q)` to a
disjunction over the same lexemes — the lexemes `plainto_tsquery` already produces, joined with
`|` instead of `&`. The dense arm, `RRF_K`, `retrieval_k`, the embedder, the chunking and the
ranking function are **not touched**. One change, so the number moves for one reason.

### 2.1 A choice the golden set cannot make, named as such

An obvious alternative is to try the AND first and fall back to OR when it returns nothing, so
that a query whose terms all co-occur keeps its precise match. **On this corpus the two are
indistinguishable**: the AND returns nothing for 43 of 43, so the fallback fires every time and
the behaviours are identical on every input the golden set contains. The instrument cannot
adjudicate it, and pretending otherwise by reporting two near-identical numbers would be theatre.

It is therefore decided on argument, and the argument is recorded here so it can be disagreed
with: **always-OR.** A fallback branch that never fires on any measured input is untested code
shaped like a safety net, and this repository has just spent a task on a gate that shipped
un-runnable because nothing exercised it. If a future corpus makes AND matches real, that is the
moment to add the branch and the moment a measurement could justify it.

### 2.2 What is deliberately not tuned

`ts_rank_cd`'s normalisation flags are unset today and stay unset. An arm that matches 83% of the
corpus is obviously sensitive to how rank is normalised, which is precisely why changing it in the
same commit would make the result uninterpretable. It becomes a candidate the golden set can
adjudicate afterwards, the way T6.4 deferred the rerank.

---

## 3. The decision rule, fixed in advance

- **The number that decides is `recall@5` over all 43 queries**, because that is what the
  registered floor is stated in and what the CI gate reads.
- **Tie-break: `MRR@5`.** If both are within 0.02, the change is reported as *no measured
  difference* and the simpler implementation stands.
- **Both `k` = 3 and `k` = 5 are reported**, as T6.4 reported them, and all five partitions —
  all / corpus-age / planner / synthesizer — so a gain concentrated in one place is visible as a
  concentration rather than an average.
- **One run.** The measurement is deterministic given the corpus and the golden set. If it is
  re-run, every run is reported, and no run is dropped for being inconvenient.
- **The golden set is not touched.** No query added, no label edited, no query re-read before the
  score. It is committed and it stays as it is.

### 3.1 The gate

`GATE_RECALL_AT_5` and `GATE_MRR_AT_5` are recalibrated **in the same commit** as the fix, by the
rule the existing constants already embody: **the same relative margin below the measurement.**
Today 0.40 sits 14.0% below 0.465 and 0.18 sits 17.8% below 0.219. The new constants keep those
percentages. The registered floor (recall@5 ≥ 0.60, MRR ≥ 0.45) does **not** move — it was argued
before any measurement existed and a floor that follows the measurement is not a floor.

---

## 4. Predictions

Registered before the fix is written. Failures get reported as failures.

1. **The text arm returns a non-empty list for all 43 queries**, and 5 chunks for at least 42 of
   them. Near-mechanical given §1.3's minimum of 29, and listed so that a failure here means
   something is wrong with the implementation rather than with the idea.
2. **`recall@5` over all 43 rises above 0.465.**
3. **It rises by between 0.02 and 0.15 absolute** — landing in [0.485, 0.615].
4. **It does not clear the registered floor of 0.60.** Prediction 3 permits it; I predict against
   it.
5. **`MRR@5` rises by less than `recall@5` does, in absolute terms.** A second arm that matches
   most of the corpus should add relevant documents at low rank more often than it promotes one to
   the top.
6. **`MRR@5` does not clear 0.45.** It is at 0.219 and would have to double.
7. **The synthesizer partition improves more than the planner partition, in absolute `recall@5`.**
   It has the headroom — 0.273 against 0.667. **The honest counter-argument, registered because it
   may well be the right one**: synthesizer queries are long, and a long query ORs into the widest
   match sets in §1.3, so dilution should hurt them most. If prediction 7 fails, that is the
   reading to take, and it is why prediction 8 exists.
8. **At least one of the five partitions gets *worse* at `recall@5`.** Fusion with a low-precision
   second arm displaces dense hits. If every partition improves, the fusion is doing less than this
   registration assumes.
9. **The corpus-age gap does not close below 0.10.** It is 0.269 today (0.419 against 0.150). The
   gap is about what the documents say, not about how they are matched, so a retrieval fix should
   barely touch it. This is the prediction most likely to be uncomfortable if it fails, because a
   large movement would mean the gap was an artefact of a broken arm rather than the corpus
   finding T6.4 reported it as.
10. **$0.00 spent.** No model call anywhere in the task.

---

## 5. What this will not settle

- **Whether retrieval helps the agent.** Unchanged from T6.4 §5: `recall@5` measures whether the
  right document is reachable, not whether reading it changes a verdict. Nothing here touches that.
- **Whether `RRF_K = 60` is right.** It has never been tuned, and after this it will for the first
  time be a constant over two real lists rather than one — which makes it newly meaningful and
  still unmeasured. That is a queue item, not this task.
- **Whether the labels are right.** One author wrote most of the labels and most of the documents;
  T6.4 §5 named that as the residual weakness and it is unchanged.
- **Whether an OR arm is the right design.** It is the arm that can be measured against what
  exists. A better text arm — BM25, a learned sparse retriever, field weighting — is not ruled out
  by anything here, and this measurement is what such a proposal would have to beat.
