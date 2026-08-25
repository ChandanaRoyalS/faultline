# ADR-0018: The past-incident corpus — embeddings, chunking, quarantine, and retrieval

- **Status:** accepted
- **Date:** 2026-08-24
- **Task:** T2.4b (corpus seeding), inside the context layer
- **Builds on:** ADR-0002 (pgvector), ADR-0008 (both contamination axes), ADR-0017 (context layer)

## Context

ADR-0002 chose pgvector and sketched hybrid retrieval — "dense vectors fused with Postgres
full-text search" — with provenance filters as plain SQL so that leave-one-out exclusion at
T4.1b is "enforced in the query itself". It named no embedding source. ADR-0008 fixed the
seeding input as one path and made axis 2 — a scenario retrieving its own rehearsal — an
enforcement problem rather than a rule. `ARTIFACTS.md` made `incident.md` the file that gets
seeded and the file "a retrieval agent will surface months later".

What was left to decide was everything between a directory of markdown and a query with an
exclusion argument on it.

**The corpus is small and its shape is measured, not assumed.** Nine dev bundles carry a
narrative; two are marked `INVALID.md`, so **seven** are seedable. Every one of the nine has
YAML front matter, one `# Title`, and the same five sections:

    What was observed | What was checked | Root cause | Resolution | Detection notes

That uniformity is load-bearing below: it is what makes a section a stable unit rather than
one author's habit.

## Decision

### Embeddings: a local model, and the choice is replaceable by construction

**A local model — `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions.**

| | local model | API embedder |
|---|---|---|
| reproducibility | pinned with the code; a scored run repeats | depends on a remote model version nobody pins |
| dependency | heavy — torch, installed as an optional extra | one HTTP client |
| failure mode | slow first load | network, rate limits, an outage mid-scoring run |
| determinism | same input, same vector, forever | a silent model update changes every number |

The deciding argument is the project's own standard rather than a preference. This repo pins
its world by content digest, refuses to compare bundles recorded against different compose
files, and re-records rather than backfills. A benchmark built that carefully cannot then
hand its retrieval to a service that can change under it without telling anyone, and whose
change would show up as a shift in accuracy that nothing in the tree would explain. ADR-0014
already names the class: a field that moves on its own is worse than no field.

The cost is real and is not hidden: torch is a large dependency for a `make check` that runs
in under three seconds. It is therefore an **optional extra** (`faultline[embeddings]`),
imported lazily inside `SentenceTransformerEmbedder._load`, so nothing in the seeding or
retrieval path loads a model until something asks for a vector.

**Three things make the choice replaceable rather than load-bearing:**

- `Embedder` is a Protocol. Nothing else in the corpus layer imports a model.
- Tests use `HashingEmbedder` — a deterministic hashed bag-of-words, built on `hashlib`
  rather than `hash()` whose seed is randomised per process. It is **not a model** and says
  so; it gives enough signal for a test to assert that an exclusion changed a result, and not
  enough for anything to be judged on.
- **Every chunk stores the embedder name and dimension that produced its vector.** A model
  swap that left old and new vectors mixed would degrade retrieval silently, and silent
  degradation of a measurement substrate is the failure this repo keeps rediscovering.

### Chunking: the section is the unit

**One chunk per `##` section**, with `document_id` and `section_index` on each so the whole
narrative is reconstructable.

The consumer is a T3.x agent that arrives holding **symptoms** — an alert set, a service, a
shape of failure — and asks whether anything like this has been seen. The section that
resembles what it holds is *What was observed*. A whole-narrative chunk buries that surface
under four sections of other content and matches on the average of a document rather than on
the part that corresponds to the query.

Storing both was considered and rejected: it puts the same prose in the corpus twice, and one
document then wins a query with two hits for no reason connected to relevance.

The section that states the answer outright is named in the code (`ANSWER_SECTION = "Root
cause"`) because it is what a leave-one-out failure hands over verbatim. It is **legitimate
content for every other scenario**, which is exactly why the defence is an exclusion at query
time and not a redaction at seed time.

**Every chunk carries, from its bundle's manifest and front matter:** `origin`, `split`,
`scenario_id`, `fault_class`, `scenario_fingerprint`, `recorded_from`, `title` and
`source_path`. That is the provenance that makes T4.1b's exclusion a WHERE clause rather than
a special case — `origin` is the key it filters on, and the rest is what makes a stale or
mislabelled chunk detectable rather than merely present.

### The quarantine, structurally

**The seeder takes one root, and it is the dev directory.** Not a `--split` flag, not a
filter applied over both trees, not "seed everything then exclude". ADR-0008 is explicit that
the path-based quarantine only works if exactly one path is read, and each of those
alternatives is a one-character edit away from seeding the holdout.

Three guards, in descending order of how much they are trusted:

