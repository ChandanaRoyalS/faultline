# Pre-registration — dev sweep 9, the first sweep that can say which service broke

**Written and committed before any scenario runs.**

## Two generations, not one

Dev sweep 8 measured `bc222a353936`. The stamp has moved **twice** since, and a reader who assumes
one move will mis-attribute everything in this sweep.

| | stamp | what moved it |
|---|---|---|
| dev sweep 8 | `bc222a353936` | Batch B |
| Batch C | `7c6894e9dd92` | `TriageJudgement` entered `stamp._CONTRACTS` — the *set the stamp covers* grew; no behaviour changed |
| **this sweep** | **`ba8684b01201`** | `Verdict` gained `service` and `alternatives`; `SYNTHESIZER_SYSTEM` asks for both (T4.2) |

**`ba8684b01201` has never been run.** Neither has `7c6894e9dd92`: Batch C landed and no sweep
followed it, which is why the T4.2 contract change was made now — there were no figures on that
stamp to orphan. That was the right trade and it has a cost, paid here: **this sweep cannot
separate Batch C's effects from T4.2's**, and nothing in it should be read as attributing a
difference to either.

## The change this sweep cannot see, and must therefore say out loud

**Q23 moved the planner's behaviour and moved no digest at all.**

The planner now receives the top-3 similar past incidents that T3.2 always specified. That is a
real change to what a model is shown, and `prompt_digest` covers system prompts and contract
schemas — **a briefing's contents are neither**. Batch C measured it: the digest read
`7c6894e9dd92` before and after.

> **A reader comparing sweep 8 to sweep 9 by stamp alone will attribute any planner difference to
> the T4.2 prompt move. That attribution would be wrong.**

This row exists because Q23's queue entry said in advance that the sweep governing it must say so.
It is recorded in `trajectory_retrievals` with its `excluded_count`, so the fact of retrieval is
checkable per run even though the stamp is silent about it.

## What is genuinely new in the run

| | change | first observation? |
|---|---|---|
| **Culprit service, scored** | The verdict names a service, and it is scored against `injection.target` | **yes — in any sweep, ever** |
| **Ranked alternatives** | Up to two runners-up with `why_not`, scored as top-3 | **yes** |
| Planner retrieval | Top-3 past incidents reach the planner (Q23) | **yes** — and invisible to the stamp |
| `model_map` | `AGENT_ROLES` gained `triage` and `proposer` (Q22) | no — a frozen key, not behaviour |
| **B0.2 as an arm** | The corrected no-LLM heuristic, at \$0.00 per run | **yes** |

The service axis is the one worth stating plainly: **until T4.2 this benchmark never scored which
service broke.** It graded triage recall/precision, `fault_class` and `remediation_class`. Every
accuracy figure this project has published is about the *mechanism* and none is about the
*culprit*, and this is the first sweep where that stops being true.

## Scope: five scenarios, plus B0.2 on the same five

Sweep 8 scored five of eight. The three it could not reach — `product-catalog-flag-failure`,
`shipping-quote-misconfig`, `shipping-wrong-image` — failed on a credit-balance error, not on
anything about the pipeline, and **remain unmeasured on any pipeline after Batch B.**

**Registered scope: the same five sweep 8 scored, one run each, plus B0.2 on those five.** Five,
not eight, because a sweep that pairs against sweep 8 needs the scenarios sweep 8 actually scored;
the other three would be first observations mixed into a comparison and would weaken both.

**B1 and B2 are out of scope for this sweep** and that is a budget decision, not a methodological
one. B0.2 is in because it makes no model call: its cost is \$0.00 and its inclusion is free.

## The predictions

### 1. Every scored run names a service

**Registered: 5 of 5 return a non-empty `service`.** The field defaults to empty so old artifacts
still validate, which means an empty one here is not a schema failure — it is the synthesizer
declining to answer a question its prompt asks. **One empty service is a defect in the prompt, not
an abstention**, and would mean the field was added without being asked for convincingly.

### 2. The pipeline names the culprit, not the propagator, on `ad-memory-squeeze`

**Registered: `adservice`, not `frontend`.**

This is the sharpest single prediction in the document because **B0 v1 failed exactly here.** It
picked the earliest alerting service, which is `frontend` — the propagator — found no change on it,
and answered `dependency_latency` against a truth of `resource_exhaustion`. ADR-0020 §6 names this
trap: `start_from` is an entry point, not a culprit claim.

The pipeline has always got the *class* right on this scenario, across every sweep that ran it. It
has never been asked for the *service*. **If it names `frontend`, the pipeline has been passing
this scenario for the right class and the wrong reason**, and five sweeps of `resource_exhaustion`
✔ would need re-reading.

### 3. Top-3 adds almost nothing at this catalog size

**Registered: `gained_by_ranking` is true on at most 1 of 5 runs**, and plausibly 0.

