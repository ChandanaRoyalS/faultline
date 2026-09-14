# Pre-registration — Q53, does retrieval depth change a verdict?

**Written and committed before any run.** Governed by [ADR-0041](../../docs/adr/0041-deciding-a-change-to-the-retrieval-depth.md).

Four retrieval write-ups have measured whether a relevant document is **reachable**. None has
measured whether the model reads it and answers differently. T6.4 §5 named that limitation and it
has survived every measurement since.

**This is the first task in this repository that spends money to answer a retrieval question**, and
the first stage of it is designed to be killable for about twelve dollars.

---

## 1. What is already known, at $0

| | recall@3 | recall@5 |
|---|---:|---:|
| flag 0, `retrieval_k = 3` (production today) | **0.395** | 0.442 |
| flag 2 | 0.419 | **0.605** |

- **Raising `k` alone buys two queries of 43.** Flag 2 alone at `k = 3` buys one — inside ADR-0040
  clause 5's band, and Q52 measured that selecting among flags at `k = 3` is *worse* than not
  selecting (out-of-sample −0.0288). **Only the joint change is worth testing**, and that is what
  this registers.
- **Q52 established flag 2's `k = 5` margin is not a selection artefact**: 0.1628 in-sample against
  0.1545 out-of-sample, 95% surviving, selected on 733 of 1000 splits.
- **The token cost of `k = 5` is negligible and is now measured, not argued.** Over 269 recorded
  retrievals the rendered lines are a median of 321 characters each; two extra chunks at two
  retrieval sites is **~321 tokens per investigation, $0.0016** — 0.27% of a median run. Q53's row
  says a larger `k` "puts more retrieved text in front of the model on every investigation", and it
  does, and that is not a cost worth weighing. **The real risk is distraction**, which is precisely
  what a verdict comparison measures and a token count cannot.
- **What a run costs**, from 218 recorded trajectories with token counts:
  median **$0.597**, mean $0.588, p90 **$0.787**, max $1.049.

## 2. The change under test

`TEXT_NORMALISATION` 0 → **2** and `ContextSettings.retrieval_k` 3 → **5**, together. Neither alone.

## 3. The design

**Paired on the incident.** One injection, one incident, **two investigations** — one at
(flag 0, k = 3), one at (flag 2, k = 5). The pair shares a world state, an incident, an alert set
and a change log, so the only difference between the two verdicts is what retrieval handed the
model. World variance is the dominant noise source in this benchmark and pairing removes it
entirely; ten pairs this way are worth far more than twenty unpaired runs.

**Ten pairs, one per dev scenario**, taken in catalog order. No selection.

**Order is alternated**, arm-first on odd pairs and arm-second on even. A second investigation runs
against an incident that already carries a proposal from the first, and whether that matters is
unknown — T6.3's reject-loop re-investigates and found the driver needed the harness's own bounds
before it was comparable. Alternating does not remove an order effect; it stops one being confounded
with the arm.

### 3.1 What ten pairs can and cannot do

Registered as arithmetic, before any run. If the true rate at which a verdict changes is `p`, the
chance this pilot sees **at least one** change is `1 − (1−p)¹⁰`:

| true rate `p` | chance the pilot sees any change |
|---:|---:|
| 0.186 — the retrieval upper bound, 8 of 43 queries | **87%** |
| 0.10 | 65% |
| 0.05 | 40% |

So **ten pairs can falsify "this matters a lot" and cannot establish "this never matters."** It is
a kill switch, not a measurement, and no result from it will be reported as a rate.

### 3.2 The decision

- **0 of 10 verdicts differ** → Q53 closes. The effect is below the retrieval bound with 87%
  confidence, and the larger measurement is not funded. Flag 0 and `k = 3` stand.
- **1 or more differ** → the pilot has done its job and stops. It does **not** adopt anything: a
  changed verdict is not a better one, and `n = 10` cannot say which direction dominates. The next
  step is a registered measurement at 30–40 pairs, priced from this pilot's actual spend.

**Adoption is out of scope for this task entirely.** ADR-0041's rule is satisfied on the retrieval
side already; what is missing is evidence about verdicts, and one pilot does not supply it.

## 4. The budget, as a hard stop

