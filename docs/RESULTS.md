# Results

Everything here was produced by running the system against a pinned OpenTelemetry demo world with
labelled, reversible faults. Raw runs, per-run manifests and the sweep reports are in
[`evals/runs/`](../evals/runs/); this document is the method and what the record supports.

**Agent `claude-opus-5` · judge `claude-haiku-4-5` · SHARED LINEAGE on every judged figure.**

> **The current-world result leads; everything else in this document is labelled.** The figures are
> in [the section immediately below](#the-current-world-result) — **19 scored runs on
> `compose_digest f5bd108f…`, none of them holdout** — and are not repeated here.
> *(They were repeated here until T7.60, which gave them a section; a banner and a section saying
> the same thing is how the two drift apart.)*
>
> **The current world holds under a fifth of the record.** Of the 97 manifest-carrying runs in
> `evals/runs/`, **69 describe `4a7690c6fdda…`** and **12 describe `299d791c5e0d…`**. That is why
> *The tables* is labelled the way it is.
>
> **The world is reconstructible, and that is what makes the digest worth quoting (T7.48).** The
> stack was torn down and rebuilt with the documented commands; **`compose_digest`,
> `observability_digest`, `ffs_stub_source_digest`, the demo image digest and all 28 container image
> ids came back identical**, and the behaviour did too — `cartservice` p95 back at its documented
> **1.9 ms**. The before/after comparison is committed at
> [`docs/evidence/t7.48-rebuild/`](evidence/t7.48-rebuild/) for a reader who would rather check than
> believe.
>
> **What that does and does not license.** It means a digest here identifies a world someone can
> reconstruct rather than one that merely happened to be running. It does **not** mean a cold
> clone-and-pull reproduces it: the teardown reused local images, and the separate check that the
> registry tag still resolves to `sha256:97d55955…` is **a weaker substitute for a cold pull**.
> **No scored run has been made since the rebuild**, so the world is identical and the figures are
> not thereby re-established.
>
> **What `n` counts.** Every scenario figure in this document is over **slots filled, not slots
> allocated** - 13 valid scenarios against 20 allocated. `bad_deploy-5` is deliberately left empty
> because that class's mechanism space is exhausted (T7.34, T7.35), and the reasoning is in
> [CATALOG.md](../evals/scenarios/CATALOG.md). A gap between the two numbers is a recorded decision;
> it is not a target to be closed by authoring filler.
>
> **The rest of this document describes earlier worlds** — **most of it `4a7690c6fdda…`, and some
> of it `299d791c5e0d…` (dev sweep 6).** *(Corrected 2026-09-01, T7.54: this sentence had the two
> worlds the wrong way round. Counted by run directory the split over the 97 run directories that carry a manifest is
> **69 on `4a7690c6fdda…`, 12 on `299d791c5e0d…`, 16 on the current `f5bd108f…`** — the older world is the majority of the
> record, not the minority. The per-file banners in `evals/runs/` had the same error and are
> corrected.)* Those figures are not wrong; they are correct about
> worlds that no longer exist, and they do not carry over. **Comparing a figure here against sweep
> 7 compares worlds, not agents**, and sweep 7's own comparison to sweep 6 rescores sweep 6 first
> so the two sides are like-for-like.
>
> **A method note that outlived its world.** Sweep 7 found that `scoring.py` had moved at T7.17,
> after every sweep-6 run — so sweep 6's stored figures were computed by a scorer that did not know
> two remediations work for `dependency_latency`. Rescoring moved sweep 6's class-of-fix from 4/5
> to 5/5. This is the second time a scorer change has silently sat between two sweeps (T7.10 caught
> the first, T7.3's blast-radius fix), and **any future comparison must check for it before
> reporting a delta.**

---

## The current-world result

**This is the only section describing the world that exists.** Everything under *The tables* ran on
a world that has since been replaced, and says so.

### What is scored, and what is not

Three different things assess a run, and the difference between them is the single most useful thing
to know before reading any number here. *(Stated whole in one place from T7.60; it was previously
true in [ADR-0022 §1.2](adr/0022-evaluation-harness.md), T7.44's analysis and T7.52's measurement,
and stated whole in none of them.)*

| | what it asks | what it cannot see |
|---|---|---|
| **the scorer** | Is the returned **fault class** the labelled one, and is the **class of fix** the one that works? | *how* the conclusion was reached. A right label from a wrong story scores the same as a right label from the right one |
| **the judge** | Does the verdict name **the same mechanism** as the recorded narrative? `same_mechanism` / `adjacent` (right subsystem, wrong mechanism) / `different` | whether the evidence the agent cited **supports** the mechanism it named |
| **warrant** | Does the stated causal path actually follow from the evidence gathered? | — **nothing assesses this** |

**Warrant is assessed nowhere, and that is a deliberate gap rather than an oversight.** Every
scenario carries a `GroundTruth.root_cause` that no scoring code reads (T7.44). Adopting a warrant
check on the evidence available would tune the benchmark to its last result, so it is queued (**Q3**)
rather than built. **A figure here says the agent reached the right answer; no figure here says the
agent had the right reasons.**

`unknown` is an **abstention, not a wrong answer** — excluded from accuracy and reported as
coverage, so accuracy and coverage are never quoted apart.

### The figures

**World `compose_digest f5bd108f…` / `observability_digest 857d95b4…`, stamp
`prompts:1b0e7cbb4c47`, agent `claude-opus-5`, judge `claude-haiku-4-5` — SHARED LINEAGE on every
judged figure.**

> **HEAD is no longer this pipeline (T3.9 and T3.1, 2026-09-02).** The remediation proposer added
> a sixth stage and triage gained a judgement half, so two role prompts and two contracts entered
> the stamp; HEAD is `prompts:a7330c098770`, by way of `prompts:20088b22cede`. **The `budget`
> block moved too** (T3.2c and Q16): four bounds became eight, adding a briefing cap, a
> per-incident dollar cap and the price table that cap is computed at. Every figure below was
> recorded under the four. **Every figure below describes `prompts:1b0e7cbb4c47`, and none of
> them describes the agent this repository now builds.** ADR-0028 §6 required the role to land
> with a re-sweep and named this cost in advance; the re-sweep has not run. Nothing below is
> altered, because a figure that was true of the pipeline that produced it stays true of it -
> what changes is which pipeline a reader may attribute it to.

**19 scored runs, over 10 of the 13 valid scenarios. Every one is a dev run: there is no
current-world holdout figure at all**, and there will not be one — see *What remains*.

| | |
|---|---|
| coverage (reached a class) | **18 / 19** |
| fault class, of answered | **17 / 18** |
| class of fix, of answered | **15 / 18** |
| judged mechanism agreement, over all 19 | **`same_mechanism` 15 · `adjacent` 3 · `different` 1** |
| runs judged | 19 / 19 |

| ground-truth class | n | answered | fault class of answered | class of fix of answered | `same` / `adj` / `diff` |
|---|---:|---:|---:|---:|---|
| `bad_config` | 11 | 10 | 9 / 10 | 9 / 10 | 9 / 1 / 1 |
| `bad_deploy` | 2 | 2 | 2 / 2 | 2 / 2 | 2 / 0 / 0 |
| `dependency_latency` | 4 | 4 | 4 / 4 | **2 / 4** | 2 / **2** / 0 |
| `resource_exhaustion` | 2 | 2 | 2 / 2 | 2 / 2 | 2 / 0 / 0 |
| **all** | **19** | **18** | **17 / 18** | **15 / 18** | **15 / 3 / 1** |

**Four of the nineteen are not clean, and they are the same few runs each time.** One abstention
(`payment-telemetry-blackout`, reconstructed at T7.43). One class miss (`shipping-quote-misconfig`,
`bad_config` returned as `bad_deploy`, judged `adjacent` — label and judge agree it is wrong). And
two `redis-cart-dependency-latency` runs that got the class right, missed the fix, and are judged
`adjacent` — right subsystem, wrong mechanism (T7.51).

**The pre-registered sweep inside that corpus is dev sweep 7** — 8 of the 19 runs, one per runnable
scenario, no discards: coverage 8/8, fault class 7/8, class of fix 7/8, judge `same_mechanism` 7/8,
\$4.6870 ([`SWEEP-2026-08-30-refound-again.md`](../evals/runs/SWEEP-2026-08-30-refound-again.md)).
The other eleven are the two scenarios authored at T7.36 and T7.38 (n = 5 and n = 3) and T7.58's
traceability split.

**n is 1 for six of the ten scenarios.** A 95% interval on any cell above spans most of the unit
interval. **These support direction, not magnitude.**

### What the label score can and cannot see — measured

*(Brought into this document at T7.60 from [`docs/evidence/t7.52-corpus-judge/`](evidence/t7.52-corpus-judge/),
where it qualified figures it was not next to. The numbers are over the **whole record**, not only
the current world, because that is the n the question needs.)*

Over **56 answered runs** with a judged verdict:

| | |
|---|---|
| class-label accuracy | **52 / 56** |
| judged `same_mechanism` | **52 / 56** |
| runs that are **both** | **49** |

**The same number, and not the same runs.** Six disagree — **three in each direction** — so the
label score is **not flattering; it is noisy, symmetrically**:

- **Three runs the label credits and the judge does not.** Two are the `redis-cart-dependency-latency`
  runs above (`adjacent`), one is a `cart-bad-image-tag` run judged `different` — a wrong story that
  landed in the right bucket.
- **Three runs the label marks wrong and the judge calls `same_mechanism`** — the agent named the
  exact mechanism and chose the other defensible label at the config/consequence boundary. **All
  three are already in `CLASS_DISPUTES`**, and the judge, which is never told the label, agrees with
  the agent on precisely the three rows the register flags as contested. That is corroboration from
  a direction that could not have been tuned to produce it. **It does not make them right** —
  ADR-0022 §1.2 stands and a disputed miss is still a miss.

**Abstentions are excluded from the agreement figure and that matters:** all 17 in the record judge
`different` by construction, so counting them would make agreement look worse than accuracy as a
pure artifact.

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
trajectory_retrievals: 88 rows · 88 carry exclude_origin · 0 returned their own origin
```

*(Was `26 rows · 26`, the count when T3.2 first published it. **Re-read live at T7.59: 88 of 88.**
The invariant is that the two numbers are equal and the third is zero, and it has held through every
run since — a count that only ever grows is worth re-reading rather than quoting from memory.)*

This is the assertion [ADR-0008](adr/0008-contamination-model.md) said must be checked at eval
time rather than trusted, and the column has been on the table since T3.2 precisely so it could be.

**A fifth axis — judge contamination.** The judge is a separate setting with no default; unset,
narrative scoring refuses to run. Lineage is checked at eval time at the **vendor-family** level,
and a violation refuses by default and must be opted into by name, after which it is stamped on
every figure. This project holds one provider's credentials, so every available judge violates
the rule. **The label is on every judged number in this document.**

### The freeze

[ADR-0022 §3.3](adr/0022-evaluation-harness.md) requires that "frozen" mean something a script can
check. **Seven items** are hashed and re-checked: prompts, corpus, model map, budget, tool layer, judge —
and, since T7.54, **the world**: `compose_digest`, `observability_digest`, `ffs_stub_source_digest`,
the demo image digest and `CAPABILITY_VERSION`. *(Was "six items". T7.53 found the omission; T7.54
fixed it and found it had already cost something — 69 of 97 recorded runs were attributed to the
wrong world generation. T7.55 wired the check into `faultline-eval`: a run that cannot establish its
world now **refuses**, and a changed world is recorded as a new comparability generation rather than
silently compared.)* The manifest
([`FREEZE-2026-08-26-holdout.json`](../evals/runs/FREEZE-2026-08-26-holdout.json)) was committed
as its own commit **before any holdout scenario ran**.

After the run, five of six were byte-identical. The sixth — the tool-layer git sha — moved by
exactly one commit, the freeze commit itself, with no change to `src/faultline/`. That is a
self-reference flaw in the manifest and it was **recorded, not fixed**: fixing anything during a
holdout run is what the freeze exists to prevent.

### The pipeline stamp

`runtime_version` is derived, not typed: the package version plus a digest over every role system
prompt and every contract schema — the two things that determine what the agent *is*. It moves
when and only when the agent changes, so a table can say which pipeline produced it. ~~Two stamps~~
**Four stamps** appear in this document, and the table below has held four rows since T4.14
*(corrected T7.60 — the sentence was written when there were two and the table outgrew it)*:

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
and no claim here extends them to the current one. ~~Re-entering the holdout under the new stamp is
a separate decision with its own pre-registration under ADR-0022's protocol, and it has not been
made.~~ **It was made: entry 3 is that re-entry**, argued against ADR-0022's four conditions in the
T4.15 addendum — the sentence outlived the entry it denied and contradicted the line three above it.
*(Struck T7.60.)* **What has not been made is entry 4, and it cannot be** — see
[ADR-0029](adr/0029-four-fault-classes-and-why-there-is-no-fifth.md). See [ADR-0023](adr/0023-a-freeze-manifest-outlives-the-pipeline-it-froze.md), which is where
this obligation to say so instead of asserting it in a test comes from.

### The figures below were measured against a world that no longer exists

T7.1 changed four things about the world — kafka's heap is capped, `otel-col`'s limit is 600M,
Prometheus keeps 15 days instead of 6 hours, and the flag-service stub variants are renamed — and
re-recorded all twelve scenario bundles against the result. `world.compose_digest` moved from
`4a7690c6fdda…` to `299d791c5e0d…` and `ffs_stub_source_digest` from `5d06a3668aa0…` to
`8defed3104c4…`.

**Nothing under *The tables* was re-measured.** Every dev sweep, every variance experiment, every
holdout entry and the retrieval corpus behind them were produced against the **old** world, and
they stand exactly as measured. *(Was "nothing in this document", which stopped being true at T7.29
and read as false the moment T7.60 gave the current-world result a section above this one. Scoped
T7.60 — the sentence was correct about the document it was written in.)* What changes is what they
can be compared to:

- **A future run is not comparable to any figure under *The tables*.** It would differ in the agent
  *and* the world, and this document cannot separate those. Comparing across the digest boundary is
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
  cannot say **what the retrieval said**. Cumulatively this now reaches **60 of 62 stored
  trajectories** — the union across every rewritten document, wider than the 39 and 41 that T7.6
  and T7.7 each reported for their own. T7.9 fixed it going forward — the rendered lines are
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

## The tables — **every sweep and entry below ran on a superseded world**

None of the figures in this section describes `f5bd108f…`. They are correct about the worlds they
name and they do not carry over; the current-world result is at the top of this document.

### Dev sweep 6 — `world 299d791c5e0d…`, **superseded**

> **Corrected and moved 2026-09-01 (T7.60).** This section was headed *"Dev, on the world that
> exists"* and called sweep 6 **"the current-world benchmark"**, and it sat inside **Method**, above
> the divider announcing superseded figures. Both statements were true when written and both were
> falsified by T7.28. **T7.59 found this and its correction did not reach the file** — see
> [the audit's own correction](design/t7.59-record-audit.md). The ordering is what let it survive: a document arranged by date has no
> place that is obviously *the current result*, so a stale heading could hold the position.

Pre-registered, run on the re-recorded bundles under the then-current
stamp `prompts:1b0e7cbb4c47` and the T4.7 budget
([`SWEEP-2026-08-28-refound.md`](../evals/runs/SWEEP-2026-08-28-refound.md)).

| scenario | fault class | class of fix | judge |
|---|---|---|---|
| ad-memory-squeeze | **`resource_exhaustion`** ✔ | `config_revert` ✔ | `same_mechanism` |
| cart-bad-image-tag | **`bad_deploy`** ✔ | `rollback` ✔ | `same_mechanism` |
| cart-dependency-latency | **`dependency_latency`** ✔ | `config_revert` ~~✘~~ **✔** | `same_mechanism` |
| cart-redis-misconfig | **`bad_config`** ✔ | `config_revert` ✔ | `same_mechanism` |
| frauddetection-memory-squeeze | **DISCARD** — no incident in 900s | — | — |
| product-catalog-flag-failure | **`bad_config`** ✔ | `config_revert` ✔ | `same_mechanism` |
| shipping-wrong-image | `unknown` — **abstained** | — | `different` |

**Scored 6 of 7. Coverage 5/6, fault class 5/5, class of fix ~~4/5~~ 5/5.** _(rescored 2026-08-29 under T7.17: `config_revert` is a **measured** working fix for `dependency_latency`, so it is no longer a miss. Originals struck. See ADR-0027.)_ Cost $3.3650 + $0.2229 judge.

**No fault class changed across the world boundary** — every scenario that produced a class
produced the same one S5 did, and every one was correct. Two scenarios did not produce a
comparable result: `shipping-wrong-image` abstained after spending **zero** dispatches on the
failing service (the collapse T4.12 identified, and **not** traceable to the capture change —
the service was in its blast radius both times), and `frauddetection-memory-squeeze` never
alerted within 900s — **which T7.11 established was the host suspending mid-run**, not the world
and not the scenario: two injections both paged at T+382s and T+381s against a recorded 390s, and
the metrics store has a sixteen-minute hole in which all fifteen services stop reporting together.
**That discard is environmental and is not a result about this system.** It stands in the record;
coverage is quoted over the six runs that produced one.

**Triage is unchanged.** Five of six scenarios score identically to S5 once S5 is rescored under
the current scorer — the raw stored figures appear to improve only because T7.3 fixed the
blast-radius exclusion after S5 ran.

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

Drawn from [`docs/PLAN.md`](PLAN.md) and [`docs/QUEUE.md`](QUEUE.md).

> **What is open, and what is closed for good — added T7.59, because "what remains" had come to
> hold both and a reader cannot tell them apart from the list alone.** Items struck below are
> answered. These four are **not open questions; they are settled limits of this world**, and no
> further work here will move them:
>
> - **The catalog is closed at thirteen valid scenarios.** `bad_config` has no distinct fifth item
>   — T7.56 designed one against the recorded page space, gated it, and abandoned it at its first
>   gate — and `bad_deploy`'s remaining slots need a mechanism the capture set deliberately
>   excludes.
> - **There is no fifth fault class.** Four injector mechanisms bind one-to-one to four classes by
>   test; `config_revert` already fixes three of them; the one unclaimed remediation, `scale`, is
>   one this world can neither cause nor perform; and adding a class would move the pipeline stamp
>   and re-found every figure here
>   ([ADR-0029](adr/0029-four-fault-classes-and-why-there-is-no-fifth.md)).
> - **The capture set is closed by decision, not by omission** — the container exit reason is
>   excluded deliberately, because a capture printing `OOMKilled: true` would delete the inference
>   three `resource_exhaustion` scenarios exist to test (T7.40, queued as **Q1** with what would
>   reverse it).
> - **The holdout arm is finished at three entries** — seven agent-facing runs, four answered, all
>   on `4a7690c6fdda…`, two worlds back. **Entry 4 is blocked indefinitely rather than pending**,
>   because ADR-0022's T4.15 addendum permits another entry only once the set is extended and the
>   two lines above say it cannot be. **No more holdout evidence is coming without a different demo
>   world.**
>
> **What would change any of them is the same thing: a different demo world**, with more failure
> surface, knobs that are not all addresses, a topology that does not funnel every failure through
> checkout, and services that can scale. That is a re-founding, not a task.

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
   nothing in this repository has measured. ~~and the other two holdout scenarios are still
   untested under the raised bound.~~ **Closed by entry 3** (T4.15): all three ran under the raised
   bound and all three answered correctly. *(Struck T7.59 — a caveat that outlived the task that
   answered it.)*
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
   and ~~**variance is now measured for exactly one of ten scenarios**~~ — **two of thirteen**, the second
   being `product-catalog-flag-failure` in this same bullet *(corrected T7.59: the catalog is 13
   valid, not 10, and T4.11 measured the second arm)*. **T5.3 added a seventh observation of that configuration and it abstained** — the
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
admitted to the dispute register — a decision for an ADR, not for a report; ~~**the baseline
gate's blindness to recently-resolved incidents**, which cost T4.7 a scenario when one sitting
inside the settle window captured the next run's alerts~~ — **fixed: the gate reads
`settling_incidents` and refuses, and T7.58 watched it refuse three runs in four seconds for exactly
this reason** *(struck T7.59)*; and **dead-end coverage as the least
stable thing yet measured** — 3 to 7 closed across five runs that agreed on the verdict.