Top-3 can only exceed top-1 when the first answer is wrong and a later one is right. Sweep 8 got
four of five classes right at top-1, so there are at most one or two runs where ranking has
anything to add. **A top-3 figure much above top-1 here would be surprising and would need
explaining**, not celebrating.

### 4. `depth` is greater than 1 on most runs — and if it is not, the field is decorative

**Registered: at least 3 of 5 runs carry at least one alternative.**

An empty `alternatives` list is a legal answer, deliberately: an incident whose evidence admits one
explanation should say so. But if the list is empty *everywhere*, then top-3 equals top-1 by
construction, the field is costing tokens for nothing, and the honest response is to say the
synthesizer does not rank rather than to publish a top-3 column. **This prediction is how that gets
found out on the first sweep instead of the fourth.**

### 5. Triage is byte-identical to sweep 8

**Registered: recall and precision exactly sweep 8's, on all four scenarios it recorded.**

| scenario | sweep 8 recall / precision |
|---|---|
| `ad-memory-squeeze` | 1.00 / 0.43 |
| `cart-dependency-latency` | 1.00 / 0.33 |
| `cart-redis-misconfig` | 0.80 / 0.67 |
| `frauddetection-memory-squeeze` | 1.00 / 1.00 |

Nothing since Batch B has touched the blast-radius traversal. **A difference is a defect, not
variance** — the traversal is deterministic over a fixed graph.

### 6. `cart-bad-image-tag` is registered as unsettled, and a second failure would be a pattern

Sweep 8 got it **wrong** — the only `bad_deploy` scenario measured, and the class scored 0 of 1.
Nothing since then targets it. **No outcome is predicted.**

What *is* registered: **if it fails again, that is the second consecutive failure on the only
`bad_deploy` scenario this pipeline has measured, and it stops being an instance.** It would mean
the class has a systematic problem rather than a sample of one, and it belongs in the next
pre-registration as a named investigation rather than as another unsettled row.

### 7. B0.2 does not beat the pipeline, and its cost is \$0.00

**Registered: B0.2 scores below the pipeline on fault class, and its cost is exactly zero.**

The zero is a measurement, not a missing value — B0 makes no model call. If B0.2 *matches* the
pipeline across five scenarios, that is the most consequential result this sweep can produce and
it goes at the top of the sweep document, not in a footnote. The plan's reason for baselines is
exactly this: *"you need to be the one who discovers that."*

**B0 v1's single run is not comparable to any of this.** Its runtime is the unversioned
`faultline/0.0.1+baseline:B0`; v2 is `B0.2`; the eval database cannot pool them.

### 8. Cost, registered so an overrun is visible as one

Sweep 8's five counted runs cost **\$3.4796**, about \$0.70 each. This pipeline asks the
synthesizer for two extra fields and a short reason per alternative, which lengthens one reply and
no brief.

**Registered: \$3.50–\$5.00 for the five runs, plus judge. B0.2 adds \$0.00.** Materially above
that is a finding about the alternatives field, not noise.

### 9. Discards below 10%, and if they are not, the cause is named

Sweep 8 recorded **16 non-scored outcomes against 6 scored** — a 32% discard rate at the run level,
and most of it was one cause: a credit-balance error mid-sweep. That is a property of the account,
not of the pipeline.

**Registered: with credits funded, non-scored outcomes fall below 10%.** If they do not, the sweep
document names which cause replaced credits, because a discard rate that stays constant while its
cause changes is the number most likely to be reported as if it were stable.

## What would surprise me

1. **`frontend` named as the culprit on `ad-memory-squeeze`** — prediction 2, and the one that
   would reframe five sweeps of results.
2. **Every `alternatives` list empty** — prediction 4. Top-3 would be top-1 wearing a hat.
3. **Any triage number moving** — prediction 5. The traversal is deterministic.
4. **B0.2 matching the pipeline** — prediction 7.
5. **A run halting on the dollar cap.** Six sweeps have never exhausted a bound.
6. **A scored run with an empty service** — prediction 1. It would mean the prompt asks for
   something the model does not treat as required.

## Order of operations

1. **Confirm the stamp reads `ba8684b01201`** before anything is injected. A move after this
   document is committed means the sweep is measuring something nobody planned to measure, and the
   sweep stops rather than proceeding. `uv run pytest tests/test_harness_run.py -k stamp` asserts
   it against the ledger.
2. Confirm the capability and world generation are unchanged from sweep 8 — `cap:c4d52d00`,
   `f5bd108f4f70`. A world move makes this a different comparison and belongs in this document
   rather than in the sweep's.
3. Run **B0.2** on the five scenarios first. It costs nothing, it exercises injection and revert on
   every scenario, and a failure there is a harness failure discovered before any money is spent.
4. Run the five pipeline scenarios, **one each, no re-runs.** A discard is recorded and never
   re-run to improve a number.
5. Score, judge, and write the sweep document against these nine predictions — **including the ones
   that fail**, which is the only reason to write them down first.