- 20 investigations at the p90 of **$0.787** = **$15.74**.
- The harness discards about **16.7%** of runs (`outcome_of`'s own measurement), so ~24 runs to get
  20 scored: **$18.89**.
- **Hard ceiling: $25.00.** If spend reaches it, the run stops where it is and reports what it has,
  including the pairs it did not complete. A budget that is revised upward mid-task is not a budget.
- `budget_max_usd` stays at its per-incident 2.0. Nothing here raises a per-run cap.

## 5. Predictions

1. **At least one of the ten pairs produces a different `fault_class` or `remediation_class`.**
2. **No more than three do.** The retrieval bound is 18.6% and a reachable document is not a read
   one, so I expect the verdict rate to sit below the retrieval rate.
3. **Where a verdict changes, `k = 5` is right at least as often as `k = 3`.** Registered because
   the opposite is the outcome that would matter most: more context making the answer worse is the
   distraction risk, and it is the one thing this pilot could discover that would settle Q53 against
   the change outright.
4. **No pair differs only in `remediation_class`.** `baselines.py` records the class→remediation
   mapping as one-to-one across all eighteen scenarios, so remediation should move only when the
   class does. If one moves alone, that mapping has an exception nobody has found.
5. **Total spend is under $15.**
6. **At least 8 of the 10 pairs complete** — the discard rate is 16.7% and both halves of a pair
   must score for the pair to count.
7. **The `k = 5` arm's retrieved documents are a superset of the `k = 3` arm's in fewer than half
   the pairs.** Q48 established the two are *not* nested: each arm applies its own `LIMIT k` and
   `fuse` takes `limit=k`, so a deeper cut can reorder rather than extend. Listed because a reader
   will assume nesting and the record should say it does not hold.

## 6. What this cannot settle

- **Whether `k = 5` is better.** Ten pairs cannot. That is the 30–40 pair measurement, and this
  pilot exists to decide whether to pay for it.
- **Whether the change helps the agent on holdout scenarios.** Dev only. Every holdout entry is
  spent deliberately and none is spent on a pilot.
- **Whether flag 2 is right.** Q52 left it unconfirmed and unadoptable for want of held-out queries;
  that is unchanged, and this task adopts nothing.
- **Whether the floor is cleared.** If `k = 5` were adopted, a configuration measured at 0.605 would
  meet a 0.60 floor written at `k = 5` when production ran 3. ADR-0041 says what to do about that:
  **a floor met because the depth moved to meet it is not a floor that was cleared**, and it must be
  said in the same breath as any adoption.

---

# Amendment 1 — the second arm is only reachable through `REJECTED`, so the outcome is `fault_class`

**2026-09-14, written before the pilot ran and after the third dry run.** Appended, not edited:
nothing above this line is changed, and §3 and §5 are to be read against what follows.

## What the dry run found

`--only cart-bad-image-tag`. The first arm completed and wrote its verdict artifact. The second
refused:

> `REFUSED: incident 514bd81a-1baf-4bbe-8b43-975a2a36dd29 is in state proposing; the machine`
> `investigates from rejected, triaging only. See ADR-0016 and`
> `faultline.orchestrator.machine.INVESTIGABLE.`

**This is a defect in §3's design, not in the driver.** `machine.ALLOWED` admits `PLANNING` from
`TRIAGING` and from `REJECTED` and from nowhere else — which is the whole reason `INVESTIGABLE` has
exactly two members — and an incident that has been investigated once is past `TRIAGING`
permanently. So *"one injection, one incident, two investigations"* is not a design the state
machine can run. There is no third door, and the cost of finding out was **$0.79**.

The machine is right and the registration was wrong. Adding a transition so that a measurement
could proceed is the thing the reject-loop driver refused to do in its own docstring — *"changing
the product to fit the instrument"* — and it is refused again here.

## The amendment

**§3 stands, with the route named: the pair's second arm is reached by rejecting the first arm's
proposal through `POST /api/v1/incidents/{id}/reject`.** One injection, one incident, one
rejection, two investigations. `REJECTABLE` is `PROPOSING`, `SYNTHESIZING`, `AWAITING_APPROVAL`, so
this works whether the first arm proposed an action or abstained.

**`REJECTION_REASON` is fixed in `depthpilot.py` and is identical for all ten pairs.** It carries no
scenario-specific content, and a test asserts both. A reason chosen after seeing a verdict would be
prompt-fitting.

**§5's outcome narrows from *`fault_class` or `remediation_class`* to *`fault_class`*.**

This is the price, and it is paid rather than argued away:

- A rejection reaches **the proposer's brief and nothing else** — `roles.py`'s
  `Section(name="operator-rejection", priority=4, essential=True)`, pinned by
  `test_an_operator_rejection_reaches_the_proposer_in_the_user_message_only`, which exists because
  operator text is untrusted input and would otherwise strand `stamp.prompt_digest()`.
- **T6.3 measured what a rejection does to the next proposal: 2 of 2 changed, both abstentions**
  (`LOOP-2026-09-12-t6.3.md` §9). So `remediation_class` in this pilot is contaminated by an effect
  this repository has already measured at 100%. Counting it would let ten pairs recommend funding a
  30–40 pair measurement on T6.3's finding wearing Q53's name.
- **`fault_class` is clean.** It is the synthesizer's, and the synthesizer never sees the rejection.
  The re-investigation reuses the triage it already has, works from the same episodes, the same
  catalog and the same corpus — `context/seed.py` is the only writer to the past-incident store, so
  nothing the first arm did changes what the second one can retrieve. Retrieval is the only injected
  difference upstream of the verdict.

`remediation_class` is **recorded in every pair and in the artifact**, under a line saying why it
does not decide. If it moves in roughly half the pairs, that is T6.3's effect appearing again; if it
never moves, that is worth knowing too.

**The symmetry cannot be restored and no attempt is made to fake it.** Seeding a proposal and
rejecting it before the *first* arm as well — the reject-loop's trick, and free — would make both
arms run from `REJECTED`, but the second arm's brief would still quote the first arm's real
proposal while the first arm's quoted a fabricated one. Structural symmetry with asymmetric content
is worse than an acknowledged asymmetry, because it looks controlled.

## What §5's predictions become

| # | as registered | after this amendment |
|---|---|---|
| 1 | at least one pair produces a different `fault_class` **or** `remediation_class` | **at least one produces a different `fault_class`** |
| 2 | no more than three do | unchanged, read on `fault_class` |
| 3 | where a verdict changes, `k = 5` is right at least as often | unchanged |
| 4 | no pair differs only in `remediation_class` | **retired.** It is unanswerable here: the rejection moves `remediation_class` by a route that has nothing to do with retrieval. It was a real prediction about the one-to-one class→remediation mapping and this pilot can no longer test it. |
| 5–7 | spend, completion rate, document nesting | unchanged |

**Prediction 1 gets harder and that is the correct direction.** It was registered against two
channels and now has one, and the one it keeps is the narrower. Nothing about the decision rule in
§3.2 changes: 0 of 10 closes Q53, 1 or more stops the pilot and adopts nothing.

## Two operational consequences

**The pilot now needs `faultline-ingest` running with the executor key.** The rejection goes through
the authenticated route rather than through `record_rejection`, so that the pilot cannot reach
`REJECTED` by a path no operator has. `faultline-depth-pilot` refuses before injecting anything if
`FAULTLINE_API_PASSWORD` is unset, and — the lesson T6.3 paid for and this task has now paid for
twice — it also refuses before injecting anything if the `agents` extra is missing.

**No `InvestigationRunner` may be running with `--investigate` against this world.**
`runner._reinvestigable()` picks up rejected incidents under the cap and starts its own
investigation. Against this pilot that is both a race for the second arm and up to ten
model calls nobody budgeted. This is stated rather than enforced: the driver cannot see the
runner, and a check it cannot make honestly is worse than a sentence in the protocol.

## The budget is unchanged

Still twenty investigations, still a hard **$25.00**. The rejection costs nothing — it is a state
transition and a ledger row. The $0.79 the third dry run spent is **already counted against this
task's record** and is not re-spent: Q53's running total before the pilot is **$1.39**, for three
defects that would each have spoiled the ten-pair run.

---

# Amendment 2 — a budget that can see a failed arm, and one re-attempt per scenario

**2026-09-14, written before the pilot ran and after the fourth dry run.** Appended, not edited.

## What the dry run found, at $0.12

`--only cart-bad-image-tag`, ceiling lowered to $2. The first arm died:

> `FAILED MID-INVESTIGATION: SchemaValidationError: schema validation failed twice`
> `(1 validation error for DispatchPlan / skipped_note / Extra inputs are not permitted)`

and the pilot printed **`spend $0.00 of $25.00`**, which was false. A triage had been judged and a
planner had run and been refused twice; the incident went to `failed` with trajectory `808bae11`
holding all of it. There was no verdict, the pair's cost was summed from its verdicts, and so the
spend was invisible.

**Two defects, and the accounting one is the serious one.**

### 1. The ceiling could not see a failed arm

`PairResult.cost_usd` summed `Verdict.cost_usd`, which exists only when an investigation returned a
verdict. Twenty investigations at the harness's own 16.7% discard rate is between three and four
runs whose spend the $25 ceiling would never have observed. §4 says *a budget that is revised
upward mid-task is not a budget*; a budget that cannot observe its own spend is worse, because
nothing announces it.

**A pair now costs what its incident cost** — every token on every trajectory carrying that
incident id, read from the world after each arm, verdict or no verdict. The figure appears per pair
in the artifact and in the rendered report.

### 2. A dead pair could not be retried, and the arithmetic behind prediction 6 was wrong

A pair dies whole when either arm fails, and the incident is then `failed`, which ADR-0016's table
makes terminal — there is no resuming it. §5's prediction 6 reads *"At least 8 of the 10 pairs
complete — the discard rate is 16.7% and both halves of a pair must score for the pair to count."*
It names the right mechanism and then uses the per-**run** rate: both halves scoring is
0.833² = **0.694**, so the expectation is 6.9 complete pairs, not 8, and P(≥8) is about 13%.

**Prediction 6 stands exactly as registered and will be scored as written.** It is recorded here as
wrong on its own arithmetic, before the run, because noticing it afterwards and reporting it as a
near miss would be worth nothing.

What follows from it is the real problem: at ~7 complete pairs §3.1's detection probability at the
retrieval bound falls from **87% to 76%**, and the pilot was budgeted and argued at ten.

**So: one re-attempt per scenario, and one only.** A pair that fails for any reason other than a
completed comparison is re-injected once. `ATTEMPTS_PER_SCENARIO = 2`, in the driver, fixed before
any pair ran.

- **The retry keeps the arm order of the attempt it replaces.** A re-attempt that flipped the order
  would confound the retry with the arm, which is the one thing §3's alternation exists to prevent.
- **It is a rule about run failures, not about results.** A differing verdict is a completed pair
  and is never retried. A rule that retried until the answer changed would be a different study.
- **Two, not "until it works."** A retry count chosen after seeing how many pairs completed would
  be a budget responding to its own outcome.
- **Cost.** Up to ten extra attempts in the worst case, but the expectation is about three at the
  measured discard rate — roughly **$4**, inside the unchanged $25 ceiling, which is what the
  ceiling is for. Every attempt is reported, including the ones that died.

## What this does not change

The arms, the outcome channel (`fault_class`, Amendment 1), §3.2's decision rule, and the ceiling.
Ten pairs is still the target and 0-of-10 still closes Q53.

## The failure itself is not this task's to fix

`skipped_note` was refused because `DispatchPlan` carries `REQUESTED` (`extra="forbid"`).
`contracts.py` states the governing rule in its own docstring: *"relax the ones whose extras are
inert, and keep refusing the ones where an unexpected key is an attempted instruction."* An extra on
`Dispatch` is an attempted instruction — `test_the_window_is_told_to_the_specialist_never_asked_of_it`
depends on that refusal. An extra on the **plan envelope**, whose fields are `dispatches`, `skipped`
and `rationale`, has no reader and no path, exactly like `alternatives_note` on `Verdict` ($0.3890,
two refusals) and `confirm_within_seconds_note` on `Proposal` (sweep 11, finding 35). **This is the
same defect a third time, one contract over.**

It is not fixed here. `DispatchPlan`'s JSON schema sits inside the frozen `prompts` key, so
`extra="allow"` would move `prompt_digest` and strand every published figure. It queues as **Q54**,
and until it lands it is part of this pilot's discard rate — which is precisely what the re-attempt
above is sized for.
