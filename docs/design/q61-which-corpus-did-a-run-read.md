# Q61 — which corpus did a run read, and what should stop two of them sharing a table

**$0.00.** Everything below is read off `evals/runs/` and the tree.

Q61's row: *"A re-seed changes what every run reads and moves no generation. `generations.
generation_of` reads `compose_digest` and `host_platform` and **nothing about the corpus**, so two
runs either side of a `faultline-seed` group into one table and ADR-0022 §3.3's refusal to print
incomparable results side by side never fires."*

It became urgent because
[T6.5 Amendment 1](../../evals/runs/PREREGISTRATION-T6.5.md) found that the learning-effect
measurement cannot avoid a seed: accepted postmortems join the corpus, and `context/seed.py` is
the only writer to it.

---

## 1. Six facts, measured

**The archive has already crossed a corpus boundary, and it is recorded.** Over 551 run
directories, 183 carry a corpus block and they fall into exactly two states:

| corpus `sha256` | chunks | documents | runs | span |
|---|---|---|---|---|
| `e4ca493867b4` | 35 | 7 | **6** | 2026-09-01 07:49 → 09:49 |
| `5e372dd5955d` | 103 | 25 | **177** | 2026-09-02 09:55 → 09-11 07:12 |

`generation_of` calls all 183 one generation. The six ran against a corpus **one third the size**
of the one the other 177 read — ADR-0018's *"a corpus of seven is not a corpus"* is literally
those six runs.

**No published stamp pools two corpora.** Grouped by `runtime_version`, every stamp is
corpus-homogeneous: sweep 5's `1b0e7cbb4c47` holds the 7-document corpus (5 runs) plus 31 runs
that recorded no corpus at all; every later stamp is the 25-document corpus. The only bucket
holding both digests is the stampless one, which is unscored runs rather than figures.

**That is timing, not a mechanism.** The corpus happened to change *between* sweeps rather than
inside one. Nothing arranged it and nothing would have reported it.

**No run carries a body digest.** 0 of 183. `body_sha256` landed 2026-09-14 (Q36, Q45) and no
scored run has been recorded since — the newest is 2026-09-11. So the archive can be checked on
document membership and cannot be checked on wording, for any run, ever.

**`group_by_generation` has no production consumer.** It is referenced by `tests/
test_world_generations.py`, by two docstrings, and by nothing that builds a figure. The functions
that actually decide whether two runs share a table are **`scenario_table._qualifies`** (README's
generated table) and **`evaldb.FINGERPRINT_INPUTS`** (the eval database's configuration rows).
Q61's row named the wrong function, which matters because a fix aimed at it would have changed
nothing a reader sees.

**`FINGERPRINT_INPUTS` does not include the corpus.** It has eleven entries, one of which is
`observability_digest`. So two runs on different corpora share an `eval_configs` row today.

## 2. The decision: pin and compare, do not fold into the name

Q61's row poses the choice as *fold the corpus into the world key, or leave it*, and notes the
cost: folding *"would split the archive's 183 runs from everything after it, which is **correct**
and is also the first time this repository would separate two tables over a change nobody has
argued is material."*

**The repository has already answered this question, for a digest of exactly the same kind.**
`CURRENT_OBSERVABILITY` exists because a Tempo blind to the last five minutes and a Tempo that is
not are one `compose_digest` and two different things to an agent. The answer there was not a
second generation axis. It was a **pinned expected digest, compared where the figures are
printed**, with absent read as *unknown* rather than *different* — and a queue row (Q31) left
open for the naming question.

The corpus is the same shape: it changes what an agent can **retrieve**, not what world it ran
in. So it gets the same mechanism rather than a new one, and the naming question joins Q31's
rather than being answered separately.

**Two constants, because the two digests see different changes.** `sha256` hashes
`document_id|section` and sees a document added or removed. `body_sha256` hashes the text and
sees a rewrite under an unchanged heading, which `sha256` cannot see at all. The T6.5 seed
carries **both kinds at once**: postmortems are new documents, and Q45's nine drifted runbooks
are rewrites with identical shape. One constant would catch one of them.

## 3. What landed

- `generations.CURRENT_CORPUS_SHAPE` — the current corpus's `sha256`, pinned as a literal for
  `CURRENT_OBSERVABILITY`'s reason: reading it off a live store would make a published figure's
  membership depend on which database the reader has.
- `generations.CURRENT_CORPUS_BODY = None` — *no expected value established yet*, which is the
  honest state and is distinct from *every run agrees*. Set from the digest the T6.5 seed records.
- `scenario_table._corpus_agrees`, checked in `_qualifies` alongside `_observability_agrees`.
  Both axes independent; **absent is unknown, not different**, which is every archived run on the
  body axis and 289 directories on both.
- A test asserting that no stamp pools two corpora — a tripwire for the next seed rather than a
  claim about the past.

**README's generated table does not move.** Every run it counts is already on
`5e372dd5955d`, which is what `make check` passing `test_readme_carries_exactly_what_the_tree_
generates` says.

## 4. What did not land, and why it is a separate change

**`FINGERPRINT_INPUTS` needs `corpus_sha256` and `corpus_body_sha256`**, on exactly the argument
its own docstring makes for `observability_digest`: *"Without this input those fifteen runs would
share a fingerprint with every run made after the fix, which is the silent pooling the whole table
exists to prevent."*

It was not in the first change because `eval_configs.fingerprint` is a **stored primary key**,
not a read-time computation: adding an input changes the fingerprint of every future ingest of a
run that carries a corpus block, so the same manifest ingested before and after lands under two
configuration rows. That deserved its own diff.

**Landed in the follow-up, and the feared cost was measured and is not there.** Over all 548
manifests on disk the grouping after the change is the **same 38 groups with the same members**,
only renamed — because every configuration in this archive was already corpus-homogeneous, which
is §1's finding from the other side. So the cost is names rather than membership: a half-loaded
database holds one configuration under two names, which a re-backfill resolves. The input
therefore separates nothing today, and it is right anyway — **it is a mechanism for the next seed
rather than a repair of the last one.**

**The generation name still under-specifies the world**, now on two axes rather than one. That is
Q31, and the corpus joins it rather than opening a second row: renaming a generation renames it
in README, RESULTS and PLAN, and the two digests should be argued together or not at all.

## 5. What this means for T6.5

Amendment 1 set the gate as *"Q61 is settled — something records which corpus a run read, in a
form `group_by_generation` respects."* **That phrasing named a function with no production
consumer**, which §1 establishes, so it cannot be met literally and meeting it would buy nothing.

What the amendment was *for* is that a T6.5 figure must not silently pool with runs that read a
different corpus. Against that, after §3 and §4: **neither the README table nor the eval database
can.** The gate is met in substance, and it is met by a mechanism that has never had to fire —
which is the only kind worth having in place before the seed rather than after it.

## 6. What the seed must do, corrected

§5 said *"record `body_sha256` before and after, and set `CURRENT_CORPUS_BODY` in the same
commit"* and named only one of the two pins. **Both have to move, and the shape one is the
load-bearing omission.**

Ten accepted postmortems are **ten new documents**, so they add `document_id|section` pairs and
the corpus `sha256` moves — which means `CURRENT_CORPUS_SHAPE` stops describing the corpus the
pipeline reads the moment the seed lands. A seed that moved only the body pin would leave every
T6.5 run **excluded from the at-stamp figures by the very mechanism built to protect them**, and
the table would stay empty with forty runs sitting beside it.

So the seed commit sets **both**:

| pin | why it moves | what happens if it does not |
|---|---|---|
| `CURRENT_CORPUS_SHAPE` | ten new documents, ten new sets of section pairs | every T6.5 run is excluded; the at-stamp table stays empty |
| `CURRENT_CORPUS_BODY` | the postmortems' text, **and** Q45's nine drifted runbooks, which the same seed reconciles | the body axis stays unarmed and the drifted runbooks enter the corpus with nothing able to see they moved |

**Record both digests before and after**, not just after: the before-values are what say the seed
did what it was supposed to, and `faultline-corpus-drift` prints the body pair for free. The
shape digest comes from `freeze.corpus_state`, or offline from the working tree — they agree
whenever the two sides differ only in wording, which is the case Q45 found.

**This corrects [T6.5 Amendment 1](../../evals/runs/PREREGISTRATION-T6.5.md), which named only the
body pin.** The amendment is not edited — a pre-registration amended after the fact is not one —
so this note is where the correction lives, and the seed's own amendment will carry the measured
digests.
