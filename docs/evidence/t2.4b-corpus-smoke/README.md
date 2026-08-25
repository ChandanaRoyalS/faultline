# T2.4b evidence — the corpus seeded live, and axis 2 demonstrated

ADR-0008 specified two contamination defences. The path quarantine has been enforceable
since T1.6. The second — leave-one-out exclusion, where a scenario must not retrieve its own
rehearsal — has been a design since August 23rd and nothing more. **This is the first run
where it is a measured behaviour**, against real vectors in real pgvector, with the evidence
committed beside it.

| | |
|---|---|
| seeded | 2026-08-25, `evals/scenarios/artifacts/dev/` |
| store | `faultline-postgres-1`, `pgvector/pgvector:pg16`, extension `vector 0.8.6` |
| embedder | `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, local |
| result | **7 documents, 35 chunks**, 0 holdout chunks |

## Files

- **`store-state.txt`** — `psql` after the seed: per-document chunk counts, the embedder
  stamp beside `vector_dims(embedding)`, and the holdout count.

## The seed

```
documents=7 chunks=35
seeded : ad-memory-squeeze, cart-bad-image-tag, cart-dependency-latency,
         cart-redis-misconfig, frauddetection-memory-squeeze,
         product-catalog-flag-failure, shipping-wrong-image
skipped: [('currency-cpu-throttle', 'bundle is marked INVALID'),
          ('flag-service-crashloop', 'bundle is marked INVALID')]
```

Nine dev bundles carry a narrative and seven were seeded. The two skipped by name are
**`currency-cpu-throttle`** and **`flag-service-crashloop`**, both marked `INVALID.md`: they
are blocked scenarios whose faults produced nothing observable, so seeding them would put two
incidents in the corpus that never happened. The skip is reported rather than silent, which is
how the count reads as a decision instead of a discrepancy.

This matched `tests/test_corpus.py` exactly — the hermetic test asserts the same 7 and 35
against a fake embedder and a dict.

## Store state

Every document holds exactly five chunks, one per narrative section:

```
              document_id               | count
----------------------------------------+-------
 scenario:ad-memory-squeeze             |     5
 scenario:cart-bad-image-tag            |     5
 scenario:cart-dependency-latency       |     5
 scenario:cart-redis-misconfig          |     5
 scenario:frauddetection-memory-squeeze |     5
 scenario:product-catalog-flag-failure  |     5
 scenario:shipping-wrong-image          |     5
```

**The embedder stamp agrees with what the database actually holds** — the one check that
could not be made without a live pgvector:

```
                embedder                | dimensions | vector_dims
----------------------------------------+------------+-------------
 sentence-transformers/all-MiniLM-L6-v2 |        384 |         384
```

ADR-0018 records the vector's provenance on every chunk so that a model swap leaving old and
new vectors mixed is visible in the data rather than degrading retrieval silently. This row
is that column verified against the vector beside it, not against the code that wrote it.

```
 holdout_chunks
----------------
              0
```

## The axis-2 pair, verbatim

Query: `ad-memory-squeeze`'s own **What was observed** section, read from its bundle.

> The page was `ServiceHighErrorRate` on **frontend** and **loadgenerator** together, 3m30s
> after onset. No service between them and the edge was named. frontend's alert then did so …

```
--- WITHOUT exclude_origin
  1. ad-memory-squeeze                What was observed    score=0.0328 dense=1 text=1
  2. ad-memory-squeeze                Detection notes      score=0.0161 dense=2 text=None
  3. cart-redis-misconfig             What was observed    score=0.0159 dense=3 text=None

--- WITH exclude_origin="scenario:ad-memory-squeeze"
  1. cart-redis-misconfig             What was observed    score=0.0164 dense=1 text=None
  2. product-catalog-flag-failure     What was observed    score=0.0161 dense=2 text=None
  3. cart-bad-image-tag               What was observed    score=0.0159 dense=3 text=None
```

**The unexcluded block is the leak in its predicted shape.** A scenario's own symptoms
retrieve its own narrative in the top *two* slots, and slot 1 is the only hit anywhere in the
run where both arms agree — `dense=1 text=1`. The dense and full-text arms independently rank
one document above every other document in the corpus, and that document is the query's own
source. ADR-0008 describes this as the agent not diagnosing the incident but looking up the
answer key; here it is the ranking rather than the argument.

**The excluded block is the defence working.** Both `ad-memory-squeeze` chunks are gone and
three other dev incidents take their place: `cart-redis-misconfig`, `product-catalog-flag-failure`,
`cart-bad-image-tag`. The corpus still answers — exclusion removes one scenario, not
retrieval.

Two details worth keeping:

- **Every survivor is a *What was observed* section.** ADR-0018 chose the section over the
  document because an agent arrives holding symptoms and that is the surface which resembles
  them. This is that argument as an observation.
- **This is within-split leakage.** All seven documents are dev, so the path quarantine is
  structurally blind to it and was never going to catch it. The two defences are not
  substitutes, which is exactly why ADR-0008 separates the axes.

## What this smoke did not exercise

- **Retrieval quality.** Three plausible neighbours is not a relevance measurement. The
  scores — 0.0164 / 0.0161 / 0.0159 — are flat and nearly tied across three unrelated
  scenarios, which is what a seven-document corpus with a single text-arm hit looks like.
  ADR-0018 says nothing here should be reported as retrieval quality until T6.4 (≥50
  documents) and T7.1 (30+ scenarios); this run is evidence for that caution, not against it.
- **Idempotent re-seed.** The store upserts on `ON CONFLICT (id) DO UPDATE`, and the seeder
  was run exactly once. Whether a second run leaves 35 chunks rather than 70 is tested and
  unobserved.
- **The model-download path on a clean machine.** The weights were already cached when the
  live seed ran, so the first-download branch — the one step `make check` can never cover —
  has not been watched end to end.
- **The `faultline-seed` CLI against the real store.** The entry point did not exist at smoke
  time and the seed ran through a module invocation. The CLI landed afterwards and its
  `--dry-run` reproduces the same 7 and 35, but no live run has gone through it.

## Reproducing

```bash
uv sync --extra embeddings
uv run faultline-seed --create-schema          # --dry-run first, for the guards without a DB
docker exec -i faultline-postgres-1 psql -U faultline -d faultline \
  -c "SELECT document_id, count(*) FROM incident_chunks GROUP BY 1 ORDER BY 1;"
```
