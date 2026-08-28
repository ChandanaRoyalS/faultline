# Execution plan — reconstructed from in-repo citations

> **This file is not the plan.** The execution plan lives outside this repository. Every
> entry below was reconstructed by collecting task references from ADRs, scenario files,
> code comments and tests, and paraphrasing what those citations say the task will do.
> Where the repo assumes something the plan has never stated in the tree, that is marked
> **contract not written**.
>
> Treat this as an index of what the codebase believes, not as authority. If it disagrees
> with the real plan, the real plan wins and this file should be corrected.
>
> Reconstructed 2026-08-24, after T1.5 completed.

## How this was built

`grep` over `*.md`, `*.yaml`, `*.yml`, `*.py` for task references of the form `T<digits>`
with an optional sub-number and letter. Matches inside `world/` (the vendored OTel demo)
and matches that were actually ISO timestamps or product identifiers were discarded —
`T06`, `T32`, `T64`, `T100`, `T212`–`T217` and similar are not tasks.

---

## Phase 0 — foundations

### T0.3 — compose profiles
Splits the stack into `world` and `platform` profiles.
`docker-compose.yml:1`

### T0.5 — benchmark feasibility spike
Chose the benchmark target and fixed a **runtime contract**: the agent runtime must be
packageable to a specified interface.
`docs/adr/0004-benchmark-target.md:5`, `docs/adr/0003-in-house-agent-runtime.md:10`

---

## Phase 1 — the world, the injector, the catalog *(complete)*

### T1.1 — bring up the world
Pinned OTel demo v1.2.1 on arm64, with emulation headroom and a feature-flag stub.
`docs/adr/0005`, `docs/adr/0006`, `compose/world-arm64.override.yml:1`

### T1.2 — telemetry
Loki, promtail shipping container logs labelled by service, Loki registered with Grafana.
Originally filtered the flag service's error noise; that filter is now gone.
`compose/telemetry.yml:1`, `compose/promtail-config.yml:1`, `compose/grafana-loki-datasource.yml:1`

### T1.3 — alert rules
Three rules with thresholds grounded in a measured baseline; Alertmanager routed to
Faultline's ingest webhook.
`compose/prometheus/alert-rules.yml:1`, `docs/adr/0012:5`

### T1.4 — chaos injector CLI
Reversible, labelled fault injection. Four fault classes.
`docs/adr/0007:5`, `src/injector/*`

### T1.5 — scenario catalog and rehearsal
Ten scenarios rehearsed by hand into artifact bundles. Produced ADRs 0009–0014.
`docs/adr/0009:8`, `src/evalharness/rehearse.py:1`

### T1.6 — dev/holdout split
Split assigned at authoring, before any rehearsal artifact exists. Enforced by path.
`evals/scenarios/SPLIT.md:1`, `docs/adr/0008:31`, `tests/test_contamination.py:1`

---

## Phase 2 — ingestion, orchestration, context

### T2.1 — alert ingestion *(built)*
Alertmanager webhook receiver, fingerprint dedupe. `POST /api/v1/alerts` validates a v4
delivery, deduplicates on `(fingerprint, startsAt, status)`, and publishes one
alert-episode transition per new alert onto the `faultline:alerts` Redis stream. Identity,
the dedupe rule, and the stream event shape T2.2 consumes are all in ADR-0015; incident
correlation is deliberately **not** decided here.
`src/faultline/ingest/`, `docs/adr/0015-alert-ingest-identity-and-dedupe.md`,
`docs/evidence/t2.1-webhook/README.md` (eight captured deliveries the design was measured
against), `docs/evidence/t2.1-live-smoke/README.md` (the receiver running live),
`docs/evidence/gate-1/README.md:19`

### T2.2 — orchestrator *(built)* / T2.3 — agent fan-out
Event consumption, an eleven-state incident machine, agent fan-out. ADR-0001 commits to a
global investigation concurrency cap with severity-ordered overflow.

**T2.2 is built:** the consumer loop, correlation behind a `CorrelationPolicy` seam
(`TimeOverlapPolicy` now, `DependencyPolicy` at T2.4), the eleven-state machine with an
enforced transition table, the cap, and incident persistence to Postgres. The states that
need T3.x and the action plane are present and stubbed, and calling one says which task owns
its contract. **T2.3 is not**, and cannot be until T3.x exists.

**ADR-0016 designs all of it** and closes the "contract not written" marker this entry
carried: incident correlation, the eleven states with a trigger on every transition,
consumer-group ack semantics — an event is processed when its incident state change is
durable, not when the investigation finishes — and the cap, its severity source, and its
overflow order.

Two of its claims were corrected in place when it was implemented, both marked there rather
than edited over: the cap is unreachable **by construction** rather than merely untested,
because `TimeOverlapPolicy` joins any firing to any live incident so nothing can ever count
to two; and an incident closes on the last resolution rather than after the settle window
elapses, which leaves reopening as the window's only job.

Four numbers in it are placeholders with reasons and no measurements (cap 3, settle window
5m, claim idle timeout 60s, poison threshold 5), to be set from T4.1's first runs. Its last
two states depend on the action plane, which has no task number: see "Discovered omissions"
below.

`docs/evidence/t2.2-live-smoke/` records the first live run: a backlog drained unprompted
against data that was never a fixture, a crash on the first empty read that no fixture-driven
test could have produced, and a clean recovery with no event loss and no duplicates across
sixteen events.
`src/faultline/orchestrator/`, `docs/adr/0016-orchestrator-correlation-state-and-cap.md`,
`docs/evidence/t2.2-live-smoke/README.md`, `docs/adr/0001:9`,
`docs/adr/0015-alert-ingest-identity-and-dedupe.md`

### T2.4 — context layer *(designed, not built)*
Service catalog, dependency-graph scoping, retrieval.

**ADR-0017 designs the first two** against a measured graph
(`docs/evidence/t2.4-dependency-graph/`, 24h over three injected incidents): the catalog's
node set and `canonical_service` identity, a committed graph snapshot rather than a runtime
Jaeger query — with the ADR-0014 lesson applied, so the thing that notices drift compares the
edge set and never `callCount` — and `DependencyPolicy` at a 2-hop radius.

Three findings from the capture constrain it. ADR-0016's prediction that a graph rule joins
`emailservice` to the cart incident **holds**. `featureflagservice` has no node at all, so a
graph policy is structurally blind to it — the same blindness already measured for alerting.
And the graph **cannot distinguish a synchronous edge from an asynchronous one**: trace
context propagates through kafka, so `checkoutservice -> frauddetectionservice` is identical
in every field to `checkoutservice -> emailservice`, while the bundles measure their failure
semantics as opposite. That distinction is declared out of scope for correlation and in scope
for blast radius, which makes it T3.1's problem.

Landing this policy is also what makes ADR-0016's concurrency cap reachable — at 2 hops it
declines 28% of service pairs, so two incidents can be live at once for the first time.
**Retrieval is not designed here**, and T2.4b's corpus seeding remains a separate contract.
`src/faultline/context/__init__.py:1`,
`docs/adr/0017-context-layer-graph-and-dependency-policy.md`,
`docs/evidence/t2.4-dependency-graph/README.md`, `docs/ARCHITECTURE.md:21`

### T2.4b — corpus seeding *(built)*
Seeds the past-incident store from `evals/scenarios/artifacts/dev/` **only**. The input is
`incident.md` — the hand-written narrative in each bundle.
`docs/adr/0008:80`, `evals/scenarios/ARTIFACTS.md:127`, `evals/scenarios/SPLIT.md:62`

**ADR-0018 settles all of it** and closes this entry's "contract not written" marker:
sections as chunks, a local embedding model behind an `Embedder` Protocol, hybrid retrieval
fused on ranks, and `exclude_origin` in the query signature from day one so T4.1b passes an
argument rather than patching a query. The seeder takes the dev directory as its only root —
not a flag, not a filter over both splits — and refuses a holdout path, a narrative whose
front matter disagrees with its path, and a bundle marked INVALID.

Measured: the dev tree yields **seven** documents and 35 chunks. Nine bundles carry a
narrative and two are INVALID, which is where the two missing ones go.
Seeded live on 2026-08-25 against real pgvector: 7 documents, 35 chunks, 0 holdout chunks,
and the embedder stamp verified against `vector_dims(embedding)`. The same run is **the first
live demonstration of ADR-0008's axis-2 exclusion** — a scenario's own symptoms retrieve its
own narrative at rank 1 in both arms without `exclude_origin`, and not at all with it.
`faultline-seed` is the entry point.
`src/faultline/context/`, `docs/adr/0018-past-incident-corpus.md`,
`docs/evidence/t2.4b-corpus-smoke/README.md`, `docs/adr/0002:8`, `docs/adr/0008:80`,
`evals/scenarios/ARTIFACTS.md:154`

### T2.6 — tools *(built)*
Typed tools with scoped read-only credentials and trust-labelled results. Also bound by
ADR-0004's runtime contract.

**ADR-0019 designs the layer, and it is built** — four tools, not three. It closes the "contract not written" marker below, taking its
requirements from the nine rehearsed narratives' *What was checked* sections — nine tool-call
traces of successful investigations. Contracts for `promql_query`, `logql_query` and
`change_history`; a trust envelope whose closing delimiter carries a per-call id, so a log
line cannot close a frame it cannot name; `evalharness.prom`'s transport extracted to a shared
client rather than imported (ADR-0004 forbids the product depending on the harness) or copied
(the drift its own docstring warns about); and read-only established at the tool surface,
because Prometheus here runs with `--web.enable-lifecycle` and Loki's push endpoint is open,
so it cannot come from the server.

Three findings from the requirements list shape it. **Change history appears in 9 of 9
investigations**, more often than metrics or logs, and in five the load-bearing answer is
*nothing changed* — so `empty` and `error` are distinct contract terms, not implementation
detail. **The named tool set does not cover the nine**: traces are the first narrowing step in
two narratives and `ARCHITECTURE.md` names no trace tool. And **a third narrative class still
reasons from unreachable evidence** — both `dependency_latency` narratives cite running-container
inspection, the same defect already fixed for `bad_deploy` and for the memory scenarios.
ADR-0019 predicted change history covers it, since a created container is a change; the
implementation confirms it — a `dependency_latency` injection emits a `container created`
record naming the network-namespace attachment.

