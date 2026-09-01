# ADR-0022: The evaluation harness — what a run scores, what it reports separately, and how it is conducted

- **Status:** accepted
- **Date:** 2026-08-26
- **Task:** T4.x (T4.1 runner, T4.1b self-exclusion, T4.2 scoring), binding on T5.x reporting
- **Design only. Nothing here is built.**

> **Numbering.** This is 0022, not 0021. `docs/adr/0021-verdict-grounding-and-two-ended-truncation.md`
> was merged to `main` at T3.4b (PR #27) and holds that number.

## Context

Phase 3 is finished and the pipeline is a command (`faultline-investigate`, T3.5). What does
not exist is any way to say whether it is any good. Every figure quoted so far has come from
reading one run's output by hand.

**What actually exists to design against**, read out of the database rather than remembered:

| trajectory | scenario | steps | verdict | flags |
|---|---|---|---|---|
| `7a354b85` | cart-redis-misconfig | 14 | **none** — predates the synthesizer | — |
| `4e42184d` | shipping-wrong-image | 13 | `unknown` / `none` / low | budget exhausted |
| `e7739dec` | shipping-wrong-image | 17 | `bad_deploy` / `rollback` / medium | — |
| `6b9715de` | shipping-wrong-image | 17 | `unknown` / `none` / medium | contradiction (false positive) |
| `f7afdb76` | shipping-wrong-image | 19 | `bad_deploy` / `rollback` / high | contradiction (false positive) |
| `68ac9a67` | cart-dependency-latency | 15 | `bad_config` / `config_revert` / medium | — |
| `f7261a74` | cart-dependency-latency | **0** | none — the T3.5 failed start | — |

**Three corrections to how this set gets described**, because the design depends on them:

1. There are **five verdicts, four of them on one scenario** — not three on shipping and one
   each elsewhere. `cart-redis-misconfig` was run before the synthesizer existed (T3.3) and has
   no verdict to score. Two distinct scenarios have been scored end to end, ever.
2. `f7261a74` is a **zero-step row**: the T3.5 failed start wrote a trajectory before the guard
   that now prevents it. The harness will meet rows like this from before the fix and must not
   count them as investigations.
3. Every trajectory says `runtime_version: 't3.3'`, including T3.5's. **The field is stale and
   has been since T3.4.** A harness that reports what version produced a number cannot read it
   from there today.

Six `trajectory_retrievals` rows exist. **All six carry `exclude_origin`, and none returned its
own origin** — so ADR-0008's axis-2 assertion is verifiable against data that already exists,
before T4.1b writes a line.

**The bundles.** Twelve exist: nine dev, three holdout. Two of the nine dev bundles carry an
`INVALID.md` and empty `alerts_over_window` — `currency-cpu-throttle` and
`flag-service-crashloop`, the latter because featureflagservice emits no span metrics at all.
**Neither can produce an incident, so neither can be run end to end.** The scoreable set is
**seven dev plus three holdout = ten**, and that is what "the ten scenarios" means operationally.

Class distribution over all twelve: `resource_exhaustion` 4, `bad_deploy` 4,
`dependency_latency` 2, `bad_config` 2; `config_revert` 6, `rollback` 4, `restart` 2, `scale`
**0**. Over the ten scoreable: no `scale` at all, and `bad_config` down to one dev scenario.

## 1. What is scored, per layer

### 1.1 Triage — the blast-radius set, against `alerts_over_window`

ADR-0009 fixed the target: "blast radius is what T3.1 scores triage on". The comparison is the
predicted set against the services in `alerts_over_window`, **excluding entries whose
`began_after_revert` is true** — ADR-0009 §"the blast radius blames the fault for damage the fix
did". Three bundles have such entries: emailservice in `cart-bad-image-tag` and
`cart-redis-misconfig`, frontend in `shipping-wrong-image`. Scoring them in would credit or
penalise triage for recovery-phase alerts.

**Recall is the primary number, and it is primary for a stated reason.** ADR-0017 §"the hop
measurement in this ADR is undirected" is explicit: the 19% / 72% / 97% coverage at 1/2/3 hops
was measured over *undirected* pairs to size correlation, triage then used the same radius for a
*directed* traversal, and "directed 2-hop coverage over these fifteen edges has not been
computed". The ADR names the number that would settle it — "a directed 2-hop traversal that
under-reaches shows up there as a recall miss on services that alerted and were not predicted.
That is the number to look at, and it does not exist yet." **T4.2 produces exactly that number
and nothing else discharges it.**

**Precision is reported and is not folded in.** The two live triage runs both returned twelve
services; `cart-dependency-latency` alerted on four. A set that is three times the size of the
answer is not obviously wrong — a blast radius is a place to look, not a claim about damage —
but a single F-score would blend a question about reach with a question about restraint and let
one hide the other.

> **Marked decision: recall and precision are reported as a pair, never combined.** No F-score,
> no "blast-radius accuracy". If a summary number is later wanted, it gets its own ADR and its
> own argument. The alternative — an F1 — was rejected because the two components answer
> different questions and ADR-0017 has a live hypothesis riding on one of them alone.

**Entry times are scored as a set property, not per service.** Each `BlastRadiusMember` carries
`entered_at`; the bundle carries `first_seen` per alert. The scoreable claim is the ordering of
the alerting subset, compared as a sequence, plus the count of members with no entry time at
all. Absolute offsets are not scored: ADR-0009 says the detection times "are one sample each …
and they are a function of load-generator behaviour as much as of the fault".

**`start_from` is not scored as culprit accuracy.** PLAN.md's standing note, from ADR-0020 §6:
it is "the earliest alerting service the graph can reason about, which is where a responder
looks first and not what caused the incident". Both live runs make the point — triage said
`checkoutservice` and `cartservice` respectively, and in the shipping runs the culprit was one
hop further out. Scoring it as a diagnosis would report triage as wrong for doing what it was
asked. It is reported as **entry-point distance**: hops from `start_from` to the injected
target, a descriptive figure with no pass mark.

**Unmeasured edges are quoted on every blast-radius figure.** The two live runs crossed five and
four. ADR-0017 declines to give the graph sync/async, so membership reached through an
unmeasured edge is not evidence at the same strength as membership reached through a measured
one. A recall figure that does not say how many of its hits arrived that way is overstating what
was measured.

### 1.2 Verdict — fault class and class of fix, and the ambiguity T3.5 measured

Ground truth is `fault_class` and `expected_remediation_class` from the bundle manifest.

**The ambiguity, stated precisely.** T3.5 ran `cart-dependency-latency`, whose labels are
`dependency_latency` / `restart`. The agent returned `bad_config` / `config_revert` — while
reconstructing the mechanism exactly: 300ms zero-jitter egress delay on eth0, one hop per Redis
call, compounding across the two sequential cart calls `PlaceOrder` makes. It classified on
**what changed** (a container carrying a delay configuration was attached); the label set
classifies on **what the symptom is** (a dependency became slow).

Three readings are available:

- **(a) The label set is right and the agent is wrong.** A shaping rule is not configuration of
  the service; nothing in cartservice's config changed.
- **(b) The agent is right and the label is a least-bad fit.** ADR-0008 records that the two
  `dependency_latency` scenarios "initially had no clean answer among" the four remediation
  values and were "labelled `restart` provisionally and flagged as a least-bad fit".
- **(c) Both are defensible; report the class separately and score nothing.** ADR-0008's general
  rule for a label we find ourselves arguing about.

> **Marked decision: (a), and the tiebreak is measured rather than stylistic.**
>
> **A fault's class is settled by which fix actually works, and for this pair that has been
> measured.** ADR-0008: "Pumba binds to the container present when its sidecar starts, so
> recreating the target durably clears the delay: cartservice p95 went 1.9ms baseline -> ~650ms
> under fault -> back to 1.9ms after `docker restart`, and stayed there with the sidecar still
> running (ADR-0007). Restarting the service genuinely resolves the incident. **The provisional
> marking has been removed from both scenarios.**"
>
> Reading (b) rests on a provisional flag that measurement has already withdrawn. And the
> agent's own proposal fails its own test: `config_revert` names no configuration that could be
> reverted, because none was changed. A class of fix that would not fix it is wrong in the only
> sense that matters operationally.
>
> **What the losing reading gets, so it is not silently counted as wrong.** Every scored verdict
> records a `class_dispute` field when the returned class is a documented near-miss of the
> ground-truth class — this pair is the first entry, and the entries are enumerated in the ADR
> that adds them, not inferred by the scorer. Disputed misses are counted as misses **and**
> reported as their own line under the per-class table, so a reader can see how much of a
> fault-class error rate is this boundary. ADR-0008's standing requirement is unchanged and
> reinforced: remediation-class accuracy is reported **broken out by fault class, never only in
> aggregate**, because "if agents systematically miss one class and nowhere else, that may be a
> labelling artifact of our own making".

**`unknown` is an abstention, not a wrong answer.** Two of the five stored verdicts are
`unknown` / `none`. Counting them as fault-class errors and counting a confident wrong class as
the same thing would make a system that says "I do not know" indistinguishable from one that
guesses badly, which is the opposite of what this project wants to reward.

> **Marked decision: `unknown` verdicts are excluded from the accuracy numerator and denominator
> and reported as a coverage figure — "n of N runs reached a class".** Rejected alternative:
> counting `unknown` as wrong, which collapses abstention and error. Also rejected: dropping
> them silently, which would let a system score 100% by answering once. **Coverage and accuracy
> are always reported together and neither is ever quoted alone.**

**Evidence citations are validated, and validation is separate from correctness.** Every
`result_id` in `Verdict.evidence` must resolve against `trajectory_tool_calls` for that
trajectory. This is a property of the record, not of the diagnosis, and is reported as its own
integrity figure. `ARCHITECTURE.md` requires a "cited, citation-validated RCA"; T3.4's renderer
already refuses an unresolvable citation, so a run that reaches the scorer with one is a defect
in the harness's inputs, not a low score.

**Root cause is not string-matched.** It is prose and goes to the judge (§1.3).

### 1.3 Narrative and root cause — judged, under the decisions already taken

ADR-0020 §1 decided this and the decisions are binding here, not re-opened:

- **The judge model is its own setting and inherits no default.** `AgentSettings.judge_model`
  is `""` today and empty means unset. "Defaulting it to whatever the agent runs is how the two
  silently become one model grading its own output, and a default that is usually right is worse
  than one that must be stated, because nobody reads it."
- **The lineage rule is checked at eval time by the harness.** ADR-0008 names judge
  contamination as "the likeliest fifth contamination axis". The harness asserts the judge is
  not the same instance, prompt, or tuning lineage as the agent under test, and **marks the run
  invalid rather than annotating it** — ADR-0008's pattern for axis 2, applied here. A run whose
  lineage check did not execute is invalid too; a prohibition nothing verifies is the failure
  mode ADR-0008 names by title.
- **Every published figure carries both model ids.** "A judged accuracy number is a function of
  two models, and reporting one of them is reporting half the experiment."

**What the judge is asked.** Not "is this good". Three structured questions with the recorded
narrative as the reference:

1. **Root-cause agreement** — does the verdict's root cause name the same mechanism the
   recorded `incident.md` names? Three levels: same mechanism, adjacent (right subsystem, wrong
   mechanism), different.
2. **Dead ends** — `ARTIFACTS.md` calls these "the most useful thing in the document". Which of
   the recorded narrative's dead ends does the agent's narrative also close, and which does it
   leave open?
3. **Traps** — each recorded narrative names at least one confident wrong answer available from
   the evidence. Did the agent take it? `shipping-wrong-image`'s is the OOM reading; T3.4c's run
   named it in its open questions and did not take it, which is a scoreable event and was
   observed by hand.

> **Marked decision: the judge sees the recorded narrative and the agent's, and never the
> `fault_class` label.** Options considered: (i) label-free comparison as specified; (ii) judge
> given the label as a rubric; (iii) reference-free rubric judging. (ii) is rejected outright —
> it is ADR-0008's fifth axis by construction, a judge told the answer. (iii) was rejected
> because a reference-free rubric is a rubric someone wrote by reading these scenarios, which is
> axis 1 leakage wearing a different hat. Comparison against a committed artifact is the only
> option whose inputs are all versioned.

## 2. What is reported separately, and never averaged in

Four categories. Each is a count with its denominator, printed next to the headline, never
folded into it.

**Flagged verdicts (ADR-0020 §5).** Exhaustion "produces a flagged verdict rather than silence,
because a partial diagnosis is scoreable and a `FAILED` incident is not". Scoreable is not the
same as comparable: a run that stopped early answered a smaller question. One of five stored
verdicts is flagged for budget exhaustion (`4e42184d`, "metrics tool calls: 2 of 2 used").

**Specialists that failed alone.** T3.3 made a specialist that fails twice fail alone rather
than kill the investigation. **This category currently has zero observations**: no stored
trajectory contains a step whose specialist failed both attempts. Eleven steps across six
trajectories took the one re-ask and succeeded. The category is reported anyway, at zero,
because a rate that only appears once it is non-zero is a rate nobody calibrated.

**Contradiction-checker firings.** ADR-0021 §3 built the check; PLAN.md's note requires the
class be reported separately because "a verdict that is wrong about its own evidence … is a
different failure from one that ran out of budget".

> **The ledger, stated as it is: two live firings, two false positives, zero true positives.**
> `6b9715de` and `f7afdb76` both fired and both were wrong — the first on a comma-joined clause
> whose second half said the service *was* covered, the second on a clause citing the very
> `result_id` it was qualifying. Each was caught by reading the run rather than trusting the
> flag, and each produced a narrower rule. The check's one true positive is historical
> (`e7739dec`), and the context-assembly fix that shipped beside it removed that verdict's
> cause. **The harness reports firings with this history attached until a batch gives it a
> denominator.** A flag whose live precision is 0/2 is not yet evidence about an agent.

**Budget exhaustion**, with which bound and how much of it was used. `4e42184d` names its own:
tool calls, not tokens or wall clock. Which bound bit is the actionable part and an "exhausted"
boolean discards it.

**Aggregation rule.** None of the four is subtracted from or averaged into the headline
accuracy. A run in any of these categories appears in the headline denominator with its outcome
as recorded, and again in its category's line. Removing them would let a bad run improve a score
by failing loudly.

## 3. The run protocol

### 3.1 A baseline gate before every injection — the one thing the harness must not inherit

**The model already exists on the other path.** The T1.5 rehearsal recorder refuses to record
against a dirty baseline and refuses to start when any container has been up for less than five
minutes. The agent path has no equivalent, and PLAN.md's standing T4.1 note says so.

The cost of not having it is on record. T3.4's smoke found the world already degraded —
checkoutservice and frontend pinned at 15000ms p95, accountingservice at 0.000 req/s — and the
check that caught it was a human deciding to look. T3.4b, T3.4c and T3.5 all did it by hand
afterwards. **Three consecutive tasks performing the same manual check is a specification.**

> **Marked decision: the gate refuses, it does not warn.** The harness aborts the run before
> injecting and reports the scenario as `not_attempted` with the failing signal. Rejected
> alternative: run and mark the result suspect — which produces a number someone will quote.
> ADR-0008's pattern again: invalid rather than annotated.
>
> The gate's checks, taken from what the three manual checks actually looked at: zero firing
> alerts in Alertmanager; no service p95 above a threshold; every service that should be serving
> above zero request rate; no active injections; no non-terminal incident in the store. The
> threshold values are **placeholders** — set them from T4.1's own first runs, exactly as
> ADR-0016 says of the cap and the settle window.
>
> Two known-good facts the gate must encode or it will fail on a healthy world: `frontend-proxy`
> sits at 0.000 req/s in the clean baseline (`evals/baselines/20260824T033742Z`, 181 consecutive
> samples of 0.0), and a container restarted within the last five minutes makes the p95 reading
> meaningless (CATALOG.md, world hazards — "readings taken 0.8, 4.0 and 14.2 minutes after cart
> reverts were written up as evidence that the service is bimodal", which it is not).

### 3.2 One driver of the world

The world is a single shared mutable resource. Every smoke from T3.3 onward carried this as an
instruction to a human. The harness enforces it with a lock file next to the injector's own
state (`.faultline/injections.json`), taken for the whole run and released on revert.

A run that finds the lock held **does not wait** — it exits and says who holds it. Waiting on a
world lock is how two harness processes end up interleaving injections with nothing in either
log to show it.

### 3.3 Dev runs, and the holdout protocol

**Development runs use dev scenarios only.** ADR-0008 axis 1: prompt text, context tuning and
retrieval corpora are fitted on dev, and holdout artifacts never enter any retrieval corpus.
The corpus today holds seven dev scenarios at five chunks each and zero holdout chunks
(`docs/evidence/t2.4b-corpus-smoke/store-state.txt`), which is the state to preserve.

**A holdout run happens once per reported result, and what freezes is enumerated.** "Frozen"
has to mean something a script can check, or it means nothing:

| what freezes | how it is checked |
|---|---|
| every prompt string in `faultline.agents` | sha256 over the concatenated `*_SYSTEM` constants, recorded in the run manifest |
| the corpus | row count and content hash of `incident_chunks`, plus the assertion that zero rows carry a holdout origin |
| the model map | `AgentSettings.effective_models(roles)` and `role_efforts`, both recorded verbatim |
| the budget | all four bounds |
| the tool layer | the git sha of the working tree, with `git_dirty` recorded as the recorder already does |
| the judge | model id and prompt hash, separately from the agent's |

The run manifest records all of it. **A holdout run whose manifest does not match the dev run it
is being compared against is not a comparison**, and the harness refuses to print them side by
side. Changing anything above and re-running holdout is a *new* experiment and gets a new
manifest, not an updated one — the number of holdout runs is a fact worth being unable to hide.

> **Marked decision: the holdout set is not re-run to fix a disappointing number.** If a holdout
> run is discarded, the run and the reason are recorded in the results directory. This is a
> discipline, not a mechanism; recording it is what makes it checkable by anyone reading the
> repository. The alternative — trusting nobody will do it — is how a holdout becomes a second
> dev set.

### 3.4 Cost and model map recorded per run

Tokens in and out are already per step in `trajectory_steps`. The run manifest records the sum,
the dollar figure with the rate used, the effective model map, and the effort map. ADR-0020: "A
sweep run with `{"scribe": "claude-haiku-4-5"}` is not the same experiment as one run without
it, and a headline that says only `claude-opus-5` would not show the difference."

Observed per-investigation cost across the five stored verdicts: $0.27 to $0.56, 18,677 to
52,175 tokens. **n=5, one scenario dominating.** A ten-scenario sweep at three repeats is
therefore an order-of-magnitude estimate of $12–$18 and is stated as an estimate.

## 4. What persists

**The run manifest**, per run: scenario id and fingerprint, split, everything frozen in §3.3,
the baseline-gate readings, injection and revert timestamps, incident id, trajectory id, cost,
and the outcome including which of §2's categories it fell into.

**The trajectory** already persists and is the scoring input. Two fixes it needs first:
`runtime_version` must record what actually ran — it has said `t3.3` since T3.4 — and the
harness must skip zero-step rows like `f7261a74` rather than counting them.

**The `DecisionLog`, whose deferral ends here.** ADR-0017 recorded that every correlation
decision's rule — `graph`, `no_graph_presence`, `no_judgeable_candidate` — goes to an in-process
log, that "`incidents` has no column for it", and that "the schema change lands with whoever
builds that reporting". That is T4.1. The exposure ADR-0017 named is exactly the reporting
question: "how often did the graph actually decide, and how often did this quietly become time
overlap again". A column on `incidents` recording the join rule, written by the orchestrator,
read by the harness.

**Where T4.1b reads the assertion.** `trajectory_retrievals` carries `exclude_origin` per row
(T3.2). T4.1b asserts, for every scored run: at least one retrieval row exists; every row's
`exclude_origin` equals the scenario under test; and no returned `document_id` has that origin.
**All three are true of all six rows in the database today** — the check is verifiable before it
is written, which is the point of having stored the column from day one.

A scored run failing any of the three is **invalid, not annotated** — ADR-0008: "Silent
non-enforcement is precisely how this defect returns after being fixed once."

> **Marked decision, open: `k` counts chunks, not documents.** T3.5's run asked for `k=3` and
> got two chunks of `cart-bad-image-tag` and one of `cart-redis-misconfig` — two distinct past
> incidents, not three. Whether `k` should mean documents is unexamined, and the harness reports
> **both counts** on every retrieval figure until it is settled. Reporting one alone would make
> "three past incidents retrieved" a claim the data does not support.

## 5. Honest n, everywhere

CLAUDE.md's rule six — "any figure that leaves the repo carries n, R, and a 95% CI, next to a
baseline" — plus four requirements specific to what this harness measures:

1. **Unmeasured edges are quoted on every blast-radius figure.** How many the traversal crossed,
   and how many of the recalled services arrived through one.
2. **Per-scenario n on any rate.** Today's five verdicts are four `shipping-wrong-image` runs and
   one `cart-dependency-latency`. "40% fault-class accuracy" over that set would be a statement
   about one scenario wearing the clothes of a benchmark.
3. **No aggregate over mixed fault classes without the per-class table.** ADR-0008 already
   requires this for remediation class; it extends to fault class for the same reason. With
   `scale` at zero scenarios and `bad_config` at one dev scenario, an aggregate is dominated by
   which classes happen to be present.
4. **Coverage beside accuracy, always** (§1.2), and **both model ids beside any judged figure**
   (§1.3).

**What cannot be measured on this catalog, said once rather than discovered per figure.**
`scale` has no scenario, so remediation-class accuracy is over three of four labels. Two dev
bundles cannot produce an incident at all. Ten scoreable scenarios across four fault classes
means a per-class n of 2–4 before repeats, and a 95% CI on a per-class rate at that n spans most
of the unit interval. **The per-class table will mostly show that the per-class table cannot yet
say much**, and printing it anyway is the honest form of that finding.

## Consequences

- T4.1 gains three things the plan did not list: the baseline gate, the world lock, and the
  `DecisionLog` schema change ADR-0017 deferred to it.
- T4.2 gains the `class_dispute` register, the coverage figure, and the four separate-report
  categories.
- **Two pre-existing defects block a first clean run**: `runtime_version` is stale, and zero-step
  trajectory rows exist. Both are small and neither has a task; they belong to T4.1.
- The contradiction checker enters the harness with a live precision of **0/2**. If a first batch
  does not improve it, the honest options are to narrow it further or to retire it — and either
  is a decision with an ADR, not a quiet edit.
- Nothing here measures the demo path (T5.3) or the threat model (T6.x). Both read trajectories
  this harness will produce and neither is designed against.

---

## Addendum (T4.3): the dispute register records disagreeing *readings*, not a silent tiebreak

§1.2 above introduced the `class_dispute` register with one entry, and defined it loosely enough
that two readings were possible: a dispute is where **the fix tiebreak disagrees with the agent**,
or a dispute is where **the two readings of the label set disagree**. With one entry the two
definitions were indistinguishable. The first sweep produced four observations and separated
them.

**Decision: the register records where the two readings disagree.** The fix test is how ADR-0022
*resolves* a dispute; it is not the test for whether one exists.

### Why the sweep settles it

The four observations of this boundary:

| scenario | truth | returned | fix tiebreak |
|---|---|---|---|
| cart-dependency-latency (T3.5) | `dependency_latency` / `restart` | `bad_config` / `config_revert` | **discriminates** — restart clears it, there is nothing to revert |
| cart-dependency-latency (sweep) | same | same | same |
| ad-memory-squeeze (sweep) | `resource_exhaustion` / `config_revert` | `bad_config` / `config_revert` | **silent** — both readings give `config_revert` |
| frauddetection-memory-squeeze (sweep) | `resource_exhaustion` / `config_revert` | `bad_config` / `config_revert` | **silent** |

A register defined by the tiebreak records the first two and is blind to the other two — and the
two it misses are the ones where the label set's ambiguity is *worst*, because nothing downstream
disagrees. Defining visibility by whether a tiebreak fires means the register goes quiet exactly
where the labels are least separable.

### The finding this changes, which is the point of taking the decision

Under the narrow definition the per-class table reads: **"wrong on `resource_exhaustion`, 0/2."**
Under the wide one it reads: **"reads every change-mediated fault as `bad_config`."** The sweep
data says which is true, and it is not close.

Across all seven scenarios the agent returned exactly **two** values: `bad_deploy` where the
change record touched an image, `bad_config` everywhere else. It never returned a symptom class
for any scenario. That one rule predicts all seven rows — including the four it got right, which
are right because the artifact and the symptom happen to agree there.

Both `resource_exhaustion` verdicts identify the mechanism *correctly* before classifying:

> "A process killed by the kernel for exceeding its cgroup limit dies without emitting an
> application-level…" — `frauddetection-memory-squeeze`

> "adservice began hitting the newly imposed memory ceiling…" — `ad-memory-squeeze`

These are not runs that failed to understand resource exhaustion. They are runs that understood
it and then answered a different question: *what changed*, rather than *what is wrong*. That is a
single, coherent, wrong classifier — and it is a far more actionable finding than a per-class
accuracy of 0/2, because it names the thing to fix.

### What this does not change

**Every disputed miss is still a miss.** The register is visibility, not forgiveness: the four
entries are counted wrong in the per-class table and in every aggregate, and the fault-class
figure stays 4/7. What changes is that a reader of the scored output can see that three of the
four errors are one error, without reading seven verdicts to find out.

The entries stay **enumerated, never inferred**. A scorer deciding for itself which misses were
nearly right would be grading on sympathy; each entry names the ADR section that admitted it.

### Consequences

- The register has four entries where it had two, and the two new ones cite this addendum.
- ADR-0008's requirement is reinforced, not relaxed: remediation-class accuracy stays broken out
  by fault class. The sweep's 6/7 fix figure is inflated by `resource_exhaustion` and
  `bad_config` sharing `config_revert`, which is the same collinearity that silenced the tiebreak.
- **Whether the prompt should teach the symptom/change distinction is not decided here.** It is a
  prompt change, so it moves `runtime_version` and needs its own before/after comparison —
  CLAUDE.md's eval-before-opinion rule, applied to the first finding this harness has produced
  that suggests one.

---

## Addendum (T4.8): a second holdout entry, and what separates one from a re-run

**The question.** [`HOLDOUT-2026-08-26.md`](../evals/runs/HOLDOUT-2026-08-26.md) was produced with
`max_tool_calls_per_specialist: 4`. Both of its abstentions carry the starvation signature T4.7
dissolved on dev — `changes` exhausted at 4 of 4, with the target service's change record beyond
the cutoff in the planner's own plan. Does §3.3 permit a **second** holdout entry under the
raised bound: same stamp, budget declared in advance, run once, published beside the first?

### The answer: yes — and §3.3 already says which thing it is

Three sentences of §3.3 decide it, and none of them needed to be stretched.

**"A holdout run happens once per reported result."** Not *once, ever*. The unit is the reported
result, and the sentence forbids running holdout repeatedly **for the same result** — which is
exactly what re-running to improve a number is. T4.7 produced a new reported dev result under a
new configuration. Under §3.3's own words that result is entitled to its own holdout run, and the
first entry is not entitled to be refreshed.

**"Changing anything above and re-running holdout is a *new* experiment and gets a new manifest,
not an updated one."** The budget's four bounds are item four in the freeze table, so changing
one *is* changing something above — and §3.3 does not forbid that. It **categorises** it. The
clause exists precisely because the authors expected a frozen item to change one day and wanted
the result to be a new entry rather than an edit.

**"The number of holdout runs is a fact worth being unable to hide."** The guard is not scarcity;
it is visibility. A protocol whose defence is that nobody counts is weaker than one whose defence
is that everybody can.

### The test that separates a new entry from a re-run in costume

"Something changed" cannot be the test — something always changes. Four conditions, all
checkable, and a second entry qualifies only if it meets all four:

1. **The change is validated on dev before holdout is touched.** T4.7 raised the bound, re-ran
   seven dev scenarios and published the comparison. Holdout is asked about a change that has
   already been measured somewhere else.
2. **The change is justified by a mechanism, not by the holdout result.** The bound of 4 predates
   T3.4c, which made a dispatch name exactly one service and thereby multiplied change-history
   needs by the size of the blast radius. That is arithmetic about the dispatch contract, visible
   in dev sweeps 1 and 2, and true whether or not holdout had ever run.
3. **A prediction is registered before the run.** This is what makes the entry falsifiable rather
   than exploratory. An entry whose prediction is written afterwards is a re-run in costume no
   matter what changed.
4. **The first entry stands unedited, beside the second.** Never replaced, never revised, and
   both published together so a reader sees the sequence rather than the best of it.

### The leakage this does not pretend away

Condition 2 is the one under real strain, and the honest account is this: **the holdout result is
what made the confound salient**. `HOLDOUT-2026-08-26.md` is where "abstention lines up exactly
with `changes` exhaustion" was first written down, and that observation is a signal read off the
holdout set which then influenced a configuration choice. Some information flowed the wrong way.

What bounds it: the *mechanism* was visible on dev independently — `ad-memory-squeeze` exhausted
`changes` at 4 of 4 in both dev sweeps — and the fix was chosen, applied and measured on dev
before holdout was reconsidered. Holdout corroborated; it did not discover, and it did not select
the value.

That is a defensible flow, not a clean one, and **each entry spends some of the set's remaining
value even when the protocol is followed perfectly.** With three scenarios, this set is cheap to
exhaust. So:

### The ledger, and the limit

**Every holdout entry is numbered and counted in one place**, and each new entry states which
reported result entitled it. This is the mechanism §3.3 asked for when it said the number of runs
should be impossible to hide.

| entry | reported result it belongs to | stamp | `changes` bound | file |
|---|---|---|---|---|
| **1** | T4.5's taxonomy-instruction pipeline | `prompts:53fafe9c12bc` | 4 | `HOLDOUT-2026-08-26.md` |
| **2** | T4.7's raised-bound configuration | `prompts:53fafe9c12bc` | 8 | `HOLDOUT-2026-08-26-entry2.md` — **1 of 3 scored**, two discarded to an empty API account and **not re-run** |

**A third entry needs an argument this addendum does not supply.** Two entries in one day on a
three-scenario set is already close to the line, and the next one should have to say why the
answer is not "report entry 1's limitation and stop". The reason a flat *no* was rejected here is
that it has a cost of its own: a holdout number that can never be refreshed describes a system
that no longer exists, and the project would be unable to report a holdout figure for its current
configuration — which is a different way of having no benchmark.

### Consequences

- The budget must be recorded on every scored run, not only in the freeze manifest. Entry 1's
  `score.budget` is `null`, because the field was added at T4.7 — its bounds are recoverable from
  `FREEZE-2026-08-26-holdout.json` and that recovery is itself the argument for the field.
- Entry 2 declares its configuration and its prediction **before** running, in a committed file.
- Neither entry is a comparison against the other in the sense §3.3 forbids: they differ in a
  frozen item and are published as two experiments, side by side, with the difference named.

---

## Addendum (T4.15): the third entry, argued against the four conditions

The T4.8 addendum ended by saying a third entry **needs an argument this addendum does not
supply**, and that it should have to say why the answer is not "report entry 1's limitation and
stop". This is that argument.

**The answer: yes — with one condition met only under strain, and it is named rather than
smoothed over.**

### What entitles it

Dev sweep 5 ([`SWEEP-2026-08-27-locus.md`](../../evals/runs/SWEEP-2026-08-27-locus.md)) is a new
reported result under a new stamp: `prompts:1b0e7cbb4c47`, coverage 7/7, fault class 7/7, every
pre-registered condition met. Under §3.3's "a holdout run happens once per reported result", that
result is entitled to its own entry and entries 1 and 2 are not entitled to be refreshed.

Why not "report entry 1's limitation and stop": **entry 1's limitation has been chased through
two further findings and answered on dev, and the answer has never been tested where it counts.**
Entry 1's two abstentions were `changes` starvation. T4.7 dissolved that on dev; entry 2 tested
it on holdout and found a *third* cause — the plan not investigating the service it had
implicated. S5 addresses that cause on dev and beats both baselines. Meanwhile **the project's
published holdout figure now describes a pipeline two stamps old**, which is precisely the
failure mode the T4.8 addendum gave for rejecting a flat no: a holdout number that can never be
refreshed describes a system that no longer exists.

### The four conditions

**1. Validated on dev before holdout is touched — MET, and more strongly than entry 2's.** The
instruction was measured twice on dev before this question was asked. Its first formulation
(T4.12) was **rejected** on dev against a pre-registered floor, and the second (T4.14) was kept on
dev against six pre-registered conditions including a primary endpoint chosen ahead of coverage.
Holdout is being asked about a change that has already been through a full reject-and-refine cycle
somewhere else.

**2. Justified by mechanism, not by a holdout signal — MET UNDER STRAIN, and the strain is worse
than T4.8's.** The honest account:

*What came from dev.* The quantity the instruction optimises — dispatches at the failing service —
was defined and measured on dev at T4.12, from three dev regressions whose counts collapsed 3→0,
4→1, 3→0. The wording was selected on dev, the rejected version was rejected on dev, and T5.3's
demo observed the same tendency at baseline on a dev scenario. No holdout run informed the
wording, the value, or the decision to keep.

*What came from holdout.* **The failure mode was first named in entry 2**, in these words: "the
plan simply did not investigate the implicated service". The T4.14 instruction says a localized
service keeps its claim on the dispatches until its evidence classes are exhausted. That is the
same failure, and holdout is where it was first written down — a day before T4.12 measured it on
dev.

T4.8's leak was that holdout made a confound *salient* while the mechanism was independently
visible on dev beforehand. **This leak is more direct**: for this specific failure mode, holdout
was chronologically first. The dev evidence is stronger and quantitative, but it is not prior.

*What that costs, and how it is paid.* It is paid by labelling rather than by exclusion.
`email-wrong-image` is the scenario whose failure produced the concept, so **its entry-3 result is
corroborative, not confirmatory, and is reported that way** — a hypothesis tested on the case that
generated it is not independent evidence about that case, whichever way it comes out. The other
two scenarios do not have this problem: neither has ever been read for a mechanism, because
`recommendation-memory-squeeze` abstained on starvation and `productcatalog-dependency-latency`
answered. Dropping `email-wrong-image` instead was considered and rejected: excluding the hardest
case to protect a number is worse than running it and saying what it is worth.

**3. A prediction registered before the run — MET.** In the branch's first commit, before any
scenario runs, naming what should resolve, what should not, and the falsifier.

**4. Entries 1 and 2 stand unedited beside it — MET.** Neither file is touched. All three are
published together and the ledger below counts all three.

### The argument from T7.1, weighed and declined

There is a real argument that was not counted. T7.1 re-records the world; entries 1 and 2 were
measured against the current one, so an entry comparable to them must run now or never.

**The urgency is real and it is not a protocol argument.** A deadline created by another task's
schedule says nothing about whether this entry is a new experiment or a re-run in costume, which
is the only question the four conditions ask. Counting it would establish that any impending
change unlocks the holdout set, and that is a precedent worth more than one entry. **This entry
stands on conditions 1–4 or not at all**; had condition 2 failed, T7.1's schedule would not have
rescued it.

### What this entry spends

The set holds three scenarios. Agent exposures before this entry: `email-wrong-image` **2**,
`productcatalog-dependency-latency` **1**, `recommendation-memory-squeeze` **1** — entry 2's two
discards died at their first model call, so no agent ever saw them. Entry 3 makes those 3, 2 and 2.

**This should be the last entry before the set is re-authored or extended.** Not a rule this
addendum can enforce on its successor, but the reason is arithmetic rather than taste: a
three-scenario set read four times is no longer a holdout in any sense a reader would recognise,
and T7.0's four further fault classes are the honest way to buy more.

### The ledger

| entry | reported result it belongs to | stamp | `changes` bound | file |
|---|---|---|---|---|
| **1** | T4.5's taxonomy-instruction pipeline | `prompts:53fafe9c12bc` | 4 | `HOLDOUT-2026-08-26.md` |
| **2** | T4.7's raised-bound configuration | `prompts:53fafe9c12bc` | 8 | `HOLDOUT-2026-08-26-entry2.md` — **1 of 3 scored**, two discarded to an empty API account and **not re-run** |
| **3** | T4.14's return-to-locus pipeline (dev sweep 5) | `prompts:1b0e7cbb4c47` | 8 | `HOLDOUT-2026-08-27-entry3.md` — condition 2 met **under strain**; `email-wrong-image`'s row is corroborative, not confirmatory |

---

## Addendum (T7.53): entry 4 assessed against the T4.15 limit, and **not opened**

The T4.15 addendum ended by saying entry 3 **should be the last entry before the set is re-authored
or extended**, and noted it could not enforce that on its successor. This is the successor, and it
is enforcing it on itself. The full assessment is
[`HOLDOUT-2026-09-01-entry4-NOT-OPENED.md`](../../evals/runs/HOLDOUT-2026-09-01-entry4-NOT-OPENED.md);
what belongs in the ADR is the decision and the two things that make it non-obvious.

**The four conditions pass — that is not what stopped it.** Condition 1 is met by dev sweep 7
(T7.29, 8/8 scored on the current world). **Condition 2 is met without qualification, which no
previous entry managed**: the change entry 4 would test is T7.28's world fix, and every input to it
came from T7.27/T7.29's kafka investigation on **dev sweeps**. Entries 2 and 3 both met condition 2
*under strain* because a holdout observation had informed the change; entry 4 has no such leak.
Conditions 3 and 4 were within reach — the prediction is drafted and deliberately not activated,
and no prior entry file was touched.

**What stopped it is that the set was never extended.** `evals/scenarios/artifacts/holdout/` holds
the same three bundles; the fourth `split: holdout` YAML, `flag-service-bad-deploy`, is blocked and
produces no bundle. SPLIT.md's three free holdout slots — `bad_config-5`, `bad_config-6`,
`bad_deploy-6` — were **allocated at T7.35 and never filled**, and every scenario authored since
went to a dev slot. **Allocating capacity is not extending the set**, and entry 4 would have made
the exposures 4 / 3 / 3, which is the arithmetic T4.15 described.

**The entitlement argument is stronger than it has ever been, and still loses.** Both prior addenda
rejected a flat *no* on the ground that a holdout number which can never be refreshed describes a
system that no longer exists. **That is now true in its strongest form: all seven holdout runs
predate T7.28, so every published holdout figure describes the superseded world
`4a7690c6fdda…` - two worlds back, corrected by the T7.54 addendum below - and there are zero
current-world holdout figures.** It loses for the reason T4.15
gave when declining T7.1's schedule: urgency created elsewhere says nothing about whether the set
can bear another read. Spending the last comfortable read of a three-scenario set to refresh a
stale number makes the arm thinner, not stronger — and the remedy is allocated and waiting.

**A gap in §3.3 found on the way, recorded and not fixed.** The freeze table enumerates six items —
prompts, corpus, model map, budget, tool layer, judge — and **the world digest is not among them**.
Entry 3 and a hypothetical entry 4 share a stamp and would pass every freeze check while having run
against different worlds. §3.3's *"a holdout run whose manifest does not match the dev run it is
being compared against is not a comparison"* therefore does **not** catch a world move; only the
superseded-world banners on the three entry files record it. Whether the world belongs in the freeze
table is a decision of its own and is not taken here.

### The ledger

| entry | reported result it belongs to | stamp | world | `changes` bound | file |
|---|---|---|---|---|---|
| **1** | T4.5's taxonomy-instruction pipeline | `prompts:53fafe9c12bc` | `4a7690c6fdda` *(two worlds back)* | 4 | `HOLDOUT-2026-08-26.md` |
| **2** | T4.7's raised-bound configuration | `prompts:53fafe9c12bc` | `4a7690c6fdda` *(two worlds back)* | 8 | `HOLDOUT-2026-08-26-entry2.md` — **1 of 3 scored**, two discarded to an empty API account and **not re-run** |
| **3** | T4.14's return-to-locus pipeline (dev sweep 5) | `prompts:1b0e7cbb4c47` | `4a7690c6fdda` *(two worlds back)* | 8 | `HOLDOUT-2026-08-27-entry3.md` — condition 2 met **under strain**; `email-wrong-image`'s row is corroborative, not confirmatory |
| **4** | *would be T7.29's dev sweep 7* | — | — | — | `HOLDOUT-2026-09-01-entry4-NOT-OPENED.md` — **assessed and declined; nothing ran, \$0 spent, exposures unchanged at 3 / 2 / 2** |

**Agent exposures are unchanged: `email-wrong-image` 3, `productcatalog-dependency-latency` 2,
`recommendation-memory-squeeze` 2.**

**What unblocks entry 4:** fill at least one free holdout slot with a recorded, rehearsed scenario —
`bad_config` first, since it has zero holdout representation and the most unexplored paths. The set
is then extended on T4.15's own terms, the four conditions already pass, and dev sweep 7's
entitlement is waiting. Queued as **Q9**.

---

## Addendum (T7.54): the freeze table did not freeze the world

T7.53 found that §3.3's freeze table omits the world digest, recorded it, and did not fix it. This
fixes it, and the interesting part is not the missing item — it is why it was missing, and what the
omission had already done to the published record.

### The six, and what each protects

| item | protects |
|---|---|
| `prompts` — sha256 over every `*_SYSTEM` in `faultline.agents` | the instructions the pipeline runs on |
| `corpus` — rows, content hash, `holdout_chunks` as a **number** | contamination (ADR-0008 axis 1); the one freeze item that is also a contamination check |
| `model_map` — `effective_models` and `role_efforts` | which model actually answered, per role |
| `budget` — all four bounds | the resource envelope, since a bound change is a different experiment (T4.7/T4.8) |
| `tool_layer` — git sha, `git_dirty` recorded but not load-bearing | the code the agent runs on |
| `judge` — model id and prompt hash, **separately from the agent's** | the grader, because a judged number is a function of two models (ADR-0020 §1) |

### Why the world was missing, and what else fell through the same seam

**Every one of the six is something this repository *constructs* — Python constants, database rows,
settings objects, a git sha. The world is something it *observes*.** That is the seam. ADR-0014
later gave the world provenance on the **bundle**, and nobody carried it back to the **experiment**;
the artifact learned what world it was recorded against while the run that used it did not.

So the fix is not "add `compose_digest`". Adding one observed item and leaving its siblings would
repeat the mistake at smaller scale. `freeze.world_state()` records:

- **`compose_digest`** — the three layered compose files; the world's definition.
- **`observability_digest`** — the seven alerting, scrape and collector files. **This has the
  strongest claim of any item in the table, including the original six**: it decides what the
  agent's tools can see at all, which sits nearer the experiment than the compose layer does.
- **`ffs_stub_source_digest`** — the one world component built here rather than pulled.
- **`otel_demo_image_digest`** — the immutable half of a mutable tag (ADR-0026).
- **`capability_version`** — `cap:…`, over the tool surface, `CAPTURE_SET` and
  `TOOL_BEHAVIOUR_REVISION`. **`tool_layer.git_sha` does not cover this**: a sha moves for unrelated
  commits and says nothing about whether what an agent could *ask* changed. Kept as its own field
  rather than folded into the world, because `capability.py` argues the two guards must stay
  separate so neither double-fires and teaches a reader to ignore both.

**`ffs_stub_image_id` is deliberately excluded.** ADR-0014 records it and refuses to compare it — a
rebuild churns the id from unchanged source. Freezing a field that moves on its own trains a reader
to ignore the manifest.

### Absence reads as `unverifiable`, never as unchanged

Every freeze manifest written before this addendum lacks `world`, and comparing two of them says
nothing about whether the world moved between them. `freeze.diff` now returns `world:unverifiable`
rather than silently omitting it. **A check that answers "no difference" to a question it cannot see
is worse than one that says it cannot see it** — and that exact failure is what the next section is
about. The same rule applies within the block: `otel_demo_image_digest` needs a live container, and
`None` on both sides is recorded as unverifiable rather than compared as equal.

### What the omission had already done: entries 1–3 are attributed to the wrong world

The question T7.53 left open was whether entries 1–3 were run against the world their figures are
attributed to. **They were not.** Checked from the record rather than inferred:

- No run manifest records a world, so attribution has to be reconstructed from timestamps against
  the re-records. The re-record windows come from the `t_inject` of the bundles each one wrote:
  **T7.1 captured `2026-08-28T02:41:26Z`–`05:20:49Z`**, T7.28 `2026-08-29T22:54:04Z`–`2026-08-30T01:36:51Z`.
- **All eleven holdout run directories, across all three entries, are earlier than
  `2026-08-28T02:41Z`.** The latest is entry 3's `20260828T015130Z` — fifty minutes clear. So every
  holdout figure was measured against **`4a7690c6fdda…`**, the world *before* `299d791c5e0d…`.
- T7.28's superseded-world banner attributed them to `299d791c5e0d…`. It was applied **per file
  rather than per run**, and it is wrong on **69 of the 97 manifest-carrying runs**.
- **The repository contradicted itself and the earlier statement was the right one.**
  `PREREGISTRATION-2026-08-28-refound.md` says, contemporaneously: *"Every published figure in this
  repository was measured on"* the `4a7690c6fdda…` world. T7.28's later uniform banner overwrote a
  correct attribution with an incorrect one.

**The omission was therefore not latent and harmless.** It was latent and load-bearing: nothing
could check the banner, so nothing did. Corrected in ten report files, in `RESULTS.md` and in
`README.md`, each correction dated and stating what it previously said.

**One piece of good news, and it is checkable:** *no run straddles a world move.* Nothing ran inside
either re-record window, so every run has an unambiguous world. `tests/test_world_generations.py`
pins that as an invariant along with the 69 / 12 split, both of whose boundaries are in the past and
therefore immutable.

### The protocol decision: a failing check records a generation, it does not refuse

Adding the world to the freeze table means the harness will start flagging things it previously
allowed. What should an entry that fails the new check do?

**Decision: run, and be recorded as a new comparability generation — not refuse.** The argument,
rather than the assumption:

- **Refusal protects a comparison that is already gone.** If the world has moved, comparability with
  prior entries is broken *in fact* before any check runs. Refusing does not restore it; it only
  ensures no figure exists for the current world. That is the failure mode both T4.8 and T4.15 named
  when they rejected a flat no: *"a holdout number that can never be refreshed describes a system
  that no longer exists."*
- **Refusal would have made this worse, not better.** The set is three scenarios. A rule that
  discards an entry on a world move hands the decision to whoever last edited a compose file.
- **The labelling machinery already exists and works.** Dev sweeps 6 and 7 are each recorded as their
  own generation with the digests on the page, and RESULTS.md leads with the current-world result and
  labels the rest. Applying the same treatment to holdout entries is the established pattern, not a
  new one.
- **What refusal is right for is the thing it can actually protect: silence.** So the refusal moves
  down a level. A freeze manifest that *cannot say* what world it ran against is refused —
  `world:unverifiable` is an error, not a warning — while one that *can say*, and says something
  different from the entry before it, runs and is labelled. **Refuse blindness, not change.**

Concretely: an entry whose `world` differs from the previous entry's is a **new comparability
generation**. It is published with its own digests, it is not printed side by side with entries from
another generation as though the columns were comparable, and the ledger records the world alongside
the stamp — which it now does.

### Digests: nothing moved

Checked rather than assumed. `runtime_version` is `faultline/0.0.1+prompts:1b0e7cbb4c47`, unmoved:
its digest covers role `*_SYSTEM` prompts, `UNTRUSTED_RULE` and the contract schemas, and this
addendum touched none of them. `CAPABILITY_VERSION` is `cap:9c416e0a`, unmoved: `freeze.py` is
harness code and is not in the tool surface, `CAPTURE_SET` or `TOOL_BEHAVIOUR_REVISION`.
`compose_digest`, `observability_digest`, `ffs_stub_source_digest` and `scenario_fingerprint` are all
unmoved — no compose file, observability file or scenario was edited. **An ADR amendment and a
freeze check move no digest**, which is what makes this fix cheap; it is the reason to do it now
rather than bundle it with a world move.

### The sixth instance: the freeze is computable, and nothing computes it

The hashes are real code — `freeze.build()` and `freeze.diff()` exist and are tested. **But nothing
in any run path calls either of them.** `grep` across `run.py`, `judge_cli.py` and `rehearse.py`
returns nothing; there is no console entry point and no `make` target. The freeze manifests in
`evals/runs/` were produced ad hoc, per task, by hand.

So §3.3's sentence — *"the harness refuses to print them side by side"* — describes **a refusal that
exists nowhere in the harness.** That is the sixth instance of this arc's defect: a rule stated in
prose, believed because it is written down, enforced by nothing. The five before it were the slot
rule (T7.35), the one-driver rule (T7.37), the "flaps" shape (T7.39), the opt-in hole (T7.33) and the
warrant rule (T7.44).

**Not fixed here, and deliberately.** Building the invocation path is a harness feature with its own
design questions — when it runs, what it exits with, whether a dev sweep writes one too — and folding
it into an ADR amendment is how scope stops meaning anything. **Queued as Q10, and its trigger is the
next holdout entry**: entry 4 must generate its freeze manifest through `freeze.build()` and verify it
through `freeze.diff()`, because an entry that hand-writes the manifest is exactly what produced this
addendum's finding.
