# Dev sweep 8 — the Phase 3 pipeline as the specification describes it

**Scored against [`PREREGISTRATION-2026-09-02-batch-b.md`](PREREGISTRATION-2026-09-02-batch-b.md),
which was committed before any scenario ran.** Two of its six predictions failed. Both failures
are below, before the result they qualify.

**This is not the sweep that was registered.** Eight scenarios were registered, one run each. Five
were scored. One — `product-catalog-flag-failure` — was attempted four times and discarded four
times when the Anthropic API returned `invalid_request_error: credit balance too low`, and the
remaining two were never started for the same reason. **Nothing here was stopped for a result
anybody disliked**; the cause is billing, and it is stated in full in §5 so that a reader does not
have to take that on trust.

| | registered | actual |
|---|---|---|
| scenarios scored | 8 | **5** |
| fault classes covered | 4 | **4** |
| discards | 0 expected | **4**, all one scenario, all billing |
| baseline-gate refusals | — | 1 (settle window; nothing injected) |
| spend | \$8–12 | **\$3.5013** |

---

## 1. The runs

Runtime `faultline/0.0.1+prompts:bc222a353936`, capability `cap:c4d52d00`, world generation
`f5bd108f4f70` on every run. No stamp moved during the sweep.

| # | run | scenario | class | fix class | cost |
|---|---|---|---|---|---|
| 1 | `20260902T104002Z` | `ad-memory-squeeze` | `resource_exhaustion` ✔ | `config_revert` ✔ | \$0.7421 |
| 2 | `20260902T133126Z` | `cart-bad-image-tag` | `dependency_latency` **✘** (label `bad_deploy`) | **ABSTAINED** (label `rollback`) | \$0.7271 |
| 3 | `20260902T162429Z` | `cart-dependency-latency` | `dependency_latency` ✔ | `config_revert` ✔ | \$0.6775 |
| 4 | `20260902T164343Z` | `cart-redis-misconfig` | `bad_config` ✔ | `config_revert` ✔ | \$0.8761 |
| 5 | `20260902T220529Z` | `frauddetection-memory-squeeze` | `resource_exhaustion` ✔ | `config_revert` ✔ | \$0.4785 |

Run 3's fix class is counted correct through ADR-0027's `also_correct_remediation`: T7.17 measured
that deleting the netem qdisc clears the delay durably, 3/3, so the fault has two working fixes and
`config_revert` is one of them.

**Coverage 5/5. Fault class 4/5 of those answered. Fix class 4 correct, 1 abstained** (excluded
from accuracy, counted in coverage, per ADR-0022 §1.2). **Zero gated, zero flagged, zero specialist
solo failures, zero bounds exhausted, zero narratives refused.**

| class | runs | pipeline completed | class correct |
|---|---|---|---|
| `resource_exhaustion` | 2 | 2 | 2 |
| `bad_deploy` | 1 | 1 | 0 |
| `dependency_latency` | 1 | 1 | 1 |
| `bad_config` | 1 | 1 | 1 |

---

## 2. The predictions

### 1. The gate does not close on a real incident — **HELD**

**5 of 5 disposed `investigate`.** No `noise`, no `duplicate`.

The interesting half is that the gate declined to decline *while saying it had little to go on*.
Run 5's judgement is `low` confidence — *"No signal yet distinguishes deploy, config, or resource
causes"* — and it investigated anyway. Run 4's is `medium`, with `suspects unknown`. **A cheap
model asked to decline things did not decline things**, which is the failure this prediction named
as its strongest falsifier and which did not occur in five observations. At `n = 5` that is an
observation about the gate, not a rate.

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
| zero actions outside the allowlist, targets outside the radius, or unresolvable `rests_on` | **zero violations in five runs** |
| abstention rate reported, never scored | **1 of 5**, on run 2 |
| execution axis reported `NOT MEASURED` | **5 of 5** |

