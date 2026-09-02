# ADR-0020: The agent layer — the model, the nine roles, trajectories, and what bounds a run

- **Status:** accepted
- **Date:** 2026-08-25
- **Task:** T3.x (nine agent roles), binding on T3.1 and T4.2
- **Design only.** Nothing here is built.

## Context

Everything the agents stand on is now built and measured. ADR-0016 gives them five states
with declared triggers and no contract for what advances them. ADR-0019 gives them four tools
with a typed calling convention, an untrusted envelope, and a warning about what that envelope
does *not* defend. ADR-0017 and ADR-0018 give them a dependency graph, a service catalog, and
a past-incident corpus with `exclude_origin` in the retrieval signature. ADR-0009 already
decided what triage will be scored on.

And ADR-0003 specified the runtime — typed tools, scoped credentials, bounded re-ask, per-agent
budgets, trust labels, full trajectory persistence, a benchmark-compatible entry point — while
naming **no model at all**. That is the largest unwritten contract in the project and §1
closes it.

The behavioural specification is the same place T2.6's requirements came from, read a second
time for a different question. The ten rehearsed narratives' *What was checked* sections are
ten investigations by a competent responder: what was consulted, in what order, which negatives
were treated as findings, and which first instincts were wrong.

## 1. The model

**ADR-0003 says nothing about it.** It lists what the runtime must control and never says what
it is controlling. Every budget, every trust label and every eval number downstream depends on
a choice nobody has written down.

One thing *is* written down, in ADR-0004: the benchmark target "routes models through LiteLLM,
so any provider works", and grades with "a configurable judge model". So T7.2 will run this
system against a harness that already assumes the model is a configuration value. **The
provider boundary is therefore not optional** — it is a requirement inherited from the
benchmark, before any preference about which model to use.

### The trade-off, stated the way ADR-0018 stated it for embeddings

| | API model | Local model |
|---|---|---|
| capability | frontier; the investigations below are hard multi-step reasoning | far below frontier at this task class |
| reproducibility | a pinned model id is stable; a *silent* provider-side update is not | byte-identical forever |
| cost | per token, and every eval sweep pays again | hardware, paid once |
| failure mode | rate limits, outages, a model deprecation mid-project | none, beyond the box |
| honesty of the benchmark | numbers depend on a model we did not train and cannot freeze | numbers are ours end to end |

ADR-0018 chose local for embeddings, and the argument does not transfer. Embedding a
seven-document corpus is a task a 384-dimension MiniLM does adequately; **diagnosing a
four-service cascade from interleaved metrics, logs and change records is not.** A local model
that cannot do the task produces a reproducible zero, and a benchmark whose headline number is
bounded by the model rather than by the system measures the wrong thing.

### Decision

**An API model, behind a provider-agnostic boundary, defaulting to Claude Opus 5
(`claude-opus-5`).** Current first-party pricing is **$5.00 / $25.00 per million input /
output tokens**, with a 1M context window.

Three conditions come with it.

**The model id is configuration, and it is recorded on every trajectory.** Not a constant. The
runtime takes a model id, an effort level and an endpoint from configuration — which ADR-0004's
runtime contract requires for endpoints already, and which T7.2's LiteLLM routing requires for
the model. A trajectory that does not record which model produced it is not comparable with
one that does, which is the `compose_digest` argument (ADR-0014) applied to the agent layer.

**Reproducibility is bounded and the bound is stated.** A pinned model id is stable in name and
not in behaviour: the provider can update the model under it. So a Faultline eval number is
reproducible *given the same model on the same date*, and any published figure carries the
model id the way every other figure here carries `n` and a CI. This is a real weakening of the
project's reproducibility story and it is the price of the capability.

**A cheaper model is a configuration change, not a redesign.** `claude-sonnet-5` at $3.00 /
$15.00 is the obvious lever if sweep cost becomes the binding constraint, and `claude-haiku-4-5`
is plausible for the scribe, which summarises rather than reasons. **Marked for decision:**
whether per-role model selection is worth the complexity, and it should be decided from T4.2's
measured accuracy rather than from a cost estimate.

### Two API-shape facts the runtime should be built around

- **Adaptive thinking, not a token budget.** `thinking: {type: "adaptive"}` with depth
  controlled by `output_config.effort` (`low` → `max`). The fixed thinking-budget parameter is
  removed on current models. Effort is a per-role setting: a specialist reading one tool result
  does not need what the synthesizer needs.
- **Task budgets are advisory and server-side.** `output_config.task_budget` gives the model a
  token ceiling it can *see*, so it paces itself and finishes rather than being cut off. That
  is the right mechanism for §5's token bound, and it is different from `max_tokens`, which is
  an enforced ceiling the model does not know about. Both are needed: one to shape behaviour,
  one to guarantee termination.

### Cost, estimated and marked as such

At an assumed 200K input and 20K output per investigation, Opus 5 costs roughly **$1.50 per
incident**, so a 10-scenario sweep at 5 repeats is about **$75**. Prompt caching should cut the
input side substantially, since the system prompts and tool definitions are identical across
runs. **No measurement exists** — the numbers above are arithmetic on an assumption, in the
same class as ADR-0016's four placeholders, and T4.1's first sweep replaces them.

