# Q68 — how far does the retrieval benchmark move when nothing changes

**Registered 2026-09-15, before the measurement is run. $0.00** — every step is a re-seed and a
`faultline-retrieval score`, neither of which calls a model.

---

## 1. What was found, and why this needs measuring rather than just fixing

`PgVectorPastIncidentStore.search` orders both arms with no tiebreaker:

- dense: `ORDER BY embedding <=> %(v)s::vector LIMIT k`
- text: `ORDER BY ts_rank_cd(body_tsv, tq.q, N) DESC LIMIT k`

At a tie the rows returned are whichever the scan reaches first, which is heap order, which moves
when rows are rewritten. **Measured on the live corpus: 22 of the 43 golden queries have a tie
spanning the k boundary in the text arm alone** — rank `0.6` four ways, rank `3.9`, rank `0.2`.

It was found because two `faultline-retrieval score` runs over a corpus with **byte-identical
bodies and byte-identical embeddings** returned `recall@3 = 0.302` and `recall@3 = 0.326`. The
only thing that differed was that a re-seed had rewritten thirteen rows
([evidence](../../docs/evidence/t6.5-seed/2026-09-15-the-seed-that-could-not-update-a-heading.md)
§6, prediction 1, which registered that a move meant the reasoning was wrong and which is the
prediction that failed).

**The fix is one sort key per arm and it is not in dispute.** What is worth a measurement is the
thing the fix destroys: *how far has this instrument been moving all along*. `recall@3 = 0.395`,
`recall@5 = 0.442`, Q49's seven-row flag table and the `GATE_RECALL_AT_3` constant are each one
arbitrary resolution of those ties. After a tiebreaker lands the spread is zero by construction
and the question can never be asked again. **It is a claim about the record, not about the
future, which is why it is measured before the repair and not after.**

## 2. Procedure

No code changes at any point during the measurement. The corpus content is fixed: 311 chunks,
60 documents, `body_sha256 = cc473105c036…`.

1. **Control.** `faultline-retrieval score` twice with **no seed between them**.
2. **Five cycles.** `faultline-seed`, then `faultline-retrieval score`. Five times.

`body_sha256` is recorded at every cycle. It must not move; if it does, the corpus changed and
the measurement is about something else.

Autovacuum is not controlled and cannot be. That is part of what is being measured — the
instrument as it actually ran, not the instrument under a bench setup nobody used.

## 3. Registered predictions

1. **The control pair is identical**, to every digit, on every reported figure. Scoring a fixed
   store is deterministic; if the two controls differ, the wobble is not seeding and §1's
   account is wrong.
2. **The five cycles are not all equal.** At least two distinct values of `recall@3`.
3. **The range of `recall@3` across the five is 1 to 3 queries — 0.023 to 0.070.** Stated as a
   band because 22 of 43 queries tie somewhere, but a tie only changes recall when the two tied
   rows differ in *whether they are the labelled answer*, which is a strict subset.
4. **`body_sha256` is `cc473105c036…` at all five**, and the chunk count is 311 at all five.
5. **The synthesizer figure moves at least as much as the planner figure**, relatively. Its
   `recall@3` is 0.045 — one query of twenty-two — so a single tie flip is its whole number.

**If prediction 2 fails** — five identical readings — then re-seeding does not reshuffle the
heap, the 0.302 → 0.326 move has a cause not yet found, and the tiebreaker should not land until
it is, because a fix aimed at the wrong mechanism is how a real defect gets closed.

## 4. What is reported, and what is not

Reported: the seven values (control ×2, cycles ×5) for `recall@3`, `recall@5`, their MRRs, and
the planner and synthesizer splits; the range and the distinct-value count; and whether each
prediction held.

**Not reported: a "corrected" value for any published figure.** The measurement says how wide the
uncertainty on the record is. It does not say which of the values inside that width was right,
because none of them was — a tie has no right answer, only an arbitrary one. Any figure quoted
after this carries the range beside it or is quoted from a run made after the tiebreaker lands.

**And no cycle is discarded.** Five are run and five are reported, including any that is
inconvenient. The whole point of the number is its spread.
