# Retrieval, measured — T6.4, 2026-09-12

**The first number anyone has put on this pipeline's retrieval.** It is below the registered
floor, and the reason is a defect the pre-registration predicted would be there.

| | measured | registered floor | |
|---|---|---|---|
| `recall@5` | **0.465** | ≥ 0.60 | **below** |
| `MRR@5` | **0.219** | ≥ 0.45 | **below, by half** |

**Cost: $0.00**, as registered. Embeddings are local, recall and MRR are arithmetic, and no model
was called at any point.

**The headline finding is not the number.** `PgVectorPastIncidentStore`'s hybrid has two arms and
**one of them returns nothing for every query in the golden set** — 43 of 43, both roles. The
"hybrid" has been dense-only in production since T2.4b, and the fusion step never said so.

Evidence: `evals/retrieval/golden.yaml` (the set), `faultline-retrieval score` and
`faultline-retrieval arms` (the instruments), `/tmp/retrieval.json` per-query detail.

---

## 1. The measurement

Both `k` values, because the pre-registration registers a floor at `recall@5` and, two sections
later, that `retrieval_k` stays at **3** for the first measurement. Those are not the same
pipeline. 3 is what production runs; 5 is what the floor was argued against. Neither is quotable
without the other.

| | n | recall@3 | MRR@3 | | recall@5 | MRR@5 |
|---|---:|---:|---:|---|---:|---:|
| **all documents** | 43 | **0.256** | **0.159** | | **0.465** | **0.219** |
| answer predates T6.4 | 20 | 0.100 | 0.050 | | 0.150 | 0.062 |
| answer written for T6.4 | 43 | 0.209 | 0.136 | | 0.419 | 0.196 |
| role: planner | 21 | 0.333 | 0.230 | | 0.667 | 0.333 |
| role: synthesizer | 22 | 0.182 | 0.091 | | 0.273 | 0.111 |

Mean distinct documents spanned by the top `k` chunks: **2.56** at k=3, **4.05** at k=5. That is
the ceiling on what a document-level recall can see, and it is why the two columns differ so
much: at k=3 the metric is close to asking whether the two or three best-matching documents
happened to include the right one.

## 2. The defect, which is what this task was for

`PgVectorPastIncidentStore.search` runs a dense arm and a text arm and fuses them by reciprocal
rank. The text arm is:

```sql
WHERE body_tsv @@ plainto_tsquery('english', %(q)s)
```

**`plainto_tsquery` ANDs every lexeme it parses.** Measured against the seeded corpus:

| query | chunks matched |
|---|---:|
| `frontend` | 37 |
| `memory` | 44 |
| `frontend cartservice` | 14 |
| `frontend loadgenerator critical` | 1 |
| `frontend, adservice, loadgenerator critical starting at frontend` | **0** |

The last one is a real planner query, and what the parser builds from it is
`'frontend' & 'adservic' & 'loadgener' & 'critic' & 'start' & 'frontend'`. No chunk in a 263-chunk
corpus contains all six.

**Every one of the 43 golden queries matches zero chunks on the text arm.** Not the long ones —
all of them. The shortest planner query in the set is 24 characters and still conjoins enough
terms to miss.

When the text arm returns nothing, `fuse()` still succeeds: it fuses one list. So the ranking a
model reads is pure cosine similarity, the `tsvector` index is dead weight, and **nothing
anywhere reports it.** ADR-0018's four unmeasured parameters include `RRF_K = 60`; a fusion
constant over a single arm has no effect at all, so one of the four has been a no-op for as long
as it has existed.

### What this does not say

It does not say the dense arm is bad. It says the measured figure is a **one-armed** figure, and
that no figure for the two-armed pipeline has ever existed. Whether fixing the text arm raises
recall is unmeasured and is exactly what the follow-up is for.

### Not fixed here, deliberately

§2.4 registers that a fix is a follow-up rather than something back-fitted into the task that
first measures the number. Fixing it now would also mean the first published figure came from a
pipeline nobody had ever measured in its original state, which is the comparison a regression
gate needs. **Q39** carries it: `websearch_to_tsquery` and an OR-joined `to_tsquery` are the two
obvious candidates, they behave differently on this corpus, and choosing between them on argument
rather than on the golden set would repeat the mistake ADR-0018 already records.

### A correction to how this was first diagnosed

