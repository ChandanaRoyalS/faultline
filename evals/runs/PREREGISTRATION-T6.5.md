# Pre-registration — T6.5, the scribe loop and the learning-effect measurement

**Written and committed before any line of the postmortem step is built.** Governed by
[the design note](../../docs/design/t6.5-what-a-registration-must-fix.md), which named five
decisions; §1 and §2 below record the two that were taken and the one that had to change when its
premise was checked.

The plan's row: *"Postmortem generation + learning-effect measurement — post-resolution draft for
human edit, accepted postmortems join the corpus, cross-scenario transfer within a fault class
measured with/without."*

---

## 1. What a postmortem is, and the narrowing that was forced

**Decided:** a postmortem is a **new document class**, written after the incident resolves, carrying
what a narrative cannot because the narrative is written mid-investigation.

**The narrowing.** That decision was taken as *"carrying the outcome"*, and the outcome does not
exist. `recovery` on 266 manifests is the **world's** state after the injector reverts —
`active_injections`, `firing_alerts`, `consumer_idle_ms` — a gate reading, not *did the fix work*.
Remediations have only ever executed in T6.2's repair replay (nine triples) and T6.3's loop, both
drivers outside the scored pipeline. **A postmortem saying "the system recovered" when the harness
reverted the fault would be false and would leak the harness into the corpus in one sentence.**

So a postmortem carries what **is** recorded for every run and what a narrative provably cannot:

- the verdict and root cause **as finally stated**, after the investigation closed;
- **the proposal** — action, target, preconditions, blast radius, and the falsifier it named;
- **the proposal's fate at the validator boundary** — accepted, refused and why, escalated, or
  abstained with the abstention's reasoning;
- what stayed **unmeasured**, which every verdict already records as `OPEN` lines.

**A postmortem does not claim a remediation worked**, anywhere, ever. Where an outcome exists it is
T6.2's replay's and is not in scope here.

## 2. The leak boundary, and one guard that is a benchmark artifact

Existing rules apply unchanged: `HARNESS_VOCABULARY` (injector words and the four `fault_class`
values), scenario ids, and ADR-0036's rule that an authored document may name no catalog scenario.

**And one more, which is this task's:** a postmortem **may not name its remediation action**.

`baselines.py` maps fault class to remediation **one-to-one across all eighteen scenarios** —
measured, not assumed: it is what Q53's prediction 4 was written against. So a same-class postmortem
naming `rollback_image` hands the reader `bad_deploy` through a lookup table, and a transfer
measurement over it would be measuring an agent reading a mapping rather than generalising from an
incident.

**This is a property of this benchmark and not of production**, and it is a real cost to the
artefact's realism: a postmortem that cannot say what fixed it is a strange postmortem. It is
accepted because the alternative is a measurement that cannot mean what it claims, and it is
recorded in §7 as a limitation rather than buried as a guard.

**What a postmortem carries instead is the mechanism**: the observable shape (*repeated boot
banners with no request handling*; *fast-fail at the client span with no server span*; *a
near-constant floor on every leaf regardless of command*), what ruled the alternatives out, and what
was never measured. That is what a responder actually takes from a prior incident.

## 3. The accept gate

**Decided:** a person, through the approval surface — ADR-0039's shape, reused rather than
re-invented. A route behind T5.5's credential, the caller recorded as the authenticated username,
an append-only ledger row, and the seeder refusing any postmortem without one.

**The failure mode this avoids is named so it can be checked for:** *a boolean nobody sets.* If the
only caller that ever accepts a postmortem is a script, the gate is a field and not a gate, and the
plan's *"draft for human edit, never auto-published"* is unimplemented while appearing done.

## 4. The measurement, and why it is not a corpus swap

**The plan's "measured with/without" is corrected here to a query-time exclusion, deliberately.**