Two observations worth keeping, both first instances of behaviour T3.9 was built for:

**A proposal that named the condition under which it does nothing.** Run 5's change log records
`None -> memory=200m` with no prior value, and `if_wrong` says so: *"if no concrete prior spec is
stored the revert may be a no-op — the operator should verify one exists before executing."* A
proposal is supposed to be a falsifiable claim rather than a command, and this is what that looks
like when the claim is about the proposal's own precondition.

**An abstention that named what would supersede it.** Run 2 declined to propose and said what
evidence would change that, rather than proposing something weak to fill the field.

### 4. No run exhausts a bound — **HELD, and the cost estimate missed low**

No run exhausted the token bound, the wall clock, the dispatch rounds, or the new \$2 dollar cap.
The most expensive run was **\$0.8761**, 44% of the cap.

**\$3.5013 over five runs, \$0.7003 each, projecting ≈ \$5.60 for eight against a registered
\$8–12.** That is outside the registered band. **An underrun is a miss of the estimate in the same
way an overrun is**, and it is recorded here rather than quietly banked: the estimate assumed two
extra model calls and a larger synthesizer brief would cost more than they did.

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
wrong about *which* sections, which is a bookkeeping error in the prediction.

**Not established here, and needed before the next briefing change:** the per-role `over_budget`
flags and the section names live on the trajectory rows, not in `report.txt`, and were not
transcribed for runs 1–3. **The question left open is whether the 4,000-token cap binds the roles
that matter at all** — the synthesizer, scribe and proposer briefs are built almost entirely from
`essential` sections, which are never dropped, so a cap they exceed is recorded rather than
enforced by design (`briefing.py`, `over_budget`). T7.3's ablation needs that number stated, not
inferred.

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
holding on live data**, not only over the 91 seed sets the extraction was proved on.

**The fifth moved, and the counts say more than the ratios.** S7: 8 of 10 alerted predicted, 8 of
12 predicted alerted. S8: **10 of 10, and 10 of 14**. The alerted set is 10 in both. **The
predicted set grew from 12 to 14.**

**The prediction's reasoning was too strong when it was written, and this run is where that shows.**
It argued that because nothing in Batch B touched the traversal, the numbers must be identical.
The traversal is deterministic *given its seeds*, and the seeds are which services alerted and
when — a property of a live world that no sweep holds constant. S7's own document already
demonstrated the milder form of this: `product-catalog-flag-failure` moved 0.43 → 0.57 on an
unchanged prediction because `checkoutservice` joined the alerting set. **A moved figure is
therefore not sufficient evidence of a defect**, and this document does not claim one.

**It is also not sufficient evidence of no defect**, and the growth of the *predicted* set from 12
to 14 is not explained by the alerting-set arithmetic that covered S7's case. The check that would
settle it is deterministic, costs nothing, and needs no model: **compare the `blast_radius` arrays
in the two runs' manifests** and name the two services that joined. That is left as the follow-up
rather than guessed at here.

---

## 3. Gate 3 — **DECLARED**

> *"The full pipeline — triage, plan, parallel specialists, synthesis, validated citations,
> proposal — completes successfully on at least 3 of the 4 fault classes."*

**All six stages executed on all five scored runs**, across all four fault classes. The sixth
stage — the proposer — did not exist before #143 and is why this gate was undeclarable until now.

The gate passes on both available readings of *"completes successfully"*:

| reading | result |
|---|---|
| the pipeline runs to completion | **4 of 4 classes** — five runs, zero gated, zero refused, zero bounds exhausted |
| and returns the correct fault class | **3 of 4 classes** — `resource_exhaustion`, `dependency_latency`, `bad_config` |

The stricter reading passes at exactly the threshold, which is worth saying plainly rather than
resting on the weaker one: `bad_deploy` completed and was wrong.

