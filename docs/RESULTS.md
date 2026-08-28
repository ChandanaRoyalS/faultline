# Results

Everything here was produced by running the system against a pinned OpenTelemetry demo world with
labelled, reversible faults. Raw runs, per-run manifests and the sweep reports are in
[`evals/runs/`](../evals/runs/); this document is the method and what the record supports.

**Agent `claude-opus-5` · judge `claude-haiku-4-5` · SHARED LINEAGE on every judged figure.**

---

## Method

### The two contamination axes, and how each is checked

[ADR-0008](adr/0008-contamination-model.md) names two, and both are verified rather than asserted.

**Axis 1 — split quarantine.** Three scenarios were assigned to holdout *at authoring*, before
any artifact existed. Their narratives never entered the retrieval corpus, and no prompt, context
window or corpus in this pipeline was ever fitted against them. Checked at freeze time:

```
corpus: 35 rows, 7 documents, holdout_chunks = 0
```

Re-checked after the holdout run: still 0. The seven corpus documents are the seven dev
scenarios; **not one chunk of any held-out scenario has ever been retrievable**.

**Axis 2 — run-time self-exclusion.** A scenario's own artifacts are unreachable while it is
being scored. Every retrieval carries `exclude_origin` and every one is recorded:

```
trajectory_retrievals: 26 rows · 26 carry exclude_origin · 0 returned their own origin
```

This is the assertion [ADR-0008](adr/0008-contamination-model.md) said must be checked at eval
time rather than trusted, and the column has been on the table since T3.2 precisely so it could be.

**A fifth axis — judge contamination.** The judge is a separate setting with no default; unset,
narrative scoring refuses to run. Lineage is checked at eval time at the **vendor-family** level,
and a violation refuses by default and must be opted into by name, after which it is stamped on
every figure. This project holds one provider's credentials, so every available judge violates
the rule. **The label is on every judged number in this document.**

### The freeze

[ADR-0022 §3.3](adr/0022-evaluation-harness.md) requires that "frozen" mean something a script can
check. Six items are hashed before a holdout run and re-checked after: prompts, corpus, model map,
budget, tool layer, judge. The manifest
([`FREEZE-2026-08-26-holdout.json`](../evals/runs/FREEZE-2026-08-26-holdout.json)) was committed
as its own commit **before any holdout scenario ran**.

After the run, five of six were byte-identical. The sixth — the tool-layer git sha — moved by
exactly one commit, the freeze commit itself, with no change to `src/faultline/`. That is a
self-reference flaw in the manifest and it was **recorded, not fixed**: fixing anything during a
holdout run is what the freeze exists to prevent.

### The pipeline stamp

`runtime_version` is derived, not typed: the package version plus a digest over every role system
prompt and every contract schema — the two things that determine what the agent *is*. It moves
when and only when the agent changes, so a table can say which pipeline produced it. Two stamps
appear in this document:

| stamp | what it is |
|---|---|
| `prompts:59bf438b2a96` | dev sweep 1 |
| `prompts:53fafe9c12bc` | dev sweeps 2 and 3, **the holdout run**, and both variance experiments — the synthesizer taught the taxonomy. Sweep 3 raised a budget bound and moved no prompt, which is why it shares sweep 2's stamp: ADR-0022 keeps budget out of the digest so that raising a bound reads as the same agent given more room. |
| `prompts:bf7605651ef2` | **dev sweep 4 only** — the planner taught that an empty stream is silence rather than a bad query (T4.12). Measured net harmful against a floor registered before the run — coverage 6/7 → 4/7 — and **reverted**. This stamp was HEAD for the length of one sweep and exists now only in that sweep's record. |
| `prompts:1b0e7cbb4c47` | **dev sweep 5 and current HEAD** — T4.12's instruction decomposed: silence changes the evidence **class**, not the **subject**, and a localized service keeps its claim until its evidence classes are exhausted (T4.14). Every registered condition met; **coverage 7/7, fault class 7/7**. |

A test pins the current value and fails loudly if it moves, with the reason spelled out.