A with/without-*corpus* comparison seeds and unseeds between arms, so the arms differ in
`body_sha256` — the axis ADR-0014 exists to separate — and nothing records which corpus a run read
in a form `group_by_generation` respects (**Q61**). A query-time exclusion makes the "without" arm
*the same corpus, one wider exclusion*: **one corpus, one digest, one generation**, and the
exclusion already recorded per retrieval in `trajectory_retrievals`.

`PastIncidentStore.search` takes `exclude_origin: str | None` and the SQL is `AND origin <> %s`.
**It becomes a set.** That is the only production change the measurement requires.

**The two arms**, for each dev scenario S in class C:

| arm | corpus | exclusion |
|---|---|---|
| **WITHOUT** | the one corpus | S's own documents, **and every other dev scenario in C** |
| **WITH** | the one corpus | S's own documents only |

Both arms exclude S's own documents, which T4.1b already does and which is not what is being
measured. **R ≥ 2**, alternating, so the A/A check can run on each arm.

**What this design cannot separate**, and says so rather than being asked later: the WITH arm
carries same-class **narratives and postmortems together**, so a positive delta is *prior same-class
incidents help* and not *postmortems add something over narratives*. Separating them needs a third
arm and 26 more runs; it is not bought here.

## 5. Two floors, both named before the run

A delta has to clear **both**:

1. **The catalog's MDE: 16.2pp** at `n = 10, R = 3` — `variance`'s own table.
2. **The instrument's own noise: ~10pp.** Sweep 12's A/A check measured **+10.0pp on fault-class
   accuracy between two halves of one configuration**. A transfer delta under that is inside what
   this harness produces from nothing on the same axis.

**And one attenuation that is not a floor but bounds the whole thing.** `recall@3` is **0.395**: the
WITH arm can only transfer what retrieval actually surfaces, so a true effect is attenuated by a
retriever that finds the relevant document under two times in five. **A null result here is
therefore not evidence that prior incidents do not help** — it is evidence that they do not help
*through this retriever at this recall*, which is a different and weaker claim, and §7 keeps it.

## 6. The budget, as a hard stop

- **13 dev scenarios × 2 arms × R = 2 = 52 scored runs.** At sweep 12's measured $0.59–0.77 that is
  **$31–40**; at the harness's 16.7% discard rate, **$37–48**.
- **Postmortem generation is separate and small**: one model call per donor scenario, drafted
  offline from the recorded incident, ~13 calls. Budgeted at **$5**.
- **Hard ceiling: $55.** Reaching it stops the run where it stands and reports the arms it did not
  complete. A budget revised upward mid-task is not a budget.

## 7. Predictions

1. **The WITH arm's fault-class accuracy exceeds the WITHOUT arm's.** Direction only.
2. **The delta does not clear 16.2pp.** This catalog has never resolved anything at `n = 10` that
   was not enormous, and transfer is not enormous.
3. **The delta does not clear 10pp either** — so the honest report is *no measurable effect*, and
   registering that in advance is the point. Q57 was got wrong by predicting a resolvable effect it
   had no power to see; this predicts the opposite and will be scored on it.
4. **In fewer than half the WITH-arm investigations does retrieval surface a same-class document at
   all.** The direct test of §5's attenuation, read off `trajectory_retrievals`, and the number that
   decides whether prediction 3 is about learning or about `recall@3`.
5. **Abstention is at least as common in the WITHOUT arm.** Less context should produce more
   declining, not more guessing — and if it produces more guessing, that is worth more than the
   accuracy delta.
6. **No postmortem trips the leak guard on its first draft.** Registered because it is the one I
   expect to fail: the model has the fault class and the remediation in the record it drafts from,
   and §2 forbids both.
7. **Total spend under $50.**

## 8. What this cannot settle

- **Whether postmortems beat narratives.** §4's two arms cannot separate them.
- **Whether a remediation worked.** §1: no scored run executes one.
- **Whether prior incidents help in general.** §5: only *through this retriever, at recall@3 = 0.395*.
- **Whether the guard in §2 costs the artefact its realism.** It does. How much is not measured here.
- **Anything on holdout.** Dev only; no holdout scenario is spent on a learning-effect measurement.
