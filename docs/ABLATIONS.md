# Ablations

**Four things have been removed from this pipeline to see what they were worth.** Each is reported
in full somewhere in [`evals/runs/`](../evals/runs/); until 2026-09-20 there was no document that
named them together, which is what G7's assessment found and this file answers
([`docs/GATES.md`](GATES.md)). **Nothing here is new evidence.** Every number is lifted from the
run document beside it, and where the two ever disagree, that document wins.

**What counts as an ablation here.** One component is withheld and everything else is held fixed —
the same scenarios, the same stamp, the same world, the same bounds — and both arms run under one
pre-registration written before either did. A comparison against a *baseline* (B0's no-LLM
heuristic, B1's single agent, B2's model prior) is a different thing and lives in
[`RESULTS.md`](RESULTS.md); a comparison against an earlier sweep is not an ablation at all,
because the world and the stamp moved with it.

**Two floors, and both matter more than any number below.** At ten scenarios and R = 3 the
registered minimum detectable effect is **16.2 pp**. Separately, dev sweep 12's A/A check —
arm A split alternately against itself, a difference produced by nothing at all — measured **10.0
pp on fault class**. So a delta under about ten points is indistinguishable from the instrument,
and one under sixteen was registered in advance as undetectable. **Three of the four results below
sit under both floors.** That is not a disappointment; it is the reason the floors were registered
first.

---

## 1. The traces specialist — the one effect that shows

**Dev sweep 12, 2026-09-11.** Arm A runs the full four-specialist pipeline; arm B is
`--without traces`. Ten dev scenarios, R = 3, world `90e9f29e…`, stamp `prompts:06f24e827915`.
Full report: [`SWEEP-2026-09-11-sweep12.md`](../evals/runs/SWEEP-2026-09-11-sweep12.md).

| axis | with traces (30) | without (34) | delta, paired |
|---|---|---|---|
| fault class, of answered | **26 / 27** | 20 / 27 | **+20.0 pp** [95 % CI −5.0, +46.7] |
| culprit service | **23 / 30** | 18 / 34 | — |
| fix class, of answered | 23 / 27 | 19 / 23 | +6.5 pp [−5.6, +20.4] |
| abstentions | 3 | 7 | — |
| median cost | \$0.713 | \$0.602 | **+\$0.10** [+\$0.06, +\$0.14] |

**The point estimate clears the MDE and the interval reaches zero.** The sweep says so itself:
*"what this sweep does not establish: that +20 pp is the size of it. The interval is [−5, +47]."*
**The cost delta is the only one whose interval excludes zero** — so the firmest thing this
ablation establishes is what the fourth specialist costs, not what it buys.

**Where the effect sits.** Not on the two `dependency_latency` scenarios the pre-registration
named — one is 3/3 in both arms, the other 0/3 on service in both. It sits on
`shipping-quote-misconfig` (3/3 against 0/4 on service), `cart-bad-image-tag` (3/3 against 1/3)
and `shipping-wrong-image` (3/3 against 2/4): deploy and config faults downstream of checkout,
where without a span tree the synthesizer watches checkout's log trail stop and names the next hop
by position. With traces, nine of nine.

## 2. The past-incident corpus — no measurable effect, and the sign reversed

**T6.5, 2026-09-17/18.** WITH arm retrieves from the 60-document corpus; WITHOUT arm has
same-class documents withheld. Ten dev scenarios, R = 3, 60 runs, **\$44.79**. Full report:
[`TRANSFER-2026-09-18-t6.5.md`](../evals/runs/TRANSFER-2026-09-18-t6.5.md).

| | WITH | WITHOUT | delta |
|---|---|---|---|
| **fault class**, abstentions excluded | 20 / 24 — 83.3 % | **25 / 27 — 92.6 %** | **−9.3 pp** |
| fault class, abstentions counted wrong | 20 / 30 | 25 / 30 | −16.7 pp |
| culprit service | 21 / 30 | 23 / 30 | −6.7 pp |
| **abstentions** | **6** | **3** | **+3** |