### The judge is a separate setting, and inherits no default

ADR-0008 names judge contamination — "an LLM judge that has seen the label rubric during its own
prompt tuning" — as the likeliest fifth contamination axis. If T4.2 uses an LLM judge, it
inherits everything above **and** must not be the same instance, prompt, or tuning lineage as
the agent under test.

**Decided, alongside the model recommendation above:**

- **The judge model is its own configuration setting with no default inherited from the agent
  under test.** Defaulting it to whatever the agent runs is how the two silently become one
  model grading its own output, and a default that is usually right is worse than one that must
  be stated, because nobody reads it.
- **The lineage rule is checked at eval time by the harness, not assumed here.** ADR-0008's
  pattern throughout: the harness "asserts the filter actually fired" and marks a run invalid
  rather than annotating it. A prohibition an ADR states and nothing verifies is the failure
  mode that ADR names by title. T4.2 owns the check.
- **Every published figure carries both model ids.** Not just the agent's. A judged accuracy
  number is a function of two models, and reporting one of them is reporting half the
  experiment.

## 2. The nine roles

`ARCHITECTURE.md` names them: triage → planner → [log · metrics · change · trace] specialists →
synthesizer → remediation proposer → scribe.

| Role | Input | Tools | Produces | Orchestrator state |
|---|---|---|---|---|
| **Triage** | the incident's alert episodes, service catalog | none — it reasons over what ingest already gathered | severity, **blast radius** (§6), the service to start from | `TRIAGING` |
| **Planner** | triage output, dependency graph; then specialist findings | none | an ordered plan naming which specialists to dispatch and what each is asked — **and at most one follow-up round** once findings are in | `PLANNING` |
| **Metrics specialist** | a question, a window | `promql_query` | findings with citations to result ids | `INVESTIGATING` |
| **Log specialist** | a question, a window, a service | `logql_query` | as above | `INVESTIGATING` |
| **Change specialist** | a service, a window | `change_history` | as above | `INVESTIGATING` |
| **Trace specialist** | a service, a window | `trace_query` | as above | `INVESTIGATING` |
| **Synthesizer** | every specialist finding, the retrieval results | retrieval (`exclude_origin`) | a **cited** root cause, citation-validated | `SYNTHESIZING` |
| **Proposer** | the RCA | none | a remediation class and a concrete action | `PROPOSING` |
| **Scribe** | the whole trajectory | none | the incident record (§4) | any terminal transition |

### Checked against what the investigations actually needed

The four specialists map cleanly onto the four tools. The *load* does not map at all:

| Specialist | Investigations that needed it |
|---|---|
| Change | **10 of 10** |
| Metrics | **10 of 10** |
| Log | 7 of 10 |
| Trace | **2 of 10** |

Four equal roles over a 10/10/7/2 workload. That is not an argument against the split — a trace
specialist that idles eight times out of ten is cheap, and the two investigations that need it
are the two where it supplies the *first real narrowing*. It is an argument against dispatching
all four every time, which the planner exists to prevent.

**Two findings from the narratives argue the split is incomplete rather than wrong.**

**Much of the work is cross-evidence and belongs to no specialist.** "Whether the service was
idle or absent" needs metrics *and* logs together — it is the check three narratives turn on,
and `ServiceNoTraffic` cannot answer it alone. "Direction of propagation" needs metrics across
services plus the dependency graph. "The two waves of silence" needs the metrics *and* the
knowledge that fifteen seconds between groups is scrape granularity rather than causal
ordering. Under this split those land on the synthesizer, which sees all findings and holds no
tools.

**Decided: the planner gets a second dispatch round. The synthesizer does not get tools.**
The simpler option was to arm the synthesizer, and four things rule it out.

**It reopens the path §4 exists to close.** The scribe discipline works because prose is
generated from validated objects and quotes only by `result_id` against a stored envelope —
free-form pass-through from tool output into corpus material has nowhere to happen. Putting
tools on the synthesizer puts raw untrusted envelopes back into the context that writes the
narrative, which is thesis 1 with a persistence layer, arriving through the role this ADR
routed it away from.

**What is missing is a question, not a capability.** "Whether the service was idle or absent"
is an ordinary metrics query and an ordinary logs query, asked together. Both tools already
exist and both specialists already hold them. The gap is that nobody asked the second question
after seeing the first answer — which is dispatch, and dispatch is the planner's job.

**The budget stays in three units.** §5 accounts tool calls per specialist and tokens and wall
clock per investigation. A follow-up round is more dispatches, visible in exactly those units.
Tools on the synthesizer would need a fourth accounting path for a role the budget currently
treats as terminal, and a bound nobody accounts is a bound nobody enforces.

**Trajectory persistence is unchanged.** Every tool call stays inside a specialist dispatch, so
`trajectory_tool_calls` keeps one shape and T5.3 replays one thing.