**What this declaration does not claim.** Not that the pipeline is accurate — that is Gate 4's
threshold and T4.2's scoring. Not that Batch B improved anything: six changes landed together at
`n = 1` per scenario and the pre-registration says in its own words that this sweep **cannot
attribute any difference to any one of them**. Not that the registered sweep completed.

---

## 4. What this sweep cannot say

- **`product-catalog-flag-failure` is unmeasured on this pipeline.** Its last recorded verdict is
  S7's.
- **`shipping-quote-misconfig` and `shipping-wrong-image` never ran.** The first is the sweep's
  registered *unsettled* scenario — wrong once, right once — and it stays unsettled.
- **Nothing here is a rate.** Five runs, one each, `n = 1` per scenario.

---

## 5. The discards, and the refusal

**Four discards, one scenario, one cause.** Each injected the fault, failed at the triage call with
HTTP 400 `invalid_request_error` — *"Your credit balance is too low to access the Anthropic API"* —
reverted the world, confirmed recovery, and wrote `DISCARDED.md`. Exit 4. No trajectory persisted,
no verdict artifact, no tokens billed.

| attempt | run | outcome |
|---|---|---|
| 1 | `20260902T222926Z` | DISCARDED — credit balance |
| 2 | `20260902T224251Z` | DISCARDED — credit balance |
| 3 | `20260902T225555Z` | DISCARDED — credit balance |
| 4 | `20260902T231048Z` | DISCARDED — credit balance |

**All four are kept.** The pre-registration's rule is that a discard is recorded and never re-run
to improve a number; the decision to retry was taken on the ground that **no number existed** — the
agent never ran — and it is recorded here with the retries visible rather than collapsed into one
row. The scenario was injected five times in total (four discards plus one earlier attempt), each
one reverted, with the baseline gate reporting `clean: 15 services reporting, 0 alerts` before
every attempt.

**One baseline-gate refusal, which is not a discard.** `20260902T163827Z-cart-redis-misconfig`
refused before injecting: a prior incident was still inside the orchestrator's 300s settle window.
**Nothing was injected and nothing was consumed.** The gate is ADR-0022 §3.1 working — a run
started inside that window would have attributed its alerts to the previous incident.

### The defect this exposed

**The harness injects a fault before it discovers it cannot reach the model.** The baseline gate
already establishes the principle — refuse before touching the world — and the model's reachability
is not checked at all. Four faults were injected into a live world to learn a billing fact that one
cheap call before the gate would have returned.

**Queued, not fixed here.** Changing the harness mid-sweep would have made the sweep measure
something nobody registered. The row goes to `docs/QUEUE.md` with these four discards as its
evidence.

---

## 6. Follow-ups this sweep generated

| # | what | why it is here |
|---|---|---|
| 1 | **Compare the `blast_radius` arrays** for `cart-bad-image-tag` between S7 and S8 | Prediction 6. Deterministic, no model, and it names the two services that joined the predicted set |
| 2 | **A pre-flight model check before the baseline gate** | §5. Four injections to learn a billing fact |
| 3 | **State whether the 4,000-token briefing cap binds the large roles at all** | Prediction 5. T7.3's ablation needs it stated, not inferred |
| 4 | **Q1's exclusion held under live pressure** — record it on the row | Run 5 requested container termination reason, restart counts and working-set bytes, got nothing, made the OOM inference from the log signature, and marked it `OPEN` as *inferred, never observed*. **Evidence for keeping the exclusion, not for reversing it** |
| 5 | **Run 4 returned `high` confidence with seven `OPEN` items** | One of them says the crash-loop rests entirely on a single log query. Confidence and stated residual uncertainty pull in different directions; worth a look before the next synthesizer change |
| 6 | **Run 4's `OPEN`: the frontend change query "covered onset-forward rather than the pre-onset period"** | If accurate this is a T3.2b/T3.4 finding — the change analyst opens at onset − 24 h by policy. Check against the trajectory; **no re-run** |
