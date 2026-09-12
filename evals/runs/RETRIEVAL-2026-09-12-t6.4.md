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