**Exactly one follow-up round.** A second round that itself surfaces new gaps ends in a verdict
flagged as incomplete, not a third round. Unbounded re-dispatch is the same non-termination
risk §5 exists to remove, arriving through the planner instead of through a specialist, and an
investigation that has asked twice and still has gaps has produced a finding about its own
evidence that is worth reporting rather than spending more budget on.

**Nothing owns ruling things out, and the narratives say that is the valuable part.**
`ARTIFACTS.md`: the dead ends "are the most useful thing in the document — they are what makes
a retrieved incident a piece of experience rather than a lookup table". Three narratives open
by setting `loadgenerator` aside as the synthetic client; two spend their longest paragraph on
a wrong reading of the two silences. A negative finding is a finding, and the specialist output
contract must carry `ruled_out` alongside `found` or the synthesizer never sees the work.

### The dispatch contract: one service per dispatch *(added T3.4c)*

The table above says the planner produces "an ordered plan naming which specialists to dispatch
and what each is asked" and never says what a single dispatch addresses. `docs/PLAN.md` carried
the question. It is settled here, by a defect.

**A dispatch names exactly one service, and that service must be one the catalog knows.**

T3.4b's planner put four names in one `service` field —
`"paymentservice, currencyservice, cartservice, productcatalogservice"` — and in the same round
put a sentence in another: `"checkoutservice and its direct dependencies (paymentservice, ...)"`.
The contract was a bare `str` and accepted both. The tool layer turned the first into a PromQL
label value that cannot match any `service_name`, so the query matched no series at all — not
even the denominator of total calls — and the metrics specialist reported an empty result. Two
of six dispatches were spent asking questions no series could answer, and the shipping and quote
coverage the planner's own rationale intended never happened.

**This is where ADR-0019 §empty-is-not-error stops.** An empty answer from a well-formed query
is evidence, and eight of the nine rehearsed narratives turn on one. A selector that *cannot*
match anything is a contract error at construction time. Its emptiness looks identical to the
kind that means everything, so accepting it silently converts a malformed request into a
confident negative finding — the same failure lenient parsing produces, arriving through the
tool layer instead of through the parser.

A planner wanting three services' metrics makes three dispatches. That is the same principle as
one tool call per dispatch, already in the table, and it needs no new bound: **the budget's
dispatch-rounds and per-specialist tool-call limits are the natural governor.** A planner that
wants breadth pays for it in dispatches, visibly, rather than smuggling it into a string.

Validation runs at plan-parse time against the service catalog, and takes **the same bounded
re-ask as any other schema failure** (ADR-0003 §): the planner is told which value was wrong,
which kind of wrong it was, and what the legal values are — once. Either naming scheme is
accepted, since `cart-service` and `cartservice` are the same service and `canonical_service`
is what says so; the stored value is normalised to the compose name so everything downstream of
the plan sees one identity.

A second failure **fails that dispatch alone**. The plan keeps its legal dispatches and drops
the rest, each drop recorded as a failed dispatch and reaching the verdict's flags by the same
route a specialist takes when its own output will not validate twice. Three good dispatches and
one bad one is three dispatches' worth of evidence; throwing the round away to punish the fourth
costs the investigation more than the fourth was worth. A plan with nothing legal left is still
a failure of the round — salvage is not leniency.

## 3. Trajectory persistence

ADR-0003 promises "full trajectory persistence to Postgres" and does not say what a trajectory
is. It has two consumers with different needs: **T4.2 scores it** and **T5.3 replays it**.
Replay is the harder constraint — reconstructing what the model *saw* means storing the
rendered text, not the object it was rendered from.

```
trajectories        id · incident_id · model · effort · started_at · ended_at
                    outcome · budget_exhausted · runtime_version

trajectory_steps    trajectory_id · seq · role · kind · at · tokens_in · tokens_out
                    latency_ms · payload

trajectory_tool_calls   step_id · tool · request · result_id · envelope
trajectory_retrievals   step_id · query · k · exclude_origin · returned · scores
```

Four things it must hold, each because something downstream fails without it:

- **Every tool call and the envelope it produced, verbatim.** `result_id` links a claim to its
  evidence — which is what makes the synthesizer's RCA *citation-validated* rather than merely
  cited — and `envelope` is the rendered text the model actually read. A replay that
  re-renders from the typed result is replaying a different prompt.
- **Every retrieval with its `exclude_origin`.** ADR-0008 is explicit: the harness "sets it to
  the scenario under test on every scored run and then asserts the filter actually fired; a
  scored run where the filter did not fire is marked **invalid**, not annotated". That
  assertion needs the argument recorded per retrieval, and this column is where T4.1b reads it.
- **Every retrieval with the text the model read** — added at T7.9, and it should have been here
  from the start. See below.
- **Every inter-agent message.** Fan-out means a specialist's conclusion becomes the
  synthesizer's input; scoring the synthesizer without seeing what it was given scores the
  wrong thing.
- **The model and effort.** Two trajectories from different models are not comparable, and
  nothing else in the record would say so.

~~**Marked for decision:**~~ **Decided at T3.2: stored inline in Postgres, keyed by
`result_id`, alongside the other trajectory tables.** One queryable store, consistent with
`change_records`, and each row is exactly what one call saw.

