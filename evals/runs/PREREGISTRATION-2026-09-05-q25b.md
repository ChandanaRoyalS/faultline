# Pre-registration — Q25b, after `extra="forbid"` destroyed a second verdict

**Written and committed before the run.** One scenario, one run, `cart-bad-image-tag`, again.

## Why there is a second pre-registration a day after the first

`PREREGISTRATION-2026-09-05-q25.md`'s **prediction 1 failed**, and it failed into the clause that
document registered as the larger finding:

> *"If validation fails again on a **different** extra field, that is a finding about the policy
> rather than about this key: it would mean `extra="forbid"` on model-facing contracts is a
> standing hazard, and the right response would be to reconsider the policy across every contract
> rather than to add a second field."*

It did. `Candidate.remediation_class` was added; the model invented **`alternatives_note`**, valued
`""`, and the verdict was rejected twice again.

| stamp | what the model volunteered | outcome | cost |
|---|---|---|---|
| `ba8684b01201` | `remediation_class` on both alternatives | no verdict | \$0.3890 |
| `42e34a1811c4` | `alternatives_note: ""` | no verdict | \$0.3433 |

**\$0.7323 for zero verdicts on one scenario, and each fix closed exactly one key.**
`cart-bad-image-tag` has now failed to be diagnosed three times running — wrong in dev sweep 8,
unreachable in dev sweep 9, unreachable again at `42e34a1811c4`.

## What changed, and the part a test forced

**Reporting contracts accept unexpected keys; requesting contracts still refuse them.**

| | contracts | policy |
|---|---|---|
| **reported** — read field by field, extras inert | `Verdict`, `Candidate`, `Finding`, `RuledOut`, `SpecialistFindings`, `TriageJudgement`, `NarrativeSection`, `NarrativeDraft` | `extra="allow"`, and the harness records what arrived |
| **requested** — the model asking the harness to act | `Dispatch`, `SkippedSpecialist`, `DispatchPlan`, `Proposal` | `extra="forbid"`, unchanged |

**The split was forced by a test and the test was right.** The first version of this change relaxed
every contract, and `test_the_window_is_told_to_the_specialist_never_asked_of_it` failed: it
asserts a planner cannot name its own query window — *"the window is a property of the incident
and the evidence already read; no contract has a field through which a model could name one"* —
and it enforces that through `extra="forbid"` on `Dispatch`. A blanket relaxation would have opened
that boundary **silently**, because nothing reads a `window` key: the model would simply have been
able to send one.

So the policy is not *relax the contracts*. It is **relax the ones whose extras are inert, and keep
refusing the ones where an unexpected key is an attempted instruction.**

**`allow` rather than `ignore`**, because ignoring discards whatever the model meant — which is
exactly how `remediation_class` stayed invisible until it broke a run. `unexpected_fields()` puts
the keys on the manifest, computed from the declared field names, so a field that later becomes
real stops being reported on its own.

**Nothing declared is weakened.** Types and required fields are unchanged: a reply missing
`fault_class`, or carrying one outside the literal, is rejected exactly as before.

## The stamp

`ba8684b01201` → `42e34a1811c4` → **`b6837dd449ca`**. Three prompt generations in two days on one
contract. `cap:c4d52d00` and world `f5bd108f4f70` unchanged.

**The middle one lasted a single run**, which is the shortest-lived stamp this project has
recorded and is itself the evidence for this change: a fix that closes one key at a time, at a
stamp move each, is not a fix.

## The predictions

### 1. The verdict validates, and this time the mechanism cannot recur

**Registered: a verdict is produced.** Not because the specific key is now permitted — that was
the last prediction and it was wrong — but because **no unexpected key on a reporting contract can
reject a reply any more.** The failure mode is closed by class rather than by instance.

**If a verdict still fails to validate, it will be for a declared field**: a missing requirement or
a value outside a literal. That would be a different finding entirely and a much less comfortable
one, because it would mean the synthesizer cannot satisfy a schema it is shown.

### 2. `unexpected_fields` on the manifest is non-empty

**Registered: at least one key is recorded.** The model has volunteered one on both attempts. If
this run's manifest records `{}`, the two earlier failures were flukes of sampling rather than a
tendency, and the policy change is insurance rather than a repair — still worth having, but the
story about it is wrong.

**What lands there is the interesting part.** `remediation_class` was worth adding.
`alternatives_note: ""` was worth nothing. A third distinct key would say the model improvises
freely and the schema block is advisory.

### 3. The verdict names `cartservice`

**Registered: `service` is `cartservice`.** The image tag does not exist, the container never
comes up, and its callers see connection failures. The culprit sits one hop behind the loudest
service — the trap the pipeline cleared 4 of 4 times in dev sweep 9.

### 4. `depth` is at least 2

**Registered, and grounded rather than guessed.** The rejected reply at `ba8684b01201` carried
exactly two alternatives; the rejected reply at `42e34a1811c4` carried at least one. This
synthesizer ranks on this scenario, and both times the ranking is what the contract choked on.

### 5. Fault class: the clause fires this time or it does not fire at all

**No outcome predicted.** Dev sweep 8 scored this scenario **wrong**. Sweep 9 and the
`42e34a1811c4` run never reached a verdict. So a wrong answer here is the **second scored miss on
the only `bad_deploy` scenario in the catalog**, and dev sweep 9's prediction 6 clause applies:
it stops being an instance and becomes a systematic problem needing its own investigation.

A correct answer makes it 1 of 2 and leaves the class genuinely unsettled.

### 6. Cost \$0.55–\$0.85

The two failed runs cost \$0.3890 and \$0.3433 and both died before synthesis completed. A run that
finishes should cost about the \$0.53 median plus the extra keys.

### 7. Triage is *not* predicted to be identical, and the last document was wrong to

**Registered: no prediction.** Q25's prediction 7 said triage would be byte-identical to dev sweep
9's run of this scenario and it was not — 0.80/0.67 against 1.00/0.71 — because this run started
from `frontend` and sweep 9's started from `checkoutservice`. **The traversal is deterministic
given `start_from`; `start_from` is a property of which service alerted first, which varies.**

Dev sweep 9's own document said exactly this — *"the determinism is in the prediction, not in the
pair"* — and the next day's pre-registration asserted the stronger claim anyway. Recorded here
because the error was in the prediction, not the pipeline.

## Order of operations

1. **Confirm the stamp reads `b6837dd449ca`** — `uv run pytest tests/test_harness_run.py -k stamp`.
2. Confirm the world is quiet and the orchestrator is polling; the baseline gate does both.
3. **Run `cart-bad-image-tag` once.** No repeats.
4. **Read `unexpected_fields` on the manifest** before reading anything else — it is the direct
   measurement of prediction 2 and the thing this change exists to make visible.
5. Judge the narrative if one is produced.
6. Write the result against these seven predictions, including the ones that fail.
