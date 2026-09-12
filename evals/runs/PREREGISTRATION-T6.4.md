# Pre-registration — T6.4, retrieval quality: a corpus that reaches 50, and the first number anyone has ever put on this pipeline

**Written and committed before any new document is authored and before any query is scored.**

This repository has had hybrid retrieval since T2.4b — pgvector cosine and a `tsvector` arm fused by
reciprocal rank, heading-aware chunking, `origin` carried for self-exclusion, the holdout
quarantined at seed time. What it has never had is **any measurement of whether retrieval finds the
right thing.** `recall@`, `MRR` and `golden set` return zero hits across `src/`, `tests/`, `evals/`
and `scripts/`. ADR-0018 names four parameters — `RRF_K = 60`, `retrieval_k`, section-over-document,
the 384-dimension model — and records all four as *chosen rather than tuned*, with no measurement
behind any of them.

T6.4's deliverable is that those stop being guesses.

**Cost: $0.00.** Embeddings are local (`sentence-transformers/all-MiniLM-L6-v2`), recall and MRR are
arithmetic, and the new documents are authored as repository content the way every ADR in this tree
was. **Any model call in this task is a defect**, on T6.2's rule.

---

## 1. What T6.4 is, in the plan's words

*"Retrieval pipeline over a ≥50-doc corpus + recall@5 / MRR gates"* — heading-aware chunking with
document summaries, hybrid dense+sparse, cross-encoder rerank, recency-aware, deprecated excluded at
ingest, `origin` carried for self-exclusion, golden set in CI.

**What the tree has** (Phase 6 audit, ~45%): the hybrid, the swappable `Embedder`, heading-aware
chunking (ADR-0018), `origin` enforced (T4.1b), holdout quarantined (T1.6), and a corpus of **25
documents / 103 chunks** — 15 authored runbooks and 10 dev narratives.

**What it lacks**: half the corpus; document summaries; cross-encoder rerank; recency weighting;
deprecated-document metadata; git-synced ingest; and — the part with teeth — **a golden set,
recall@5, MRR, or anything at all gating retrieval quality**.

**Deferred by name**, so the audit finds them deferred rather than forgotten: **cross-encoder
rerank, recency weighting, document-level summaries, deprecated-doc metadata and git-synced
ingest.** Each is a plausible improvement. Adding any of them in the same task that first measures
retrieval would mean never knowing which one moved the number, and this task exists to produce the
number they would be judged against. They become candidates the golden set can adjudicate.

---

## 2. Scope — what is built

### 2.1 The corpus reaches 50, and the 25 new documents are `service-*` and `world-*` runbooks

**Authored, not generated.** The owner chose this on 2026-09-12 and the reason is ADR-0036's, not
stylistic: **runbooks sit outside the exclusion filter**, so anything written in one reaches every
scored run forever through the one channel the quarantine does not check. ADR-0036 records that two
of the first fifteen had to be rewritten because they cited a holdout scenario's fault *without
naming it* — an id-matching test would have passed both. Twenty-five documents drafted in a batch is
that review burden multiplied, against a failure that is invisible and permanent.

The existing 15 cover every fault class, every allowlist action and every alert rule. The 25 new
ones are a different kind of knowledge:

- **15 `service-*` runbooks, one per service in `SERVICE_CONTAINERS`** — what the service does, who
  calls it and whom it calls, whether it is instrumented, whether it can page on its own behalf,
  what its ordinary latency band is, and what a reader should not conclude from its silence. This is
  institutional knowledge in ADR-0036's sense and it is the material the catalog encodes without
  explaining.