**The arm that read more scored lower, and the honest reading is that neither arm moved.** −9.3 pp
sits under the 16.2 pp MDE and under the ~10 pp the A/A check measured between two halves of one
configuration — and the report refuses the margin it technically won: *"prediction 3 held by 0.7 pp
against a floor estimated at '~10 pp', and that margin is not meaningful. The honest statement is
that the delta and the instrument's own noise are the same size."*

**The within-arm test is the one that settles it.** Inside the WITH arm, runs where a same-class
document actually surfaced scored **12/14 — 85.7 %**; runs where none did scored **8/10 — 80.0 %**.
If the corpus were doing the work, the difference would be here, and it is not.

**One result survives the variance argument.** Prediction 5 registered that *less* context should
produce *more* declining. The opposite happened — the WITH arm abstained twice as often, 6 against
3 — and every extra abstention sits on a scenario whose accuracy also fell. *"Whatever the larger
corpus did, it made the agent less willing to commit rather than better informed."* That is a
finding about behaviour, it is in the same direction on every scenario where anything moved, and it
does not depend on the accuracy delta being real.

**Four of seven predictions failed**, scored one by one in the report. **What it does not say**:
not that prior incidents do not help (this is a measurement *through this retriever*, whose
attenuation bound moved to `recall@3 = 0.302`); not that postmortems are worse than narratives
(the arms cannot separate them); not that the WITHOUT arm is better; and nothing about the holdout.

## 3. Text normalisation, flag 2 — cross-validated and rejected

**Q52, 2026-09-14**, 1000 splits, seed 20260914, **\$0.00** — no model call; the ablation is over a
retrieval index. Full report:
[`RETRIEVAL-2026-09-14-q52.md`](../evals/runs/RETRIEVAL-2026-09-14-q52.md).

| | k = 3 | k = 5 |
|---|---:|---:|
| in-sample margin of the best flag | +0.0233 | +0.1628 |
| **out-of-sample margin of the chosen flag** | **−0.0288** | +0.1545 |
| shrinkage as a share of the margin | **224 %** | 5 % |

**Flag 2 is not adopted; `TEXT_NORMALISATION` stays 0.** At k = 3 the flag that looks best in
sample is *worse than not selecting at all* out of sample — the shrinkage is more than twice the
margin it was chosen on. This is the ablation that most deserves to be copied: an in-sample win of
+0.0233 would have been adopted by anyone who did not hold out a test set, and it is negative.

## 4. Retrieval depth, k = 3 against k = 5 — a pilot, and it is labelled one

**Q53, 2026-09-14**, ten paired runs, **\$14.43** of a \$25 ceiling. Full report:
[`PILOT-2026-09-14-q53.md`](../evals/runs/PILOT-2026-09-14-q53.md).

**2 of 10 pairs produced a different `fault_class`, and in both the deeper arm is the correct one.**
This is the first measurement in this repository of whether the model *reads* a reachable document
and answers differently — the four retrieval write-ups before it measured reachability alone.

**Nothing is adopted and Q53 does not close.** `retrieval_k` stays 3. One or more pairs differing
was registered in advance as the outcome that *funds* a larger measurement rather than deciding
anything: **30–40 pairs at \$43–\$58, which is [Q58](QUEUE.md)**. Ten pairs carry no interval and
the report claims none.

---

## What none of these establishes

**No ablation here has been run on the holdout set.** All four are dev-only, which is where prompts
and retrieval were fitted — so each measures a component's contribution on the scenarios the
pipeline was tuned against. The holdout arm is finished at three entries on a world two
generations back ([ADR-0029](adr/0029-four-fault-classes-and-why-there-is-no-fifth.md)).

**None was run at the pipeline this repository runs today.** The newest is 2026-09-18;
self-instrumentation landed on the same day and no sweep has run since. Two gates are waiting on
that same missing sweep ([`GATES.md`](GATES.md), G4 and G6).

**And n is ten scenarios.** Every interval above is wide for that reason, and the two that are
narrow — the cost delta, and flag 2's shrinkage — are narrow because they measure something other
than accuracy. **The tables support direction, not magnitude**, which is the same sentence the
front door carries about the headline figures and applies here with more force.
