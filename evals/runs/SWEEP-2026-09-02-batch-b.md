# Dev sweep 8 — the Phase 3 pipeline as the specification describes it

> **Correction, same day.** #154 merged a **superseded draft** of this document — the wrong file of
> three was applied — so what landed reported four discards rather than sixteen, omitted §3
> entirely, and did not carry the `evals/runs` exclusion. **#154's commit message describes this
> version**: it states that the duplicate scored run is declared and that the ledger is twenty-two
> directories, and the document it merged said neither. Nothing was concealed and no figure was
> chosen — the artifacts for every run, `20260902T101301Z` included, went in with that same commit
> and contradicted the draft from the moment it landed. **Recorded here rather than fixed
> silently**, because a document that quietly grows a section between merges is the one thing a
> reader of a benchmark cannot check.

**Scored against [`PREREGISTRATION-2026-09-02-batch-b.md`](PREREGISTRATION-2026-09-02-batch-b.md),
which was committed before any scenario ran.** Two of its six predictions failed. Both failures are
below, before the result they qualify.

**This is not the sweep that was registered**, and two departures matter more than the numbers:

1. **Five of eight scenarios were scored.** `product-catalog-flag-failure` was injected and
   discarded four times when the API returned a credit-balance error; two scenarios never started
   for the same reason.
2. **`ad-memory-squeeze` was scored twice under one configuration.** The sweep counts the first and
   reports the second. §3 states why the second exists and what it agreed on.

| | registered | actual |
|---|---|---|
| scenarios scored | 8 | **5** |
| fault classes covered | 4 | **4** |
| scored runs produced | 8 | **6** — one scenario ran twice |
| non-scored outcomes | 0 expected | **16** (§6) |
| spend, counted runs | \$8–12 | **\$3.4796** |
| spend, all scored runs | — | \$4.2217 |

---

## 1. The runs

Runtime `faultline/0.0.1+prompts:bc222a353936`, capability `cap:c4d52d00`, world generation
`f5bd108f4f70` on every run. **No stamp moved during the sweep.**

| # | run | scenario | class | fix class | cost |
|---|---|---|---|---|---|
| 1 | `20260902T101301Z` | `ad-memory-squeeze` | `resource_exhaustion` ✔ | `config_revert` ✔ | \$0.7204 |
| 2 | `20260902T133126Z` | `cart-bad-image-tag` | `dependency_latency` **✘** (label `bad_deploy`) | **ABSTAINED** (label `rollback`) | \$0.7271 |
| 3 | `20260902T162429Z` | `cart-dependency-latency` | `dependency_latency` ✔ | `config_revert` ✔ | \$0.6775 |
| 4 | `20260902T164343Z` | `cart-redis-misconfig` | `bad_config` ✔ | `config_revert` ✔ | \$0.8761 |
| 5 | `20260902T220529Z` | `frauddetection-memory-squeeze` | `resource_exhaustion` ✔ | `config_revert` ✔ | \$0.4785 |
| — | `20260902T104002Z` | `ad-memory-squeeze` **(second run, counted nowhere)** | `resource_exhaustion` ✔ | `config_revert` ✔ | \$0.7421 |

Run 3's fix class is counted correct through ADR-0027's `also_correct_remediation`: T7.17 measured
that deleting the netem qdisc clears the delay durably, 3/3, so the fault has two working fixes and
`config_revert` is one of them.

**Coverage 5/5. Fault class 4/5 of those answered. Fix class 4 correct, 1 abstained** (excluded from
accuracy, counted in coverage, per ADR-0022 §1.2). **Zero gated, zero flagged, zero specialist solo
failures, zero bounds exhausted, zero narratives refused.**

| class | scenarios | pipeline completed | class correct |
|---|---|---|---|
| `resource_exhaustion` | 2 | 2 | 2 |
| `bad_deploy` | 1 | 1 | 0 |
| `dependency_latency` | 1 | 1 | 1 |
| `bad_config` | 1 | 1 | 1 |

---

## 2. The predictions

### 1. The gate does not close on a real incident — **HELD**

**5 of 5 disposed `investigate`** (6 of 6 including the uncounted run). No `noise`, no `duplicate`.