The size argument stands and is not resolved by this: identical envelopes recur across repeats
of one scenario and are stored once per call, not once per distinct text. What the row carries
instead is an `envelope_sha256` beside the text, so the byte-identity claim is checkable at read
time rather than only in a smoke, and so a later decision to deduplicate has the data to justify
itself without a migration. Content-addressing was rejected for now on the ADR's own ground -
"a place for a hash to disagree with its content" - which is a real failure mode when the hash
*is* the key, and merely a detectable one when it sits beside the text.

### Addendum (T7.9): retrieval is evidence too

**The inconsistency.** This section states the principle — *"reconstructing what the model saw
means storing the rendered text, not the object it was rendered from"* — and then applies it to
one of the two kinds of evidence an agent reads. Tool results are stored verbatim by `result_id`.
Retrievals were stored as **chunk ids**, because the bullet above specified them for ADR-0008's
contamination assertion rather than for replay, and the principle was never carried across.
Retrieval was the only evidence in the trajectory not stored as read.

**Why it mattered rather than merely being untidy.** Chunk ids do not keep pointing at the same
text. The corpus is re-seeded whenever a narrative is corrected, and narratives were corrected
three times in four tasks, and **60 of 62 stored trajectories name chunks whose prose has since
changed** - the union across every rewritten document, not the 39 and 41 that T7.6 and T7.7 each
reported for their own. A tool envelope from the same run still reads exactly as it read. A retrieval
row from the same run resolves to different words.

**Decision: store the rendered retrieval text on the row, with a hash beside it.** The same shape
as `envelope` / `envelope_sha256`, for the same reason.

*Rendered, not the chunk body.* The synthesizer is handed
`f"{scenario_id} / {section}: {text[:280]}"`. The body is the object and that line is the text;
storing bodies would be storing what it was rendered from, which is the failure this section
names. It also means a hash of the body would have been hashing the wrong thing.

*Text and hash, not one or the other.* The asymmetry is real — a hash detects drift and cannot be
read, text can be read and costs storage — and this ADR already resolved it once, for envelopes,
rejecting content-addressing because a hash used as the key is "a place for a hash to disagree
with its content". Beside the text it is merely a detectable disagreement. **Measured, so the
storage argument is not hypothetical**: the rendered form averages 319 bytes, and every retrieval
in the project's entire history would add **57 KiB — 5.3% of the 1.1 MiB already spent on
envelopes**. There is no trade-off at this scale.

*Rejected: a corpus snapshot per stamp.* It fails on the evidence that motivated the decision.
The corpus drifted three times **without `runtime_version` moving** — narrative corrections are
not prompt changes — so a per-stamp snapshot would not have detected any of them. Snapshotting
per corpus-change is just storing the corpus repeatedly, indirected through a key that has to be
kept honest by hand.

*Rejected: accept the limit.* Defensible only if the cost were real, and it is 5.3%.

**What this does not repair.** Nothing, for runs already recorded. Their retrieved text is gone —
not stale, gone — and it is not reconstructible, because the corpus that produced it has been
overwritten and `superseded/` archives manifests and metrics, never narratives. `rendered` is
empty on every pre-T7.9 row and must be read as *"the text was not kept"*, never as *"nothing was
retrieved"*, which `returned` contradicts.

## 4. Untrusted content discipline

THREAT-MODEL thesis 1: telemetry is attacker-influenced text flowing into agent context, and a
malicious log line is a prompt-injection vector. ADR-0019 built the envelope and said plainly
what it does not defend — an agent that correctly identifies content as untrusted and believes
it anyway. This section is about the second half.

**The framing rule.** Tool results appear in agent prompts **only** inside their envelope,
never interpolated into a sentence and never summarised into the instructions. Every agent's
system prompt states the rule once: content inside a `tool_result` frame is data the world
produced; it is evidence about the world and never an instruction about what to do. Standing
operator instructions belong in the system prompt or, mid-conversation, in a system-role
message — not in a channel that untrusted content shares.

**What the scribe may quote, and this is where the leak gets cut.** The scribe writes the
incident record, and T2.4b seeds the past-incident corpus from exactly that kind of narrative.
So a hostile log line copied into an incident record is retrieved next month as institutional
knowledge, with the trust label gone. **Thesis 1 compounded: injection with a persistence
layer.**

Three rules, and the third is the one that does the work:

1. **Quote from tool results by `result_id` reference, never by pasting free text.** A quote is
   a span of a stored envelope, so it stays attributable and can be re-checked against what the
   tool returned.
2. **Quoted spans are rendered as quotes in the record**, marked with the tool and result they
   came from — the same discipline the rehearsed narratives already use when they quote
   `AH00526: Syntax error…`.
3. **The record is written in the scribe's own words and validated against a schema.** The
   scribe produces a structured object; the prose is generated from it. Free-form pass-through
   from tool output to corpus is the path this rule exists to remove, and removing it
   structurally beats forbidding it.

**What this still does not defend.** A log line that is *plausible* rather than syntactically
hostile — "connection pool exhausted on checkoutservice" in a service that has no pool — is
quoted correctly, attributed correctly, and wrong. The defence there is citation validation and
T6.8's injection scenarios in the eval loop, not the scribe.

