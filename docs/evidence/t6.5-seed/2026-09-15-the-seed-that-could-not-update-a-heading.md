# The T6.5 seed, and the reading that was superseded before it was used

**2026-09-15. $0.00** — every number below is a database read, a tree read, or
`faultline-retrieval score`, which makes no model call.

This records a measurement that **is not the T6.5 seed's post-seed reading**, and why. It is
kept because it is what found the defect, and because a superseded number that is deleted is a
number nobody can check. Nothing here is edited later; the second reading gets its own record.

---

## 1. Before the seed

| | value |
|---|---|
| chunks | **261** |
| documents | **50** |
| `sha256` (store) | `9c5e5958e8c7fde52cbd5d8defb8c992c71ecb15bd225a291860df6a44fd62b6` |
| `body_sha256` (store) | `6cde2afd5016d79693ed975101cb65f0e60079be04126bd13f33505bedd702b5` |
| `holdout_chunks` | **0** |
| `recall@3` / MRR | **0.395 / 0.233** (n=43) |
| `recall@5` / MRR | **0.442 / 0.286** |
| synthesizer `recall@3` | **0.182** |
| planner `recall@3` | **0.619** |

`recall@3 = 0.395` reproduces Q49's flag-0 row exactly, a day later on a separately loaded
model. The instrument is stable, which is what makes the rest of this readable.

**`faultline-corpus-drift` before the seed** named ten postmortems in the tree and not in the
corpus, and nine runbooks *"on both sides, saying different things"*.

## 2. Two things the before-state established that were not known

**`CURRENT_CORPUS_SHAPE` matched neither side.** Pinned at
`f34651707c7f928ffdb7f231dfe5cc827dcc5468b93582050a44a90061c28f03`; the live store read
`9c5e5958e8c7`. Computed offline over the working tree minus postmortems, `f34651707c7f`
reproduces exactly — so [Q61's correction](../../QUEUE.md) moved the pin off the archive and onto
**the tree**, not onto the deployed corpus it is compared against. The pin has never named a
corpus any run could have read.

**The nine drifted runbooks are not body-only drift.** Thirteen `(document_id, section)` pairs
differ between store and tree — `runbook:class-bad-deploy` holds *"Confirming it"* and *"What
makes this class easy to get wrong"* where the tree has *"What the change record holds"* and
*"What the mechanism does to the container"*. Both digests see this. `CURRENT_CORPUS_BODY`'s
docstring says *"the drifted runbooks are rewrites (only body moves)"* and Q45's row says a
rewrite under an unmoved heading; **neither is what is on disk.**

## 3. The seed

`faultline-seed` against the live store: `documents=60 chunks=311`, ten
`(postmortem)` lines, both INVALID bundles skipped, all forty runbooks re-seeded.

## 4. After the seed — the reading that is superseded

| | value |
|---|---|
| chunks | **311** |
| documents | **60** |
| `sha256` (store) | `36860c910d9dd20c5b1e1e7ed679d3cdf5097abe55c03d6afab7f94bbebc004c` |
| `body_sha256` (store) | `c72c79c315f4ad287af55434c8d5f073d7021c1863fa05e9b99c662264804a4c` |
| `holdout_chunks` | **0** |
| `recall@3` / MRR | **0.302 / 0.186** |
| `recall@5` / MRR | **0.372 / 0.243** |
| synthesizer `recall@3` | **0.045** |
| planner `recall@3` | **0.571** |

**And the drift check still named the same nine runbooks.** Store `body_sha256`
`c72c79c315f4`, working tree `cc473105c036`, on a corpus seeded from the tree minutes earlier
through the same `load_runbooks()` the check reads.

## 5. Why, in one line of SQL

`PgVectorPastIncidentStore.add` upserts `ON CONFLICT (id) DO UPDATE SET` five columns — body,
embedding, embedder, recorded_from, scenario_fingerprint — and **`section` is not one of them**.
A chunk's id is `document_id#section_index`. Renaming a heading does not move the index, so the
row is updated in place with the new body **under the old heading**, and `prune_document` finds
nothing stale because nothing is stale by its key.

Measured on `runbook:action-scale-unavailable` after the seed: four sections each side, three
byte-identical, and the fourth reading *"The consequence for the benchmark"* in the store against
*"The consequence"* in the tree.

**So Q45's diagnosis was wrong.** The row has stood since 2026-09-14 as *"nothing notices a
commit"* — a deployment that the seeder had not reached. The seeder reached these nine documents
every time it ran and could not change them. The corpus could accept a new document and could
not accept an edit to one it already held, and `faultline-corpus-drift`'s exit code had been
permanently 1 for that reason rather than reporting a state anyone could clear.

**Why no test caught it.** `InMemoryPastIncidentStore.add` assigns the whole `Chunk` at the key,
so the substituted store takes the edit and every test written against it passes. The defect
lived only in the SQL, which no test read. It does now.

## 6. What supersedes this, registered before it is run

The fix lands, the seed runs again, and §4's table is taken again. **Registered now so the
second reading cannot be chosen:**

1. **`recall@3` after the fix will be `0.302`, unchanged, and not merely close.** `chunk.text`
   is the section body with the heading stripped (`corpus.chunk_runbook`), the dense arm embeds
   `chunk.text` and the text arm ranks `body_tsv` — so `section` is metadata that no arm reads.
   Thirteen stale headings cannot move a retrieval number by one query. **If it moves at all,
   this reasoning is wrong and that is the finding**, not the new number.
2. **`sha256` will move; `body_sha256` will move.** Thirteen heading pairs change and thirteen
   bodies were already correct, so the shape digest moves and the body digest moves with it.
3. **`faultline-corpus-drift` will exit 0** — the first time it ever has.
4. **Chunk count stays 311 and `holdout_chunks` stays 0.** A rename is an update, not an insert;
   if the count moves, the upsert is inserting where it should be updating.

## 7. What this does not excuse

**The retrieval regression is real and is not the defect's doing.** `recall@3` 0.395 → 0.302,
and synthesizer `recall@3` 0.182 → 0.045 — four queries of twenty-two down to one. By §6.1 the
second reading will carry the same numbers, so the cause is the **fifty postmortem chunks**,
which are topically near-identical to the narratives the golden set labels as the answer and
displace them.

Amendment 3 §5 asked for exactly this — *"corpus growth tracked in the retrieval evals"* — and
registered `recall@3 = 0.395` as the attenuation bound for the whole T6.5 measurement. **That
bound is now 0.302, and the measurement has not run.** What to do about it is a decision for an
amendment, not for this file, which records only what was measured.