The interesting half is that the gate declined to decline *while saying it had little to go on*.
Run 5's judgement is `low` confidence — *"No signal yet distinguishes deploy, config, or resource
causes"* — and it investigated anyway. Run 4's is `medium`, with `suspects unknown`. **A cheap model
asked to decline things did not decline things**, which the pre-registration named as its strongest
falsifier. At `n = 5` that is an observation about the gate, not a rate.

### 2. The verdicts hold — **FALSIFIED**

`cart-bad-image-tag` returned `bad_deploy` ✔ in S7 and `dependency_latency` ✘ here. **This is the
class moving down on evidence that is strictly richer than S7's**, which the pre-registration named
in advance as a finding about the briefing change rather than about the world.

Two contributing observations from the run, neither of them a cause established at `n = 1`:

- **No change dispatch ever ran against `cartservice`**, which is where the image change was.
- The trace query returned a backend 500. Jaeger answered 200 on a manual check afterwards, so a
  transient is the likely reading.

The coverage clause — *"7/8 or better"* — **cannot be assessed**: three scenarios did not run.

The other four scored scenarios returned their S7 class.

### 3. The proposer is observed, not predicted — **HELD, as registered**

Nothing was registered about content. What was registered, and what happened:

| registered | observed |
|---|---|
| every scored run produces a proposal object | **5 of 5** — four actions, one abstention |
| zero actions outside the allowlist, targets outside the radius, or unresolvable `rests_on` | **zero violations** |
| abstention rate reported, never scored | **1 of 5**, on run 2 |
| execution axis reported `NOT MEASURED` | **5 of 5** |

Two observations worth keeping, both first instances of behaviour T3.9 was built for:

**A proposal that named the condition under which it does nothing.** Run 5's change log records
`None -> memory=200m` with no prior value, and `if_wrong` says so: *"if no concrete prior spec is
stored the revert may be a no-op — the operator should verify one exists before executing."* A
proposal is meant to be a falsifiable claim rather than a command, and this is what that looks like
when the claim is about the proposal's own precondition.

**An abstention that named what would supersede it.** Run 2 declined to propose and said what
evidence would change that, rather than proposing something weak to fill the field.

### 4. No run exhausts a bound — **HELD, and the cost estimate missed low**

No run exhausted the token bound, the wall clock, the dispatch rounds, or the new \$2 dollar cap.
The most expensive run was **\$0.8761**, 44% of the cap.

**\$3.4796 over five counted runs, \$0.6959 each, projecting ≈ \$5.57 for eight against a registered
\$8–12.** That is outside the registered band. **An underrun is a miss of the estimate in the same
way an overrun is**, and it is recorded here rather than quietly banked: the estimate assumed two
extra model calls and a larger synthesizer brief would cost more than they did.

**One caveat on the record rather than the result.** Run 1's manifest predates #152 and lists four
bounds instead of eight, so **the dollar cap is not visible in the record of the run this sweep
counts**. It is visible in the other four, which ran under the same enforced bounds. The defect is
the one #152 fixed, and it is named here because a prediction verified from four of five records
should say so.

### 5. Briefings fit — **FALSIFIED in its letter**

The prediction was *"no role reports `over_budget`, and the only section dropped, if any, is
`past-incidents`."* **Two sections were dropped on every run whose context line was transcribed**
(runs 4 and 5), not one.

| run | pushed | pulled | pull rate | sections dropped |
|---|---|---|---|---|
| 4 | 36,103 | 8,063 | 0.1826 | 2 |
| 5 | 17,209 | 2,360 | 0.1206 | 2 |

**What this is not.** Both dropped sections are designated droppable and the drop is priority
packing working as specified, not a budget squeeze forcing out something needed. The prediction was
wrong about *which* sections — a bookkeeping error in the prediction.

**Not established here, and needed before the next briefing change:** the per-role `over_budget`
flags and the section names live on the trajectory rows, not in `report.txt`, and the context line
was only printed from #152 onward. **The open question is whether the 4,000-token cap binds the
large roles at all** — the synthesizer, scribe and proposer briefs are built almost entirely from
`essential` sections, which are never dropped, so a cap they exceed is recorded rather than enforced
by design (`briefing.py`, `over_budget`). T7.3's ablation needs that stated, not inferred.

### 6. Triage is exactly S7's — **FALSIFIED**