The first reading of it, written before `arms` ran, said the AND semantics bite on long
synthesizer queries and that short planner queries "can still match". **That was wrong, and the
instrument said so within the hour**: 21 of 21 planner queries match nothing either. The
mechanism was right and the threshold was invented — it bites at about three terms, not at a
hundred. It is recorded because the wrong version was stated confidently and the right one came
from counting rows instead.

## 3. The predictions, one by one

### 1. The corpus reaches 50 documents and every guard passes — **held**
50 documents. The nine mechanical guards pass, plus four added during the task. **The chunk count
was badly wrong**: predicted 103 + ~65 ≈ 168, measured **261 at seed time**. The new documents
are longer and more heavily sectioned than the originals, and nothing had estimated that.

### 2. The stamp does not move — **held**
`prompts:06f24e827915`. No prompt or contract was touched; a test asserts the literal.

### 3. At least 30 harvested queries, both roles, all four fault classes — **held, except the last clause**
43 queries, 21 planner and 22 synthesizer, spanning `bad_deploy`, `bad_config`,
`dependency_latency` and `resource_exhaustion`.

**The clause that fails: "at least two queries labelled as having no relevant document."** There
are none. Reported rather than fixed — manufacturing one would be inventing a query, which §2.2
forbids, and widening the sample until two appeared would be selecting for a prediction. The
consequence stands: **a golden set with no unanswerable query cannot detect a corpus that always
has an answer**, and this one cannot.

### 4. The first measurement clears the floor — **failed**
0.465 against 0.60, and 0.219 against 0.45. §2.4 registered what to do about this in advance:
*"reported, with the pipeline called not working."* **Retrieval on this corpus is not doing useful
work**, and §2 is why.

### 5. Recall is higher for the synthesizer's queries than the planner's — **failed, inverted**
Planner **0.667**, synthesizer **0.273** at k=5. The registration's reasoning was *"more content
words, more for both arms to match on."* Both halves were wrong. There is only one arm, and more
content words make a dense embedding *more* diffuse, not less. A 900-character query carrying four
specialist findings embeds to a point near nothing in particular.

### 6. The new documents do not score markedly better — **failed, and this is the one that matters**
The registration named a gap above ~0.10 in `recall@5` as evidence, and called it *"the one
prediction I most want to be wrong about honestly."*

**The gap is 0.269**: 0.419 for queries whose answer was written for this task, 0.150 for queries
whose answer predates it. Nearly three times the threshold.

Documents written by the measurement's author are substantially easier to find than documents
that predate it. §2.3's split existed to expose exactly this and it did. Two things are tangled
in it and this measurement cannot separate them: the new documents may genuinely match these
queries better because the queries were read while the fact sheets were compiled, or the older
fifteen may simply be worse-written for retrieval. **The honest statement is the first one**,
because it is the one that would be embarrassing.

### 7. The service runbooks are the hardest documents to discriminate between — **unresolved**
Needs the per-query detail read against the returned document lists. Left open rather than
guessed.

### 8. `PgVectorPastIncidentStore` and the in-memory double disagree on ranking — **not tested**
No in-memory corpus was built. The prediction was about a comparison this task never set up, and
it stays unresolved rather than being quietly dropped.

### 9. Something in the real store's SQL is wrong — **held, decisively**
Registered on the ground that a first execution of untested code has found a defect three times in
this project. It has now found a fourth, and this one had been shipping wrong results for four
phases.

### 10. Cost — **held**
**$0.00.** No model call at any point.

**Two of ten held cleanly, two held with a failed clause or a wrong sub-figure, four failed, two
are unresolved.**

## 4. Three findings that were not predicted

**Holdout queries reach a golden set through a channel nothing guards.** Seven of the 243 distinct
harvested queries came from holdout runs. A synthesizer query carries four specialist findings in
its text, so committing one would have put a holdout run's findings into this repository
permanently — and a golden set is not a retrieval corpus, so the seed-time quarantine never looks
at it. They were dropped before the text left the machine holding it, and `load_golden` now
refuses one outright.

**§2.3's split is degenerate per query.** No query has an answer lying entirely among the fifteen
older runbooks, because the questions this pipeline actually asks turn out to be about things
only the newer documents cover. The partition is applied per label instead, which preserves the
comparison; the per-query version does not exist on this data.

**Re-seeding leaves orphans, and it just did.** The seed reported `documents=50 chunks=261`; the
corpus queried minutes later holds **263** chunks across the same 50 documents. §2.5 registered
that re-seeding is idempotent but not reconciling and that adding 25 documents is the moment it
stops being theoretical. It stopped being theoretical. Two chunks that no document produces are
in the retrieval pool and in `body_sha256`, and this measurement ran against them.