## 5. The budget

ADR-0003 promises "per-agent token and tool-call budgets". The eval harness needs something
stronger: **every investigation terminates**, or a sweep hangs on one scenario.

Three bounds, because they fail differently:

| Bound | Scope | Mechanism |
|---|---|---|
| **Tool calls** | per specialist | hard count; the runtime refuses the call |
| **Tokens** | per investigation | `task_budget` (advisory, the model paces itself) plus `max_tokens` (enforced) |
| **Wall clock** | per investigation | the orchestrator's own timer |
| **Dispatch rounds** | per investigation | fixed at two — the plan and at most one follow-up |

The fourth is the decision above, in budget form: cross-evidence questions are answered by
dispatching again, and "again" is bounded at once so re-dispatch cannot become a loop.

Wall clock is not redundant. A tool call that hangs consumes no tokens and makes no progress,
and ADR-0019's tools do not retry internally past one attempt — so a stuck query is a stuck
investigation with budget to spare.

**At exhaustion the investigation finishes early rather than failing.** It goes to the
synthesizer with what it has, produces a verdict flagged `budget_exhausted`, and proceeds
through `PROPOSING` normally. Two reasons: a partial diagnosis is scoreable and a `FAILED`
incident is not, and ADR-0016 already establishes that an investigation is never cancelled by
the world changing under it.

**T4.2 must report budget-exhausted runs separately and never pool them.** A sweep where a
third of investigations ran out of budget and scored poorly is a measurement of the budget, and
reporting it as accuracy is the "silent non-enforcement" failure ADR-0008 describes in a
different costume.

**Placeholders, named as such** — reasons, no measurements, in the same class as ADR-0016's:
12 tool calls per specialist; 150K tokens per investigation; 10 minutes wall clock. T4.1's
first sweep is what replaces them, and the tool-call number is the one most likely to be wrong
— the narratives run six to eight checks each, but a check is not a tool call.

## 6. What T3.1 scores

ADR-0009 decided this before the agent existed, and the triage output contract has to be its
mirror rather than something adjacent:

> `alerts_at_fire` is kept as-is — it is what the responder actually had […] `alerts_over_window`
> is added alongside it […] because blast radius is what T3.1 scores triage on and it is
> invisible in the snapshot.

So triage produces a blast radius, and the bundle already holds the ground truth to score it
against. Two consequences follow directly, and both are ADR-0009's, not new:

**Recovery-phase alerts are not blast radius.** Every bundle contains them by design — the
window runs two minutes past all-clear — and each `alerts_over_window` entry carries
`began_after_revert` for exactly this reason. ADR-0009: "a narrative that reports emailservice
as part of the blast radius blames the fault for damage the fix did". **Triage output must be
scoreable against the pre-revert set**, so it is a set of services with the time each entered,
not a flat list — otherwise scoring cannot tell a correct answer from one that swept in the
recovery alerts.

**The `emailservice` case is the hard one and it is measured three times.** It fires after the
revert in every captured `cart-redis-misconfig` run. Under ADR-0016 the *orchestrator* joins it
to the incident, correctly — the fault did reach it. Under ADR-0009 the *scorer* excludes it
from blast radius, correctly — it is damage the fix did. **Those are not in conflict and the
distinction has to survive into the triage contract:** an episode can belong to the incident
and not to the blast radius, and a triage output that cannot express both is unscoreable
against a bundle that records both.

**How the radius is traversed is ADR-0017's, not this ADR's.** Addendum 2 there records that
blast radius traverses **directed** — upstream transitively for measured propagation, downstream
one non-composing step from alerting services — while `DependencyPolicy`'s correlation join
stays undirected, and that ADR-0017's own 19/72/97 hop measurement was computed undirected and
so does not justify the directed radius. T4.1's scoring is what measures directed coverage.

**Blast radius needs sync/async and cannot have it yet.** ADR-0017 declared the distinction out
of scope for correlation and in scope for blast-radius reasoning, and left the source undecided
— `span.kind` from traces preferred, the two measured bundles as its check. **That decision is
now T3.1's blocker, not a background item.** Without it, triage reasoning from the graph
concludes that `frauddetectionservice` failing endangers `checkoutservice`, which
`frauddetection-memory-squeeze` measures as false: an async consumer died and nothing downstream
moved.

## Consequences

**Easier.** T3.x has nine contracts, a model, a record shape, and a termination rule, all
grounded in something already built or measured. The trajectory doubles as T4.2's scoring
input and T5.3's replay source, so there is one artifact rather than two.

**Harder.** The project's reproducibility story is now weaker in one specific place, stated
rather than hidden: a pinned model id is stable in name and not in behaviour. Every published
accuracy figure has to carry the model id, and a provider-side update is a re-baseline the way
a `compose_digest` change is.

**T3.1 is blocked on a decision ADR-0017 deferred.** Sync/async edge semantics were marked for
decision "at T3.1, which is the first task that needs an answer" — this ADR is the confirmation
that it does, and that reasoning from the graph as though every edge were synchronous is
measurably wrong on two of fifteen edges.