**The holdout has now been entered three times, under two stamps, and each table says which.**
Entries 1 and 2 measured `53fafe9c12bc`; entry 3 measured `1b0e7cbb4c47`, which is HEAD. Entries 1
and 2 stand unedited as measurements of a prior agent — supersession resolved by re-entering under
a pre-registered protocol rather than by leaving the figure stale, which is the third distinct way
this project has handled it (see
[ADR-0023](adr/0023-a-freeze-manifest-outlives-the-pipeline-it-froze.md)). Nothing about the holdout run has
changed and its figures stand exactly as measured — but they are a measurement of a prior agent,
and no claim here extends them to the current one. Re-entering the holdout under the new stamp is
a separate decision with its own pre-registration under ADR-0022's protocol, and it has not been
made. See [ADR-0023](adr/0023-a-freeze-manifest-outlives-the-pipeline-it-froze.md), which is where
this obligation to say so instead of asserting it in a test comes from.

### Every figure below was measured against a world that no longer exists

T7.1 changed four things about the world — kafka's heap is capped, `otel-col`'s limit is 600M,
Prometheus keeps 15 days instead of 6 hours, and the flag-service stub variants are renamed — and
re-recorded all twelve scenario bundles against the result. `world.compose_digest` moved from
`4a7690c6fdda…` to `299d791c5e0d…` and `ffs_stub_source_digest` from `5d06a3668aa0…` to
`8defed3104c4…`.

**Nothing in this document was re-measured.** Every dev sweep, every variance experiment, every
holdout entry and the retrieval corpus behind them were produced against the **old** world, and
they stand exactly as measured. What changes is what they can be compared to:

- **A future run is not comparable to any figure here.** It would differ in the agent *and* the
  world, and this document cannot separate those. Comparing across the digest boundary is
  comparing across worlds.
- **The corpus is old-world too.** It was seeded from the dev narratives as they were before the
  re-record, and those narratives have now been rewritten against new evidence — see
  [the reconciliation record](evidence/t7.1-reconciliation/README.md) for what changed. Re-seeding
  is a separate decision and has not been made.
- **The holdout entries are the sharpest case.** All three were measured on the old world; the
  set has been used three times already, and ADR-0022's T4.15 addendum records that it should not
  be entered again before it is re-authored or extended.

The re-record was deliberately kept separate from any measurement: **no sweep and no holdout entry
was run in T7.1.** What the new world is worth measuring against is a decision with its own
argument to make, and making it in the same task that moved the world would have confounded the
two.

The re-record also moved the narratives these figures were partly reasoned from. Three observations
were **removed** rather than softened because the new captures no longer contain them, and one
inference — that a fast all-clear proves nothing restarted — was **refuted by the re-record itself**,
since a scenario that does require a process to come back cleared faster. Details are in the
reconciliation record.

### Honest n

- No figure without its n.
- No aggregate without its per-class table.
- **A narrative claim can be true when written and false later, and nothing was catching it.**
  T7.7 audited every narrative against the current tool surface and the re-recorded bundles. Three
  claims were **unsupportable** and removed, three were **true but carrying unstated uncertainty**
  and are now qualified with its size, one count was wrong. The two causes are distinct: a
  **re-record** changes what was seen — already guarded by `recorded_from` — and a **capability
  arriving** changes what could have been seen, which nothing guards at all. Four narratives
  asserted *"what changed: nothing"* from before a change log existed; `ad-memory-squeeze` asserted
  its logs held *"not even a startup banner"* while the re-recorded capture holds **sixteen**.

  **A series' end is a soft edge everywhere.** Prometheus serves the last scrape forward for five
  minutes, so a series *appearing* is sharp to one scrape and a series *disappearing* is late by up
  to five minutes, always in the same direction. Measured, not assumed: `cart-bad-image-tag`'s
  runtime series stay visible until T+300s while its logs place the shutdown at T+0. Three
  narratives dated a death from a series end; all three now say what that dating is worth. **No
  figure moves** — none of this touches a scored run.
- **What is replayable for runs already recorded, and what is not.** A trajectory stores every
  tool result verbatim, so the tool evidence any past run saw reads today exactly as it read
  then. **Its retrieval evidence does not.** Until T7.9 a retrieval row held chunk *ids*, and ids
  do not keep pointing at the same words — the corpus is re-seeded whenever a narrative is
  corrected. For every run recorded before T7.9, **the retrieved text is gone**: not stale, gone,
  and not reconstructible, because the corpus that produced it has been overwritten and
  `superseded/` archives manifests and metrics but never narratives.

  So for a past run you can still say **what was retrieved** (the ids, and the `exclude_origin`
  that proves the contamination filter fired) and **what the tools returned** (verbatim). You
  cannot say **what the retrieval said**. T7.9 fixed that going forward — the rendered lines are
  stored beside a hash, the same shape as tool envelopes — and fixed nothing backwards. **No
  figure moves either way**: retrieval is an input to a run, and no run is re-scored.