Two of the ADR's four marked decisions were taken at implementation and recorded there: the
**trace tool ships** (`ARCHITECTURE.md`'s row updated in the same commit) and the change log
is a **`change_records` table** in the platform Postgres, written by the injector through
`injector.changelog`. Two more findings came out of building it: the requirements list is
**ten** narratives rather than nine, and **two catalog faults cannot be rendered without
leaking** — both flag-service faults deploy stub images whose tags name what they do — pinned
by the guard and tolerable only because both scenarios are blocked.
Smoked live on 2026-08-25 (`docs/evidence/t2.6-tools-smoke/`): all four tools against a
`cart-redis-misconfig` injection, the change record landing in the same second as the inject
and pairing exactly with its reversal, and the leak check clean on live rendered output. The
run found one defect no hermetic test had reason to look for — truncation kept the *oldest*
lines in the window, so a capped log result contained only healthy pre-onset traffic while
correctly reporting itself truncated. Fixed in the same branch, on both `logql_query` and
`trace_query`.
`src/faultline/tools/`, `docs/adr/0019-tool-layer.md`,
`docs/evidence/t2.6-tools-smoke/README.md`, `docs/adr/0004:41`, `docs/THREAT-MODEL.md:8`,
`evals/scenarios/CATALOG.md`

**Requirement derived from measurement, not a decision taken** — now designed in ADR-0019.
The third tool must be **change history, not deploy history** — it has to report resource-limit changes, not only
releases.

All three `resource_exhaustion` scenarios have a container memory-limit change as their
root cause, and that change is observable through none of the agent's other tools. Measured
on `ad-memory-squeeze` against the live world: runtime metrics do reach Prometheus
(`process_runtime_jvm_*` and friends, keyed on `exported_job`), but under fault the series
vanish rather than move, and no series anywhere reports the cgroup ceiling. The logs say
nothing — the process is SIGKILLed and prints no reason. And `docker update --memory` is
not a deploy, so a change-correlation tool scoped to releases would not see it.

A deploy-only history would therefore miss the root cause of **an entire fault class this
catalog already contains** — three of ten scenarios at n=10, one of them holdout. It would
also leave those scenarios scoreable only by guessing, the way `CATALOG.md`'s "Consequence
for T4.x" describes for the cart pair.

`evals/scenarios/CATALOG.md` ("Runtime metrics reach Prometheus, and their absence is the
signal"), `evals/scenarios/CATALOG.md:380` ("What separates them, and why it is only change
history"), `docs/ARCHITECTURE.md:23`

**contract not written** — the repo does not state what a change record contains, what
range of change it covers beyond deploys, or where the history comes from. This entry
records what the catalog *requires* of it, which is a constraint on that contract rather
than the contract itself.

---

## Phase 3 — the agents

### T3.x — nine agent roles *(designed, not built)*
Triage, planner, four specialists, synthesizer, proposer, scribe.

**ADR-0020 designs the layer** against the same ten narratives T2.6 took its requirements
from, read as a behavioural spec. It closes the largest unwritten contract in the project:
**ADR-0003 specified the runtime and named no model.** The decision is an API model behind a
provider-agnostic boundary — `claude-opus-5`, $5/$25 per Mtok — with the boundary required by
ADR-0004's benchmark routing rather than by preference, and with one honest cost recorded: a
pinned model id is stable in name and not in behaviour, so every published accuracy figure now
carries the model id the way every other figure carries `n`.

Also: the nine roles' contracts and which orchestrator state each serves; the trajectory
record, which is T4.2's scoring input and T5.3's replay source at once and must store the
rendered envelope rather than the object it came from; the untrusted-content rule for what the
scribe may quote into an incident record, since that record becomes corpus material and a
hostile log line copied into it is thesis 1 with a persistence layer; and a three-part budget
where exhaustion finishes the investigation early with a flagged verdict rather than failing
it, because a partial diagnosis is scoreable and a `FAILED` incident is not.

Two findings from re-reading the narratives. The four specialists map cleanly onto the four
tools and the **load does not**: change and metrics are needed by 10 of 10 investigations,
logs by 7, traces by 2. And **nothing owns ruling things out**, which `ARTIFACTS.md` says is
the most valuable content in a narrative — so specialist output carries `ruled_out` beside
`found`.

Cross-evidence work — the checks that need metrics and logs together — is **one planner
follow-up round**, not tools on the synthesizer. Arming the synthesizer would put raw untrusted
envelopes back into the context that writes the narrative, reopening the path the scribe rule
closes; and what those checks lack is a second question rather than a capability, which is
dispatch. Bounded at exactly one round: a follow-up that surfaces further gaps ends in a
flagged verdict, not a third round.

The judge model is a separate setting with **no default inherited from the agent under test**,
its lineage checked at eval time by the harness rather than assumed, and every published figure
carries both model ids — a judged accuracy number is a function of two models.
`src/faultline/agents/__init__.py:1`, `docs/adr/0020-agent-layer.md`, `docs/adr/0003:6`,
`docs/adr/0004:41`, `docs/adr/0009:117`, `docs/adr/0019-tool-layer.md`

### T3.1 — triage *(built)*
Scores triage, and **blast radius is what it scores on**. This is why the bundle manifest
carries `alerts_over_window` with `began_after_revert` rather than only a snapshot.

ADR-0020 §6 makes the triage output contract the mirror of that scoring, and surfaces the case
that makes it subtle: `emailservice` fires after the revert in all three captured
`cart-redis-misconfig` runs, and it belongs to the **incident** (ADR-0016 joins it, correctly)
and not to the **blast radius** (ADR-0009 excludes it, correctly). A triage output that cannot
express both is unscoreable against a bundle that records both.

~~**Blocked:** blast-radius reasoning needs sync/async edge semantics~~ — **unblocked
2026-08-25.** The kinds are measured and land as data on every `Edge`:
**9 synchronous, 1 asynchronous, 5 unmeasured** (`docs/evidence/t3.1-edge-kinds/`, ADR-0017's
addendum). Both cross-checks reproduce — `checkoutservice → emailservice` is sync, caller error
0 → 0.061 as the callee died; `checkoutservice → frauddetectionservice` is async, callee dead
for 852s and caller error 0 → 0 throughout. The two are identical in the snapshot, same parent
and both at 286 calls.

ADR-0017 preferred `span.kind` and **the bundles hold no trace data at all**, so the
measurement is failure propagation from the ten recorded incidents instead — the property blast
radius needs rather than a proxy for it, and stronger where it exists. Where no bundle broke a
callee there is nothing, and `unmeasured` is a distinct value rather than a default to `sync`.
**Any blast-radius figure should quote the five unmeasured edges** — a third of the graph — the
way every other figure here carries its `n`.

**Triage is built** (`src/faultline/agents/triage.py`). It consumes the correlated incident and
the service catalog, holds no tools, and produces severity, a blast radius as **a set with entry
times**, and an entry point — not a ranked list and not a culprit.

Traversal is directed, because `edge_kind` is a directed measurement: **upstream** (callee →
caller) is propagation and is transitive to the correlation radius; **downstream** (caller →
callee, one step, from alerting services only) names where an error could have come from, which
is the `email-wrong-image` shape. `async` edges are not crossed in either direction; `unmeasured`
edges are crossed and **surfaced with the edge and the service that arrived through it**, and
every output quotes its unmeasured `n`. Services absent from the graph stay in the output with
their `GraphPresence` rather than being dropped — `loadgenerator` alerted in almost every
captured incident and would otherwise be reported as unaffected.

Smoked live (`docs/evidence/t3.1-triage-smoke/`): the captured T2.1 deliveries replayed through
ingest → orchestrator → triage. `frauddetectionservice` is one hop from an alerting
`checkoutservice` across an edge indistinguishable in the graph, and is correctly **absent** —
the measured `async` edge. Triage is computed rather than asked: ADR-0020 chose a model for the
agent layer and is silent on which roles call it, and a scored number that moves when nothing
changed is not a measurement.
`docs/adr/0009:117`, `docs/adr/0009:137`, `docs/adr/0020-agent-layer.md`,
`docs/adr/0017-context-layer-graph-and-dependency-policy.md`,
`docs/evidence/t3.1-edge-kinds/README.md`, `src/faultline/context/graph.py`,
`src/evalharness/rehearse.py:590`

### T3.2 — the agent substrate *(built)*
The provider-agnostic model boundary and trajectory persistence — everything the roles stand on,
with no roles in it. **Not a task number the plan states**; inferred from ADR-0020's design
splitting cleanly at this seam, and recorded here so the work has a home. **contract not
written** — the real plan may number this differently or not at all.

`LanguageModel` is a Protocol with a lazily-imported Anthropic implementation behind
`faultline[agents]` and a `DeterministicModel` for tests, following the embedder precedent.
`AgentSettings` (`FAULTLINE_AGENT_*`) carries one default model, `claude-opus-5`, plus an
optional per-role override map, and **no API-key field at all** — the SDK reads credentials from
the environment, and a key that never enters this repo's configuration cannot be written to a
trajectory or printed by a `--help`.

Trajectories persist to four Postgres tables with an in-memory double. The property that drives
the shape: **replay needs the rendered envelope, not the object**, so the envelope is stored as
text and never re-rendered, with a `sha256` beside it; and `exclude_origin` is a column on every
retrieval, which is where T4.1b reads ADR-0008's assertion.

Closes both of ADR-0020's remaining open decisions — per-role selection and envelope storage —
recorded there. Smoked against live Postgres (`docs/evidence/t3.2-trajectory-smoke/`): a
trajectory written and read back through a second connection, envelope **byte-identical**, 2010
bytes, matching sha256, closing nonce intact.
`src/faultline/agents/model.py`, `src/faultline/agents/settings.py`,
`src/faultline/agents/trajectory.py`, `docs/adr/0020-agent-layer.md`,
`docs/evidence/t3.2-trajectory-smoke/README.md`

### T3.3 — planner and specialists *(built; first real dispatch not yet run)*
The planner and the four specialists, per ADR-0020 §2. **Not a task number the plan states** -
inferred from the ADR's role table, same convention as T3.2. **contract not written.**

The planner holds no tools and produces an ordered dispatch plan naming which specialists to
send and what each is asked. **A plan is a choice, not a broadcast**: the load table is why the
role exists - change and metrics were consulted in 10 of 10 rehearsed investigations, logs in 7,
traces in 2 - so `skipped` is a required field and a plan may dispatch one specialist. The
one-follow-up-round cap is enforced by the rounds bound on the budget object, not by prose.

Each specialist calls its tool, hands the **rendered envelope** to the model, and returns
validated `found` **and** `ruled_out` - both required in the schema, because a default of `[]`
would let a specialist discard the half of its work `ARTIFACTS.md` calls the most useful thing
in a narrative. Findings cite evidence by `result_id` only; the raw envelope goes to the
trajectory verbatim and travels no further, which is ADR-0020 §4's leak boundary at the point it
is first crossed.

All four budget bounds are live from the first dispatch and exhaustion produces the flagged
verdict rather than an exception - a partial diagnosis is scoreable and a `FAILED` incident is
not.

**The live dispatch has run** (`docs/evidence/t3.3-first-dispatch/`). Against a real
`cart-redis-misconfig` injection with `claude-opus-5`: two rounds, six dispatches, 26,831 tokens,
$0.28 - and it **found the root cause from evidence**, the logs specialist reading a crash loop on
Redis port 6380 and the changes specialist finding an environment update three minutes before
onset. The change record named the fault without naming the harness, which is T2.6's leak
boundary holding under a real agent reading it.

The planner dispatched **three of four in both rounds**, skipping logs in round one ("traces plus
metrics should localize the failing dependency; logs can be added later") and traces in round two
("traces already did their job"). Structured output validated first try on 6 of 8 completions.

The run also found a defect: a reply cut off at `max_tokens` is truncated JSON that arrives
looking malformed, and the re-ask invited the same too-long answer again, killing an
investigation that already had three specialists' findings. Fixed in the same branch - truncation
is re-asked as truncation, and a specialist that fails twice now fails alone.
`src/faultline/agents/roles.py`, `src/faultline/agents/investigation.py`,
`src/faultline/agents/budget.py`, `src/faultline/agents/contracts.py`,
`docs/adr/0020-agent-layer.md`, `docs/evidence/t3.3-first-dispatch/README.md`

### T3.4 — synthesizer and scribe *(built; first end-to-end investigation run)*
The two roles that turn findings into a verdict and a narrative, per ADR-0020 §2. **Not a task
number the plan states** - inferred from the ADR's role table, same convention as T3.2 and T3.3.
**contract not written.**

The synthesizer holds **no tools**. Its inputs are the triage result, the specialists' findings
as validated objects, and past-incident retrieval carrying `exclude_origin` - the first live
consumption of the context layer, and the point where ADR-0008's second axis stops being an
assertion. Its output is a `Verdict`: root cause, fault class, class of fix, confidence,
evidence by `result_id`, and open questions. A flagged investigation - budget exhausted, or a
specialist that failed alone - produces a **flagged verdict, never silence**, because a partial
diagnosis is scoreable and a missing one is not.

**Marked decision: `exclude_origin` enters through the environment**
(`FAULTLINE_EVAL_SCENARIO`), not through any product-side field. The *harness* knows which
scenario is under test; the product does not, and giving it a place to know would be a
contamination surface rather than a feature. Unset in production, where retrieval sees the whole
corpus - a distinct path, pinned by a test that says so.

The scribe is **where thesis 1 is cut**. Prose comes from validated objects; any quotation of
tool output is resolved **by `result_id` against the stored envelope**, never from text the model
carried in context. A citation the trajectory store does not hold is refused, and the T2.6 leak
guard (`BANNED_VOCABULARY`, `WORLD_OWNED_TOKENS`) runs over the finished narrative - a leak fails
the render rather than being reported.

**The first end-to-end investigation has run** (`docs/evidence/t3.4-first-investigation/`).
Against a real `shipping-wrong-image` injection: 2 rounds, 6 dispatches, 17 steps, 45,015 tokens,
$0.48, verdict `bad_deploy` / `rollback` at medium confidence - both matching the recorded ground
truth - and a rendered narrative that passed the leak guard. Retrieval returned three dev past
incidents with the scenario's own five chunks excluded.

Two findings, recorded as evidence rather than fixed here. The synthesizer **contradicted its own
trajectory**, reporting that shippingservice change history had never been queried when
`tr_f536225dc17d` holds it and names the image swap outright. And the log tool's
truncate-to-newest behaviour (the T2.6 direction fix, right for the common case) **drops the one
signal that separates this scenario from resource exhaustion** - 312 pre-onset lines that existed
in Loki inside the specialist's own window and never reached it.

One defect found and fixed: the renderer resolved citations before the trajectory was saved, so
every real `result_id` was refused - the guard firing correctly on evidence that existed, which
is indistinguishable from the fabricated-citation case it exists to catch.
`src/faultline/agents/narrative.py`, `src/faultline/agents/roles.py`,
`src/faultline/agents/investigation.py`, `src/faultline/agents/contracts.py`,
`docs/adr/0020-agent-layer.md`, `docs/evidence/t3.4-first-investigation/README.md`

### T3.4b — verdict grounding *(built; second live run captured)*
Two defects T3.4's smoke recorded, diagnosed from the stored trajectory before either was
touched. **contract not written** - a follow-on to T3.4, same convention.

**The synthesizer's contradiction was context assembly, not attention.**
`InvestigationResult.findings` keyed on specialist name, so T3.4's three `changes` dispatches
collapsed to the last - quoteservice, which was empty - and the shippingservice change record
naming the image swap outright never reached the synthesizer. Its claim that the query had
never been made was accurate about what it was shown. Every executed dispatch now reaches the
planner's follow-up brief, the synthesizer's brief and the scribe's brief, labelled with its
service and carrying its `result_id`, with a one-line-per-dispatch index ahead of the detail.

A deterministic cross-check covers what the assembly fix does not: a verdict claiming a dispatch
never happened, for a dispatch that did, becomes a **flag carrying the refuting `result_id`**.
The verdict text is never edited - it is evidence of what the model concluded, and T4.2 has to
count these rather than have them silently repaired. Its first live firing was a **false
positive**, caught by reading the run: a comma-joined sentence whose second half said the
service *was* covered. Fixed and pinned verbatim.

**Log retention is two-ended.** T3.4's specialist reported that shippingservice "emitted nothing"
for seven minutes; 312 pre-onset lines sat in Loki inside its own query window and the newest-40
cap dropped every one. The newest majority plus an oldest sample - a fifth of the budget, floored
at 3 and ceilinged at 8 - with an explicit elision marker and both counts in the envelope. T2.6's
direction and trace pins are unchanged; its newest-lines pin is amended, intent intact.

The re-run (`docs/evidence/t3.4b-rerun/`) is also the **first variance observation**: the same
scenario twice, `bad_deploy`/`rollback` the first time and `unknown`/`none` the second, both at
medium confidence, 48,526 tokens and $0.46. The second run localized the failure to the
shipping-quote hop and then never dispatched shippingservice, saying so in its own open
questions. n=2 is an observation, not a rate.
`docs/adr/0021-verdict-grounding-and-two-ended-truncation.md`,
`src/faultline/agents/grounding.py`, `src/faultline/agents/roles.py`,
`src/faultline/tools/tools.py`, `src/faultline/tools/results.py`,
`docs/evidence/t3.4b-rerun/README.md`

### T3.4c — the dispatch contract *(built; third live run captured)*
One defect from T3.4b's run and the decision it forced. **contract not written**, same
convention as T3.4 and T3.4b.

`Dispatch.service` was a bare `str`, so T3.4b's planner put four names in one field and a
sentence in another. The tool layer turned the first into a PromQL label value that cannot match
any `service_name` — no series at all, not even a zero denominator — and the specialist reported
it as an empty result. **This is where ADR-0019's empty-is-not-error principle stops**: an empty
answer from a well-formed query is evidence, and eight of the nine rehearsed narratives turn on
one, but a selector that *cannot* match is a contract error at construction time, and its
emptiness is indistinguishable from the kind that means everything.

A dispatch now names exactly one service the catalog knows, validated at plan-parse time and
canonicalised in place, so either naming scheme is accepted and everything downstream sees one
identity. The bounded re-ask names the offending value, which kind of wrong it was, and the
legal values — once. A second failure **fails that dispatch alone**: the plan keeps its legal
dispatches, each drop is recorded as a failed dispatch and reaches the verdict's flags, and only
a plan with nothing legal left fails the round. Salvage is not leniency.

Pinned with the two verbatim strings from T3.4b's stored trajectory. **The validator did not
fire live** - the third run's planner produced legal single-service names first try in both
rounds - so only the hermetic pins exercise the re-ask path.

The run also found a second defect and fixed it: **the planner's `max_tokens` was still 1200**
while the specialists moved to 3000 in T3.3, and the first attempt at this smoke lost the round
to two truncated plans before any tool ran. Measured directly against the same incident: an
untruncated plan costs 915 output tokens, so the planner had been running at three-quarters of
its budget. Raised to 3000.

The third run is the best of the three (`docs/evidence/t3.4c-rerun/`): `bad_deploy`/`rollback` at
**high** confidence, the change record cited first in its evidence, three dispatches on
shippingservice, and **the pre-onset language boundary in both the verdict and the narrative** -
the signal `incident.md` calls decisive, which T3.4 lost to truncation and T3.4b never queried
for. 52,175 tokens, $0.56. Two of three runs match ground truth; n=3 is three observations.

The contradiction check (T3.4b) has now fired live twice and **both were false positives**, each
caught by reading the run and each producing a sharper rule - the second, that a clause citing a
dispatch's own `result_id` is a claim about that result rather than a denial of it. Its only true
positive remains the historical one. T4.1's first batch is where that record gets a denominator.
`docs/adr/0020-agent-layer.md`, `src/faultline/agents/contracts.py`,
`src/faultline/agents/roles.py`, `src/faultline/agents/grounding.py`,
`docs/evidence/t3.4c-rerun/README.md`

### T3.5 — the investigation runner, and the state machine it drives *(built)*
**The plan called this task "state machine" and it is broader than that** - the machine's
agent-driven transitions are one part of packaging the pipeline as an operational entrypoint.
The difference is marked rather than resolved silently: the transitions this entry describes are
exactly the ones the plan scoped, and the CLI around them is the component they were waiting
for. **contract not written** for the CLI; the transitions' contract *was* written, in ADR-0016,
and this closes it.

`faultline-investigate` is the fourth command and the one T4.1 drives. Everything T3.1-T3.4c
built ran as a hand-assembled script in the evidence directories, which is fine for a smoke and
useless to a harness. It takes an incident id (or `--list`), runs triage, planner, specialists,
synthesizer and scribe under the budget from settings, persists the trajectory, writes the
verdict as JSON and the narrative as markdown under `--out`, and exits **0** on a clean verdict,
**2** on a flagged one, **3** on a refusal, **4** on no verdict - four codes because a sweep
that cannot tell them apart will pool them, which is what ADR-0020 §5 exists to prevent.

**`record_agent_outcome` stopped being a stub.** ADR-0016 named the five agent-driven states and
left the contract to T3.x; T3.x has built it. The decisions the runner forced are recorded in
ADR-0016 §5: an investigation starts from `TRIAGING` and nowhere else (which the table already
said), it stops at `SYNTHESIZING` and does not claim a `PROPOSING` it has no proposer for, a
flagged verdict is not a failed incident, and the trajectory id lands on the incident row -
upserted with `COALESCE`, because the orchestrator saves incidents too and has no id to offer.

Two defects found by the smoke. **A failed *start* is not a failed investigation**: the first
live attempt raised `ModuleNotFoundError` before any model call, the runner marked the incident
`FAILED`, and `FAILED` is terminal - one absent optional extra permanently retired a live
incident nothing had investigated. And **"the trajectory is persisted up to the failure" was not
true** until this task: a run that died in the synthesizer left nothing in the store at all.

The smoke (`docs/evidence/t3.5-runner-smoke/`) drove one investigation of `cart-dependency-latency`
entirely through the CLI - a fault class no agent run had faced. States
`triaging -> planning -> investigating -> synthesizing`, then `-> resolved` by the orchestrator
with the investigation id intact. 43,513 tokens, $0.47, exit 0. The agent reconstructed the
mechanism exactly - 300ms egress delay, one hop per Redis call, compounding across two
sequential cart calls - and classified it `bad_config`/`config_revert` against a ground truth of
`dependency_latency`/`restart`. **Retrieval earned its keep for the first time**: the agent
refused the empty-error-ratio trap that sent T3.4's run to the wrong service, citing two past
incidents in the corpus for why.
`src/faultline/agents/cli.py`, `src/faultline/agents/runner.py`,
`src/faultline/orchestrator/machine.py`, `src/faultline/orchestrator/store.py`,
`docs/adr/0016-orchestrator-correlation-state-and-cap.md`,
`docs/evidence/t3.5-runner-smoke/README.md`

---

## Phase 4 — the eval harness

> **Note for T4 scoring.** Triage's `start_from` is an **entry point, not a culprit claim** -
> the earliest alerting service the graph can reason about, which is where a responder looks
> first and not what caused the incident (ADR-0020 §6, `src/faultline/agents/triage.py`).
> **T4 must not score it as culprit accuracy.** Root cause is the synthesizer's output and is
> scored there; scoring an entry point as a diagnosis would report triage as wrong for doing
> exactly what it was asked to do.

> **Note for T4.1.** The live agent path needs a **baseline gate before injection**. The
> rehearsal recorder (T1.5) refuses to record against a dirty baseline; the agent-run path has
> no equivalent, so nothing stops an injection landing on an already-degraded world and nothing
> marks the resulting run as suspect. Found in T3.4's smoke, where the world *was* degraded
> beforehand (checkoutservice and frontend pinned at 15000ms p95, accountingservice at 0.000
> req/s) and the check that caught it was manual
> (`docs/evidence/t3.4-first-investigation/README.md`).

> **Note for T4.2.** **Contradiction flags are a distinct class.** A verdict that is wrong about
> its own evidence - claiming a dispatch never happened when the trajectory holds it - is a
> different failure from one that ran out of budget, and pooling them would hide the more
> interesting of the two (T3.4b, `src/faultline/agents/grounding.py`).

> **The dispatch contract, settled by T3.4c.** The planner passed **comma-separated service
> lists** where one service belongs, and both the dispatch schema and the tool layer accepted
> it; the resulting PromQL matched no series at all and two of six dispatches were spent on it
> (T3.4b's re-run, `docs/evidence/t3.4b-rerun/README.md`). **One service per dispatch**, one the
> catalog knows, validated at plan-parse time with the same bounded re-ask — recorded in
> ADR-0020 §2, which had left it open.

> **Note for T4.2: the fault-class boundary `cart-dependency-latency` sits on.** A shaping rule
> attached to a container's network namespace is readable as `dependency_latency` (a dependency
> got slow) or as `bad_config` (something was configured wrong), and T3.5's run chose the
> second against a ground truth of the first - while reconstructing the mechanism exactly. The
> class of fix follows the same fork: `incident.md` says `restart` because "nothing was deployed
> and no configuration was wrong", and the agent proposed `config_revert` for a fault with no
> configuration to revert. **This is an ambiguity in the label set, not only an agent error**,
> and scoring needs a position on it before it reports a fault-class accuracy
> (`docs/evidence/t3.5-runner-smoke/README.md`).

> **Note for T4.1: retrieval `k` counts chunks, not documents.** T3.5's run asked for 3 and
> got two chunks of one document plus one of another - two distinct past incidents, not three.
> Whether that is what `k` should mean is unexamined.

> **All of the notes above are now designed against in ADR-0022**, which cites each one. They
> stay here because a note is where the evidence was first recorded and the ADR is where the
> position was taken; the two are not the same document.

### T4.1 — harness runner *(built)*
Drives runs from the scenario catalog: **what to inject, how long to wait, how long
between runs**, reading `injection`, `seconds_to_alert`, `seconds_of_steady_state` and
`seconds_to_settle` from bundle manifests. Specified to work **through public interfaces
only**. Computes the retrieval seed at seed time rather than at record time.

ADR-0022 §3 adds three things this entry did not list. A **baseline gate that refuses rather
than warns** - the T1.5 recorder's gate is the model, the agent path has none, and T3.4, T3.4b,
T3.4c and T3.5 all performed the same check by hand. A **world lock**, because one driver of the
world has been an instruction to a human since T3.3. And the **`DecisionLog` schema change
ADR-0017 deferred to "whoever builds that reporting"** - **landed**, as `join_rule` on
`incident_episodes` rather than on `incidents`: a join is a decision about an episode, and an
incident accumulates several. Every deployed join now records `time_overlap`, which is ADR-0017's
exposure made visible - the graph policy is not the one running.

**Only ten of the twelve bundles are runnable.** `currency-cpu-throttle` and
`flag-service-crashloop` carry an `INVALID.md` and an empty `alerts_over_window`; neither can
produce an incident, so neither can be investigated. Seven dev plus three holdout, and the
command refuses the other two by name.

`faultline-eval <scenario>` runs the whole protocol as one command: baseline gate, inject,
wait for the orchestrator to correlate, invoke `faultline-investigate` **as a subprocess**, revert,
confirm recovery, score. The CLI is invoked rather than imported because ADR-0009 specifies the
harness works through public interfaces only, and the exit code being relied on has to be the one
being exercised.

**The gate refuses rather than warns**, and encodes both of ADR-0022's known-good facts:
`frontend-proxy` at 0.000 req/s is the healthy state (181 baseline samples of 0.0), and the
five-minute post-restart p95 hazard is the recorder's own `require_settled_containers`, reused
rather than restated. **The world lock does not wait** - waiting is how two harness processes
interleave injections with nothing in either log to show it.

**A run that dies is a recorded discard, never a deletion**: the run directory is created before
the gate is read, and whatever happens next is written into it. Applied to every run rather than
only to holdout, because the rule costs nothing to extend.

Scoring is deterministic only - no judge, which is T4.2. Triage recall **and** precision as a
pair with the unmeasured-edge count quoted; `unknown` treated as abstention and reported as
coverage; the `class_dispute` register for the boundary ADR-0022 resolved; and the four held-out
categories printed even at zero.

Two defects from the design review are fixed. **`runtime_version` is now derived**
(`faultline.agents.stamp`) from the package version plus a digest over every role system prompt
and every contract schema - the two things that determine what a run *is* - so it cannot say
`t3.3` three tasks later. No git and no subprocess: ADR-0004 keeps benchmark infrastructure out
of the product, and the harness records the git sha separately where that already belongs. And
**a zero-step trajectory is an explicit recorded discard** naming `f7261a74` as the row that
prompted it.

The first scored run (`docs/evidence/t4.1-first-scored-run/`) produced **ADR-0017's number, and
it is not zero**: blast-radius recall 0.78 on `cart-redis-misconfig`, missing
`frauddetectionservice` and `quoteservice`, with precision 0.58 reported beside it and not
combined. One observation on one scenario settles nothing; what changed is that the hypothesis
ADR-0017 could only state is now a measurement every run produces. The verdict **abstained**, and
the run is the first demonstration that the scorer treats that as coverage rather than error -
for two reasons it names: a Jaeger 500, and **the comma-list dispatch defect recurring**, whose
fix is T3.4c sitting unmerged in PR #28.

**Open gap, found by breaking it.** The discard rule holds for every failure the process can
observe. A `SIGKILL` runs no `except` and no `finally`, so an externally killed run leaves a
directory with no `manifest.json` and no `DISCARDED.md`. Any aggregation over `evals/runs/` must
treat a directory without a manifest as an incomplete run.

A **second run** was attempted once T3.4b and T3.4c were both in the pipeline, and was discarded:
the API account ran out of credit on the investigation's first model call. It produced no score
and none is claimed - but it exercised three rules under a failure nobody arranged. The
failed-start distinction held (no trajectory, incident left `triaging` rather than terminal
`FAILED`, resolved normally afterwards); the revert ran from its `finally` and the world came
back clean; and the run was recorded rather than deleted. The one comparison available without a
model call is the stamp, which moved - `prompts:69aa6c670318` to `prompts:59bf438b2a96`, because
T3.4c changed the `Dispatch` contract - and that is exactly what a derived stamp is for.

**The complete-pipeline run landed** (`20260826T055345Z`): `bad_config`/`config_revert`, **both
correct, at high confidence**, against run 1's abstention on the same scenario - and it named the
port, the crash loop and the propagation path. Two runs of one scenario, one per pipeline, so the
honest statement is *the run that could reach a class did*, not *the fix caused it*; the
abstention had two causes and only the comma-list dispatch defect is addressed, the Jaeger 500
simply not recurring. 52,055 tokens, $0.54. Triage was identical on both runs - deterministic
traversal, same alerting set - which makes ADR-0017's under-reach misses
(`frauddetectionservice`, `quoteservice`) observed twice rather than once.

> **Note for T4.2: a refused narrative render is invisible in the scored report.** Run 3's
> narrative was refused by the leak guard for using a banned word, so it wrote no `narrative.md`
> - correct behaviour, and `faultline-investigate` still exited 0 because a verdict existed. But
> T4.2's judge scores narratives, and nothing in `report.txt` says there is none to score. The
> four held-out categories do not cover it and a fifth may be owed
> (`docs/evidence/t4.1-first-scored-run/README.md`).
`src/evalharness/run.py`, `src/evalharness/gate.py`, `src/evalharness/scoring.py`,
`src/faultline/agents/stamp.py`, `src/faultline/orchestrator/models.py`,
`docs/adr/0022-evaluation-harness.md`, `docs/evidence/t4.1-first-scored-run/README.md`

### T4.1b — run-time self-exclusion *(designed, ADR-0022 §4)*
ADR-0008 axis 2. A scenario's own artifacts are never retrievable while it is scored;
leave-one-out exclusion enforced in the retrieval query itself, filtering on the `origin`
provenance stamp.

Three assertions per scored run, and a failure makes the run **invalid rather than annotated**:
a retrieval row exists, every row's `exclude_origin` is the scenario under test, and no returned
`document_id` carries that origin. **All three already hold for all six `trajectory_retrievals`
rows in the database** - the check is verifiable against existing data before it is written,
which is what storing the column from T3.2 was for.

Open and reported both ways until settled: **`k` counts chunks, not documents.** T3.5 asked for
3 and received two chunks of one past incident plus one of another.
`docs/adr/0022-evaluation-harness.md`, `docs/adr/0008:96`, `evals/scenarios/SCHEMA.md:21`,
`docs/adr/0002:19`, `tests/test_artifact_bundle.py:121`

### T4.2 — RCA and remediation scoring *(deterministic half built; the judge is still owed)*
Scores runs against the recorded bundles. Must report remediation-class accuracy **broken
out by fault class**, never only in aggregate.

ADR-0022 settles the label ambiguity T3.5 measured: **fault class is scored on which fix
actually works**, which for `dependency_latency` was measured in ADR-0008 - Pumba binds to the
container present, so a restart durably clears the delay while there is no configuration to
revert. The losing reading is not silently wrong: a `class_dispute` register names documented
near-misses, and disputed misses are counted as misses *and* broken out under the per-class
table.

**`unknown` is an abstention, not a wrong answer** - excluded from accuracy and reported as
coverage, with coverage and accuracy never quoted apart. Two of the five stored verdicts are
`unknown`.

Reported separately and never averaged in: flagged verdicts, specialists that failed alone
(**currently zero observations** across every stored trajectory), contradiction-checker firings
(**two live firings, two false positives, zero true positives**), and budget exhaustion with the
bound that bit named.

Triage is scored on blast-radius recall against `alerts_over_window` with `began_after_revert`
entries excluded; **recall and precision are reported as a pair and never combined**, because
ADR-0017's directed-under-reach hypothesis rides on recall alone. `start_from` is reported as
entry-point distance and is not scored as culprit accuracy.

The judge decisions from ADR-0020 §1 govern unchanged, and ADR-0022 adds what it is asked:
root-cause agreement at three levels, dead ends closed, and traps taken - **never the
`fault_class` label**, which would be ADR-0008's fifth axis by construction. **The judge is not
built.** What is built is everything deterministic, plus the first dev sweep it will eventually
be pointed at.

**The leak guard turned out to be two guards.** Its first live refusal took run 3's whole
narrative over a sentence containing no banned word: `default` contains `fault`, on a scenario
whose subject is a Redis port that is not the default one. Diagnosed before anything moved -
`BANNED_VOCABULARY` was built for the **change tool**, whose text is rendered from the injector's
own model, so any of that vocabulary appearing there is evidence the rendering leaked and a
substring match is right. The scribe composes prose from validated findings and cannot see that
model, so the same string proves nothing. Recorded in ADR-0019's leak-boundary section: terms
that reveal the harness stay banned everywhere (`HARNESS_VOCABULARY`, including the four class
labels, which are the answer key); ordinary incident vocabulary is banned only where its
appearance is evidence of leakage (`PROSE_VOCABULARY` - one word, `fault`). The narrative guard
matches on boundaries, **asymmetrically**: nothing may precede a term, which is what makes
`default` safe, but inflections may follow one, because a strict tail lets `scenarios` and
`rehearsed` through. The change-tool guard is byte-for-byte unchanged and its `KNOWN_LEAKING_FAULTS`
pin still holds.

**`narrative_refused` is a fifth reported-separately category.** Run 3 produced a correct verdict,
exited 0, and wrote no narrative, and the scored report said nothing about it - so a judge would
have had nothing to score and no way to tell that from an oversight. Printed at zero like the
other four. The four categories are also **disjoint** now: a budget-exhaustion flag was being
counted both as `flagged` and as `budget_exhausted`, which double-counted one run in the sweep.

**The first dev sweep has run** (`evals/runs/SWEEP-2026-08-26.md`): seven scenarios, one scored
run each, **one pipeline stamp across all seven**, 259,299 tokens and **$2.92** against a $3.85
budget. Coverage 7/7, zero abstentions.

Two things the per-class table shows that neither aggregate does. **`bad_config` is behaving as a
default** - returned for five of seven, right on both that are `bad_config` and wrong on all three
that are not, so 4/7 fault-class accuracy describes a different system than it sounds like. And
**the 6/7 class-of-fix figure is inflated by label collinearity**: `resource_exhaustion` and
`bad_config` share `config_revert`, so both resource-exhaustion runs got the fix right *while
getting the fault class wrong*. Per class: `bad_config` 2/2, `bad_deploy` 2/2,
`resource_exhaustion` **0/2**, `dependency_latency` 0/1, `scale` no scenario.

Triage over seven: recall mean **0.94**, precision mean **0.56**, 19 unmeasured edges crossed.
**ADR-0017's under-reach number now exists at n=7** and points at one specific pair -
`frauddetectionservice` and `quoteservice`, missed on both cart-rooted scenarios and nowhere else.

`cart-dependency-latency` reproduced T3.5's disputed miss **exactly**, on an independent run: same
two wrong labels, same reasoning shape. One observation was an anecdote; two is a pattern.

### T4.12 — silence is evidence: the evidence-class experiment *(built; result negative, stamp not recommended)*
The experiment T4.11 named. **contract not written.** One addition to `PLANNER_SYSTEM` teaching
the consequence ADR-0019's empty-is-not-error rule implies - an empty stream is silence, not a
query to retry - and demoting the dispatch-count prior in the same breath. Stamp
`53fafe9c12bc` -> `bf7605651ef2`; budget held at T4.7's so **the prompt is the only delta against
dev sweep 3**, which is the baseline. Prediction registered in the branch's first commit per
T4.8's precedent (`evals/runs/PREREGISTRATION-2026-08-27-evidence.md`). $3.57 agent + $0.29 judge
(`evals/runs/SWEEP-2026-08-27-evidence.md`).

**The prediction hit and the mechanism was confirmed on the trajectory.**
`product-catalog-flag-failure` answered `bad_config` correctly at **high** confidence, judge
`same_mechanism`, all four traps avoided - the first time it has answered since S1's different
stamp. The trajectory shows the registered mechanism executed: logs at the failing service came
back **empty at seq 6**, it did **not** re-issue them (T4.11 re-issued the identical query), it
changed vantage across four services, reached **`change_history` at `featureflagservice`** - a
dispatch no T4.11 repeat ever made - and called **`trace_query`**, never called once in any T4.11
repeat. Falsifier 3, registered as the outcome most likely to be misread as a win, did not fire.

**And the instruction is net harmful: coverage 6/7 -> 4/7.** Three registered must-not-regress
scenarios fell to abstention - `cart-bad-image-tag`, `cart-redis-misconfig`, `shipping-wrong-image`.
Accuracy-of-answered held at 4/4 and triage was flat (0.91 -> 0.92 recall), so **no run returned a
wrong class**; every regression is answer -> abstention.

**The column that predicts the outcome is dispatches at the service whose failure is the fault.**
Three regressions: 3->0, 4->1, 3->0. Four non-regressions: 2->2, 3->5, 4->4, and 6->3 on the one
scenario where dispatching away is correct. **Every regression is a target-dispatch collapse and
no scenario whose target dispatches held regressed.** The regressed runs localized the locus and
failed to establish the mechanism, saying so themselves. `cart-redis-misconfig` spent nine
dispatches on checkoutservice x5, paymentservice x2, currencyservice x2 and cartservice x1 - and
T4.10 measured that scenario answering **6/6** under the byte-identical budget, so this is not
plausibly its variance.

**Primary endpoint, registered as behavioural rather than coverage: failed, and improved.**
Re-issues after silence 4-in-3-runs -> 2-in-2-runs, both survivors bare same-window PromQL
re-asks; **2 -> 0 on the targeted scenario**. `trace_query` adoption rose 3/7 -> 5/7 while total
tool calls fell 58 -> 50.

**The `bad_config` per-class row reads "no change" in both sweeps** - 1/1 answered, 1 abstained -
while its two scenarios swapped places. The house rule that an aggregate needs its per-class table
was not enough here; only the per-scenario row shows it.

**Outcome: the instruction was reverted and the stamp returned to `53fafe9c12bc`.** The
experiment's result was adopted as registered - it buys one scenario and sells three, which the
pre-registration had said in advance would not be worth the stamp. Everything else is kept: the
pre-registration, all seven run directories, the sweep report, ADR-0023 and the re-issue analyser.
`bf7605651ef2` survives as `SWEEP_4_DIGEST` and in the sweep record, because a rejected pipeline is
still a pipeline this repository ran and the freeze guard's lineage check has to place it.

**Run at T4.14, and it worked - see above.** The formulation below became `1b0e7cbb4c47`.

**Next candidate experiment - the mechanism decomposed by the regressions.** The instruction taught
**switching vantage** and never taught **returning**: having moved outward from a silent stream,
nothing brought the planner back to the service it had already localized, and the failing-service
dispatch count collapsed 3->0, 4->1, 3->0 on exactly the three regressions. The next formulation
separates the two: **silence at a service changes the evidence CLASS, not the SUBJECT - keep
dispatching at the service you localized, with tools whose streams are not silent.** That keeps
what the winning trajectory needed at seq 6 and removes what emptied `cartservice` of dispatches.
Separate stamp, separate sweep, with the same pre-registration discipline - and the registered
endpoint should be the failing-service dispatch count, which is the thing S4 showed actually
predicts the outcome.

ADR-0023 fell out of this being the first prompt change to land after a holdout was frozen: a
freeze manifest is a historical record, so its guard checks completeness and known lineage rather
than agreement with HEAD, and the holdout figures now carry a note that they describe a superseded
pipeline.

### T4.11 — the abstention path, repeated *(built)*
The complement to T4.10. **contract not written.** Five repeats of `product-catalog-flag-failure`
under the byte-identical T4.10 configuration - stamp `prompts:53fafe9c12bc`, `changes` 8/others 4 -
so the two experiments differ only in scenario. Declared and frozen before the first run; one
discard (529 mid-run, exit 4), no replacement. $1.75 agent + $0.15 judge
(`evals/runs/VARIANCE-2026-08-27-abstention.md`).

**`email-wrong-image` stays untested.** It is holdout, and five development repeats of a holdout
scenario is repeated holdout use wearing a costume. `product-catalog-flag-failure` is the dev-legal
instrument for the same behaviour.

**The abstention is 5/5 stable** (four repeats plus T4.7's byte-identical archive row): every run
reached `unknown`/`none` at low confidence, and **no repeat answered** - so the hoped-for
"trajectory that answered" does not exist and none was manufactured.

**But the stability has a mechanical cause outside the agent's judgement.** Every plan in every
repeat dispatched `logs:productcatalogservice`. That stream is empty by construction - ADR-0005
published it at **0 lines/hour**, and the scenario file records the same fact in a comment. The
agent read the empty result as a *label-syntax defect* ("both attempts used the hyphenated form"),
re-issued it as "corrected logs pending", and **never called `trace_query` in any repeat** - while
four of the scenario's eight `expected_evidence` items, including both discriminators, sit on
traces. The planner prompt supplies the prior that invites the skip: *"traces in two"* of ten. The
one run that ever solved this scenario (S1, different stamp, not a repeat) queried **frontend**
logs and got `Error: 13 INTERNAL: Error: ProductCatalogService Fail Feature Flag Enabled` in one
call. The difference between solve and abstention is which service's logs were queried.

**Dispersion is *lower* on the abstention path than on the answering path**, on every measure:
round-1 breadth spread **1** (4,4,5,5) against T4.10's **8** (2.6x); tokens 1.35x against 1.9x;
zero exhaustions against one. An agent that cannot reach the evidence does not flail - it converges
cheaply on the same wrong plan. Low dispersion here is a symptom of a systematic blocker, not of
calibration.

**What it forces on S2's `4/7` dev coverage figure:** the number is reproducible - it will not
drift to `5/7` on a re-run - but it must **not** be glossed as "answers 4, correctly declines 3".
At least one of the three non-answers is forced by evidence reachability, not by calibrated
refusal to guess. The other two non-answers have not been analysed this way; one of three is
explained, and that is the whole claim. Nothing product-side changed and the stamp did not move.

**Next candidate experiment (not run here):** dispatch `traces` on this scenario and measure
whether it converts the abstention to an answer. It is a stamp-moving change - either a planner
prompt that stops treating traces as the rare specialist, or a tool layer that distinguishes
"stream has no lines" from "your selector was wrong". Both were out of T4.11's scope.

### T4.10 — variance, measured at last *(built)*
The experiment T4.9 named. **contract not written.** Five repeats of `cart-redis-misconfig`
holding scenario, stamp (`prompts:53fafe9c12bc`) and budget (`changes` 8, others 4) constant -
**the first measurement in this project where all three are fixed.** Declared and committed before
the first run; five attempts was the experiment and a discard would not have been replaced. Zero
discards. $3.01 agent + $0.17 judged (`evals/runs/VARIANCE-2026-08-27.md`).

**One distinct verdict from five identical configurations.** All five `bad_config`/`config_revert`,
all correct, all judged `same_mechanism`. A sixth byte-identical row already existed in the archive
(T4.7's sweep row), making it **six for six**.

**Target-in-plan was stable; breadth was not.** `cartservice` entered the plan in all five - four
times in round 1, once in round 2 - while round-1 breadth ran **5, 7, 8, 8, 13** (2.6x). Reaching
the broken service is not a by-product of planning widely. This answers T4.9's cause-versus-symptom
test for **one** scenario: target-in-plan *can* be stable while breadth is not. T4.8's
`email-wrong-image`, where it was not stable, remains untested under repeats.

**What varied:** tokens 36,430-68,493 (1.9x), cost $0.48-$0.70, rounds used (1 once, 2 four
times), confidence (high x4, medium x1), one exhaustion of five. **The widest plan was the
cheapest run** - 13 dispatches, exhausted `metrics` in round 1, no follow-up, 47% fewer tokens
than a run that planned 8 and used both rounds. And the **least stable thing measured was
dead-end coverage**: the judge found 3 to 7 closed and 2 to 6 missed on five runs that agreed
entirely on the answer, which `ARTIFACTS.md` calls the most useful part of a record.

Three corrections it forces on earlier figures: verdicts where a scenario answers look stable and
are unlikely to be lucky draws (measured for one of ten scenarios); **cost figures are single
draws with a ~1.9x spread and must never be quoted as points**, which puts the difference between
two sweep totals well inside one scenario's repeat spread; and anything read off a single run's
plan is one sample from a 2.6x spread - T4.8's finding stands as reported, at the n it was
reported with.

### T4.9 — planner allocation, read from the archive *(analysis only; nothing product-side changed)*
No model calls, no injections. **contract not written.** Every stored investigation, one row each
(`docs/evidence/t4.9-allocation/README.md`): 39 trajectories, **36 carry a plan**, 33 produced a
verdict. Thirteen predate the run manifest and their scenario is inferred from the injector's
`change_records`, marked as such.

The question came from a run pair on `email-wrong-image`: same scenario, same stamp, **12 planned
round-1 dispatches against 3**.

**Breadth is variable and unevenly so.** Round-1 dispatches range 3 to 13 across the archive. Per
scenario at n>=2: `frauddetection-memory-squeeze` planned exactly three every time (spread 0);
`email-wrong-image` planned three and twelve (spread 9). **These are not repeats** - they differ in
stamp, bound and the day's incident - so every spread is an upper bound on variance, not a
measurement of it.

**Breadth does not predict outcome.** Narrowest band (3-4, n=20) answered 14/20; widest (9-13,
n=8) answered 5/8. Every budget exhaustion lives among the wider plans, and planned breadth
overstates what was queried: 13 planned dispatches yielded 4 distinct services queried.

**What travels with outcome is whether the broken service was asked about at all.** Target planned
in any round: **22/25 answered**. Never planned: **1/8**. Excluding the three
`product-catalog-flag-failure` rows whose target `featureflagservice` emits no span metrics and
therefore cannot be planned: **5 of 5 that never planned the target abstained**. Labelled a
correlation - a planner reaching the right service may be one that already understood the incident
- though the mechanism is not mysterious, since a verdict cannot classify evidence nobody gathered.

> **Next candidate experiment, not run here: repeat one scenario several times under one fixed
> configuration.** The archive contains **no two rows holding scenario, stamp and budget
> constant**, so run-to-run variance has never been measured and every spread in T4.9 is
> confounded. Repeats would give the first clean variance figure for planner breadth and would say
> whether "did the plan include the target" is itself stable or is the thing that varies. It needs
> no new machinery - only the harness, one scenario, and several passes.

### T4.8 — the holdout, second entry *(protocol answered; entry run, incomplete)*
**contract not written.**

**The protocol answer is yes**, and ADR-0022 §3.3 did not need stretching. "A holdout run happens
**once per reported result**" - not once ever; the unit is the reported result, and what is
forbidden is running holdout repeatedly for the same one. "Changing anything above and re-running
holdout is a **new experiment** and gets a new manifest" categorises rather than forbids. And the
guard is visibility, not scarcity: the number of holdout runs is a fact worth being unable to hide.

Four checkable conditions separate a new entry from a re-run in costume: the change is validated
on dev first; it is justified by a mechanism rather than by the holdout result; **a prediction is
registered before the run**; and the first entry stands unedited beside the second. The addendum
also states the leakage it does not pretend away - the holdout report is where the confound was
first written down, so a signal read off holdout did influence a configuration choice - and adds a
**numbered ledger** with the note that a third entry needs an argument the addendum does not supply.

**The entry ran 1 of 3.** Two scenarios were discarded to an empty API account before their first
model call and, per the pre-registration, **were not re-run**. There is no judged column: the judge
runs on the same account.

The one scored scenario **falsified the registered prediction, in the way it was written to be
falsifiable**. `email-wrong-image` abstained again **with `changes` unexhausted** - the exact
condition the pre-registration named as disproving the starvation reading.

And the reason is a **third** cause neither hypothesis named. With eight `changes` calls available
the planner used **two**, both on `checkoutservice`, and **never asked about `emailservice`** - the
service its own traces implicated. Entry 1 planned twelve round-1 dispatches including
`emailservice` at #5 and was cut off by the bound; entry 2 planned three and never reached. **Same
scenario, same prompts, same stamp, fourfold difference in planner breadth.** Not starvation, not
the taxonomy instruction: **planner allocation**. n=1.

`docs/adr/0022-evaluation-harness.md`, `evals/runs/HOLDOUT-2026-08-26-entry2.md`,
`evals/runs/HOLDOUT-2026-08-26-entry2-PREREGISTRATION.md`

### T4.7 — the budget confound, separated *(built)*
The manipulation HOLDOUT-2026-08-26.md left open. **contract not written.**

**First, the instrument.** Budget bounds are experiment parameters the stamp does **not** cover,
so two runs with the same `prompts:53fafe9c12bc` and different bounds were different experiments
wearing one stamp. Decision recorded where the stamp's contract lives
(`faultline/agents/stamp.py`): **bounds stay out of the stamp and travel beside it.** Folding
them in would orphan every stamped figure and - decisively - make this very comparison
unexpressible, since raising a bound and re-running is a statement about *the same agent given
more room*. The obligation that creates: the run manifest now records **all four** bounds rather
than the two the CLI takes, and the scored report and every sweep table print the budget beside
the stamp.

**The manipulation**, justified from the stored trajectories rather than picked: every
budget-exhausted run in the record exhausted the *same* bound, and in three of four the target
service's change record was dispatch **five or six** of a plan cut off at four. T3.4c made a
dispatch name one service, which multiplied change-history needs by the blast radius while the
bound stayed where it had been set for a planner that could ask about several at once. Largest
observed plan: 6. **`changes` 4 -> 8**, and only `changes`; `Budget` gained per-specialist
overrides, which does not move the stamp.

**The answer is mixed, and it decomposes** (`evals/runs/SWEEP-2026-08-26-budget.md`). All three
outcomes the question anticipated occurred, one per scenario:

- **Budget owned `ad-memory-squeeze`**: abstained while exhausted on `changes`, answered
  **correctly** with the bound raised.
- **The instruction owns `product-catalog-flag-failure`**: abstained in both sweeps, exhausted on
  nothing in either. It had budget to spare and declined anyway.
- **Neither owns `shipping-wrong-image`**: abstained then answered, exhausted in neither run. At
  n=1 per side, variance and planner re-allocation are indistinguishable.

Starvation was real and is gone: **zero runs exhausted `changes`, against two**. Coverage 4/7 ->
**6/7**, accuracy-of-answered held at 100% (4/4 -> **6/6**), fix 3/4 -> 5/6, judge
same_mechanism 4 -> **6**. The bound moved to the next constraint: two runs exhausted `metrics`
and both still answered. $3.69 + $0.28 judged.

**First variance data at n=2**: four scenarios answered in both sweeps and **all four returned
the identical class**. Not clean repeat variance - one bound differs - but under the same prompts
and contracts, no scenario that produced a class produced a different one.

> ~~**Note for T4.1: the gate is blind to recently-resolved incidents.**~~ **Closed at T4.13.**
> A stranded incident resolved by hand minutes before the sweep sat inside the orchestrator's
> 5-minute settle window; the next scenario's alerts reopened it into `OPEN` and every subsequent
> event joined it, so no `triaging` incident ever appeared and the run was discarded after 900s.
> The gate refused on *non-terminal* incidents; a recently-resolved one was invisible to it and
> captured a new run's alerts just as effectively. The gate now refuses on those too - see
> T4.13 below.
`src/faultline/agents/budget.py`, `src/faultline/agents/stamp.py`,
`src/evalharness/run.py`, `src/evalharness/scoring.py`,
`evals/runs/SWEEP-2026-08-26-budget.md`

### T4.6 — the holdout run *(run; the number this project exists to produce)*
The three runnable holdout scenarios, once each, under ADR-0022 §3.3's protocol.
**contract not written.**

**Freeze first, as its own commit before any scenario ran** (`FREEZE-2026-08-26-holdout.json`),
computed from outside the product because a freeze that asks the thing being frozen whether it
has changed is not a check. Pipeline `prompts:53fafe9c12bc` - S2, the taxonomy-taught
synthesizer. Verified after the run: five of six items byte-identical; the sixth,
`tool_layer.git_sha`, moved by exactly one commit - the freeze commit itself - with no change to
`src/faultline/`. That is a self-reference flaw in the manifest, **recorded not fixed**, because
fixing anything mid-holdout is what the freeze forbids.

**The corpus check that the whole quarantine was for**: `holdout_chunks: 0` over 35 rows and 7
documents, every one dev. These three scenarios had never been run by any agent and no chunk of
any of them has ever been retrievable.

Results in `evals/runs/HOLDOUT-2026-08-26.md`, with the dev tables beside them clearly labelled
dev.

| | holdout | dev sweep 2 |
|---|---|---|
| fault class, of answered | **1/1** | 4/4 |
| coverage | **1/3** | 4/7 |
| class of fix, of answered | **0/1** | 3/4 |
| triage recall / precision | **1.00** / 0.32 | 0.95 / 0.57 |
| judge same_mechanism / different | 1 / 2 | 4 / 3 |
| budget exhausted | 2 of 3 | 2 of 7 |

n is **1 per class and 3 in total**; two of the five labels have no holdout scenario at all.
Nothing here is a rate.

**The strongest single result**: `dependency_latency` was answered correctly on **both** dev and
holdout, by a pipeline whose instruction never named either scenario - and it rests on n=1 per
side.

**Coverage, not accuracy, is where holdout differs.** Everything the agent asserted was right; it
asserted once. **On holdout the abstentions line up exactly with budget exhaustion** - both
exhausted `changes tool calls: 4 of 4` - and **on dev they did not**. At n=3 this cannot separate
"the taxonomy instruction causes abstention" from "the planner spends its changes budget and
leaves the synthesizer nothing to classify from". That needs a run with a larger per-specialist
bound and is not answered anywhere in this repository.

`email-wrong-image` **took all three traps the judge identified** - the most of any run - on the
scenario whose recorded narrative says the logs contain the answer. It spent its whole `changes`
budget and never read them.

Recorded, not fixed: the last scenario's **recovery check failed** (the documented CATALOG
degradation). All three gates passed *before* injection, so every measurement was against a
clean world; the world was repaired afterwards with the documented `docker restart`.
`evals/runs/HOLDOUT-2026-08-26.md`, `evals/runs/FREEZE-2026-08-26-holdout.json`,
`src/evalharness/freeze.py`

### T4.5 — teaching the taxonomy, measured *(built)*
The experiment T4.3 deferred: **28 lines added to `SYNTHESIZER_SYSTEM`, nothing else in any
prompt**, then the same seven dev scenarios re-run through the unchanged harness and re-judged
with the same judge configuration. **contract not written.**

The instruction defines the four classes by **mechanism** - what the service is doing wrong -
and states that a change record is evidence *for* a class and never the class itself. Derived
from what the labels mean, not from the scenarios: a test asserts no scenario id, service name or
other answer key appears in any prompt, because a prompt fitted to these scenarios is ADR-0008
axis 1 in one sentence.

**The stamp moved, which is the point**: `prompts:59bf438b2a96` -> `prompts:53fafe9c12bc`.
T4.3's pin fired on the change and now records both, so neither sweep can be mistaken for the
other.

Results in `evals/runs/SWEEP-2026-08-26-taxonomy.md`, beside sweep 1 throughout.

- **Fault class moved on both target classes.** `dependency_latency` 0/1 -> 1/1;
  `resource_exhaustion` 0/2 -> 1/1 answered. Both were returned for the first time, and **no run
  in either sweep answered one of these classes and got it wrong**.
- **Two previously-correct scenarios regressed - to abstention, not to a wrong answer.**
  `product-catalog-flag-failure` and `shipping-wrong-image` returned `unknown`. It is not budget
  exhaustion: one abstention was exhausted, two were not, and one exhausted run did not abstain.
- **The two-value classifier became a real one.** Sweep 1 returned `bad_config` and `bad_deploy`
  and never a symptom class; sweep 2 returned all four classes plus `unknown`.

**The classifier stopped being wrong (4/7 -> 4/4 of answered) and started declining (coverage
7/7 -> 4/7).** Whether that trade is an improvement is not settled by this data, and the file
says so: two abstentions replaced correct answers, and n is 1 per scenario. Triage was unchanged
(recall 0.94 -> 0.95, precision 0.56 -> 0.57), which is the closest thing here to a control.

The judge agrees from the prose: **the three `different` verdicts are exactly the three
abstentions**. That also removes T4.4's largest caveat - the judge had never used a level other
than `same_mechanism`, so it had not been shown to discriminate. It has now, on exactly the runs
a separate measurement calls different.

Two defects the sweep found, both fixed, neither touching the stamp. **A lost update**: the
runner held an incident loaded before the run and `save` upserted its stale episodes over
`resolved_at` values the orchestrator had written meanwhile, stranding the incident and making
the gate refuse two scenarios - the runner now uses a narrow write. **Retry meeting terminal
states**: T4.3's retry fired on a 529 that landed after the run had done work, and a run that
did work leaves the incident `FAILED`, which is terminal - so the retry could only be refused,
twice. Retry is now limited to a failed start.
`src/faultline/agents/roles.py`, `src/faultline/orchestrator/store.py`,
`src/evalharness/run.py`, `evals/runs/SWEEP-2026-08-26-taxonomy.md`,
`docs/evidence/t4.5-taxonomy/prompt-addition.md`

### T4.4 — the judge *(built)*
Narrative scoring, per ADR-0022 §1.3. **The judge lives in `evalharness` and never in the
product.** `faultline-judge` reads runs already on disk - no world, no injections - compares each
narrative against its scenario's recorded `incident.md`, and writes the answers into the run
manifest beside the deterministic score. **contract not written**, same convention as T4.1-T4.3.

**No default model, and unset refuses.** ADR-0020 §1's argument taken literally: the obvious
default is the agent's own model, and taking it silently is how one model comes to grade its own
output. `AgentSettings.judge_model` is marked superseded and no longer read - keeping the judge's
configuration out of the product's settings object is the stronger form of "inherits nothing".

**Lineage is checked at eval time, at the vendor-family level.** Marked: reading ADR-0020's "same
instance, prompt, or tuning lineage" as model-id equality would clear `claude-haiku-4-5` grading
`claude-opus-5`, which is two models from one lab sharing a pretraining lineage. A violation
**refuses by default** and must be opted into by name, and then rides on every figure - ADR-0008's
"invalid rather than annotated" exists to stop a defence failing *silently*, and a violation that
must be requested and is then stamped is not silent. **This project holds Anthropic credentials
only, so every available judge is a violation**; the first live judging carries the label rather
than waiting for a provider this repository cannot test against.

**A contamination defect was caught by the tests before any live call.** Every recorded
`incident.md` opens with YAML front matter carrying `fault_class` **and**
`origin: scenario:<id>` - the label ADR-0022 says the judge is never told, and the scenario id
ADR-0019 bans separately as the answer key. Passing the file verbatim would have contaminated
every judged figure this project ever produced, invisibly. The front matter is stripped; the prose
is passed intact.

The seven sweep narratives judged for **$0.27** (`docs/evidence/t4.4-judge/`): **7/7
`same_mechanism`**, one trap taken, dead ends closed-versus-missed ranging 8/4 down to 4/6.
Read beside the deterministic 4/7 fault class, **these are the same finding twice**: the judge
grades mechanism and never sees a label, the scorer grades labels, and together they say the gap
is taxonomy rather than comprehension - T4.3's conclusion from the verdicts, reached independently
from the prose by a different model. **7/7 is not a headline**: the judge never used `adjacent` or
`different`, so it has not been shown to discriminate, and the supportable claim is that it found
no narrative naming the wrong mechanism.

The run whose narrative the leak guard refused was **reported, not judged, not averaged**, and no
model call was made for it.
`src/evalharness/judge.py`, `src/evalharness/judge_cli.py`,
`docs/evidence/t4.4-judge/README.md`, `evals/runs/SWEEP-2026-08-26.md`

### T4.3 — the decisions the sweep forced *(built)*
Three decisions, each recorded where it belongs. **contract not written** - a follow-on to T4.2.

**The contradiction checker is retired** (ADR-0021 addendum), on the condition ADR-0022 set in
advance. Live ledger: **0 true positives, 4 false positives** - and the one historical true
positive does not survive scrutiny either, because T3.4b diagnosed its cause as a context-assembly
defect and fixed it, so the verdict that check caught was accurate about what it had been shown.
Narrowing was rejected because each of the four false positives had a *different* cause and each
fix bought exactly one round: parsing prose for intent is a small language model made of regexes,
with none of the calibration and all of the confidence. The module is kept unwired with its ledger
and a stated bar for re-admission: **a mechanism that does not parse prose** - the obvious shape
being a structured `unqueried: [{specialist, service}]` field beside `open_questions`, which turns
the check into a set comparison.

**The dispute register records disagreeing readings, not a silent tiebreak** (ADR-0022 addendum).
With one entry the two possible definitions were indistinguishable; the sweep's four observations
separated them. A register defined by the fix tiebreak records `dependency_latency` twice and is
**blind to both `resource_exhaustion` rows**, because both readings there give `config_revert` -
so it would go quiet exactly where the labels are least separable. The finding changes shape with
the definition: "wrong on `resource_exhaustion`, 0/2" versus **"reads every change-mediated fault
as `bad_config`"**, and the data says the second. Across seven scenarios the agent returned
exactly two values - `bad_deploy` where the change touched an image, `bad_config` everywhere else
- and never a symptom class. That one rule predicts all seven rows, including the four it got
right. Both `resource_exhaustion` verdicts identify the mechanism *correctly* before classifying
on the change. The register now holds four entries; **every disputed miss is still a miss** and
the fault-class figure stays 4/7.

**Bounded retry on transient provider failures** (`evalharness.run`). Transient statuses only -
529, 429, 5xx, connection and timeout errors - three attempts after the first at 20s/60s/120s,
every attempt recorded in the run manifest with its delay, and a run that exhausts them discards
exactly as before. **A 400 is deliberately not retried**: `invalid_request_error` covers both a
malformed request and an exhausted credit balance, and T4.1's second run died on the latter.
Retrying is cheap because the fault is still injected and the incident still exists, so only the
investigation repeats; the sweep paid an injection, a correlation wait, a revert and ten minutes
for one 529.

**The stamp does not move for any of the three.** `runtime_version` is the package version plus a
digest over the role system prompts and the contract schemas. Retirement removes a call site,
the register is harness-side scoring, and retry is harness-side transport - none touches a prompt
or a contract. `prompts:59bf438b2a96` is pinned by a test, so the sweep's rows stay comparable to
every run made after this task.

Not decided here: **whether the prompt should teach the symptom/change distinction.** That is a
prompt change, so it moves the stamp and needs its own before/after comparison - CLAUDE.md's
eval-before-opinion rule, applied to the first finding this harness has produced that suggests one.
`docs/adr/0021-verdict-grounding-and-two-ended-truncation.md`,
`docs/adr/0022-evaluation-harness.md`, `src/evalharness/run.py`,
`src/evalharness/scoring.py`, `src/faultline/agents/grounding.py`
`docs/adr/0022-evaluation-harness.md`, `docs/adr/0008:121`, `docs/adr/0009:12`

---

## Phase 5 onward

### T5.3 — demo *(built)*
**Scope note: what was built is not what this entry described.** The entry above was written
from the bundle-rendering side - "renders bundles for a human audience; needs `title` and the
alert summary before anyone reads a scenario file." What T5.3 actually delivers is `make demo`:
one narrated **live run** of the whole pipeline end to end. The two overlap only in that both
serve a human reader. **The bundle-rendering half was done separately at T5.3b, which closes
this entry's original scope** - see below.

`make demo` -> `faultline-demo`, a wrapper over the same `faultline-eval` the sweeps use. Same
baseline gate, same revert, same recovery check, same run directory. It narrates the arc a
first-time viewer needs - what fired, what the orchestrator correlated, what the planner
dispatched, what the specialists asked, the verdict, the narrative, the revert, the confirmed
recovery - from `@@EVENT` progress lines the harness emits under `--progress-json`, rather than
by scraping prose, so rewording a print statement cannot silently break the narration.

**No product code and the stamp does not move**: everything is in `src/evalharness/`, and
`src/faultline/` is byte-identical to main.

The demo run is marked `demo` in its manifest and **excluded from every aggregate** by
`counts_toward_aggregates`, one predicate rather than a convention, wired into the judge's run
enumeration - which is the only place runs are enumerated - and pinned by three tests. Naming a
demo run explicitly still reaches it; the rule is that no aggregate counts it, not that nobody
may look at it.

Scenario: **`cart-redis-misconfig`**, chosen for a story a stranger can follow - seven services
alert, the blast radius narrows to one hop, **the alerting service is not the broken one**, and
the answer is a change record rather than an inference - and because it is the only scenario
whose repeat behaviour has been measured (T4.10: 6/6 correct under a fixed configuration).

**Two defects the demo found by being run, both fixed in T5.3:**

1. A plain `uv sync` drops the optional `agents` extra, so the model client is missing and an
   investigation dies on `ModuleNotFoundError` **after** a fault has been injected and an
   incident correlated. The preflight now checks it and refuses with the fix. Cost of learning
   this: one discarded run, recorded not deleted.
2. **The demo ran the default `changes` bound of 4 while every claim about its scenario was
   measured at 8.** It reproduced T4.7's starvation exactly - the planner asked for five
   `changes` dispatches, exhausted the bound at 4/4, never reached the failing service's change
   history, and abstained on a scenario watched to answer correctly six times out of six. A new
   entry point had not inherited the configuration. The bound is now explicit in
   `demo.CHANGES_BOUND` with the reasoning next to it, and the intro states the configuration
   the viewer is watching. **A demo must run the configuration its claim rests on**; choosing a
   scenario on evidence gathered at one budget and demonstrating it at another is a different
   experiment wearing the first one's reputation.

**And one finding about the exclusion rule, on its first use.** The recorded demo run is
byte-identical in configuration to T4.10's five repeats - same stamp `53fafe9c12bc`, same four
bounds - and it **abstained**, where those five and S3's row all answered correctly. The incident
was the same shape as every other run of this scenario (9 alerted, 12 predicted, recall 0.78), so
the world had not drifted; the planner exhausted `metrics` at 4/4 and never spent a `changes`
dispatch on `cartservice`, which is where the answer was.

**The failure mode is T4.12's next candidate, seen at the reverted stamp.** The demo run
localized to `cartservice` and then never dispatched `changes` there - which is precisely what
that entry names: *keep dispatching at the service you localized.* This matters for how T4.12's
regressions are read. Those three could have been read as the rejected instruction *creating* a
tendency to abandon the localized service; this run shows the same shape at `53fafe9c12bc`, with
no such instruction in the prompt. **The tendency pre-exists the instruction.** Stated at its
honest weight: one occurrence in seven runs at baseline, against three of seven under the
instruction - which is consistent with amplification rather than creation, and is not enough
observations to claim it.

That is also a legitimate seventh observation of a configuration this repository has published a
6/6 on - and `counts_toward_aggregates` excludes it. **The rule is still right**: demos are re-run to
be watched and on whichever scenario tells the best story, so letting them into aggregates would
weight every figure toward watchability. But its first application hid a real datum, which is
worth knowing about the rule rather than discovering later. The resolution taken here is to keep
the exclusion and **record the observation beside the figure it bears on** rather than inside it:
T4.10's 6/6 stands as published and unamended, and README.md states the demo-inclusive record as
6 of 7 where it describes the demo. A figure and an observation it is not allowed to absorb can
coexist as long as both are visible.

`docs/adr/0009:12`, `src/evalharness/rehearse.py:739`

### T4.15 — the holdout, entry three *(argued, then run)*
The protocol question first. The T4.8 addendum said a third entry needs an argument it does not
supply; **ADR-0022 now carries that argument as its next ledger row**, and the answer is yes with
condition 2 met **under strain**. What came from dev: the quantity the instruction optimises was
defined and measured at T4.12 from three dev regressions, the wording was selected on dev, the
first formulation was rejected on dev, and T5.3's demo saw the tendency at baseline. What came
from holdout: **entry 2 is where the failure mode was first named** - "the plan simply did not
investigate the implicated service" - a day before T4.12 measured it. T4.8's leak was holdout
making a confound salient while the mechanism was independently visible on dev beforehand; this
leak is more direct, because here holdout was chronologically first. Paid by labelling rather than
exclusion: **`email-wrong-image`'s row is corroborative, not confirmatory**, and dropping it was
considered and rejected because excluding the hardest case to protect a number is worse than
running it and saying what it is worth.

**The T7.1 argument was weighed and declined.** A re-record does close comparability with entries
1 and 2 permanently, and that is not a protocol argument: a deadline from another task's schedule
says nothing about whether this is a new experiment or a re-run in costume, and counting it would
establish that any impending change unlocks the holdout set.

**The result: 3 of 3 answered, 3 of 3 correct, 3 of 3 judged `same_mechanism`, zero budget
exhaustions, triage recall 1.00 on all three** (`evals/runs/HOLDOUT-2026-08-27-entry3.md`). Both of
entry 1's starvation abstentions resolved. Every registered prediction hit and neither falsifier
fired - including the behavioural endpoint for the hard case: `emailservice` was dispatched on
three times where entry 2 sent zero. $1.68 agent + $0.11 judge.

**What it does not license.** n=3, one run each, no interval; `bad_config` has n=0 on holdout and
always has; the fix class is 2/3, with `productcatalog-dependency-latency` making the same
`config_revert`-for-`restart` miss it made in entry 1 and that `cart-dependency-latency` makes on
dev in every sweep, unmoved by three stamps.

**One operational finding, recorded because it cost a batch.** `email-wrong-image`'s revert
restored the image but **not** `checkoutservice`, which held broken state after `emailservice` was
recreated beneath it; `accountingservice` separately stopped reconnecting to Kafka and claimed no
message for four hours. The baseline gate refused the next two scenarios rather than measuring a
sick world - T4.13's gate doing its job one task after being built, and the reason this entry has
three clean rows instead of one clean row and two contaminated ones. **Both services are the same
failure class CATALOG.md documents for the maintenance path**, arriving through a different door:
a scenario's own revert rather than a maintenance restart. The documented repair applied unchanged.
The two refused scenarios were then run as **firsts, not re-runs** - a gate refusal is upstream of
any exposure, and this repository's own accounting already counts entry 2's pre-call discards as
zero exposures.

### T4.14 — return to the locus *(built; stamp KEPT)*
The refined formulation this plan carried after T4.12, run before T7.1 because both baselines -
S3 and S4 - were measured against the current world and neither survives a re-record.
**contract not written.** Pre-registered in the branch's first commit
(`evals/runs/PREREGISTRATION-2026-08-27-locus.md`); results in
`evals/runs/SWEEP-2026-08-27-locus.md`. Stamp `53fafe9c12bc` -> **`1b0e7cbb4c47`**, budget
unchanged at `changes` 8 so both baselines stay live comparisons. $3.83 agent + $0.26 judge.

**Every registered condition met, and the stamp is kept.** Coverage **7/7**, fault class **7/7**,
class of fix 6/7 - **the first sweep in this repository where every dev scenario was answered and
every answer was right** - against S3's 6/7 and S4's 4/7. It is also the cheapest in tool calls,
**47** against S3's 58, so this is not "dispatch more and hope".

**The primary endpoint moved with the outcome.** Failing-service dispatches, registered ahead of
coverage because S4 measured it as the thing that predicts the result: total **15 -> 26**, and
**zero scenarios collapsed to <=1** against S4's three. Distinct evidence classes at the failing
service - the second half of the instruction stated as a number - went 20 -> 17 -> **25**, with
four scenarios reaching one more class at their target than they ever had. All three S4
regressions recovered to 3 dispatches each, and S4's product-catalog gain was retained: the
"improve on **both** baselines" condition T4.12 failed.

**Falsifier 4 - coverage rising with the dispatch counts unmoved, registered as the outcome most
likely to be misread as a win - did not fire**, and not marginally: the counts moved on five of
seven scenarios and the endpoint and the outcome moved on the same rows.

**What did not improve, recorded beside it.** Triage was flat (0.91 -> 0.90 recall), which is the
control - the instruction changed how dispatches are spent, not what the blast radius looks like.
`cart-bad-image-tag` returned the correct class and fix while the judge scored its narrative
`different` with its weakest dead-end row of any sweep, which is a right answer with a narrative
the judge does not follow. `cart-dependency-latency` still returns `config_revert` for a
network-path fix, unmoved by this stamp. Re-issues held at S4's 2 rather than reaching zero, and
one of them is `product-catalog-flag-failure` re-asking a silent stream at its own target - the
one place the sweep disobeys its own instruction. Cost rose to $3.83, the highest of the three.

**Consequence for the holdout figures:** HEAD is `1b0e7cbb4c47`, so the holdout numbers describe a
superseded pipeline again. ADR-0023's reporting obligation is discharged in RESULTS.md and
README.md rather than asserted in a test - which is the case that ADR was written for, now
occurring a second time and resolving the other way from T4.12.

### T4.13 — the gate learns about the settle window *(built; closes T4.7's recorded note)*
The blind spot T4.7 measured and recorded rather than fixed. **Harness-side only**: the stamp
does not move and `src/faultline/` is untouched - the orchestrator's settle window was already
public on `OrchestratorSettings`, so nothing needed exposing.

The baseline gate now refuses when any incident's `resolved_at` is within the settle window of
now, naming **which incident, when it resolved, and how many seconds until the window clears** -
a refusal a person can act on by waiting, which is exactly what T4.7 did by hand. Terminal
incidents pass the old open-incident check while remaining able to swallow a new run's alerts,
which is the whole of the defect.

**The window is read from `OrchestratorSettings`, not copied.** ADR-0016 calls it a placeholder
to be replaced by measurement, so a constant in the gate would go stale the moment it is
replaced. A test pins that the gate follows the environment variable a deployment would set.

**One thing the change had to be careful about**, now documented at the call site and pinned by a
test: `confirm_recovery` calls the gate *without* the incident arguments, deliberately. After a
revert this run's own incident has just resolved and is inside the window by construction, so a
recovery check that applied this refusal would fail every run against the fault it had just
fixed. Recovery asks whether the world came back; the baseline gate asks whether it is safe to
inject. Only the second one owns this question.

The gate's two known-good-world exemptions - `frontend-proxy` at zero, and the post-restart p95
hazard reused from the recorder rather than restated - are untouched and still pinned.

### T5.3b — the bundles, rendered for people *(built; closes T5.3's original scope)*
The half of T5.3 the demo did not do. `faultline-render` turns a recorded bundle into a
Markdown page: the narrative's own title, the scenario front matter, an alert timeline
summarised from `alerts_over_window`, what the capture set holds with the query behind each
file, a short log excerpt, and `incident.md` inline. All twelve bundles plus an index in
`docs/bundles/`.

**Deterministic by construction** - nothing reads the clock, the filesystem's ordering or the
environment; every collection is sorted; times print as offsets from the injection rather than
as local times; the render carries no provenance of its own. Pinned two ways: render-twice
byte-equality, and a test that makes `datetime.now` raise during a render. No model calls and no
live services, so the conftest guards have nothing to intercept. Nothing is written inside the
capture trees, and the pre-commit exclusion lists are untouched.

**Four things the bundles taught the renderer**, each now pinned by a test:

1. **`docs/bundles/` is not in the captured-evidence exclusion**, so `trailing-whitespace` and
   `end-of-file-fixer` rewrite whatever is left there. A renderer emitting a trailing space
   would be corrected on commit and then disagree with its own output forever. Every line is
   stripped and the file ends in exactly one newline.
2. **Captured logs are hostile by construction.** Two committed captures carry ANSI escape
   sequences - 25 in `cart-bad-image-tag`, 5 in `cart-redis-misconfig` - which ADR-0019
   measured rather than supposed. They are stripped before any log line reaches a page.
3. **The two INVALID bundles carry `null` for `seconds_to_alert` and `t_alert_firing`.** A page
   rendering those as `T+0m00s` would claim an instant page for a fault that never paged; they
   render as "never paged" under the INVALID banner.
4. **A narrative keeps its own clock, and it is not the manifest's.** Checked across every
   bundle with a narrative offset: `cart-redis-misconfig` and `shipping-wrong-image` measure
   `T+` from the page, `ad-memory-squeeze` from the injection, and two match neither - they are
   counting from something in the logs. The manifest records only `t_inject`, so a page's table
   and the narrative below it can give the same moment two offsets. **Not fixed in the
   narratives**, which are recorded artifacts and corpus material; each page says so instead and
   points at the absolute timestamps as the tiebreak.

The index states in one line why rendering holdout narratives for people is not a contamination
event: ADR-0008's quarantine governs the retrieval corpus and the agent, both refused
structurally, and neither is touched by a person reading a narrative that has been committed
since it was recorded.

### T6.4 — knowledge corpus
Commits to ≥50 documents in the retrieval store.
`docs/adr/0002:8`

### T6.8 — security pass
Completes the threat model. Prompt injection via log lines is the core thesis; defences
built at T2.6 are attacked here.
`docs/THREAT-MODEL.md:3`, `docs/THREAT-MODEL.md:19`

### T7.0 — four more fault classes
Extends the injector from four classes to eight, and extends the scenario schema's
`fault_class` enum with it.
`evals/scenarios/SCHEMA.md:10`, `docs/adr/0010:23`, `src/injector/faults.py:1`

### T7.1 — grow the catalog past 30
Every fault class gets holdout representation. `checkout-currency-misconfig` is held in
the injector, unused, as the spare for this. Until then, three holdout scenarios is an
anecdote and will not be headlined as anything else.
`docs/adr/0008:74`, `docs/adr/0008:161`, `evals/scenarios/SPLIT.md:50`, `src/injector/catalog.py:282`

**Scope note: this entry and the work done under the T7.1 name are two different things.**
The entry above is catalog growth. What the tree has been calling "T7.1" everywhere else -
`CATALOG.md`'s queue table, `ARTIFACTS.md`, ADR-0019, `RESULTS.md`'s open questions, and a test
docstring - is the **digest-locked change queue and the uniform re-record it requires**. That is
what was built; catalog growth is untouched and still owed. Recorded rather than silently merged,
because a reader following either citation should land on the right thing.

### T7.1 (the digest-locked queue) — the world moves *(stage 1 built)*
Four changes taken together, since one digest change costs the same as four:

| change | file | justified by |
|---|---|---|
| cap kafka's JVM heap at 400m | `world-arm64.override.yml` | CATALOG.md measured the trajectory: raised 1200M->2g at ~10:40, back to **90.2% of 2g by ~19:30**. Nine hours to consume the new headroom - unbounded growth, not undersizing. `paymentservice` and `quoteservice`, raised the same morning, both settled *below* their old ceilings, which is what a squeezed container looks like. A cap stops the growth; another raise buys hours. |
| `otel-col` 300M -> 600M | `world-arm64.override.yml` | Measured at **291.7MiB of 300MiB - 97.2%** after ~a day, over the pre-flight gate's 90% threshold, and **a rehearsal was refused on it**. |
| Prometheus retention 6h -> 15d | `compose/telemetry.yml` | Six hours already cost a backfill: `runtime.json` could not be added to the ten existing bundles because their windows were from 08-23 and Prometheus had started 08-24T08:53Z. The window was gone before the question was asked. |
| stub variants renamed | `compose/ffs-stub/`, `src/injector/catalog.py` | ADR-0019: `faultline/ffs-stub:broken` and `:crashloop` made the **tag the answer key**, and `faultline/` gave away the harness besides. Now `ffs-stub:1/:2/:3` over `server.py`/`server_v2.py`/`server_v3.py`. |

**`KNOWN_LEAKING_FAULTS` is now empty and pinned empty.** ADR-0019 tolerated two leaking change
records because both scenarios were blocked and unreachable; T7.1 took the rename instead, because
a leak tolerated for being unreachable is a leak waiting for the scenario to become reachable.

**Digests moved, which is the point and the cost:**

| | before | after |
|---|---|---|
| `world.compose_digest` | `4a7690c6fdda…1583e` | **`299d791c5e0d…6a6c`** |
| `world.ffs_stub_source_digest` | `5d06a3668aa0…b9db` | **`8defed3104c4…7fde`** |

**Every existing bundle was recorded under the old pair and stays recorded under it.** Nothing is
backfilled: a backfilled digest would be a false claim that a capture was taken against a world
that did not exist when it was taken (ADR-0014). The bundles are stale until stage 2 re-records
them, and `test_bundles_match_the_label_they_were_recorded_against` says so out loud for
`flag-service-crashloop`, whose injection params changed with the rename. ADR-0014 already named
that state the correct one.

#### Stage 2 — the uniform re-record, and what it surfaced

Twelve bundles, one driver, **zero discards**. New digests, `capture_set` 2 with
`metrics/runtime.json`, predecessors archived under `superseded/<t_inject>/`.

Two driver defects, both caught by gates before anything was injected: a rebuilt `ffs-stub:1`
left `feature-flag-service` on an orphaned image sha, and a fixed 120s inter-scenario gap is
shorter than the 300s settle rule a revert triggers. The driver now waits for the gate.

**`INVALID.md` was not on the recorder's preserve list**, so `--force` deleted both markers -
the only files explaining why two bundles are empty. Recovered from git; `INVALID.md` now sits
beside `incident.md` in `PRESERVED`, pinned by a test.

**Six of twelve targets export no runtime metrics at all**, invisible until every target was
asked at once. `process_runtime_*` exists for four services and `runtime_*`/`system_memory_*`
adds a fifth; for the other six `{exported_job="<target>"}` matches nothing whatsoever, so the
query is not at fault. Pinned as a measured set, asserted in both directions.

**The retention hypothesis is refuted for both INVALID bundles.** Both fired nothing over a 420s
wait and across the whole window, and both recorded reasons were re-verified against the rebuilt
world rather than assumed: `featureflagservice` still emits no span metrics at all, and
`currencyservice` idles at **0.04% CPU** so a quota ceiling has nothing to bind against. Neither
reason was ever about retention. Both markers stay, and that closes the question.

#### Stage 3 — narrative reconciliation

Every narrative rewritten against its new manifest; corrections recorded in
`docs/evidence/t7.1-reconciliation/README.md` rather than inside the narratives, which are corpus
material written in a responder's voice. **Three observations were removed rather than softened**
because the new captures no longer contain them - `ad-memory-squeeze`'s crosses-clears-crosses
alert, `cart-bad-image-tag`'s two-wave split, and `recommendation-memory-squeeze`'s latency
alerts. One inference was **refuted by the re-record itself**: `product-catalog-flag-failure`
argued that a fast all-clear proves nothing restarted, and `frauddetection-memory-squeeze`, which
*does* require a process to come back, now clears faster than it does.

`email-wrong-image`'s central claim - that the broken service never alerted at all - is
contradicted: it alerts, late and only on absence. That is the scenario T4.8 and T4.15 both built
findings on, and those findings were about **planner behaviour**, not about this claim, so they
stand.

**Published figures were not re-measured**, deliberately: `RESULTS.md` and `README.md` now state
that everything in them was measured against the old world and that comparing a future run to
them compares across worlds. No sweep and no holdout entry ran in T7.1 - what the new world is
worth measuring against is a decision with its own argument to make.

#### ~~Queued~~ **Fixed at T7.3**: the blast-radius exclusion is keyed on the service, not the alert

Found at stage 3 and not fixed there, because it changes triage numbers and T7.1 re-measures
nothing. **T7.3 fixed it and re-scored every stored run** - and falsified the account below, which
is left standing with this correction rather than quietly edited.

**The claim that it was unreachable until the re-record is wrong.** `cart-redis-misconfig`'s
*original* recording has `emailservice` raising `ServiceNoTraffic` during the fault and
`ServiceHighErrorRate` in recovery; the same shape is in `cart-bad-image-tag` and, on `frontend`,
in `shipping-wrong-image`. **24 of 55 stored runs were affected, the earliest from 2026-08-26.**
T7.1 generalised from one test fixture losing its recovery alert to a claim about the whole
catalog without checking it, and the rescore is what caught that. The original reasoning follows.

Found at stage 3 and **not fixed**, because it changes triage numbers and T7.1 re-measures
nothing. `score_triage` computes `alerted - after`, which drops a service from the blast radius
entirely when it has *any* post-revert alert - including the alert it raised during the fault.
That understates the radius.

It was unreachable until now: every after-revert alert in the catalog belonged to a service that
alerted *only* after the revert, so the two sets were disjoint. The re-record retired all three
of those and produced the first overlap, `product-catalog-flag-failure`, where frontend alerts
during the fault and again in recovery. **The fix is to exclude per alert rather than per
service**, and it belongs with a decision to re-measure.

### T7.4 — evidence reachability, characterised *(analysis only; nothing changed)*
The finding T7.1 recorded and never characterised. **contract not written.** Twelve rows, one per
bundle, every cell from a committed capture, the committed graph snapshot, or the tool layer's
source - **the live world was not used**, because "can this target produce this evidence" is a
property of the recording rather than of today
(`docs/evidence/t7.4-reachability/`).

**Four of nine distinct targets export runtime metrics**, all under `exported_job` and never
`service_name`: `adservice` 48 series (`process_runtime_jvm_*`), `frauddetectionservice` 38,
`cartservice` 20 (`process_runtime_dotnet_*`), `recommendationservice` 13
(`runtime_cpython_*`/`system_memory_*`). `featureflagservice` is additionally absent from spans and
from the graph, which `context/catalog.py` already records with its measurement.

**Two scenarios cannot answer "was this service idle or absent" by any class available to the
agent.** Runtime metrics and logs are the only two that can - span and trace absence *is* the
ambiguity, and change history says what changed rather than what is running. Both zero-class cases
are product-catalog-rooted: `product-catalog-flag-failure`'s target emits 2 log lines and no
runtime series, and `productcatalog-dependency-latency`'s emits **0 log lines** and none, which
confirms ADR-0005's measurement of `product-catalog-service` at 0 lines/hour from the bundle side.

**Four narratives teach a check the agent cannot perform**, and they are named as narrative defects
rather than scenario defects: the scenarios are recordable and their faults real. Both
`dependency_latency` narratives put their **decisive** check on container inspection - *"a container
was attached to cart's network namespace"* - which is not one of the four tools, and which ADR-0019
flagged at design time and nobody closed. `cart-bad-image-tag` and `cart-redis-misconfig` name
container state as **framing** around evidence that is genuinely in the logs, which is the milder
version of the same error.

**Three implications, each with a next step that is not taken here.** For the corpus: three seeded
dev narratives teach reaching for a tool that does not exist, and whether that costs dispatches is
**unmeasured** - the next step is a pre-registered comparison, not an edit, because rewriting the
narratives would move the corpus and the numbers together. For scoring: T4.11's 5/5 stable
abstention is on the scenario this table shows has zero answering classes, and the scorer cannot
distinguish that from an abstention caused by reasoning - the next step is to record reachability
as a **scenario** field, since a scorer deciding which abstentions were excusable would be grading
on sympathy. For catalog growth: **this table is the pre-recording check PLAN.md's real T7.1
needs**, run against a target before the scenario is rehearsed rather than discovered afterwards.

### T7.3 — the blast radius counts alerts, not services *(built)*
The defect T7.1 recorded rather than fixed. **contract not written.** `score_triage` filtered alert
episodes correctly and then projected to service names *before* subtracting, so `alerted - after`
dropped any service holding both a during-fault alert and a recovery alert - understating the
radius by blaming the fault for **less** than it did, the mirror of the error ADR-0009 guards
against. The fix is to project after filtering. **Nothing else in the scorer makes the same error**:
`prom.py` sets the flag per entry, `bundle_render.py` reads it per alert, and `rehearse.py` filters
entries with comprehensions; `TriageScore` is consumed only as the `triage` key.

**Every stored run was re-scored** by pure recomputation - no model calls, no live world - each
against **the bundle recording current when it ran**, since T7.1 moved all twelve and scoring an
August 26th run against an August 28th capture would mix the two changes
(`docs/evidence/t7.3-rescore/`). **24 of 55 runs moved**, all in one direction: a service restored,
`n_alerted` up one, recall held or rose, precision rose. `emailservice` in 18, `frontend` in 6.

Per-table: S1 precision 0.56->0.60, S2 0.57->0.60, S3 0.54->0.58 with recall 0.91->0.92, S4
0.56->0.59, S5 0.54->0.57 with recall 0.90->0.91, T4.10 0.58->0.67 with recall 0.78->0.80.
**No holdout figure moved at all** - none of those three scenarios has an overlapping service - and
T4.11 is unchanged. Every corrected table keeps its original number struck beside the new one,
because a silently corrected figure is indistinguishable from one that was always right.

**No verdict, coverage or fault-class figure is affected**, established from the code rather than
assumed: `reached_a_class` reads `fault_class` alone, and `fault_class`, `fix_class` and
`categories` never reference triage.

**T4.10's finding survives its own correction.** All five repeats are the same scenario, so all
five moved by the same amount in the same direction; the spread that experiment measured is
identical.

#### Queued: a `memory_limiter` processor for otel-col — **600M is a timer, not a fix**

Not taken at T7.1, and recorded here rather than left in a commit message because the raise will
expire and whoever meets it next should find the reasoning rather than re-derive it.

**What was actually fixed and what was not.** kafka's growth is *stopped* — a JVM heap cap is a
ceiling the process cannot grow past. otel-col's is only *deferred*: nothing about 600M changes the
collector's behaviour, it just takes longer to reach. The two changes look alike in the diff and
are not alike.

**Why it was not fixed here.** The collector config is not a `compose_digest` input, so unlike the
other four this change was never locked to a re-record — it can be taken any day, and bundling it
into a digest bump would hide a behavioural change inside a batch whose whole justification is
"these had to move together". They did not.

**What would tell us it ran out.** The signal is the one that caught it the first time: the
rehearsal pre-flight gate refuses at 90% of the limit, so `otel-col` at **540MiB of 600M** is the
tripwire, and it will surface as a refused rehearsal rather than as anything resembling a memory
problem. Two numbers bound the wait — 291.7MiB after roughly a day at the old ceiling, and the
measured start of 123.3MiB immediately after this rebuild — so if growth is linear in uptime the
gate should hold for a week or two rather than a day. **That estimate is an extrapolation from two
readings of a different ceiling and should be treated as one.** `docker stats --no-stream otel-col`
between batches is the cheap check; CATALOG.md's operational section already tells a reader to run
it.

**What the fix looks like when taken.** A `memory_limiter` processor with `limit_mib` set below the
container limit, so the collector sheds load and reports it rather than being OOM-killed — the
difference between a world that says it is dropping telemetry and a world with a hole in it. That
distinction is the whole reason this one matters more than kafka's: a kafka OOM writes a spurious
incident into a bundle, a collector OOM writes nothing at all, and `test_metric_captures_have_no_holes`
would catch it only after the run that lost the data.

**The otel-col raise buys time and does not fix the growth**, and is taken anyway because
`otel-col` is the path every metric and trace takes - a kafka OOM writes a spurious incident into
a bundle, a collector OOM writes a hole. The real fix is a `memory_limiter` processor in the
collector config, which is **not** a `compose_digest` input and so was never locked to this
re-record; it is left for its own change rather than bundled into a digest bump.

### T7.2 — external benchmark confirmation
Confirms the runtime interface ADR-0004 inferred from harness source.
`docs/adr/0004:48`, `docs/adr/0004:55`

---

## Discovered omissions — described in the repo, absent from this index

Every entry above was reconstructed from a citation that names a task number. This section
holds the opposite case: something the repo describes, depends on, and never numbers. It is
here so the gap sits in the index rather than only inside the ADR that tripped over it.

### The action plane / executor — **no task number, contract not written**

`docs/ARCHITECTURE.md:12` places it in the system diagram as the last stage: "action plane
(separate service, allowlist + approval tokens)". `docs/THREAT-MODEL.md:15` makes it
load-bearing for the whole security argument — it is the only holder of write credentials,
it validates actions against an allowlist, and it requires "a single-use, action-bound
human-approval token", so that "a fully compromised investigation agent cannot execute a
write, because the tokens it holds cannot". `docs/THREAT-MODEL.md:39` adds that T6.8 has to
re-harden its public surface and make it unreachable from the internet.

**No task in this file builds it.** The grep that produced this index found no `T<n>`
citation attached to it anywhere in the tree.

What depends on it: ADR-0016's states 8 and 9 — `AWAITING_APPROVAL` and `EXECUTING` — are
the last two of the eleven-state incident machine, and both are named there with their
triggers declared and deliberately not designed, because what an approval token contains is
this component's contract and not the orchestrator's. The remediation proposer, one of the
nine agent roles at T3.x, produces the input to it.

**contract not written** — the repo does not say what an action is, what the allowlist
contains, what the token binds to, who issues or approves it, or whether the executor lives
in this repository at all.

Note the honest limit of this observation: **this file is a reconstruction, and the real
execution plan lives outside the repository.** The plan may well number this task. What is
established is that nothing in the tree cites it, so nobody reading the repository can find
out — which is the same failure mode this file exists to fix, and the reason it is recorded
as an omission rather than asserted as a hole in the plan itself.

---

## The T4 decision, and what the citations settle

An open question after T1.5 was whether the agent investigates a **live world** with tools
or reasons from a **recorded bundle**. It decides whether the missing container-state
capture — `RestartCount`, `OOMKilled`, exit codes — requires re-recording every bundle.

The citations answer it. T4.1 reads "what to inject, how long to wait, how long between
runs" from a manifest, which is a harness that injects into a running world. T4.1b excludes
a scenario's own artifacts from **retrieval** while it is scored, which means bundles are a
corpus the agent draws on, not the evidence it is handed. T4.2 scores runs against the
bundles.

**The agent investigates a live world. Bundles are the retrieval corpus and the scoring
ground truth.**

### The consequence is the opposite of what was feared, and introduces a different problem

Re-recording for container state would buy nothing — but not because the agent can read it
live. `docs/ARCHITECTURE.md:23` gives the agent's tools as **PromQL, LogQL and
deploy-history**. There is no container-inspection tool. `RestartCount`, `OOMKilled` and
exit codes are unavailable to the agent from any source.

**contract not written** — the repo does not enumerate the agent's tool set beyond that
one line, and does not say what "deploy-history" returns.

That matters for the narratives, because several of them reason from evidence the agent
cannot gather:

- `shipping-wrong-image` turns on **exit 137** distinguishing a memory kill from an
  application failure.
- `email-wrong-image` cites **exit 1** as the reason to go and read the logs.
- `frauddetection-memory-squeeze`, `ad-memory-squeeze` and `recommendation-memory-squeeze`
  all cite exit 137 or a climbing restart count.

Each of those discriminators is *also* reachable through logs, which the agent does have:
a container killed by the kernel stops mid-startup with no error line, one that fails on
its own configuration says so, and one that was never created leaves a log stream that
stops dead and never resumes. The investigations are runnable. The narratives just describe
them in terms of an artifact nobody can query.

**Open question for T2.4b and T4.2:** narratives seeded into the retrieval corpus should be
written from evidence the agent's tools can actually reach. Whether to rewrite the exit-code
references in terms of log evidence, or to add a container-state tool, is a decision that
has not been taken. Recording it here rather than leaving it to be discovered at scoring
time.