**Decided in this ADR:** the model and its provider-agnostic boundary; the judge as a separate
setting with no inherited default; and cross-evidence work as **one** planner follow-up round
rather than tools on the synthesizer.

**Decided at T3.2, when the substrate was built** — both of the remaining open items:

- **Per-role model selection: one default plus an optional override map.** `AgentSettings`
  carries a single `model` (`claude-opus-5`) that every role uses, and a `role_models` map that
  is empty by default. Naming a model per role would make nine decisions where the evidence
  supports one, and this ADR already recorded that the question should be settled by T4.2's
  measured accuracy rather than by a cost estimate — an empty map is that position expressed in
  configuration. **Every published figure reports the effective map, not the default**: a sweep
  run with a cheaper scribe is not the same experiment as one run without one, and a headline
  naming only `claude-opus-5` would not show the difference. The trajectory records the map for
  the same reason. `judge_model` remains its own setting inheriting nothing.
- **Envelope storage: inline in Postgres, keyed by `result_id`** — see §3, where the reasoning
  and the residual size question are recorded.

**No open decisions remain in this ADR.** The placeholders below are not decisions; they are
defaults waiting on a measurement.

**Placeholders, named as such:** the three budget values, and the cost arithmetic in §1 — which
is an assumption times a price, not a measurement.

**Revisit if:** T4.2 measures a cheaper model as sufficient, which turns §1's default into a
line item; T7.2's SREGym interface constrains the runtime differently from ADR-0004's inferred
contract, which that ADR already warns is provisional; or the ten-narrative behavioural spec is
extended by T7.1, which will change the specialist load table and may change the split.

## Addendum (T3.5, 2026-09-01) — the fan-out is now parallel

The plan's T3.5 is titled *Parallel fan-out* and its deliverable is *"Concurrent
investigations"*. Until today the dispatch loop was `for dispatch in plan.dispatches:` and
nothing else — specialists ran one after another. The rest of the task was built and good:
per-agent budgets, a failed specialist degrading the investigation rather than aborting it,
failures flagged and surfaced to the synthesizer, a kill-one-specialist test. The concurrency
was an intention.

That mattered beyond the checkbox. The proposal justifies multi-agent design on two grounds and
says so: *"the fan-out is both the latency win and the justification for multi-agent design."*
Sequential specialists kept the first and lost the second.

### Design

Three phases, separated on purpose. **Admission** is sequential and reserves the tool call at
admission, so a specialist with one call left cannot be dispatched twice by two entries admitted
together. **Execution** is parallel on a thread pool; each dispatch runs `_run_dispatch`, which
touches nothing shared and returns a `DispatchOutcome`. **Merging** is in plan order, so `seq`,
the trajectory and the synthesizer's input are byte-identical to what a sequential run produced.
Concurrency changes the wall clock and nothing else that is recorded — a test makes the first
dispatch finish last and asserts the record does not notice.

### Threads, not asyncio

The plan's method column says *"async concurrency"*. The model SDK calls are synchronous, so
`asyncio` would mean rewriting the agent layer for no gain over a thread pool on I/O-bound
calls. The deliverable is the property — concurrent investigations — and threads deliver it.
Recorded as the one place this task chose the deliverable over the method column.

### What moved

The token check used to run between dispatches. It now runs between rounds, and once more after
each round's merge, so a round can overshoot `max_tokens` by at most its own spend **and the
overshoot is recorded as exhaustion** — §5's flag, set. A first draft omitted the post-merge
check and two existing tests caught it: the overshoot was permitted and never flagged, which is
a partial diagnosis presented as a complete one.

A dispatch that outlives the remaining wall clock is recorded as a failed dispatch with a step
of its own — the plan's *"modality unavailable"* as typed evidence — and the investigation
finishes without it. Its thread cannot be interrupted and is abandoned rather than awaited.

### Proof

A `threading.Barrier(2)` inside two specialists' `run`: sequential execution leaves the first
waiting for a partner that never arrives and the barrier breaks; concurrent execution passes
both. Deterministic, and independent of how fast the machine is.

## Addendum (T3.6, 2026-09-02) — the evidence board, and what it may show which role

The plan's T3.6 asks for *"the typed Evidence object: claim, source query, time range,
raw-result hash, sample payload — the only currency agents may exchange"*, with *"provenance
mandatory"* and *"every Evidence object carries the trust label its source tool attached in the
runtime"*.

**Every part of it existed; no object held it.** The Phase 3 audit's wording was *the provenance
chain is split across three objects*, and it was: `Finding` held the claim and a `result_id`,
the `ToolResult` subclasses held the modality, trust, window and query, and `ToolCallRecord`
held the envelope and its digest. A citation could be resolved and its provenance could not be
read off the thing being cited.

`faultline/agents/evidence.py` is the object. `SpecialistRun.evidence` binds it, and
`board()` assembles an investigation's.

### The runtime binds it, and that is the security argument

A model contributes five fields — `kind`, `claim`, `note`, `confidence`, `result_id` — and every
other field is copied from the tool result the runtime already holds. A field a model could fill
is a field a model could fabricate, and fabricable provenance is decoration. This is also why
`Evidence` is **not** a `_CONTRACTS` member: no role prompt promises this schema, so no model is
asked to produce one. A test pins the split.