- **The corpus is a living document, and stored trajectories point into it.** T7.6 rewrote four
  narratives so every claim rests on evidence the four-tool surface can reach; three are dev
  scenarios and therefore corpus material, and the corpus was re-seeded — 35 chunks, 7 documents,
  `holdout_chunks` still **0**. **39 of 62 stored trajectories retrieved a chunk whose text has
  since changed** (`cart-bad-image-tag` 39 retrievals, `cart-redis-misconfig` 25,
  `cart-dependency-latency` 6). **T7.7 changed two more** — `ad-memory-squeeze` and
  `frauddetection-memory-squeeze`, 62 retrievals across **41 of 62** trajectories, the largest
  single overlap yet, because `ad-memory-squeeze` is the most-retrieved document in the corpus. Those runs' retrieval rows still name the chunk they were given,
  and the chunk id still resolves — but the prose behind it now reads differently, so a reader
  reconstructing what an agent saw from the *current* corpus will not see quite what that agent
  saw. **No figure moves**: retrieval is an input to a run, the runs are not re-scored, and the
  rewrites corrected claims about the *tools* rather than about the faults. What is lost is exact
  replayability of the retrieved text, and the `superseded/` archives do not cover narratives.
- **An abstention is not one thing.** T7.4 measured, per scenario, which evidence classes could
  even in principle answer *"was the target idle or absent"* — only runtime metrics and logs can,
  since span and trace absence *is* the ambiguity and change history says what changed rather than
  what is running. **Two of twelve scenarios have no such class**: `product-catalog-flag-failure`'s
  target emits 2 log lines and no runtime series, and `productcatalog-dependency-latency`'s emits
  **0** log lines and none. T4.11's **5/5 stable abstention** is on the first of those.

  From T7.5 every bundle records this, derived from its own captures, and every run's report and
  manifest carry it beside the verdict — so an abstention forced by unreachability is *visibly*
  different from one produced by an agent that had the evidence and reasoned badly. **Nothing is
  forgiven**: no figure on this page is weighted, excluded or adjusted by it, and a test pins that
  two runs identical but for reachability score byte-identically. A scorer deciding which
  abstentions were excusable would be grading on sympathy. The reader gets to make that judgement
  with the fact in front of them; the scorer does not make it for them.
- **Accuracy and coverage are never quoted apart.** An `unknown` verdict is an abstention: out of
  the accuracy ratio entirely, reported as coverage.
- Blast-radius **recall and precision are a pair and never combined** — no F-score. The two answer
  different questions and [ADR-0017](adr/0017-context-layer-graph-and-dependency-policy.md) has a
  live hypothesis riding on recall alone.
- Unmeasured graph edges are quoted on every blast-radius figure.
- **Per-scenario rows are the floor for any behavioural claim.** A per-class table is required
  above, and T4.12 showed it is not sufficient. Between dev sweeps 3 and 4 the `bad_config` row
  read identically — n = 2, one answered, one abstained — while **its two scenarios swapped
  places**: `cart-redis-misconfig` answered in S3 and abstained in S4, and
  `product-catalog-flag-failure` did the exact reverse. That row reported "no change" for the
  single largest behavioural change in the sweep. With n = 2 per class, one gain and one loss
  cancel exactly, and the aggregate cannot distinguish "nothing happened" from "everything
  happened and netted out." Any claim about *what the agent does* is quoted from the
  per-scenario table, not the per-class one.

### Run protocol

Every run: a **baseline gate that refuses rather than warns** (it aborts before injecting if the
world is not quiet), a **world lock** so there is one driver, injection, correlation, the
investigation invoked as a subprocess through its own CLI, revert, and a recovery check using the
same readings as the gate. Discards are recorded with reasons and never deleted. **Holdout is
never re-run to fix a number.**

---

## The tables

### Holdout — n = 3, and **three entries under two stamps**

