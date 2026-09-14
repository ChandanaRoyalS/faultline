# Pre-registration — Q49, the synthesizer regression and `ts_rank_cd`'s normalisation

**Written and committed before the flag is changed and before any query is re-scored.**

Q39 made the text arm disjunctive and the planner gained on every metric at both `k`. The
synthesizer did not: `recall@5` 0.273 → **0.182**, six of 22 answered down to four.

That was **predicted before it happened**. `PREREGISTRATION-Q39.md`'s prediction 7 said the
synthesizer would gain most, and carried its own counter-argument: *"synthesizer queries are long,
and a long query ORs into the widest match sets, so dilution should hurt them most. If prediction 7
fails, that is the reading to take."* It failed. This is that reading, acted on.

§2.2 of the same document deferred `ts_rank_cd`'s normalisation flags **by name**, for this:
*"an arm that matches 83% of the corpus is obviously sensitive to how rank is normalised, which is
precisely why changing it in the same commit would make the result uninterpretable."*

**Cost: $0.00.** Local embedder, arithmetic metrics, no authored content. Any model call is a defect.

---

## 1. The mechanism, stated so it can be wrong

`ts_rank_cd` with no normalisation does not divide by document length. A long chunk contains more
distinct lexemes, so under a disjunction it matches more of the query's terms and ranks higher —
whether or not it is *about* them. Synthesizer queries carry four specialist findings and name
several services, so they OR into the widest match sets in the corpus and hand the ordering to
whichever chunks are longest.

If that is what is happening, dividing the rank by a function of length should help the synthesizer
and cost the planner little. **If the synthesizer does not improve, the mechanism is not length**,
and this row should be struck rather than retried with another flag.

## 2. What was measured before this was written

Against Postgres 16.13 and the 211 authored chunks, counting how many of the 43 golden queries get
a different top-ranked chunk than the current `ts_rank_cd(..., 0)`:

| flag | divides rank by | top-1 moves |
|---:|---|---:|
| 1 | 1 + log(length) | 17 of 43 |
| 2 | length | 42 of 43 |
| 4 | mean harmonic distance between extents | 17 of 43 |
| 8 | number of unique words | 35 of 43 |
| 16 | 1 + log(unique words) | 18 of 43 |
| **32** | rank / (rank + 1) | **0 of 43** |

**Flag 32 is eliminated before any scoring, on argument rather than on a number.** `fuse()` is
reciprocal-rank fusion: it reads positions, not scores. `rank/(rank+1)` is monotone, so it cannot
change a position, and the zero above is confirmation rather than evidence. Any future proposal to
"normalise the score to 0..1" is the same no-op.

This is a mechanical property of a ranking function, of the same kind §1 of `PREREGISTRATION-Q39.md`
recorded. Nothing here is a retrieval-quality number and nothing was scored.

## 3. The change

`PgVectorPastIncidentStore.search`'s text arm moves from `ts_rank_cd(body_tsv, tq.q)` to
`ts_rank_cd(body_tsv, tq.q, 1)`. Nothing else moves: not the query construction, not the dense arm,
not `RRF_K`, not `retrieval_k`, not the corpus.

**One candidate, chosen on argument, not the best of six.** Flag 1 is the conventional mild length
normalisation and the one that addresses the named mechanism directly. Measuring all six against a
single 43-query golden set and adopting the winner would be selection on the test set — the
practice ADR-0018 records as the mistake behind its four unmeasured parameters, at a scale where
one query is 0.0233 and six draws from a noisy instrument will always produce a winner.

The other flags are **reported and not decisive**, so a reader can see the landscape without the
landscape having chosen anything.

## 4. The decision rule, fixed in advance

Under **ADR-0040**, which post-dates Q39 and governs this:

- **The deciding metric is `recall@3`** over all 43 queries — the depth production retrieves at.
  Tie-break `MRR@3`.
- **"No measured difference" is one query**, `1/43 = 0.0233`, the instrument's resolution. Not a
  constant: ADR-0040 clause 5 replaced the unreachable 0.02 band with exactly this.
- Within that band, **the change is not adopted** and flag 0 stands, because the simpler form wins
  ties.
- **Both `k` reported, all five partitions**, per ADR-0040 clause 3 — they are not nested.
- **One run**, deterministic. Re-runs are all reported.
- **The golden set is not touched.**
- The gate constants are recalibrated only if the change is adopted, by the rule
  `RETRIEVAL-2026-09-13-q39.md` §4.4 settled: the **tighter** of the registered relative margin and
  the standing constant.

## 5. Predictions

1. **Flag 32 changes no metric at all**, to three decimal places, at either `k`. Mechanical; listed
   so that a change here means my model of the pipeline is wrong, not that 32 is useful.
2. **Synthesizer `recall@3` rises above 0.182.** This is the prediction the row exists for.
3. **Planner `recall@3` does not fall below 0.571** — at most one query of 21 given up.
4. **Overall `recall@3` moves by at most two queries** (±0.047) in either direction.
5. **The decision is "no measured difference"** and flag 0 stands. I expect the synthesizer to gain
   and the planner to lose approximately what it gains. Registered because it is the outcome I
   think most likely and the one it would be most tempting to talk my way out of afterwards.
6. **Flag 2 is worse than flag 1 overall.** Dividing by raw length over-penalises long chunks that
   are long because they hold more content, and 42 of 43 top-1 results moving is a change of that
   size.
7. **`MRR@3` moves less than `recall@3` does, in absolute terms.**
8. **$0.00.**

## 6. What this cannot settle

- **Whether length is the mechanism.** If the synthesizer improves, length normalisation helped; it
  does not prove that long chunks winning was the cause rather than a correlate.
- **Whether the synthesizer's queries are the right queries.** They are what the pipeline sent,
  harvested from `trajectory_retrievals`. A synthesizer prompt that asked differently is a
  different change with a different registration.
- **Anything above `recall@5` = 0.605.** Q50: this is a reordering of the same candidate list and
  is capped by the ceiling Q42's falsification measured.