| scenario | S7 | **S8** | |
|---|---|---|---|
| `ad-memory-squeeze` | 1.00 / 0.43 | **1.00 / 0.43** | identical |
| **`cart-bad-image-tag`** | **0.80 / 0.67** | **1.00 / 0.71** | **moved** |
| `cart-dependency-latency` | 1.00 / 0.33 | **1.00 / 0.33** | identical |
| `cart-redis-misconfig` | 0.80 / 0.67 | **0.80 / 0.67** | identical |
| `frauddetection-memory-squeeze` | 1.00 / 1.00 | **1.00 / 1.00** | identical |

Four of five reproduced to two decimal places, including `cart-redis-misconfig`'s two misses and
four extras and `frauddetection-memory-squeeze`'s exact `1.00 / 1.00`. **That is the D4 extraction
holding on live data**, not only over the 91 seed sets it was proved on. The uncounted second
`ad-memory-squeeze` run also returned `1.00 / 0.43` with the same four extras — **two runs of one
configuration, hours apart, giving identical triage figures**, which is the only within-sweep
replication this sweep contains.

**The fifth moved, and the counts say more than the ratios.** S7: 8 of 10 alerted predicted, 8 of 12
predicted alerted. S8: **10 of 10, and 10 of 14**. The alerted set is 10 in both. **The predicted set
grew from 12 to 14.**

**The prediction's reasoning was too strong when it was written, and this run is where that shows.**
It argued that because nothing in Batch B touched the traversal, the numbers must be identical. The
traversal is deterministic *given its seeds*, and the seeds are which services alerted and when — a
property of a live world that no sweep holds constant. S7's own document already demonstrated the
milder form: `product-catalog-flag-failure` moved 0.43 → 0.57 on an unchanged prediction because
`checkoutservice` joined the alerting set. **A moved figure is therefore not sufficient evidence of
a defect**, and this document does not claim one.

**It is also not sufficient evidence of no defect**, and the growth of the *predicted* set from 12 to
14 is not explained by the alerting-set arithmetic that covered S7's case. **That check has now been
run** — it is deterministic, costs nothing and needs no model, comparing `score.triage` in the two
runs' manifests (`20260830T033248Z` and `20260902T133126Z`):

| | S7 | S8 |
|---|---|---|
| alerted | 10 | **10 — the identical set**, nothing joined, nothing dropped |
| predicted | 12 | **14** |
| unmeasured edges crossed | 4 | **5** |
| missed | `frauddetectionservice`, `quoteservice` | **none** |

**The two services that joined the predicted set are exactly the two S7 missed**, and the alerting
set — the truth this is scored against — is byte-identical between the sweeps. **So the
alerting-set explanation is ruled out**: the same input produced a wider radius, and the radius grew
through **one additional unmeasured edge**.

**What that leaves.** The traversal code did not change and was proved identical over all 91 seed
sets, and the seeds derive from an alerting set that did not move — so the input that differs is the
**graph** the traversal walks, which is assembled at triage time and whose edges are not a frozen
key. One more edge was available and it was an unmeasured one, which is precisely the class of edge
ADR-0017 says membership reached through must not be read at full strength.

**This is recall improving, and it is not a result.** `0.80 → 1.00` on a scenario whose class the
same run got *wrong* is not evidence that anything got better; it is one draw at `n = 1`, and the
mechanism — an unmeasured edge appearing between sweeps — is the same mechanism that would produce a
false positive on a different topology. **What it establishes is that the blast radius is not stable
across sweeps even when the alerting set is**, which no prior sweep had shown and which prediction 6
assumed away. The follow-up is what determines the graph's edge set at triage time, and whether it
should be pinned the way the traversal is.

---

## 3. The scenario that was scored twice

**`ad-memory-squeeze` has two scored runs under one configuration**, `101301Z` and `104002Z`, four
and a half hours apart. This is declared rather than resolved quietly, because from outside it is
indistinguishable from re-running until a number improves.