### Which role sees the samples, and why it is not all of them

**Marked decision: the board reaches the synthesizer, the scribe and the proposer; the *samples*
reach the synthesizer and the proposer only.**

§4's leak boundary is at exactly one role. What the scribe writes becomes corpus material at
T2.4b, so a hostile log line copied into it is thesis 1 with a persistence layer — retrieved
next month as institutional knowledge with the trust label gone. The synthesizer and the
proposer emit structured objects a validator checks; the scribe emits prose that gets stored.
So `render(sample=False)` is what the scribe receives, and it is a boundary rather than a
preference.

Where a sample does travel it is bounded (`SAMPLE_CHARS`, 400), passed through the tool layer's
own `neutralise`, and rendered inside a trust frame — the same defence as an envelope, reused
rather than restated. And a dispatch prints its sample once however many claims it produced: the
objects each carry it, the rendering does not repeat it.

### What this cost, and the honest asterisk on "nothing"

**No frozen key moved.** `prompts:20088b22cede` and `cap:9c416e0a` before and after — no prompt
text changed, no contract schema changed, no tool was added. The Phase 3 audit filed T3.6 under
Batch B expecting a contract change; binding in the runtime instead of asking a model for
provenance made it free, the same way T3.4's ranking was.

**The asterisk, stated because the freeze cannot state it.** The *user message* each role
receives did change — the board replaced the findings list. User-message content is deliberately
outside `prompts_hash` (T4.7's reasoning: the stamp answers *which agent is this*, and the brief
is assembled per run), so a change of real behavioural significance moved no digest. That is a
property of this freeze design and not a loophole to lean on: **a reader comparing runs across
this commit is comparing different briefs under one stamp.** It matters less than it would have
last week only because T3.9 already moved the stamp and the re-sweep has not run, so everything
in this batch lands inside one re-record window either way.

### A defect found while doing it, and not fixed here

`envelope.neutralise` does not strip ANSI escape sequences, though its docstring says it does and
cites five measured instances in `cart-bad-image-tag`'s capture. Its `CONTROL` pattern lists
`\x0e-\x1f`, which matches the ESC byte alone, so the alternation removes ESC and leaves `[31m`
as literal text. The delimiter defence is unaffected — that is a separate replacement — so this
is noise in what a model reads rather than a hole in the boundary. **Queued as Q18** rather than
fixed in passing: it changes the bytes of every envelope, which is `TOOL_BEHAVIOUR_REVISION`'s
question and therefore the `world` key's, and a tool-layer behaviour change is not something to
slip into an agent-layer task.
## Addendum (T3.1, 2026-09-02) — triage gains a judgement, and keeps its measurement

The specification's T3.1 asks triage to classify *"severity, affected service, blast radius,
duplicate-of, suspected fault category — as a validated structured output driving the state
machine"*, from a *"small model, strict output schema"*, and delivers *"triage decisions
persisted; noise gated before fan-out"*. What existed was `Triage`: deterministic, no model, no
`duplicate-of`, and **no gate of any kind** — every incident handed to the runner was
investigated.

`agents/triage.py`'s own docstring made the case for determinism and it is a good one: *"blast
radius is a traversal of a measured graph, so it is computed: the answer is deterministic, T3.1
scores it against a bundle, and a scored number that moves when nothing changed is not a
measurement."* T3.1 does not overturn that. It splits the task along the line the argument
implies.

### The split, and what each half may decide

**Measured, and not the model's:** severity, which is what `alert.labels.severity` says, and the
blast radius, which is `ServiceGraph.blast_radius` over edges whose propagation was measured from
recorded bundles. Both are handed *to* the model in its brief and neither is a field of its
output contract. There is no path by which sampling can move ADR-0009's scored radius.

**Judged, because a traversal cannot answer it:** `disposition` — the gate itself —
`duplicate_of`, `suspected_fault_class`, `confidence` and `reasoning`. `TriageJudgement` has
exactly those five fields, and a test asserts the set, so a later field that restates a
measurement has to be added deliberately.

**`suspected_fault_class` is deliberately not scored.** ADR-0022 scores the *verdict's* class;
scoring a guess made before any evidence exists would reward confidence at the cheapest point in
the pipeline, which is the opposite of what this benchmark is for. It is a prior the planner may
order dispatches by and must not be bound by.

### The gate, and the two states that were waiting for it

`TRIAGING → RESOLVED` and `TRIAGING → DUPLICATE_MERGED` have been in ADR-0016's table since it
was written, with **no writer** — `tests/test_orchestrator.py` listed both among the states
nothing reaches at runtime. `noise` takes the first and `duplicate` the second, and neither runs
a planner, a specialist or a synthesizer. `Exit.GATED` (5) is a fifth exit code, distinct from
`REFUSED` because something ran and judged, and from `NO_VERDICT` because no verdict was owed.