## 5. What this cannot establish

- **Whether the two-armed pipeline is any good.** Nobody has measured it. Every figure here is
  one-armed.
- **Whether retrieval helps the agent.** `recall@5` measures whether the right document comes
  back, not whether reading it changes a verdict. That is T6.5's transfer measurement and needs
  R ≥ 2.
- **Whether the labels are right.** They are mine, and 25 of the 40 runbooks are mine. §2.3's
  split is the instrument pointed at that, and it fired.
- **Whether the floor was reasonable.** It was argued, not derived. A floor missed by a pipeline
  running on one arm says little about the floor.
- **Whether 43 queries is enough.** They are a deterministic stratified draw from 236, which
  bounds selection but not sampling error, and no confidence interval is computed here.

---

## Addendum 1 — the gate was shipped un-runnable, and read as green

**Added 2026-09-12, after the fact. Nothing above is altered.**

§2.4's regression gate landed as an integration test and **errored on every run**:
`ModuleNotFoundError: No module named 'sentence_transformers'`. It needs the real embedder,
because a gate over a different one would pass while an embedder swap regressed retrieval — and
`embeddings` is an *extra*, while `ci/integration` installed `--all-groups`. Extras are not
groups. The other 29 integration tests passed; all three of the gate's errored, and the job went
red.

**It was reported here and in conversation as having run and cleared.** The evidence for that was
the integration job taking 1m1s where it usually takes 35s, which looked like a model download.
The green run was the one *before* the gate's commit. **Elapsed time is not a run id**, and the
run list said so plainly the moment anyone looked.

So: main was red for two merges, the gate measured nothing, and the claim that CI had verified
retrieval against a clean 261-chunk corpus was false. The figures in §1 are unaffected — they
were measured locally against a live corpus, not by CI — but the sentence saying CI had confirmed
them was not true when written.

**Fixed** by installing `--all-extras` on the integration job alone, with the cost taken
deliberately: that job now downloads an embedding model from the HF hub at test time. `checks`
stays on `--all-groups` so the fast job stays fast. `tests/test_ci_eval.py` holds the invariant —
the job that runs integration tests installs what those tests import — so the next test with an
optional dependency fails the guard rather than the build.

**The transferable part**: a gate is not running because a job is green. It is running because a
run you can name executed it. This document's own §2 argues that a hybrid retriever silently
running on one arm is worth more as a finding than as a better number; a gate silently running on
no arms is the same failure, committed by the person who had just written that sentence.

---

## Addendum 2 — prediction 7, resolved: **failed**

**Added 2026-09-12. Nothing above is altered.**

> *"The service runbooks are the hardest documents to discriminate between. Fifteen documents of
> near-identical shape differing in service name and details. Where retrieval fails, it fails
> here, returning a sibling service's runbook."*

Computed over the per-query detail at k=5:

| | |
|---|---|
| queries that missed | **23** of 43 |
| misses that wanted a service runbook and returned a **different** service runbook | **0** |
| misses whose answer was not a service runbook at all | **13** |

**Zero sibling confusions.** The failure mode the registration named as the most likely one does
not occur here even once, and the deliberate difficulty §2.1 built into the corpus — *fifteen
near-identical-in-shape documents is a harder discrimination test* — turns out not to be where
this pipeline fails.

The reasoning behind the prediction was about a discrimination task, and §2's defect says the
pipeline is not performing one: with the text arm dead, a service name in a query is matched by
dense similarity alone, and service names are the most distinctive tokens in these documents. The
remaining ten misses wanted a service runbook and returned neither it nor a sibling, which this
measurement does not characterise further — the per-query returns would say what they got instead
and that reading has not been done.

**What it establishes and what it does not.** It establishes that sibling confusion is not this
pipeline's failure mode *as it currently runs*. It does not establish that the fifteen service
documents are easy to tell apart, because a one-armed retriever is not the pipeline the
prediction was about. Q39's repair adds a lexical arm, on which fifteen documents sharing most of
their vocabulary is exactly the hard case — so this prediction is worth re-reading after the fix
rather than treating as settled.

**Prediction 8 remains untested.** No in-memory corpus was built, so the ranking comparison it
names was never set up. Recorded as unresolved rather than dropped.