| | `101301Z` **(counted)** | `104002Z` (reported only) |
|---|---|---|
| runtime | `bc222a353936` | `bc222a353936` |
| fault class | `resource_exhaustion` ✔ | `resource_exhaustion` ✔ |
| fix class | `config_revert` ✔ | `config_revert` ✔ |
| triage | 1.00 / 0.43, 1 unmeasured edge | 1.00 / 0.43, 1 unmeasured edge |
| extras | the same four services | the same four services |
| cost | \$0.7204 | \$0.7421 |
| manifest budget | **four bounds** (pre-#152) | eight bounds |

**Why the second run exists.** The first ran before #152, whose manifest defect printed four bounds
where Batch B had made eight — omitting the dollar cap, which would have made prediction 4
unverifiable from that run's record. The re-run was for the record, not the result.

**Why that is defensible, and how it is checkable.** #152 changed failure handling and what gets
recorded; nothing in it changes what the agent does on a successful run. So these are two runs of
one configuration, and **they agree on every scored axis** — class, fix class, triage recall,
triage precision, and the identity of all four false-positive services. The only difference is
\$0.0217 of cost. **No number was improved by the re-run**, which is the claim the artifacts
support and the reason the choice of which to count moves nothing.

**Which one counts, and why that one.** The first. The rule is that a scored run stands; if the
second were counted, the operative principle would become *the most recent run counts*, and that is
the principle under which sweeps get re-run until they read well.

---

## 4. Gate 3 — **DECLARED**

> *"The full pipeline — triage, plan, parallel specialists, synthesis, validated citations,
> proposal — completes successfully on at least 3 of the 4 fault classes."*

**All six stages executed on every scored run**, across all four fault classes. The sixth stage —
the proposer — did not exist before #143 and is why this gate was undeclarable until now.

The gate passes on both available readings of *"completes successfully"*:

| reading | result |
|---|---|
| the pipeline runs to completion | **4 of 4 classes** — zero gated, zero refused, zero bounds exhausted |
| and returns the correct fault class | **3 of 4 classes** — `resource_exhaustion`, `dependency_latency`, `bad_config` |

The stricter reading passes at exactly the threshold, which is worth saying plainly rather than
resting on the weaker one: **`bad_deploy` completed and was wrong.**

**What this declaration does not claim.** Not that the pipeline is accurate — that is Gate 4's
threshold and T4.2's scoring. Not that Batch B improved anything: six changes landed together at
`n = 1` per scenario and the pre-registration says in its own words that this sweep **cannot
attribute any difference to any one of them**. Not that the registered sweep completed.

---

## 5. What this sweep cannot say

- **`product-catalog-flag-failure` is unmeasured on this pipeline.** Its last recorded verdict is
  S7's.
- **`shipping-quote-misconfig` and `shipping-wrong-image` never ran.** The first is the sweep's
  registered *unsettled* scenario — wrong once, right once — and it stays unsettled.
- **Nothing here is a rate.** Five scenarios, one counted run each.

---

## 6. The full ledger of the day

**Twenty-two run directories, six scored and sixteen not.** All sixteen are kept: ADR-0022 §3.3's
rule is that a discarded run and its reason stay in the results directory, *so the number of runs is
a fact nobody can hide by tidying*. Reporting only the four that are convenient to explain would be
the same tidying by a different route.

| block | n | recorded reason | what it was |
|---|---|---|---|
| `093218Z`–`093248Z` | 8 | `pipeline-down` | The aborted first launch, one refusal per scenario: the environment lacked the embeddings extra and the orchestrator was not running. **Nothing injected** |
| `093450Z` | 1 | `pipeline-down` | Retry of the same, same cause |
| `095503Z` | 1 | `run failed` (exit 1) | `ANTHROPIC_API_KEY` unset. Exposed that `_judge` caught `SchemaValidationError` alone, so a transport error escaped it *and* the trajectory-preserving path, stranding the incident in `TRIAGING` with the fault already in the world. **Fixed by #152** |
| `101301Z` | — | scored | Counted. See §3 |
| `104002Z` | — | scored | Reported, not counted. See §3 |
| `130838Z` | 1 | `run failed` (exit 4) | `statistics.stdev` on a `NaN`. Prometheus returns `NaN` for `0/0`, the error-ratio template is a division, and this is the first scenario whose service actually stopped serving. **Fixed by #153** — dropped and counted, never coerced |
| `133126Z` | — | scored | Counted |
| `162429Z` | — | scored | Counted |
| `163827Z` | 1 | `baseline gate refused` | A prior incident was still inside the orchestrator's 300s settle window. **Nothing injected, nothing consumed.** ADR-0022 §3.1 working: a run started inside that window would have attributed its alerts to the previous incident |
| `164343Z` | — | scored | Counted |
| `220529Z` | — | scored | Counted |
| `222926Z`, `224251Z`, `225555Z`, `231048Z` | 4 | `run failed` (exit 4) | HTTP 400 `invalid_request_error` — *"Your credit balance is too low"* — at the triage call. Each injected the fault, failed, reverted, confirmed recovery, wrote `DISCARDED.md`. No trajectory persisted, no verdict, no tokens billed |

**On the four billing retries.** The pre-registration's rule is that a discard is recorded and never
re-run to improve a number. The decision to retry was taken on the ground that **no number
existed** — the agent never ran, so there was nothing to improve — and the retries are listed
individually rather than collapsed into one row. `product-catalog-flag-failure` was injected five
times across the day, each one reverted, with the baseline gate reporting `clean: 15 services
reporting, 0 alerts` before every attempt.

**Two of these discards were code defects that this sweep found and closed** — `095503Z` → #152,
`130838Z` → #153. Neither was re-run to improve a number; both were re-run because the code that
produced them no longer exists.

### Six narratives were rewritten by a formatting hook before their first commit

**Recorded because captured evidence is not supposed to be rewritten, and this was.** Staging these
artifacts, `trailing-whitespace` and `end-of-file-fixer` modified six run narratives — trailing
spaces stripped from two, a final newline added to six — at a moment when no pristine copy existed
in git to restore from.

| file | hook |
|---|---|
| `20260902T101301Z-ad-memory-squeeze/…-narrative.md` | both |
| `20260902T104002Z-ad-memory-squeeze/…-narrative.md` | both |
| `20260902T133126Z-cart-bad-image-tag/…-narrative.md` | final newline |
| `20260902T162429Z-cart-dependency-latency/…-narrative.md` | final newline |
| `20260902T164343Z-cart-redis-misconfig/…-narrative.md` | final newline |
| `20260902T220529Z-frauddetection-memory-squeeze/…-narrative.md` | final newline |

**No text changed** — no word, no figure, no citation. The bytes did, and a narrative is model
output recorded from a live run rather than a document anyone authored, so a reader diffing one
against a re-render would find a difference this note explains.

`.pre-commit-config.yaml` documented this failure mode in advance — *"Three trees now, each added
after a hook had already rewritten a capture in it"* — and `evals/runs` was the tree nobody had
added yet. **It is the fourth, added the same way as the first three: too late.** The exclusion
lands in this commit, so the remaining artifacts of this sweep and every one after it are safe.

### The defect the billing discards exposed

**The harness injects a fault before it discovers it cannot reach the model.** The baseline gate
already establishes the principle in the other direction — refuse before touching the world — and
the model's reachability is not checked at all. Four faults were injected into a live world to learn
a billing fact that one cheap call before the gate would have returned.

**Queued, not fixed here.** Changing the harness mid-sweep would have made the sweep measure
something nobody registered. The row is **Q20**, with these four discards as its evidence.

---

## 7. Follow-ups this sweep generated

| # | what | why it is here |
|---|---|---|
| 1 | **What determines the service graph's edge set at triage time, and whether it should be pinned** | Prediction 6, **answered and replaced**. The comparison ran: the alerting set is identical between S7 and S8, the predicted set grew by exactly the two services S7 missed, and the radius crossed one more unmeasured edge. The blast radius is therefore not stable across sweeps even when its seeds are, and the graph - not the traversal - is where that instability lives |
| 2 | **A pre-flight model check before the baseline gate** — **Q20** | §6. Four injections to learn a billing fact |
| 3 | **State whether the 4,000-token briefing cap binds the large roles at all** | Prediction 5. T7.3's ablation needs it stated, not inferred |
| 4 | **Q1's exclusion held under live pressure** — record it on the row | Run 5 requested container termination reason, restart counts and working-set bytes, got nothing, made the OOM inference from the log signature, and marked it `OPEN` as *inferred, never observed*. **Evidence for keeping the exclusion, not for reversing it** |
| 5 | **Run 4 returned `high` confidence with seven `OPEN` items** | One says the crash-loop rests entirely on a single log query. Confidence and stated residual uncertainty pull in different directions; worth a look before the next synthesizer change |
| 6 | **Run 4's `OPEN`: the frontend change query "covered onset-forward rather than the pre-onset period"** | If accurate this is a T3.2b/T3.4 finding — the change analyst opens at onset − 24 h by policy. Check against the trajectory; **no re-run** |