Every entry is numbered and counted in [ADR-0022's ledger](adr/0022-evaluation-harness.md); the
number of holdout runs is deliberately impossible to hide. **Each table below says which pipeline
produced it, because they are not the same agent.**

#### Entry 3 — stamp `prompts:1b0e7cbb4c47` (**current HEAD**), `changes` bound 8

| scenario | ground truth | fault class | class of fix | judge |
|---|---|---|---|---|
| email-wrong-image | `bad_deploy` / `rollback` | **`bad_deploy`** ✔ | **`rollback`** ✔ | `same_mechanism` |
| productcatalog-dependency-latency | `dependency_latency` / `restart` | **`dependency_latency`** ✔ | `config_revert` ✘ | `same_mechanism` |
| recommendation-memory-squeeze | `resource_exhaustion` / `config_revert` | **`resource_exhaustion`** ✔ | **`config_revert`** ✔ | `same_mechanism` |

| per class | n | fault / answered | fix / answered | abstained |
|---|---|---|---|---|
| `bad_deploy` | 1 | **1 / 1** | **1 / 1** | 0 |
| `dependency_latency` | 1 | **1 / 1** | 0 / 1 | 0 |
| `resource_exhaustion` | 1 | **1 / 1** | **1 / 1** | 0 |
| `bad_config` · `scale` | **0** | no holdout scenario | | |

Coverage **3/3**, fault class **3/3**, fix **2/3**. Triage recall **1.00** on all three. Budget
exhausted **0 of 3**. Cost $1.68 agent + $0.11 judge
([`HOLDOUT-2026-08-27-entry3.md`](../evals/runs/HOLDOUT-2026-08-27-entry3.md)).

**Read two caveats before quoting 3/3.** `email-wrong-image`'s row is **corroborative, not
confirmatory** — entry 2's finding on that scenario is in the lineage of the instruction entry 3
tests, which ADR-0022's T4.15 addendum records as condition 2 met under strain.
`recommendation-memory-squeeze` is the row that carries weight: never read for a mechanism, and it
abstained in entry 1. And n = 3 with no interval is not a benchmark.

#### Entry 1 — stamp `prompts:53fafe9c12bc`, `changes` bound 4

**Stands unedited.** This is a measurement of a prior pipeline, kept because the sequence is the
point.

| scenario | ground truth | fault class | class of fix | judge |
|---|---|---|---|---|
| email-wrong-image | `bad_deploy` / `rollback` | `unknown` — abstained | abstained | `different` |
| productcatalog-dependency-latency | `dependency_latency` / `restart` | **`dependency_latency`** ✔ | `config_revert` ✘ | `same_mechanism` |
| recommendation-memory-squeeze | `resource_exhaustion` / `config_revert` | `unknown` — abstained | abstained | `different` |

| per class | n | fault / answered | fix / answered | abstained |
|---|---|---|---|---|
| `bad_deploy` | 1 | — / 0 | — / 0 | 1 |
| `dependency_latency` | 1 | **1 / 1** | 0 / 1 | 0 |
| `resource_exhaustion` | 1 | — / 0 | — / 0 | 1 |
| `bad_config` · `scale` | 0 | no holdout scenario | | |

Triage recall **1.00**, precision 0.32, 9 unmeasured edges — **unchanged by T7.3's rescore**, as every holdout figure is. **Budget exhausted 2 of 3** — both
abstentions carry that signature, which is what entries 2 and 3 went on to chase. Flagged 0 ·
failed-alone 0 · contradictions 0 · narrative refused 0. Cost $1.08 agent + $0.12 judge.

#### Entry 2 — stamp `prompts:53fafe9c12bc`, `changes` bound 8, **1 of 3 scored**

`email-wrong-image` abstained again with the bound raised and **nothing exhausted**, having never
dispatched at `emailservice` at all. The other two were discarded to an empty API account before
their first model call and were not re-run
([`HOLDOUT-2026-08-26-entry2.md`](../evals/runs/HOLDOUT-2026-08-26-entry2.md)). $0.42, no judge.

### Dev — **not a benchmark.** n = 7 per sweep

Dev is where prompts and retrieval were fitted. These are shown to say what the same pipelines did
on scenarios they were developed against.

| | sweep 1 `59bf438b2a96` | sweep 2 `53fafe9c12bc` |
|---|---|---|
| fault class, of answered | 4 / 7 | 4 / 4 |
| coverage | 7 / 7 | 4 / 7 |
| class of fix, of answered | 6 / 7 | 3 / 4 |
| triage recall / precision | ~~0.94 / 0.56~~ **0.94 / 0.60** | ~~0.95 / 0.57~~ **0.95 / 0.60** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_
| judge same / adjacent / different | 7 / 0 / 0 | 4 / 0 / 3 |
| dead ends closed / missed | 42 / 35 | 31 / 29 |
| traps taken | 1 | 3 |
| budget exhausted | 1 | 2 |
| cost | $2.92 | $3.27 |

| per class | n | S1 fault | S2 fault | S2 abstained |
|---|---|---|---|---|
| `bad_config` | 2 | 2 / 2 | 1 / 1 | 1 |
| `bad_deploy` | 2 | 2 / 2 | 1 / 1 | 1 |
| `dependency_latency` | 1 | **0 / 1** | **1 / 1** | 0 |
| `resource_exhaustion` | 2 | **0 / 2** | **1 / 1** | 1 |

### Dev sweep 5 — return to the locus, and the best dev result yet

T4.14 ran the formulation T4.12's regressions decomposed, pre-registered before the run
([`SWEEP-2026-08-27-locus.md`](../evals/runs/SWEEP-2026-08-27-locus.md)). One addition to the
planner prompt; budget unchanged, so both S3 and S4 are live comparisons.

**Every registered condition met. Coverage 7/7, fault class 7/7** — the first sweep here where
every dev scenario was answered and every answer was right — on **47** tool calls against S3's 58.

| | sweep 3 `53fafe9c12bc` | sweep 4 `bf7605651ef2` | **sweep 5 `1b0e7cbb4c47`** |
|---|---|---|---|
| coverage | 6 / 7 | 4 / 7 | **7 / 7** |
| fault class, of answered | 6 / 6 | 4 / 4 | **7 / 7** |
| class of fix, of answered | 5 / 6 | 3 / 4 | **6 / 7** |
| failing-service dispatches, total | 25 | 15 | **26** |
| scenarios collapsed to ≤ 1 there | 0 | **3** | **0** |
| evidence classes at the failing service | 20 | 17 | **25** |
| judge same / different | 6 / 0 | 4 / 3 | **6 / 1** |
| triage recall / precision | ~~0.91 / 0.54~~ **0.92 / 0.58** | ~~0.92 / 0.56~~ **0.92 / 0.59** | ~~0.90 / 0.54~~ **0.91 / 0.57** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_

The **primary endpoint was registered ahead of coverage** — failing-service dispatches, because
S4 measured that as what predicts the outcome — and it moved with the result on five of seven
scenarios. The falsifier registered as most likely to be misread as a win (coverage rising with
the counts unmoved) did not fire.

**Read the dev caveat above before quoting 7/7.** Dev is where prompts were fitted; three stamps
have now been selected against these seven scenarios, and this is the sweep that stopped. What
7/7 licenses is "the instruction did what it was predicted to do", not "the system solves
incidents". Holdout has not been re-entered under this stamp.

What did not improve is recorded beside it: triage was flat (the control), `cart-bad-image-tag`
returned a correct class with a narrative the judge scored `different`, `cart-dependency-latency`
still returns the wrong fix class, and re-issues held at 2 rather than reaching zero.

### Dev sweep 4 — the evidence-class instruction, measured and not recommended

T4.12 tested the mechanism T4.11 found, with the prediction registered before the run
([`SWEEP-2026-08-27-evidence.md`](../evals/runs/SWEEP-2026-08-27-evidence.md)). One addition to the
planner prompt; budget unchanged, so the prompt was the only delta against sweep 3.

**Tested under `bf7605651ef2`, rejected per the pre-registration, reverted — that stamp exists
only in this record.** The prediction hit and the instruction is net harmful. `product-catalog-flag-failure` — the
reachability-blocked abstention T4.11 explained — answered `bad_config` correctly at high
confidence, and its trajectory shows the registered mechanism executed: empty logs at seq 6, **not**
re-issued, vantage changed, `change_history` at the flag service reached, `trace_query` called for
the first time on that scenario. **And coverage fell 6/7 → 4/7**, with three registered
must-not-regress scenarios falling to abstention.

| | sweep 3 `53fafe9c12bc` | sweep 4 `bf7605651ef2` |
|---|---|---|
| coverage | **6 / 7** | **4 / 7** |
| fault class, of answered | 6 / 6 | 4 / 4 |
| judge same / different | 6 / 1 | 4 / 3 |
| triage recall / precision | ~~0.91 / 0.54~~ **0.92 / 0.58** | ~~0.92 / 0.56~~ **0.92 / 0.59** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_
| re-issues after silence | 4, in 3 runs | 2, in 2 runs |
| runs calling `trace_query` | 3 / 7 | 5 / 7 |

**No run returned a wrong class** — every regression is answer → abstention — and triage was flat,
which is the closest thing here to a control. The predictor is **dispatches at the service whose
failure is the fault**: it collapsed 3→0, 4→1 and 3→0 on exactly the three regressions and held on
every scenario that did not regress. The instruction moved dispatch away from the failing service,
which is right where that service is mute and wrong everywhere else.

Two cautions this sweep supplies about reading the rest of this document. **The `bad_config`
per-class row is identical in both sweeps** — 1/1 answered, 1 abstained — while its two scenarios
swapped places; a per-class table is required here by house rule and was still not enough. And
`cart-redis-misconfig`, which T4.10 measured answering **6/6** under the byte-identical budget,
abstained once here — so a 6/6 prior is not a guarantee under a moved prompt.

**How to read sweep 2's `4 / 7` coverage.** Not as "answered 4, correctly declined 3". T4.11
([`VARIANCE-2026-08-27-abstention.md`](../evals/runs/VARIANCE-2026-08-27-abstention.md)) repeated
`product-catalog-flag-failure` five times under a byte-identical configuration: the abstention is
**5/5 stable** — the figure is reproducible and will not drift to `5/7` — but it is **forced by
evidence reachability, not by calibrated refusal to guess**. Every plan queries a log stream
ADR-0005 measured at 0 lines/hour, misreads the silence as a bad selector, and never reaches the
traces that carry the answer. **One of the three non-answers is explained this way; the other two
have not been analysed**, and no claim is made about them.

---

## Findings the record supports

### (a) The gap is taxonomy, not comprehension — two independent measurements agreeing

On dev sweep 1 the agent scored **4 / 7 on fault-class labels** while a **label-blind judge found
7 / 7 on mechanism** (`same_mechanism`, every scenario). Those are not in tension: the judge never
sees a class and grades whether the narrative names the same failing mechanism the recorded
narrative names.

Read together with the verdicts, they say the same thing from two directions. Across all seven
scenarios sweep 1's agent returned exactly **two** values — `bad_deploy` where the change record
touched an image, `bad_config` everywhere else — and never a symptom class. That single rule
predicts all seven rows, *including the four it got right*. Both `resource_exhaustion` verdicts
identified the mechanism correctly before classifying:

> "A process killed by the kernel for exceeding its cgroup limit dies without emitting an
> application-level…" — `frauddetection-memory-squeeze`

**The system understood what was wrong and named the wrong category for it.** One measurement was
made from structured labels by a deterministic scorer, the other from prose by a different model;
they agree.

Evidence: [`SWEEP-2026-08-26.md`](../evals/runs/SWEEP-2026-08-26.md),
[`docs/evidence/t4.4-judge/`](evidence/t4.4-judge/), ADR-0022 addendum.

### (b) Teaching the taxonomy traded coverage for correctness — and the trade is confounded

28 lines were added to the synthesizer's instructions defining the four classes **by mechanism**,
derived from what the labels mean and naming no scenario or service. The stamp moved, which is how
the two sweeps stay distinguishable.

| | sweep 1 | sweep 2 |
|---|---|---|
| fault class, of answered | 4 / 7 | **4 / 4** |
| coverage | **7 / 7** | 4 / 7 |
| distinct classes returned | `bad_config`, `bad_deploy` | **all four, plus `unknown`** |

Both target classes moved: `dependency_latency` 0/1 → 1/1, `resource_exhaustion` 0/2 → 1/1
answered. **No run in either sweep answered one of these classes and got it wrong.** The
two-value classifier became a real one.

Two previously-correct scenarios regressed — **to abstention, not to a wrong answer**. Triage was
unchanged (0.94 → 0.95 recall), which is the closest thing here to a control: the change is
downstream of triage and triage did not move.

**The confound, stated because it is not resolved.** On holdout, the two abstentions exhausted
the same bound — `changes tool calls: 4 of 4` — and the run that answered did not. On dev the two
did not line up: one abstention was exhausted, two were not, and one exhausted run answered. **At
n=3 and n=7 this data cannot separate "the instruction causes abstention" from "the planner
spends its `changes` budget and leaves the synthesizer nothing to classify from."** That needs a
run with a larger per-specialist bound, and nothing in this repository answers it.

Evidence: [`SWEEP-2026-08-26-taxonomy.md`](../evals/runs/SWEEP-2026-08-26-taxonomy.md),
[`t4.5-taxonomy/prompt-addition.md`](evidence/t4.5-taxonomy/prompt-addition.md).

### (c) The dispute register is about the label set, not about the agent

Four entries, all one boundary: **change-mediated versus symptom-mediated**. A shaping rule on a
container's network namespace and a lowered memory limit both read as "something was configured
wrong" or as "a dependency got slow / a service exhausted a resource".

The register records where **the two readings disagree**, not where a tiebreak fires. That
distinction was decided on evidence: a tiebreak-defined register catches `dependency_latency`
twice and is **blind to both `resource_exhaustion` rows**, because both readings there give
`config_revert` — it would go quiet exactly where the labels are least separable.

**Every disputed miss is still counted a miss.** The register is visibility, not forgiveness: it
lets a reader see that three of sweep 1's four errors were one error, without reading seven
verdicts. **Zero entries fired on holdout** — every entry is a dev scenario, admitted by an ADR
after examination and never inferred — so holdout's one wrong label is an ordinary miss, even
though it is the same wrong label on the same fault class.

Evidence: ADR-0022 addendum, `evalharness.scoring.CLASS_DISPUTES`.

### (d) A negative result worth keeping: the contradiction checker

A deterministic check compared verdict claims against the trajectory that produced them — "this
verdict says a dispatch never happened; here is the dispatch." It was **retired on its own
evidence**:

| run | fired | verdict |
|---|---|---|
| T3.4 | 1 | true positive |
| T3.4b · T3.4c · sweep 1 | 4 | **all false positives** |

**0 true positives and 4 false positives live.** The one true positive does not survive scrutiny
either: its cause was diagnosed as a *context-assembly* defect and fixed, so the verdict it caught
was accurate about what it had been shown, and the defect has had no instance since.

Narrowing was rejected because each false positive had a different cause — a comma-joined clause,
a self-citing clause, `?` not being a clause boundary, `image` matching inside `image-pull` — and
each fix bought exactly one round. **A check whose precision is maintained by patching a regex is
a small language model made of regexes, with none of the calibration and all of the confidence.**

The module is kept unwired with its ledger, and the bar for re-admission is written down: a
mechanism that does not parse prose. The idea was sound; the implementation was the problem, and
deleting the record would guarantee someone rebuilds it identically.

Evidence: [ADR-0021 addendum](adr/0021-verdict-grounding-and-two-ended-truncation.md),
`faultline.agents.grounding`.

### (e) The quarantine held, end to end

From authoring (T1.6) to the holdout run (T4.6): three scenarios split before any artifact
existed, never seeded into the corpus, never named in any prompt, never run by any agent — and
checked at both ends rather than assumed. `holdout_chunks: 0` before and after; 26 of 26 retrieval
rows carrying their exclusion; 0 returning their own origin.

This is the least exciting finding here and the one everything else depends on. A benchmark whose
held-out set leaked is not a benchmark, and the failure is invisible in the scores because the
scores go up.

---

## What remains

Drawn from [`docs/PLAN.md`](PLAN.md); each is open and none is answered by anything above.

1. ~~**The budget confound.**~~ **Run at T4.7** (`evals/runs/SWEEP-2026-08-26-budget.md`):
   `changes` raised 4 → 8, same stamp, seven dev scenarios. **The answer is mixed and it
   decomposes** — budget owned one abstention, the instruction owns another, and a third is
   neither. Starvation was real and is gone (zero runs exhausted `changes`, against two);
   coverage rose 4/7 → 6/7 with accuracy-of-answered holding at 100%. ~~What remains open is the
   part it could not settle: `product-catalog-flag-failure` abstains twice with budget to spare,
   and nothing yet explains why.~~ **Explained at T4.11**
   ([`VARIANCE-2026-08-27-abstention.md`](../evals/runs/VARIANCE-2026-08-27-abstention.md)): the
   budget was never the binding constraint. Every plan dispatches `logs:productcatalogservice`, a
   stream ADR-0005 published at **0 lines/hour**; the agent reads the empty result as a
   label-syntax error rather than a fact about the world, retries it, and **never calls
   `trace_query`** — where four of the scenario's eight expected-evidence items live.
2. ~~**The `changes`-budget question `email-wrong-image` exposed.**~~ **Answered at T4.8, and the
   answer was neither hypothesis.** A second holdout entry under the raised bound
   ([`HOLDOUT-2026-08-26-entry2.md`](../evals/runs/HOLDOUT-2026-08-26-entry2.md), pre-registered,
   1 of 3 scored) found `email-wrong-image` abstaining again **with `changes` unexhausted** — the
   registered falsifier. With eight calls available the planner used two and **never asked about
   `emailservice`**, the service its own traces implicated; entry 1 had planned that dispatch at
   #5 and been cut off. **Planner allocation, not budget and not the instruction**, at n=1. What
   remains: **planner breadth varied fourfold between two runs of the same scenario**, which
   nothing in this repository has measured, and the other two holdout scenarios are still
   untested under the raised bound.
3. **A second-provider judge.** Every judged figure here carries a lineage violation because this
   repository holds one provider's credentials. This is the cheapest change that would improve
   every judged number, and it needs credentials rather than code.
4. **T7.1's digest-locked re-record queue.** Several known fixes are blocked behind bundle
   re-recording, including the `FAULTLINE_ENABLED_FLAGS` world-owned token and the two
   `INVALID` dev bundles that cannot alert.
5. **The action plane.** Remediation is proposed and never executed; the approval-gated executor
   that `docs/ARCHITECTURE.md` and `docs/THREAT-MODEL.md` both depend on has no task number and is
   recorded in PLAN.md under "Discovered omissions".

6. **Variance beyond one scenario.** T4.10 measured run-to-run variance for the first time -
   five repeats of `cart-redis-misconfig` with scenario, stamp and budget all fixed
   ([`VARIANCE-2026-08-27.md`](../evals/runs/VARIANCE-2026-08-27.md)). **One distinct verdict from
   five identical configurations**, six for six counting a byte-identical prior row, while
   **round-1 breadth ran 5 to 13 and tokens 36k to 68k**. Two things follow that this repository
   should act on: **no cost figure anywhere is a point estimate** - each is one draw from a ~1.9x
   spread, which puts the gap between two sweep totals inside a single scenario's repeat range -
   and **variance is now measured for exactly one of ten scenarios**, the one with the most prior
   successes. **T5.3 added a seventh observation of that configuration and it abstained** — the
   demo run, byte-identical in stamp and all four bounds, which exhausted `metrics` and never
   queried the failing service's change history. It is excluded from the 6/6 above by the demo
   rule (`counts_toward_aggregates`) and recorded here instead, because a figure and an
   observation it may not absorb should both be visible. ~~Nothing is known about variance on a
   scenario that abstains~~ — **T4.11 measured
   that too**, five repeats of `product-catalog-flag-failure` under the byte-identical
   configuration ([`VARIANCE-2026-08-27-abstention.md`](../evals/runs/VARIANCE-2026-08-27-abstention.md)):
   the abstention is **5/5 stable**, no repeat answered, and **dispersion is lower than on the
   answering path** (breadth spread 1 against 8, tokens 1.35x against 1.9x). Convergence, not
   flailing — because the same reachability gap bites identically every run. Still nothing known
   about variance on holdout, or on any other fault class.

Also open and smaller: the freeze manifest's self-referential git sha; whether retrieval `k`
should count chunks or documents; whether the holdout `dependency_latency` near-miss should be
admitted to the dispute register — a decision for an ADR, not for a report; **the baseline
gate's blindness to recently-resolved incidents**, which cost T4.7 a scenario when one sitting
inside the settle window captured the next run's alerts; and **dead-end coverage as the least
stable thing yet measured** — 3 to 7 closed across five runs that agreed on the verdict.
