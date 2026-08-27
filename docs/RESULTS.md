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
| `prompts:53fafe9c12bc` | dev sweep 2 **and the holdout run** — the synthesizer taught the taxonomy |

A test pins the current value and fails loudly if it moves, with the reason spelled out.

### Honest n

- No figure without its n.
- No aggregate without its per-class table.
- **Accuracy and coverage are never quoted apart.** An `unknown` verdict is an abstention: out of
  the accuracy ratio entirely, reported as coverage.
- Blast-radius **recall and precision are a pair and never combined** — no F-score. The two answer
  different questions and [ADR-0017](adr/0017-context-layer-graph-and-dependency-policy.md) has a
  live hypothesis riding on recall alone.
- Unmeasured graph edges are quoted on every blast-radius figure.

### Run protocol

Every run: a **baseline gate that refuses rather than warns** (it aborts before injecting if the
world is not quiet), a **world lock** so there is one driver, injection, correlation, the
investigation invoked as a subprocess through its own CLI, revert, and a recovery check using the
same readings as the gate. Discards are recorded with reasons and never deleted. **Holdout is
never re-run to fix a number.**

---

## The tables

### Holdout — n = 3, stamp `prompts:53fafe9c12bc`

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

Triage recall **1.00**, precision 0.32, 9 unmeasured edges. Budget exhausted 2 of 3. Flagged 0 ·
failed-alone 0 · contradictions 0 · narrative refused 0. Cost $1.08 agent + $0.12 judge.

### Dev — **not a benchmark.** n = 7 per sweep

Dev is where prompts and retrieval were fitted. These are shown to say what the same pipelines did
on scenarios they were developed against.

| | sweep 1 `59bf438b2a96` | sweep 2 `53fafe9c12bc` |
|---|---|---|
| fault class, of answered | 4 / 7 | 4 / 4 |
| coverage | 7 / 7 | 4 / 7 |
| class of fix, of answered | 6 / 7 | 3 / 4 |
| triage recall / precision | 0.94 / 0.56 | 0.95 / 0.57 |
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
   coverage rose 4/7 → 6/7 with accuracy-of-answered holding at 100%. What remains open is the
   part it could not settle: `product-catalog-flag-failure` abstains twice with budget to spare,
   and nothing yet explains why.
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
   successes. Nothing is known about variance on a scenario that abstains, on holdout, or on any
   other fault class.

Also open and smaller: the freeze manifest's self-referential git sha; whether retrieval `k`
should count chunks or documents; whether the holdout `dependency_latency` near-miss should be
admitted to the dispute register — a decision for an ADR, not for a report; **the baseline
gate's blindness to recently-resolved incidents**, which cost T4.7 a scenario when one sitting
inside the settle window captured the next run's alerts; and **dead-end coverage as the least
stable thing yet measured** — 3 to 7 closed across five runs that agreed on the verdict.