**Marked decision: a triage that fails to validate twice does not close the gate.** The
investigation proceeds and the report carries no judgement. Declining an incident because the
cheapest role in the pipeline malfunctioned would turn a model outage into silent
under-investigation — the failure ADR-0031 built its fallback against — and an absent judgement
must be visible as absent rather than read as a decision.

**Marked decision: the gate is a role, not a requirement.** `run_investigation` without a
`Triager` behaves exactly as it did before this task, and `--no-gate` is the CLI's way to say
so. The harness's existing sweeps ran ungated, and a comparison across the gate needs both arms
runnable.

### What it cost

The stamp moves again: `prompts:20088b22cede` → `prompts:a7330c098770`, six role prompts now.
**Two moves, one re-record** — T3.9's intermediate digest was never measured either, and the
re-sweep at the end of Batch B measures the pipeline as it finally stands. Both digests are
recorded in `tests/test_harness_run.py` so a trajectory written today can be placed exactly.

## Addendum (T3.2c, 2026-09-02) — briefings under budget, and the number that describes them

The plan's T3.2c asks that agents *"start from a minimal briefing … and pull further context via
tools on demand, rather than receiving everything push-style"*, with *"briefing size … budgeted
per role and measured"* and *"briefing size and pull-rate … logged per run so T7.3's ablation has
data to compare against."*

**Half of this was already true and had never been called that.** The specialists have held one
modality each since T3.3; the synthesizer has never held a tool; retrieval has been `k=3` since
T3.4, which is the plan's *"top-3 similar past incidents"* exactly. Context does arrive on
demand here — through a planner that dispatches rather than a role that asks, which is the same
property reached by a different route.

**What did not exist was a bound or a number.** Every role assembled its brief inline and
appended until it ran out of things to append. The evidence board grows with the dispatch count,
the allowlist and the runbooks grow with the catalog, and nothing said how large a brief was or
declined to make it larger. A context discipline that amounts to *"we did not add much"* has no
defence against the day somebody does.

### The assembler

`faultline/agents/briefing.py`. A brief is a list of `Section`s with priorities; the assembler
keeps whole sections in priority order until the budget is spent, and **names what it dropped in
the brief itself** — the same principle as the tool layer's `truncated`, where the failure mode
is a capped thing that looks complete. A role told what it was denied can say its answer was
limited by it; a role left to infer a gap cannot.

Sections marked `essential` are never dropped, and an essential set that overruns is recorded in
`over_budget` and delivered anyway: refusing to brief a role would fail an investigation to
protect a number, and the number exists to describe the investigation. **The withheld notice is
deliberately not charged to the budget** — charging it would mean a brief that drops one section
might have to drop a second to afford saying so, which is the one trade this design refuses.

What each role drops first is a judgement recorded in its `sections()`: retrieval for the
synthesizer (past incidents are context, not evidence), the runbooks for the proposer (the
allowlist's preconditions survive, and without the allowlist it cannot name a legal action at
all). Triage drops nothing — it is the role the plan calls cheap, and a gate deciding on a
truncated picture is worse than no gate.

### The pull rate, and what it is not

`Disclosure`: *pushed* is what a briefing handed a role unasked, *pulled* is what the pipeline
went and fetched — a tool envelope, a retrieval. Same estimator both sides, so the ratio means
something even though neither number is a token count. It is written to the trajectory as a
final `runtime` step and onto the run artifact, so T7.3 reads stored numbers rather than
re-deriving them.

**Nothing should optimise this number.** A pipeline that pushed nothing and pulled everything
would score 1.0 and might be worse. It describes *how* an investigation got its context, which
is what an ablation against prompt-stuffing needs in order to vary one thing on purpose.

**Tokens are estimated at four characters each and the estimate is named as one.** Importing a
tokenizer into the product to enforce a budget on itself is a dependency ADR-0004 would not
accept for a figure nobody scores; the estimate is wrong in the same direction for every role,
which is what a comparison needs.

### Q16 rode this move, because it is the same key

`freeze.budget_bounds()` is a frozen block and a new bound costs a comparability generation.
T3.2c needed one (`briefing_tokens`) and **Q16** — the per-incident dollar cap — had been queued
since T2.5 waiting for exactly this batch. Two bounds, one generation.

The dollar cap is not a token cap in disguise: **a model's price can change without the token
bound moving**, and the bound is then enforcing a different amount of money than it was set to.
It is checked at the choke point that already halts on tokens, *after* the token check, so a run
breaching both reports the bound its comparators were held to. Its default is Gate 4's own
threshold, `$2`, so a run that would fail the gate stops rather than finishing and failing it.

**The prices are recorded in the freeze beside the cap**, because a `$2` bound at `$5/$25` stops
in a different place than a `$2` bound at `$15/$75` — a manifest holding only the bound would
call two different experiments the same one. The runtime holds its own price table because
ADR-0004 keeps benchmark infrastructure out of the product, and a test asserts it equals
`evalharness.run`'s: a runtime that halted at a different price than the harness scores would
stop for a reason no published figure could explain.

### What moved

`budget` — from four keys to eight. `prompts` did **not**: no system prompt changed and no
contract schema changed, because the assembler rearranges what a brief contains rather than what
a role is asked for. `capability_version` did not.