- **10 `world-*` runbooks** extending the four that exist, on measured facts this world has taught
  the project: kafka's translation-cache growth and why raising the limit is not the remedy
  (ADR-0005's T7.30 addendum), the settle window and why a firing episode inside it reopens rather
  than opens, scrape interval versus alert timing, what a recreate does and does not remove, the
  feature-flag stub's standing, and so on.

**Fifteen near-identical-in-shape service documents is a deliberate difficulty.** A corpus of
documents that differ only in details is a harder discrimination test than one where every document
is about something else, and a retrieval measurement over an easy corpus is a number that means
nothing.

Every new document passes the existing nine mechanical guards in `tests/test_runbooks.py`, and the
ADR-0036 review is explicit per document rather than trusted to the substring test — which, as that
file records, matches scenario ids case-sensitively and catches no paraphrase.

### 2.2 The golden set, and where its queries come from

**The queries are harvested, not invented.** `trajectory_retrievals` has recorded, for every
investigation this project has run, the exact query text the planner and the synthesizer sent, the
`k`, the exclusion asked for, the documents returned and — since T7.9 — the rendered lines as the
model read them. Sixty-plus trajectories of real queries, generated from real triage and real
specialist findings, by a pipeline that had no idea a golden set would ever exist.

That matters because the alternative is the failure mode this task is most exposed to: **an author
who writes the documents and then writes the queries is measuring how well retrieval finds things
they already knew were there.** Harvested queries are not immune — the documents are still authored
afterwards, and the author has read the queries — but the query side is grounded in what the system
actually asks rather than in what would be convenient to answer.

`evals/retrieval/golden.yaml`, committed: each entry is a harvested query, its source trajectory id,
which role sent it, and **hand-labelled relevant document ids** with a one-line reason per label.
Registered targets: **at least 30 queries**, drawn from both roles (the planner's are symptom-shaped,
the synthesizer's evidence-shaped, and `investigation.py` is explicit that collapsing them would
degrade both), covering all four fault classes.

**A query with no relevant document is kept and labelled as such.** Some real queries should return
nothing useful, and a golden set that quietly drops them measures a corpus that always has an
answer.

### 2.3 The metrics, and what they are computed over

`recall@5` and `MRR`, computed by `evalharness.retrieval` — deterministic, no model, no world.

**Against `PgVectorPastIncidentStore`, not the in-memory double.** The real store has *zero* test
coverage today (`make check` never touches it; its own docstring says so), so its SQL, the `<=>`
operator and `plainto_tsquery`'s behaviour have never been exercised by anything. Measuring the
double would be measuring a Python re-implementation of the thing in production. This runs in the
`integration` job, against real Postgres, on the schema migrations produce.

**Reported as three numbers, not one**, and the split is registered before the run:

| over | why |
|---|---|
| **all 50 documents** | the headline |
| the **15 original runbooks + 10 narratives** | the corpus as it was before this task |
| the **25 documents authored for this task** | whether documents written by the person building the measurement are easier to find than documents that predate it |

If the third is markedly higher than the second, that is a finding about the corpus and not about
the pipeline, and it is one this task would otherwise have hidden from itself.

### 2.4 The CI gate, and the honest thing about thresholds

**A threshold chosen after seeing the number is not a threshold.** But a floor chosen before any
measurement exists is a guess. So two numbers, with different standing:

- **The registered floor: `recall@5 ≥ 0.60` and `MRR ≥ 0.45` over the full golden set.** Argued, not
  observed: the corpus is small, the relevant documents for most queries are a `class-*` or
  `alert-*` runbook whose title states its subject, both arms of the hybrid should find those, and a
  pipeline that cannot clear this on its own documents is not doing useful work. **If the first
  measurement falls below the floor, that is the result** — reported, with the pipeline called not
  working, and the fix registered as a follow-up rather than back-fitted here.
- **The regression gate, set after the first measurement** at a stated margin below it, and
  **labelled in the code as calibrated rather than derived.** Its job is to notice change — a
  chunking edit, an embedder swap, a corpus addition that dilutes — not to certify quality. Saying
  so in the file is the difference between a gate and a decoration.

`make check` runs the golden set against the in-memory store as a fast correctness check;
`ci/integration` runs it against pgvector and is the one that gates.

### 2.5 Three small things the survey turned up, fixed here

- **`ContextSettings.retrieval_k = 5` is read by nothing.** The live default is `3`, in
  `Investigation.__init__` and in `faultline-investigate`. A setting that disagrees with production
  and is never consulted is worse than no setting; it is removed or wired, and the measurement says
  which `k` production actually uses.
- **A retrieved runbook renders as `" / Summary: …"`** — a leading empty field, because the renderer
  interpolates `scenario_id`, which runbooks correctly leave blank. The model has been reading that
  wart for every investigation since runbooks were seeded.
- **Re-seeding is idempotent but not reconciling**: nothing removes the row for a chunk that has
  disappeared, so a deleted section survives a re-seed as an orphan. Adding 25 documents is the
  moment that stops being theoretical.

---

## 3. What is *not* changed, registered

`RRF_K` stays 60 and `retrieval_k` stays 3 **for the first measurement.** They are two of ADR-0018's
four unmeasured placeholders, and the entire point of building a golden set is to be able to change
them on evidence afterwards. Tuning them in the same task that first measures them would produce a
number and no baseline to compare it against.

No prompt moves, so `prompts:06f24e827915` does not move; a test asserts the literal. No agent role
changes. No diagnosis figure in `RESULTS.md` moves — retrieval quality is a new axis, reported on its
own, and it is not a sweep.

---

## 4. Predictions

### 1. The corpus reaches 50 documents and every one passes the existing guards
50 documents, 103 + ~65 chunks. The nine mechanical guards in `tests/test_runbooks.py` pass
unmodified, including the ADR-0036 scenario-name check.

### 2. The stamp does not move
`prompts:06f24e827915`. Nothing in this task touches a system prompt or a contract.

### 3. At least 30 harvested queries, from both roles, across all four fault classes
And at least two queries labelled as having no relevant document.

### 4. The first measurement clears the registered floor
`recall@5 ≥ 0.60`, `MRR ≥ 0.45` over the full golden set. **Stated as the directional guess it is**:
the corpus is small and most golden answers are documents whose titles name their subject.

### 5. Recall is higher for the synthesizer's queries than the planner's
The planner's query is services plus severity plus a timestamp; the synthesizer's carries four
specialist finding statements. More content words, more for both arms to match on.

### 6. The 25 new documents do *not* score markedly better than the 25 that predate them
**The one prediction I most want to be wrong about honestly.** A gap above ~0.10 in `recall@5`
between §2.3's second and third rows is evidence that documents written by the measurement's author
are easier to find, and it will be reported as such rather than explained away.

### 7. The service runbooks are the hardest documents to discriminate between
Fifteen documents of near-identical shape differing in service name and details. Where retrieval
fails, it fails here, returning a sibling service's runbook.

### 8. `PgVectorPastIncidentStore` and the in-memory double will not agree on ranking
They agree on fusion — it is the same Python `fuse()` — but the arms differ: real cosine against
hashed cosine, `ts_rank_cd` against token overlap. Any golden-set number from the double is
indicative and not the result, and this prediction is what makes that concrete.

### 9. Something in the real store's SQL is wrong
It has never been executed by a test. **Stated in advance because a prediction that a first
execution finds a defect has been right three times in this project** — T4.5's kafka NPE, T6.2's
running-state drift, T6.3's stale-incident gate — and writing it down is cheaper than being
surprised.

### 10. Cost
**$0.00.** Any model call is a defect.

---

## 5. What this cannot establish

- **Whether retrieval helps the agent.** recall@5 measures whether the right document is returned,
  not whether reading it changes a verdict. That is T6.5's with/without transfer measurement, which
  needs R ≥ 2 and is not funded here.
- **Whether the thresholds are right.** The floor is argued; the regression gate is calibrated after
  the fact and labelled as such. Neither is derived from what good retrieval looks like in general.
- **Whether the golden set is unbiased.** The queries are harvested, which is better than invented;
  the labels and the documents are mine, which is the residual weakness, and §2.3's three-way split
  is the only instrument pointed at it.
- **Whether 50 documents is enough.** It is the plan's number. A corpus of 50 short documents is
  small enough that a dense retriever has an easy time; the figure should be read with that in mind,
  and re-read if the corpus ever reaches a few hundred.