1. **The resolved root may not contain a `holdout` component, and must end in `dev`.**
   Structural, checked after resolution so `dev/../holdout` cannot walk out of it.
2. **Every narrative's front-matter `split` must be `dev`**, and its `origin` must match its
   manifest's. The T1.6 guards make a mismatch near-impossible; the seeder refuses rather
   than trusts, because the cost of being wrong is a holdout answer key in the corpus and
   nothing downstream would show it. A wrong `origin` is worse than it looks: it is the
   exclusion key, so it excludes the wrong scenario.
3. **A bundle carrying `INVALID.md` is skipped, and the skip is reported.**
   `currency-cpu-throttle` and `flag-service-crashloop` are blocked scenarios whose faults
   produced nothing observable. Seeding them would put two incidents in the corpus that never
   happened. This is why the count is seven and not nine.

ADR-0008 said its seeding input "needs a test that fails on any path outside
`evals/scenarios/artifacts/dev/`". `tests/test_corpus.py` is that test, in five forms.

### Hybrid retrieval, with the exclusion in the signature from day one

`search(query, k, exclude_origin=None)`. Dense (`embedding <=> query::vector`) and Postgres
full-text (`ts_rank_cd` over a stored `tsvector`), fused by **reciprocal rank fusion**.

Fusion is on **ranks, not scores**: a cosine distance and a `ts_rank_cd` have no common
scale, and normalising two incomparable numbers invents a relationship between them. `RRF_K`
is at its conventional 60 — chosen, not tuned, with nothing to tune it against until T4.2
measures ranking quality over scored runs.

The fusion rule lives in Python and both implementations call it, so the in-memory double
used in tests exercises the same ranking the pgvector store does. The alternative — fusion in
SQL — would leave the tested path and the real path different in the one place ranking can go
wrong.

**`exclude_origin=None` is legal, and it is the product case:** a live incident has no origin
to exclude, and a real responder is entitled to every past incident there is.

**Every benchmark retrieval passes it.** ADR-0008, axis 2: when scoring scenario S the
nearest neighbour is the rehearsal of S, containing S's true root cause in the label author's
own words — the agent does not diagnose, it looks up. This is *within-split* leakage, so the
path quarantine above is structurally blind to it, and the two defences are not substitutes.
Putting the parameter in the signature now means T4.1b passes an argument rather than patching
a query, and means the two arms cannot drift into filtering differently, because they take the
same parameter at the same call.

### pgvector availability

`docker-compose.yml` ran `postgres:16-alpine`, which has no `vector` extension to enable. It
now runs `pgvector/pgvector:pg16`, and `CREATE EXTENSION IF NOT EXISTS vector` heads the
schema either way.

**That compose change is free, and it is worth stating why rather than assuming it.**
`world.compose_digest` (ADR-0014) digests exactly three files — `world/docker-compose.yml`,
`compose/world-arm64.override.yml`, `compose/telemetry.yml` — taken from
`InjectorSettings.compose_files` rather than a hardcoded list. The platform compose file at
the repo root is not among them, so **editing it invalidates no recorded bundle.**

One operational caveat, recorded in the compose file itself: same PG major, different base
image — alpine is musl and pgvector's image is glibc — so an existing `pgdata` volume carries
a collation mismatch. Recreate it. The only data in it is the T2.2 smoke's incidents, which
are already captured in `docs/evidence/t2.2-live-smoke/final-state.txt`.

## Consequences

**Easier.** T4.1b inherits an argument rather than a patch, and a corpus where every filter it
needs is a column. The seeding input cannot be widened without deleting a guard, which is a
visible act rather than a plausible refactor.

**Harder.** The embedding model is a large optional dependency, and a machine that has not
installed it can seed nothing — `make check` passes without it, and the first live seed will
be the first time the model is downloaded. Retrieval quality is also entirely unmeasured:
`RRF_K`, `retrieval_k`, the choice of section over document, and the model itself are four
decisions with no evidence between them, on a corpus of seven documents.

**A corpus of seven is not a corpus.** T6.4 commits to ≥50 documents and T7.1 grows the
catalog past 30 scenarios. Every ranking property claimed before then is measured on a
sample too small to have properties, and nothing here should be reported as retrieval
quality.

**Placeholders, named as such:** `RRF_K` (60), `retrieval_k` (5), and the 384-dimension model.
Each has a reason and none has a measurement, in the same class as ADR-0016's four.

**Revisit if:** the corpus passes ~10^5 chunks, which is ADR-0002's own trigger and is three
orders away; a second document type joins past incidents, since hand-authored runbooks carry
`origin: authored` and are never excluded (ADR-0008) and may want different chunking; or
T4.2 measures the section-level choice as worse than a document-level one, which is the
first real evidence any of this will get.
