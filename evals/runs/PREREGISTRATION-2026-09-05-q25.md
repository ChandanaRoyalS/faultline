# Pre-registration — Q25, and the one scenario dev sweep 9 could not diagnose

**Written and committed before the run.** One scenario, one run, `cart-bad-image-tag`.

## The stamp moves, and this time it costs something

| | stamp | what moved it |
|---|---|---|
| dev sweep 8 | `bc222a353936` | Batch B |
| — | `7c6894e9dd92` | Batch C. Never run |
| dev sweep 9 | `ba8684b01201` | `Verdict` gained `service` and `alternatives` (T4.2) |
| **this run** | **`42e34a1811c4`** | `Candidate` gained an optional `remediation_class` (Q25) |

**T4.2's move was free and this one is not.** Batch C had left no scored figures to orphan, so
`ba8684b01201` cost nothing when it landed. `42e34a1811c4` costs **dev sweep 9's four scored
verdicts**, and it is being spent anyway because four is the smallest that cost will ever be:
every further run at `ba8684b01201` raises it, and the contract is broken in a way that destroys
whole runs rather than degrading them.

**Capability `cap:c4d52d00` and world generation `f5bd108f4f70` are unchanged.** Only the prompt
digest moves.

## What changed, exactly

`Candidate.remediation_class`, optional, and one line added to `SYNTHESIZER_SYSTEM`'s JSON schema
block naming the key. **No prose was edited.** That matters for attribution: a behavioural
difference here is down to a key the model may now emit, not to a rewording it was also handed.

The field is optional rather than required, and that is not a hedge. A candidate whose fix is
genuinely undetermined should say so by omission; `none` already means *"no action fits"* on
`Verdict` and would be a claim rather than a gap.

**Why this route and not the cheaper one.** `extra="ignore"` would have accepted the superset and
dropped it, silently discarding something the model meant to say. The model's instinct was right —
an alternative root cause with no proposed fix is half a claim — and T4.2's top-3 scoring extends
to remediation for free if anyone wants it later. `docs/QUEUE.md` priced all three routes.

## Scope: one scenario, one run

`cart-bad-image-tag`, no repeats, no baseline arm.

**This is a first observation, not a re-run.** Dev sweep 9 injected this scenario, spent \$0.3890,
and produced no verdict — the synthesizer returned two ranked alternatives, each carrying the
`remediation_class` the prose primes, and validation failed twice. Nothing was diagnosed, so
nothing is being repeated and ADR-0022 §3.3 does not reach it.

## The predictions

### 1. The verdict validates

**Registered: a verdict is produced.** The exact failure — `extra_forbidden` on
`alternatives[].remediation_class` — cannot recur, because the field is now permitted.

**If validation fails again on a *different* extra field, that is a finding about the policy
rather than about this key**: it would mean `extra="forbid"` on model-facing contracts is a
standing hazard, and the right response would be to reconsider the policy across every contract
rather than to add a second field.

### 2. The verdict names `cartservice`

**Registered: `service` is `cartservice`.** The scenario points the service at an image tag that
does not exist, so the container never comes up and its callers see connection failures. The
culprit is one hop behind the loudest service, which is the trap this catalog sets repeatedly and
which the pipeline cleared 4 of 4 times in dev sweep 9.

A `frontend` or `checkoutservice` here would be the propagator, and would sit badly beside sweep
9's clean sweep on that axis.

### 3. `depth` is at least 2 — and this prediction is unusually well grounded

**Registered: the verdict carries at least one alternative, and most likely two.**

Every other prediction about ranking in this project has been a guess. This one is not: **the
failed run's rejected reply carried exactly two**, which is how it broke. The synthesizer ranks on
this scenario, and we know because the ranking is what the contract choked on.

**If depth comes back 1, the schema change suppressed ranking rather than enabling it**, which
would be the most surprising outcome available here and would need explaining before anything else
in this document is read.

### 4. `remediation_class` is populated on at least one alternative

**Registered: at least one candidate carries a non-null `remediation_class`.** The model
volunteered this field unprompted when it was forbidden. If it now declines to fill a field the
schema explicitly offers, the earlier emission was an artefact of the prose rather than a
judgement the model wanted to make, and the field is decoration.

### 5. Fault class: registered as the second attempt at a class with one measurement

**No outcome is predicted, and the reading is registered instead.**

Dev sweep 8 scored this scenario **wrong** on fault class. Dev sweep 9 never reached a verdict. So
this is the **second diagnosis attempt** on the only `bad_deploy` scenario this pipeline has, and
sweep 9's prediction 6 clause now applies for real:

> *"if it fails again, that is the second consecutive failure on the only `bad_deploy` scenario
> this pipeline has measured, and it stops being an instance."*

**A wrong answer here makes `bad_deploy` a systematic problem rather than a sample of one**, and
belongs in the next pre-registration as a named investigation. A correct answer makes it 1 of 2
and leaves the class genuinely unsettled, which is a weaker and more honest place than it looks.

### 6. Cost

**Registered: \$0.55–\$0.85.** The failed run cost \$0.3890 and died before synthesis; a completed
run at the measured median is \$0.53, and this one asks the synthesizer for one more key per
alternative. Materially above \$0.85 would be a finding about the added field.

### 7. Nothing else moves

**Registered: `cap:c4d52d00` and `f5bd108f4f70` unchanged, triage recall/precision 1.00 / 0.71 —
byte-identical to dev sweep 9's run of this scenario.** The blast-radius traversal shares no code
with anything this change touches, and the alert set is the same world's.

A difference in triage would mean the world moved, not the pipeline, and would invalidate the
comparison this run exists to make.

## What would surprise me

1. **`depth` of 1** — prediction 3, and the only one whose failure would suggest the fix broke
   what it was meant to repair.
2. **A second `extra_forbidden` on a different key** — prediction 1, and a much larger problem
   than the one being fixed.
3. **`frontend` as the culprit** — prediction 2, and it would break sweep 9's 4-of-4 on the axis
   that sweep's headline rests on.
4. **Every `remediation_class` null** — prediction 4. The field would be decoration and should be
   removed rather than kept.

## Order of operations

1. **Confirm the stamp reads `42e34a1811c4`** before anything is injected —
   `uv run pytest tests/test_harness_run.py -k stamp`.
2. **Confirm the world is quiet and the orchestrator is polling.** The baseline gate does both.
3. **Run `cart-bad-image-tag` once.** No repeats. A discard is recorded and not re-run.
4. **Judge the narrative** if one is produced, with the same `claude-haiku-4-5` and the same
   lineage opt-in as all 82 judged runs.
5. **Write the result against these seven predictions, including the ones that fail** — which is
   the only reason to write them down first.
