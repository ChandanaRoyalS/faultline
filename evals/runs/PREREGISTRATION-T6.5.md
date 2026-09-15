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

---

# Amendment 1 — §4 says "no re-seed" and the task cannot avoid one, so Q61 gates the run

**2026-09-15, written after all three build pieces landed (#318, #319, #320) and before anything
is drafted or spent. $0.00.** Appended, not edited: nothing above this line is changed, and §4
and §6 are to be read against what follows.

## The sentence that is wrong, and the half of it that is right

[The design note](../../docs/design/t6.5-what-a-registration-must-fix.md) §3 argues for the
query-time exclusion and closes with four bullets, the last of which is:

> **No re-seed** — which also means the nine drifted runbooks and Q45's open half stay out of it.

**That is true between the arms and false before them.** §4's design does stop the *comparison*
from crossing a corpus boundary: both arms read one corpus at one `body_sha256`, and the WITHOUT
arm differs from the WITH arm by a wider `WHERE`, which is the whole reason the exclusion became
a set. Nothing in that claim has changed and piece 3 delivered it.

But the plan's row is *"accepted postmortems join the corpus"*, and joining the corpus is
`faultline-seed`. `context/seed.py` is the only writer to the pgvector store, so **~13 new
documents have to be written into it once, before either arm runs.** The design note did not say
so and I did not notice until the seeder was the thing I was editing.

## Why that single seed is Q61 and not a formality

Verified in the tree rather than quoted from a row: `evalharness.generations.generation_of` reads
`freeze.world.compose_digest` and `host_platform`, falls back to the run-id stamp, and **reads
nothing about the corpus at all**. So a seed changes `rows`, `sha256` and `body_sha256` — what
every run afterwards retrieves from — and `group_by_generation` puts runs from either side of it
in one table.

That is Q61 exactly, reached by a different route than the one §4 closed. §4 closed the
*between-arm* route. The *before-the-run* route was always open and the note's fourth bullet
obscured it.

**And the seed carries two changes, not one.** Q45's first live run found the deployed corpus
disagreeing with `main` on **nine runbooks** — same shape, different words. Those land in the same
`faultline-seed` invocation as the postmortems. So the corpus T6.5 measures against will differ
from the corpus every prior figure was measured against in two independent ways, and a write-up
that mentions only the postmortems would be describing half of what moved.

## What this changes, and what it does not

**Unchanged:** the two arms, the outcome metric, both floors, every prediction, and the $55
ceiling. §4's design is still the better one — one seed raises the generation question **once**,
where a with/without-*corpus* comparison raises it twice per scenario, twenty-six times.

**Changed: the ordering, and it is now a gate rather than a preference.**

1. **Q61 is settled** — something records which corpus a run read, in a form
   `group_by_generation` respects.
2. Postmortems are drafted, accepted through the route #319 added, and committed.
3. **One** `faultline-seed`, and its `body_sha256` recorded before and after.
4. Both arms, on that one corpus.

**T6.5 does not start at step 2.** The standing instruction not to run `faultline-seed` until Q61
is settled is not a caution this task can spend its way past: every figure this task produces
would be incomparable with the 183 archived runs by a route no grouping sees, which is the
condition ADR-0022 §3.3 exists to refuse.

## The honest accounting of how this was missed

The design note's §3 was written to show that a query-time exclusion beats a corpus swap, and it
does. Four bullets of advantage were listed, and the fourth generalised *"the arms do not re-seed
between them"* into *"no re-seed"* without checking what putting a new document class into the
corpus requires. **The registration then inherited the claim in §4 by reference rather than
re-deriving it**, which is the same failure this repository has recorded five times in other
forms: trusting a document's summary of a thing instead of opening the thing.

It cost nothing here because it was found while building rather than while spending. That is luck
about the order the pieces were built in, not a property of the process, and the process fix is
the one already written down — *when a document describes code or a result, open the thing it
describes before repeating it.*

---

# Amendment 2 — three of the thirteen scenarios cannot run, and the floor was quoted at the wrong R

**2026-09-15, written after the build finished (#318–#326) and before any model call. $0.00.**
Appended, not edited: nothing above this line is changed, and §4, §5 and §6 are to be read against
what follows. Everything below is read off `evals/scenarios/*.yaml` and `variance.mde`.

## 1. Ten scenarios, not thirteen

`faultline-postmortem --dry-run` found **ten** donors where §6 budgeted thirteen. The catalog says
why: three dev scenarios carry `blocked: true`, meaning their faults produced nothing observable
and they cannot be rehearsed at all.

| class | dev scenarios | **runnable** | donors left when one is held out |
|---|---|---|---|
| `bad_config` | 4 | **4** | 3 |
| `bad_deploy` | 3 | **2** | **1** |
| `dependency_latency` | 3 | **2** | **1** |
| `resource_exhaustion` | 3 | **2** | **1** |

Blocked: `ad-dependency-latency`, `currency-cpu-throttle`, `flag-service-crashloop`.

**The design note's §2 counted all thirteen** and concluded *"holding one out always leaves
donors"*. That is true and it is the wrong reassurance: in **three of four classes it leaves
exactly one**, always, not — as the note said of `dependency_latency` alone — sometimes. The note
knew `ad-dependency-latency` had no narrative bundle and did not notice that being *blocked* is
the deeper reason, nor that two more scenarios share it.

**What this does to §4.** For six of the ten scenarios the WITH arm carries **one** same-class
postmortem and one same-class narrative, against a WITHOUT arm carrying neither. That is the
transfer this measurement can observe: not *does a body of prior same-class incidents help*, but
*does one prior incident help, when retrieval finds it*.

**Prediction 4 stops being a prediction.** It reads *"in fewer than half the WITH-arm
investigations does retrieval surface a same-class document at all"* — with one candidate document
in three of four classes and `recall@3 = 0.395`, that is close to arithmetic. It is still worth
recording, and it is no longer a test of anything; §7's scoring should say so rather than claim a
prediction held.

**Per-class deltas are not reportable for three of the four classes.** n = 2 with R = 2 is four
runs an arm. The report gives the pooled delta and the per-class counts, and says nothing about a
per-class effect.

## 2. The floor was quoted at an R this design does not use

§5 names *"the catalog's MDE: 16.2pp at `n = 10, R = 3`"*. §4 registers **R ≥ 2**. Those are two
different numbers and the registration used the friendlier one.

`variance.mde`, run against this catalog:

| n | R | MDE |
|---|---|---|
| 13 | 3 | 14.2pp |
| **10** | **3** | **16.2pp** |
| 13 | 2 | 17.4pp |
| **10** | **2** | **19.8pp** |

So the floor at the shape actually registered is **19.8pp**, not 16.2pp. The n was right by
accident — §5's `n = 10` matches the ten runnable scenarios rather than the thirteen §6 budgeted,
which is two errors that happened to cancel in one field.

**Decided: R = 2, and the floor is 19.8pp.** Buying back 3.6pp costs R = 3, which is 60 runs at
**$35–46**, or **$42–55** at the 16.7% discard rate — against a $55 ceiling, so one bad batch ends
the task with arms incomplete and no result. Predictions 2 and 3 already register that the delta
clears neither 16.2pp nor 10pp; spending $14 to tighten a floor on a measurement whose registered
expectation is a null buys precision in the one case the registration says will not arise.

**§5's second floor is unchanged and is the one that will do the interpretive work.** The
instrument's own noise is ~10pp, and only the larger floor can decide pass or fail — but a delta
landing *between* 10pp and 19.8pp is a different statement from one landing below 10pp, and §7's
report keeps that distinction.

## 3. §6's budget, corrected downward

| | registered | corrected |
|---|---|---|
| scored runs | 13 × 2 arms × R=2 = **52** | 10 × 2 arms × R=2 = **40** |
| at $0.59–0.77 | $31–40 | **$24–31** |
| with 16.7% discards | $37–48 | **$28–37** |
| postmortem drafting | $5 | $5 (10 donors, not 13) |
| **hard ceiling** | **$55** | **$55, unchanged** |

The ceiling does not move. A ceiling that tracked the estimate downward would not be a ceiling,
and the headroom is what pays for a re-run if a batch fails.

## 4. What this amendment does not change

The two arms, the query-time exclusion, the accept gate, §7's predictions 1, 2, 3, 5, 6 and 7, and
§8's list of what the task cannot settle. **§8 gains one line:** this measurement cannot say
whether *a body* of prior same-class incidents helps, because on three of four classes there is
only ever one.

---

# Amendment 3 — R is not a free parameter, so Amendment 2's R = 2 cannot be run

**2026-09-15, written before any model call. $0.00.** Appended, not edited: nothing above this
line is changed, and §4, §5, §6 and Amendment 2 are to be read against what follows. Everything
below is read off `variance.TIERS`, `run.py` and 548 recorded manifests.

## 1. The clause neither the design note nor the registration read

The plan's T6.5 row has four columns. The note quoted the deliverable and the eval, and **did not
read the constraints column**, which ends: *"the with/without-corpus comparison run at **T4.6's
scored-comparison tier**, so holdout scores stay clean."*

That is the third time in this task a document's summary was repeated instead of the document
(Amendment 1's *"no re-seed"*, Amendment 2's thirteen scenarios, and now this), and it is the
same fix each time: open the thing being described.

## 2. R is derived from the tier, and R = 2 is not a tier

`variance.TIERS` admits five names and each carries its own repeat count:

| tier | R | what T4.6 says it is |
|---|---|---|
| `manual` | 1 | one run by hand; an observation, never a rate |
| `ci-smoke` | 1 | change detection only, never citable |
| `nightly` | 1 | change detection; not a finding on its own |
| **`weekly`** | **3** | consolidation |
| `published` | 5 | *the only tier a printed comparison may come from* |

`faultline-eval --tier` takes `choices=tuple(variance.TIERS)`, and
`run.manifest["repeat_count"] = variance.TIERS[args.tier][0]`. **The repeat count is not an
argument.** So `R ∈ {1, 3, 5}`, and **R = 2 is unrunnable** — not merely unlabelled. Amendment 2
chose a value this harness cannot produce, and the tier joins the config fingerprint, so a run at
one tier can never pool with a run at another.

**Amendment 2's §2 decision is void.** Its §1 and §3 stand: ten scenarios, not thirteen; the floor
is read at the R actually used.

## 3. What the archive has ever done, measured

Over 548 manifests: **`weekly` 97, `manual` 58, `nightly` 10**, and `repeat_count` is **3 on 97
runs and 1 on 68**. **Nothing in this repository has ever run at `published`.** `docs/RESULTS.md`
cites no tier at all.

So reading the plan's clause as `published` would mean **no comparison this repository has
published was ever at the tier its own plan requires** — including the headline figure, dev sweep
12's arm A, which is `weekly`. Two readings survive that: the repository has been out of
compliance and nobody noticed, or *"scored-comparison tier"* means the tier at which comparisons
here are actually scored, which is `weekly`. **This amendment takes the second and records the
first as a live possibility rather than dismissing it** — it belongs to whoever writes T4.6's next
addendum, not to a task that would be marking its own paper.

## 4. Decided: `weekly`, R = 3, and the ceiling moves to $70

| | Amendment 2 | **this amendment** |
|---|---|---|
| tier | *(none — R = 2)* | **`weekly`** |
| R | 2 | **3** |
| scored runs | 40 | **60** |
| MDE at n = 10 | 19.8pp | **16.2pp** — the floor §5 quoted all along |
| at $0.59–0.77 | $24–31 | **$35–46** |
| with 16.7% discards | $28–37 | **$42–55** |
| drafting | $5 | $5 |
| **total** | $33–42 | **$47–60** |
| **hard ceiling** | $55 | **$70** |

**Why the ceiling moves, and why that is not the thing a ceiling exists to prevent.** §6's rule is
*"a budget revised upward mid-task is not a budget"*, and it is about revising after seeing
results. This revision is forced by a fact about the harness, is taken **before any model call**,
and is written down with its arithmetic. A $55 ceiling against a $47–60 estimate is a ceiling that
stops the task part-way on an ordinary discard rate — spending the money and getting no delta,
which is the worst of both.

**$70 is the estimate's top plus headroom for one failed batch**, and it does not move again. If
the walk reaches it, it stops and reports the arms it did not complete, exactly as §6 says.

## 5. The clause still unaddressed

*"corpus growth tracked in the retrieval evals"* is the one plan constraint nothing in this task
touches. Ten postmortems take the corpus from 50 documents to 60, and **`recall@3 = 0.395` — which
§5 uses as the attenuation bound for the whole measurement — is a number about the corpus before
them.** `GATE_RECALL_AT_3` and the measured constants are calibrated to 261 chunks.

**The re-score costs no model call**, so it is a step rather than a decision: `faultline-retrieval
score` runs in the seed commit, beside the two digests and the two pins, and §7's report quotes
the post-seed `recall@3` rather than the pre-seed one when it states what attenuated the effect.

---

# Amendment 4 — two of the ten postmortems are about a failure that did not happen

**2026-09-15, written after drafting and before any acceptance, seed or scored run. $0.72 spent
on the drafting this amendment is about; $0.797 was spent and discarded before it.** Appended,
not edited: §4 and §7 are to be read against what follows.

## 1. What the drafting produced

Ten drafts from ten dev scenarios, each from its newest **full-pipeline** scored run, at
`prompts:06f24e827915`, 2026-09-09. **Two guard refusals**, both recovered on the retry.

**A first attempt was discarded**: its ten donors were the `--without traces` ablation arm, which
`record_from_run` did not refuse, and its postmortems scored 4 of 9 on fault class. That run is
recorded in [`docs/evidence/t6.5-drafting/`](../../docs/evidence/t6.5-drafting/DISCARDED-2026-09-15-ablation-donors.md)
and pools with nothing.

## 2. Prediction 6 is scored, and it failed

> *"**No postmortem trips the leak guard on its first draft.** Registered because it is the one I
> expect to fail: the model has the fault class and the remediation in the record it drafts from,
> and §2 forbids both."*

**Two of ten tripped it.** The prediction is false and was registered as expected to fail. Both
recovered on the second attempt with the parser's own refusal fed back.

**Scored against the design as registered**, which matters because it briefly was not: for one
commit the brief withheld every prose field the guard matched, which would have made this a
different question. That was reverted when the withholding was measured — 183 of 204 verdicts
leak in their own prose, so withholding leaves no brief. The model had the fault class in front of
it, as §7 assumed.

## 3. The finding this amendment exists for

**Two of the ten postmortems describe a failure that did not happen**, because their donor runs
concluded wrongly. The donors score **8 of 10** on fault class:

| scenario | class | donor correct | what its postmortem says |
|---|---|---|---|
| `ad-memory-squeeze` | `resource_exhaustion` | **no** | shipping-quote unreachable at the transport layer; nothing bound to the serving port |
| `shipping-quote-misconfig` | `bad_config` | **no** | — |
| the other eight | — | yes | — |

**This is the donor rule working as designed, and the design has a cost that is now concrete.**
`donor_runs` takes the newest run rather than the best one, deliberately: *"choosing the run whose
verdict was correct would make the corpus a record of the pipeline's successes, and a measurement
of whether prior incidents help would then be measuring whether prior right answers help."* That
argument stands. What it buys is two documents whose **metadata and content disagree** — the chunk
carries `fault_class` from the manifest, which is the truth, while the prose describes something
else.

**The sharpest consequence, named so §7 cannot be surprised by it.** `resource_exhaustion` has
two runnable scenarios (Amendment 2). So for **`frauddetection-memory-squeeze`, the entire WITH-arm
advantage is `ad-memory-squeeze`'s postmortem — the wrong one, and nothing else.** That arm is not
testing whether a prior same-class incident helps; it is testing whether a prior same-class
*mistake* hurts. `bad_config` has four scenarios, so `shipping-quote-misconfig`'s wrongness
dilutes.

**And one of the two is built on Q57's residue.** `ad-memory-squeeze`'s postmortem reasons from a
change record *"oscillating … roughly five times across the preceding ~19 hours"* — which is the
harness re-injecting the same fault, read as incident history. Q57 measured a median of 12 stale
records against 1 of a run's own. This is that residue reaching the retrieval corpus through a
document, which no guard in this system looks for.

## 4. Decided: all ten are accepted, and §7 reports the split

Accepting eight would be a quality floor with a real precedent — the seeder skips a bundle marked
`INVALID` because *"seeding them would put two incidents in the corpus that never happened"* — and
it was rejected because `resource_exhaustion` would then contribute nothing at all: one of its two
scenarios would have no same-class document and the other's would be excluded as its own.

**So §7 gains a reporting obligation rather than the corpus losing documents:**

1. The delta is reported **over all ten**, as registered.
2. It is reported again **over the eight whose donors were right**, as a secondary cut, labelled
   post-hoc — it is a subgroup chosen after seeing which donors were wrong, and Q57's mistake was
   exactly a within-generation cut presented as though it had been registered.
3. **`frauddetection-memory-squeeze` is named in the report whichever way the delta falls**, because
   its WITH arm carries one wrong document and no other same-class postmortem.

**What this costs the conclusion, stated now.** A null delta over ten will not distinguish *prior
incidents do not transfer* from *two of ten prior documents were wrong*. §8 already says this task
cannot show whether a body of prior incidents helps; it now also cannot cleanly show whether
**correct** prior incidents help. That is a real narrowing and it is the price of not selecting
donors on their answers.

## 5. Unchanged

The two arms, the query-time exclusion, `weekly` at R = 3, the 16.2pp floor, the $70 ceiling, and
predictions 1, 2, 3, 4, 5 and 7. Prediction 6 is answered above.

---

# Amendment 5 — one postmortem is wrong; the other abstained, which is not the same thing

**2026-09-15, minutes after Amendment 4 and still before any acceptance. $0.00.** Appended, not
edited: Amendment 4 §3 and §4 are to be read against this.

## The correction

Amendment 4 says *"two of the ten postmortems describe a failure that did not happen"* and names
`ad-memory-squeeze` and `shipping-quote-misconfig`. **That is wrong about the second one.**

Read off the two score blocks rather than off the `correct` field alone:

| scenario | truth | returned | `correct` | `abstained` |
|---|---|---|---|---|
| `ad-memory-squeeze` | `resource_exhaustion` | **`bad_deploy`** | false | **false** |
| `shipping-quote-misconfig` | `bad_config` | **`unknown`** | false | **true** |

**`shipping-quote-misconfig` did not answer wrongly. It declined to answer**, and ADR-0022 §1.2
makes an abstention neither right nor wrong. Its postmortem says so in its own words:

> *"Confidence stayed low, and the fault class was left unknown rather than guessed, precisely
> because a client-side ERROR paired with a server-side success is not one mechanism."*

That is a document a responder can use. It describes a real discriminator — a fast client-side
error against a clean server span in the same trace — and stops where the evidence stopped.

**How the error was made, since it is the same one this task keeps making.** Amendment 4 read
`score.fault_class.correct` and treated `false` as *wrong*. The scorer records `abstained` in the
same block, one key away, precisely because the two are different — and this repository's own
README leads with *"read the abstentions before the accuracy."*

## What changes

**One wrong postmortem, not two.** `ad-memory-squeeze` answered `bad_deploy` against a truth of
`resource_exhaustion`, and its prose describes a transport-layer failure at shipping-quote. That
document, and its consequence for `frauddetection-memory-squeeze`'s WITH arm, stand exactly as
Amendment 4 §3 describes them.

**`bad_config` carries no wrong document.** Its four scenarios contribute three confident
postmortems and one honest abstention.

**Amendment 4 §4's reporting obligations stand, with the split redefined:** the secondary cut is
**nine donors that did not answer wrongly**, not eight — an abstention is not a wrong answer and
excluding it would be excluding the one document that behaved as the system is designed to.

## What is unchanged

Everything else in Amendment 4, including the decision to accept all ten, prediction 6's score,
and the Q57 residue finding.

---

# Amendment 6 — the seed ran, and found three defects between the two pins

**2026-09-15. $0.00** — every number below is a database read, a tree read, or
`faultline-retrieval score`, none of which calls a model. **$1.52 remains the task's total
spend.** Appended, not edited.

Amendment 1 made the seed the gate on this measurement and Amendment 3 §5 added the re-score to
it. Both are now done. The seed was supposed to be a step; it took four commits, because the two
pins could not be set correctly until three things were repaired underneath them.

## 1. The corpus, before and after

| | before | after |
|---|---|---|
| chunks | 261 | **311** |
| documents | 50 | **60** |
| `sha256` | `9c5e5958e8c7` (store) / `f34651707c7f` (pin) | **`844fe623366c`** |
| `body_sha256` | `6cde2afd5016` | **`cc473105c036`** |
| `holdout_chunks` | 0 | **0** |
| `faultline-corpus-drift` | exit 1 | **exit 0** |

Both pins are set in this commit, from `freeze.corpus_state` on the seeded store, and **both
reproduce off the working tree with no database at all**.

## 2. Three defects, found between reading the first digest and pinning the second

**The corpus could take a new document and not an edit to an old one** (PR #338).
`PgVectorPastIncidentStore.add` upserted five columns on conflict and `section` was not among
them; the key is `document_id#section_index`, which a renamed heading does not move. Thirteen
headings across nine runbooks survived a `faultline-seed` that printed all forty runbooks as
seeded. **Q45 had diagnosed those nine as a deployment the seeder had not reached since
2026-09-14.** It had reached them every time.

**The retrieval benchmark moved two queries when nothing changed** (Q68, PR #340). Both arms
ended `ORDER BY ... LIMIT k` on one key, so ties were resolved by heap order, which moves when
rows are rewritten. Five re-seed-and-score cycles on a fixed corpus: `recall@3` over
**0.302 / 0.326 / 0.349**. Measured before repaired, because a tiebreaker sets the spread to zero
and the width is a fact about the *existing record* — `recall@3 = 0.395`, `recall@5 = 0.442` and
`GATE_RECALL_AT_3` are each one draw from a distribution nobody sampled.

**The shape digest was a property of the collation** (Q69, PR #341). `corpus_state` hashed a SQL
`ORDER BY`, so on `en_US.utf8` the same 311 chunks hashed `ee7c7bb277cf` in the database and
`844fe623366c` off the tree. The pin would otherwise have named this Mac's locale.

**None of the three was caused by this task**, and all three were found by it, because a seed is
the one operation that reads the corpus, writes it and compares the two.

## 3. The re-score Amendment 3 §5 asked for

| | before the seed | after, reproducible |
|---|---:|---:|
| `recall@3` | 0.395 | **0.302** |
| `MRR@3` | 0.233 | 0.198 |
| planner `recall@3` | 0.619 | 0.571 |
| synthesizer `recall@3` | 0.182 | **0.045** |
| `recall@5` | 0.442 | 0.372 |
| synthesizer `recall@5` | 0.182 | **0.045** |

Two independent re-seeds after the tiebreaker returned these figures **byte-identical, down to
`MRR@5 = 0.252`**. The 0.302 is the lowest of the three values Q68 observed; the tiebreaker froze
one of them rather than lowering anything.

**Corpus growth made retrieval worse, and the synthesizer took almost all of it** — 0.182 to
0.045 is four queries of twenty-two down to one. Ten postmortems are topically near-identical to
the narratives the golden set labels as the answer, and they displace them.

## 4. What that does to this measurement, and what it does not

**§5's attenuation bound moves from 0.395 to 0.302** and §7 quotes the post-seed figure, as
Amendment 3 §5 registered. Prediction 4 — *"in fewer than half the WITH-arm investigations does
retrieval surface a same-class document at all"* — was registered against the 0.395 corpus and is
now registered against a corpus that retrieves worse. **It becomes easier to satisfy, which
makes it weaker evidence than when it was written**, and §7 says so when it reports it.

**The registered design does not otherwise change.** Ten scenarios, `weekly`, R = 3, a 16.2pp
floor, a $70 ceiling. **The floor is not renegotiated because attenuation got worse** — a floor
moved after the instrument got harder is not a floor, and Amendment 3 fixed this one at the real
R for exactly that reason.

**What is now more likely: a null result.** A WITH arm that retrieves the prior incident less
often has less to transfer. If the measurement comes back inside the floor, **that is a reportable
outcome and not a failed run**, and it is registered here as expected rather than discovered
afterwards.

## 5. What is not claimed

**Not that 0.302 is better or worse than 0.395 as a number about retrieval.** 0.395 was one draw
from a two-query-wide instrument on a different corpus; 0.302 is reproducible on this one. They
are not two measurements of one thing.

**Not that the corpus should shrink.** Whether ten postmortems earn their place is what this
task measures, and a retrieval score is not that measurement — it scores a golden set labelled
before postmortems existed, so a postmortem outranking a narrative is scored as a miss whether or
not it helped the agent. That is worth knowing and it is not a verdict.

## 6. What the next commit does

**Re-backfill the eval database.** Q69 renames every `corpus_sha256`, which `FINGERPRINT_INPUTS`
carries, so a half-loaded database holds one configuration under two names. Renames, regroups
nothing — the same shape Q61's change had, measured there over 548 manifests.

**Then the runs.** Forty to sixty scored runs at `weekly`, R = 3, $42–55 expected against a $70
ceiling that does not move.

---

# Amendment 7 — the arms interleave, because running each as a block confounds it with time

**2026-09-15, written before any scored run of this measurement. $0.00 so far beyond the $1.52
already spent.** Appended, not edited.

## 1. What §4 left unspecified

§4 names two arms and says *"R ≥ 2, **alternating**"* — which fixes the repeats and says nothing
about **the order the arms run in**. Run as written, the obvious reading is two invocations of
thirty runs each.

**That confounds the arm with position in the sweep.** Q57 measured stale change records rising
with position within a sweep; on the current generation the median investigation reads **12
against 1 of its own**, and Q59 is open because no uncontaminated control exists. An arm that ran
entirely second reads a world thirty runs dirtier than the arm that ran first, and §7's headline
delta would carry that difference inside it with nothing able to separate them.

This was not a hypothetical risk for this harness: dev sweep 12 put **arm B's first six runs in
arm A's column**, which is `scenario_table._qualifies`'s first recorded miss and one of Q66's
four.

## 2. The schedule

Six blocks of ten runs, one pass of one arm each, with the leading arm flipped every pass:

| block | arm | `--label` | pass | runs |
|---|---|---|---|---|
| 1 | **WITH** | `t6.5-with` | 1 | 1–10 |
| 2 | **WITHOUT** | `t6.5-without` | 1 | 11–20 |
| 3 | **WITHOUT** | `t6.5-without` | 2 | 21–30 |
| 4 | **WITH** | `t6.5-with` | 2 | 31–40 |
| 5 | **WITH** | `t6.5-with` | 3 | 41–50 |
| 6 | **WITHOUT** | `t6.5-without` | 3 | 51–60 |

Block positions: WITH at 1, 4, 5 — sum 10. WITHOUT at 2, 3, 6 — sum 11. **One block-position of
imbalance across sixty runs**, against thirty in the two-block form.

`--end-pass` exists as of this commit. `--start-pass` alone runs from N *through the end*, so a
single pass was not expressible, and the alternative — a tier with R = 1 — would write the wrong
`repeat_count` into every fingerprint, which Amendment 3 settled. **Every manifest still declares
R = 3**, because that is still the design; the blocks are how the passes were spread over time.

## 3. What this fixes, and what it does not

**Fixed:** the arm no longer lines up with time-in-sweep, so a delta cannot be residue
accumulation wearing an arm label.

**Not fixed, and named rather than left to be asked:**

- **Residue is still present in both arms**, at Q57's measured level. Interleaving balances it;
  it does not remove it, and Q59 is the row about there being no control group to remove it
  against.
- **The world is recycled before every pass**, which is one clearing per block rather than one
  per run, so within-block position still varies.
- **The dose is not equal across classes.** `bad_config` has four runnable scenarios and the
  other three classes have two, so a WITHOUT run of a `bad_config` scenario has three other
  scenarios excluded and every other WITHOUT run has one. **§7 reports the delta by class as
  well as pooled**, because a single pooled figure is an average over two different
  manipulations. This is §4 read literally rather than a change to it.

## 4. The ceiling, and where it is enforced

**No spend ceiling exists in the sweep.** It prints an estimate and does not stop at a dollar
figure, so Amendment 3's **$70 hard ceiling is enforced at the block boundaries** — which is the
second reason for six blocks rather than two.

**Spend is read after every block** and the schedule stops where the ceiling is reached,
reporting the blocks not run. A block is ten runs at sweep 12's measured $0.59–0.77, so **$6–8 per
block and $35–46 for all six**, before the 16.7% discard rate. If the total after block 5 leaves
less than one block's headroom, block 6 does not start.

**The ceiling is not revised.** A budget revised upward mid-task is not a budget (§6).

## 5. The label check, which is the thing most likely to go wrong

Six invocations with two labels is the shape that produced dev sweep 12's mislabelled arm. So,
**after every block**, before the next one starts: the block's manifests are read back and every
one must carry the expected `exclusion_policy` and `sweep.label`. A block whose manifests
disagree with the arm it was launched as is **discarded, not relabelled** — a manifest corrected
by hand is a record of what someone believed rather than of what ran.

## 6. Everything else stands

Ten scenarios, `weekly`, R = 3, the 16.2pp catalog floor, the ~10pp instrument-noise floor, and
Amendment 6's attenuation bound of `recall@3 = 0.302`. Predictions 1–11 are unchanged, including
prediction 2's registration that the delta is **not** expected to clear 16.2pp.
