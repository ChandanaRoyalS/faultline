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

### T7.31 — make the kafka precondition refuse *(gate logic; no digest moves)*
**Done** (`src/evalharness/gate.py`, thirteen tests). T7.30 ended by making "recycle kafka before
recording" a precondition, and a precondition that lives in a PLAN entry is the failure mode this
arc has spent ten tasks pricing: true when written, silently unmet later, and the run that violates
it produces a bundle that looks fine.

**No digest moves, confirmed by enumeration rather than assumed.** `compose_digest` is three compose
files; `observability_digest` is seven named files under `compose/` and `world/src/otelcollector/`;
`ffs_stub_source_digest` is `compose/ffs-stub/`; the pipeline stamp is the package version plus role
`*_SYSTEM` prompts, `UNTRUSTED_RULE` and contract schemas; `CAPABILITY_VERSION` is the tool surface,
`CAPTURE_SET` and `TOOL_BEHAVIOUR_REVISION`. **`gate.py` is an input to none of them.** Gate logic is
product, not world - and the check reads the memory limit from the container rather than hardcoding
2 GB, so it does not smuggle a world constant into product code either.

**The gap it closes is bigger than it looks: scored runs have never had a memory check at all.**
`require_memory_headroom` is called from exactly one place, `rehearse.py` - the recorder. `run.py`
calls `gate.require` and nothing else, and the two paths share no preflight. That is why T7.29 could
start at 69.95%, pass every check that existed, and finish at 90.69%.

**The threshold is computed, never chosen.** A run starting at `percent_now` and growing at a
measured rate for its expected duration either ends under the recorder's existing 90% guard or it
does not:

```
growth_mb      = HEADROOM_GROWTH_MB_PER_HOUR * expected_run_hours
growth_percent = growth_mb / limit_mb * 100
threshold      = MEMORY_HEADROOM_PERCENT - growth_percent
refuse         if percent_now > threshold
```

**Rate: 151 MB/h**, from T7.29 - `anon` 1,462,681,600 -> 1,903,943,680 over 2h47m = 421 MB / 2.78 h.
**T7.30's 221 MB/h is deliberately not used**: it came from a 0.22-hour window containing a single
128 MB translation-block allocation, and a rate that predicts over hours must be estimated over a
comparable window. At rest the rate is 6.2 MB/h, so this check is near-inert on an idle world.

**Duration: the assumption is explicit, and it is a parameter.** The gate cannot know how long the
run will be, so `expected_run_hours` defaults to `RUN_BUDGET_SECONDS` = **2910s = 0.81h**, summed
from the harness's own committed bounds - `CORRELATE_CEILING_SECONDS` 1800 + `SETTLE_AFTER_ALERT_
SECONDS` 90 + the T4.7 budget's `wall_clock_seconds` 600 + `RECOVERY_TIMEOUT_SECONDS` 420 - and
**pinned to those four by test** so it breaks loudly rather than drifting. That is a *bound*, not a
typical run: T7.29's runs averaged ~0.34h. A caller that knows better passes its own figure.

At the default, against a 2 GB kafka: growth 122 MB = 5.96 points, **threshold 84.04%**.

**The honesty check, replaying T7.29's measured trajectory run by run** (69.95% -> 90.69%, 8 runs):

| | gate at default | what actually happened | |
|---|---|---|---|
| runs 1-6 | PASS | stayed under 90% | correct |
| run 7 (85.5% -> 88.1%) | **REFUSE** | stayed under 90% | **false refusal - one scenario** |
| run 8 (88.1% -> 90.7%) | **REFUSE** | **crossed 90%** | correct |

**No false pass**, which is the condition that would mean the threshold is wrong, and it is asserted
against by a test rather than argued. **One false refusal, and it is a real cost** - a scenario lost
to a recycle that was not yet needed. It is the price of defaulting to the harness's worst case
instead of its typical case, and a sweep driver that passes its measured duration does not pay it.

**Declaring the real duration refuses at the start, which is the right answer.** With
`expected_run_hours=2.78`, the threshold is 69.50% and T7.29's 69.95% start is refused before run 1
- and the projection lands at **90.4% against an actual 90.69%**, within 0.3 points, which is the
check on the rate itself rather than on the gate.

**The reading is recorded on every run, passing or refusing** - `percent_now`, `limit_mb`,
`projected_percent`, `threshold_percent`, `guard_percent`, `fits` - inside `GateReading`, which
already goes into the run manifest verbatim next to the other preconditions.

**No sixth discard reason, and the decision is deliberate.** Nothing was injected and the world was
unfit, which is exactly what **`baseline gate refused`** already means. `pipeline-down` earned its
own subclass because it was the *harness* failing while looking like the world; this is the world.
The attribution the task wanted comes from the recorded reading instead: a run that later dies on
the 90% guard can be asked what it started at, without a new label.

**What this does not do.** It stops a run starting doomed. **It does not stop kafka growing** - the
growth is Rosetta translation cache, driven by work (ADR-0005's T7.30 addendum), and no gate reaches
it. The real fixes are unchanged: **recycle kafka before recording**, or **native arm64 images**,
which is the only one that removes the mechanism rather than managing it. It is also single-run
scoped by default: a sweep's problem is cumulative, and the gate sees each run alone unless the
caller tells it otherwise.

### T7.30 — the lever that engaged and did not hold *(measurement only; no digest moves)*
**Done** ([`docs/evidence/t7.30-kafka-lever/`](evidence/t7.30-kafka-lever/), ADR-0005 addendum).
T7.29's passive measurement partly falsified T7.27's diagnosis; this establishes what replaces it.

**kafka runs an `amd64` image under Rosetta emulation on an `arm64` host** - `uname -m` returns
`x86_64` and `/run/rosetta/rosetta` is mapped into PID 1. **The memory that grows is the emulator's
JIT translation cache**, not glibc arenas. At 14.12h uptime and 99.87% of its limit: **1,429 MB of
executable (`rwxp`) anonymous memory**, 1,408 MB of it in ten fully-resident, fully-dirty, THP-backed
blocks, with **arena regions at 0**. The JVM cannot own it - NMT's `Code` reserves **243 MB** at
most, leaving >=1,186 MB outside it.

**Which of the three it was: a real but secondary effect, and separately a different, load-driven
mechanism.** Not a symptom of the same allocation - two allocators holding two kinds of memory. The
arenas were real and the lever collapsed them; they held *address space* (7,413 -> 2,456 MB), never
the growing resident memory.

**The decisive measurement, same method and cadence as T7.27:** with arenas at **0**, the
anon-vs-NMT gap opens to **+23 MB at 25 min**, against T7.27's **+23 MB at 30 min** with **68**
arenas. Identical trajectory, opposite arena counts. NMT itself is unchanged by the lever - total
committed 586,971 KB against T7.27's 584,958 KB, Java Heap identical.

**Load separates cleanly from time, measured within one process** so age and config are constant:
**+6.2 MB/h at rest** (`rwxp` +0 MB) against **+221 MB/h under load** (`rwxp` **+128 MB - one new
translation block, caught in the act**). A **36x** difference; T7.29's 151 MB/h sits between them.
**T7.27's ~55 MB/h was a warm-up rate** sampled over 5->30 min; extrapolating it to ~1.3 GB/day
"matched" 1.86 GiB in 1.5 days by arithmetic coincidence - at the true idle rate that takes ~12 days.

**The queued item, answered honestly: `MALLOC_ARENA_MAX=2` stays, for a different reason than it was
added.** It moved a digest and forced T7.28's eleven-bundle re-record for a benefit not demonstrated
in resident memory. It has no measured downside, and removing it would cost a second digest move, a
second re-record, and would invalidate dev sweep 7 - the only current-world benchmark. **It stays
because removal is expensive and its effect is nil, not because it works**, and it should be dropped
the next time the world moves for an independent reason. The real fixes are recycling kafka before
recording (now a precondition), or native arm64 images - ADR-0005's own exit clause, which this gives
a second independent reason to want.

**What is not established:** Rosetta's internals were not instrumented - the attribution rests on a
ceiling argument, the executable permission bit, address ranges, and a 128 MB block appearing under
load. The load proxy was client churn, not the sweep's eight injections, and no equivalence is
claimed. **The lever-off-under-load cell is missing** and getting it would mean restoring the old
config, moving the digest and invalidating the catalog - so the lever is isolated **at rest only**,
where its effect is nil.

**World left healthy:** 15 services reporting, no alerts, kafka fresh at 26.27%, `accounting-service`
restarted after the kafka cycle per T7.27's rule, temporary NMT override deleted, **both digests
verified unmoved**.

### T7.29 — the benchmark, re-founded again *(one sweep, pre-registered, judged)*
**Done** ([`SWEEP-2026-08-30-refound-again.md`](../evals/runs/SWEEP-2026-08-30-refound-again.md)).
T7.28 left the bounded world with no measurement at all. This is T7.10's shape after T7.1: the
world moved, so the benchmark is re-founded on the world that exists. Stamp unchanged at
`1b0e7cbb4c47`, budget T4.7's — **not an experiment on the agent.**

**Eight scenarios are runnable, not seven**, and the count was checked rather than assumed:
`shipping-quote-misconfig` did not exist when S6 ran. The three that are not runnable are
unchanged and none of it is a T7.28 blockage - `ad-dependency-latency` was disqualified at T7.22,
and `currency-cpu-throttle` / `flag-service-crashloop` have carried an `INVALID.md` since T7.1.

**8 of 8 scored, no discards, no refusals - the cleanest sweep the project has run.** Coverage
**8/8**, fault class **7/8**, class of fix **7/8**, judge `same_mechanism` **7/8**.
**$4.3652 agent + $0.3218 judge = $4.6870**, mean $0.546/scenario against a $0.55 budget.

**The registered falsifier fired once.** `shipping-quote-misconfig` returned `bad_deploy` against a
truth of `bad_config` - **low** confidence, **zero dispatches at the failing service**, judge
`adjacent`. The agent named its own error in its open questions: a bad config value "would look
identical from the caller". This is T4.12's dispatch collapse, the same mechanism behind S6's
`shipping-wrong-image` abstention, **exiting as a wrong answer instead of an abstention** - and
what selects between those two exits is not established here. Attribution is left open between a
changed capture (2 -> 7 alerting services) and known planner instability; n=1 per side separates
neither.

**Two scenarios recovered.** `frauddetection-memory-squeeze`, S6's discard, paged and scored a
perfect 1.00/1.00 triage - a second independent line of evidence for T7.11's falsification of the
kafka-heap hypothesis, since a *more* memory-constrained kafka is exactly where that mechanism
should have shown. `shipping-wrong-image` answered correctly after abstaining in S6.

**The S6 rescore was necessary, and the check is now a standing one.** `scoring.py` moved at T7.17,
after every S6 run - the T7.3 confound repeating. Exactly one label moved
(`cart-dependency-latency`, correct by alternative), taking S6's class-of-fix 4/5 -> **5/5**. The
sweep compares the rescored column; comparing the stored one would credit the world with a scorer
fix.

**Triage: four of six comparable scenarios identical to two decimals.** One movement traces to a
documented capture difference and one does not, and the difference was measured rather than
inferred - each bundle diffed against its own `superseded/` archive
([`capture-differences.md`](evidence/t7.29-refound-again/capture-differences.md)). This **corrected
the pre-registration**: it named four expected movers, and only two can move. Stage 3's corrections
ran two things together - a changed *set* of alerting services (moves the triage denominator) and a
corrected *prose claim about timing* (does not, because triage never read the prose).

**The kafka question T7.27 queued, answered in the direction it could not reach.**
`MALLOC_ARENA_MAX=2` **engaged and stayed engaged** - 64 MB arena regions **0 at both ends** - and
**it does not bound long-run growth**: anon grew **+421 MB in 2h47m** and the container went
**69.95% -> 90.69%**, crossing the recorder's 90% refusal threshold during the sweep, as the
pre-registration warned it might. The premise that the setting had been live a day or more did not
hold - kafka restarted at 22:12Z, and arena state is a property of process lifetime - so this is a
~5h -> ~8h observation and **no rate comparison to T7.27's ~55 MB/h is claimed**, because that
figure came from a near-idle world and this window ran eight injections. **Recycling kafka is now a
precondition of recording, not an occasional fix.**

**Holdout not re-entered.** README and RESULTS now lead with the current-world figures; older ones
stay labelled.

### T7.28 — the queue cashed, and everything recorded against it *(all three stages done)*
T7.26 said to wait for a second genuinely-needed `compose_digest` change; T7.27's kafka finding is
it. **Stage 1 landed the three changes and the digests moved.**

| digest | before | after |
|---|---|---|
| `compose_digest` | `299d791c5e0da43e…` | **`f5bd108f4f70f460…`** |
| `observability_digest` | `3d061a2793b1cd57…` | **`857d95b4d174ec43…`** |
| `ffs_stub_source_digest` | `8defed3104c42adf…` | **unchanged** - the stub was not touched |

**All three verified live in the running containers, not merely present in a file.** kafka:
`MALLOC_ARENA_MAX=2`, **64MB arena regions 68 -> 0**, mapped anon 7,413 -> **2,462 MB**. redis-cart:
`maxmemory 12582912`, `maxmemory-policy allkeys-lru`. otel-col: the collector's own log shows
`Processor started {"name": "memory_limiter", "pipeline": "traces"}` **and** the same for `metrics`.
World up at 28 containers, 16.94 req/s, gate **PASS** (after ADR-0025's checkout remedy, which the
full-world restart made necessary).

**One deviation from T7.26's specification, and it was necessary.** The spec said to put the
collector change in `world/src/otelcollector/otelcol-config-extras.yml`, the demo's designed merge
point. **That file is gitignored** - `world/` is a clone (ADR-0026), so the edit could never be
committed and the next `make world-up` on a fresh checkout would lose it. The config now lives in
**`compose/otelcol-extras.yml`**, tracked here, mounted over the demo's path by `telemetry.yml`.
`OBSERVABILITY_FILES` gains it, so the digest covers **the file actually in effect** rather than a
stub that no longer reaches the collector; the stub stays under cover because a change there would
mean the mount had been removed.

**The stale-comment finding, acted on.** T7.26 noted that prose about kafka's growth sits inside
`world-arm64.override.yml`, a digest input, so correcting it moves the digest. It was worth moving
**because the comment was wrong** - it said the heap cap stopped the growth, and T7.11 then measured
1866 MiB against that cap. Leaving a paragraph that says the problem is solved, directly above the
setting that does not solve it, is how the next person re-derives T7.27 from scratch. The correction
carries what was ruled out and, explicitly, **what was not shown**: that `MALLOC_ARENA_MAX` bounds
long-run growth needs ~24h under the setting and is queued as a re-measure, not claimed.

**Stage 2 — eleven of fifteen re-recorded, four blocked, none discarded.** Every bundle carries the
new digests, `capture_set` 2, a `superseded/` archive of what it replaced, and a reachability field
derived correctly after T7.22's fix - visible as 48rt/145log on `ad-memory-squeeze` rather than the
0/0 the bug produced. One retry across the whole run, from a container-uptime clash.

| scenario | split | onset | reachability |
|---|---|---:|---|
| ad-memory-squeeze | dev | 210s | 48rt / 145log |
| cart-bad-image-tag | dev | 286s | 20rt / 500log |
| cart-dependency-latency | dev | 230s | 20rt / 500log |
| cart-redis-misconfig | dev | 181s | 20rt / 500log |
| email-wrong-image | holdout | 226s | 0rt / 166log |
| frauddetection-memory-squeeze | dev | 375s | 38rt / 227log |
| product-catalog-flag-failure | dev | 229s | 0rt / 2log |
| productcatalog-dependency-latency | holdout | 229s | 0rt / 0log |
| recommendation-memory-squeeze | holdout | 285s | 13rt / 153log |
| shipping-quote-misconfig | dev | 198s | 0rt / 387log |
| shipping-wrong-image | dev | 198s | 0rt / 358log |

**The checkout policy, decided before starting.** Recycle checkout at the **end** of each scenario,
so its 300s uptime requirement elapses during the inter-scenario settle. Waiting for the gate to
refuse and then applying ADR-0025's remedy costs a refused attempt, a restart and a 300s wait each
time, and at ~12 minutes to stall it would have hit most of eleven scenarios. **`accountingservice`
was checked before the first recording** rather than discovered mid-sweep (T7.27): stage 1's
world-up had stranded it, reporting no series at all. Restarted, confirmed consuming, then began.

**Stage 3 - seven of eleven narratives carried a claim the new captures contradict.**

| narrative | contradiction | correction |
|---|---|---|
| `cart-dependency-latency` | said the page named **two** services with frontend joining later; frontend was **at fire** | three at fire, checkoutservice at +15s |
| `cart-redis-misconfig` | said the page named **one**; frontend was **at fire** | two at fire, checkoutservice at +15s |
| `productcatalog-dependency-latency` | said **four alerts fired together**; one did | single alert, three at +15s, checkout at +30s |
| `recommendation-memory-squeeze` | said the page was **two alerts**; one | single alert, frontend at +15s |
| `product-catalog-flag-failure` | said **three** services alerted, and that a **fourth alert fired after the fix** | four services; **the recovery-alert claim removed** - the new recording has no after-revert alert at all |
| `shipping-quote-misconfig` | said **nothing else alerted**; seven alerts across seven services now | the `ServiceNoTraffic` cascade named |
| `ad-memory-squeeze` | last restart **eighteen seconds** before the fix | three seconds |

Plus onset durations in prose on ten of eleven. **`ad-memory-squeeze`'s "sixteen startup attempts"
survives** - a first grep for `AdService starting` found one and would have produced a false
correction; the restart evidence is the `JAVA_TOOL_OPTIONS` banner, and there are exactly sixteen
inside the fault window. **`shipping-quote-misconfig`'s corrected design also survives**: zero error
lines in 387 log lines, `GetQuoteRequest` throughout, and 80 quote requests against 2 ship orders
inside the window - orders do abort before fulfilment. Its measured error band moved 23-29% to
**25-29%**.

**One test moved to an archive.** `test_a_service_that_alerts_during_and_after_stays_in_the_blast_radius`
pinned T7.3's fix against `product-catalog-flag-failure`, whose new recording has no after-revert
alert; its fixture now reads `superseded/20260828T035307Z/`, as its own docstring predicted.

**Re-rendered, re-seeded, quarantine verified:** 13 pages, 8 documents / 40 chunks from `dev/`
alone, **`holdout_chunks` 0**, all 13 narratives at `cap:9c416e0a`.

**Every published figure now names its world.** README, RESULTS and eleven files under
`evals/runs/` carry a banner: the figures describe `299d791c5e0d…`, **nothing has been re-run, and
there are no current-world figures**. Not wrong - correct about a world that no longer exists.
**No sweep, holdout entry or agent investigation was re-run here**; what to measure against the new
world is a separate pre-registered decision. T7.24's run report was on an unmerged branch when this
was written; it landed first and carries the banner, plus a second paragraph the others do not need -
that run is superseded in its subject as well as its world, because stage 2 re-recorded the bundle
it scored against.

### T7.27 — where the kafka memory lives *(measurement only; no digest moves)*
**Done** ([`docs/evidence/t7.27-kafka-memory/`](evidence/t7.27-kafka-memory/)). NMT enabled through
a temporary override outside the repository, container restored afterwards, `compose_digest`
verified unmoved.

**The restart is the first result:** **1.949 GiB / 97.44% -> 570.1 MiB / 27.84%**. The growth is
real, accumulates with uptime, and a restart clears all of it. It was already past the recorder's
90% pre-flight guard.

**No NMT category holds the bulk, and that is the finding.** At baseline NMT accounts for ~97% of
resident anon (`committed=584,958KB` against 590,905,344 bytes), with **Java Heap 409,600KB sitting
exactly at its `-Xmx400m` cap**. But filling *every* category to its reserved ceiling caps the JVM
at **0.87 GiB**, against **1.86 GiB** observed at 1.5 days - **at least 0.99 GiB is outside every
NMT category**. **NMT's own overhead is ~2 MB** and is not a finding.

**Watched in the act:** the gap between cgroup `anon` and NMT-committed went **-2 MB -> +23 MB in 25
minutes**, ~55 MB/hour outside NMT, extrapolating to ~1.3 GB/day - which matches 1.86 GiB at 1.5
days. The `summary.diff` names what moved *inside*: **`Other` +4 KB** (direct/mapped ByteBuffers
**ruled out**), **`Thread` +56 KB** with the count flat at 97 (**ruled out**), GC +229 KB (**ruled
out**), Class +2,513 KB (real, tiny), Code +10,047 KB (JIT warmup, bounded by 249 MB reserved - not
the gigabyte), **Java Heap 0 KB**.

**It is the allocator.** RHEL 8.6, **glibc 2.28**, 97 threads, and **68 anonymous regions of exactly
63.9 MB** - the per-thread arena signature - for 7,413 MB of mapped anon address space, against a
default `M_ARENA_MAX` of 8x10 cores. Arenas retain freed pages instead of returning them. **The JVM
is not leaking; glibc is holding freed pages.**

> **Corrected 2026-08-30 (T7.30) - the attribution above is falsified; the observation is not.**
> The 68 arena regions were real and the lever collapsed them to zero. But **kafka runs an amd64
> image under Rosetta emulation** (`uname -m` = `x86_64`, `/run/rosetta/rosetta` mapped into PID 1),
> and the memory that grows is **the emulator's JIT translation cache** - 1,429 MB of executable
> `rwxp` anonymous memory at 14h, with arena regions at **0**. The JVM cannot own it: NMT's `Code`
> reserves 243 MB at most. With arenas at zero the anon-vs-NMT gap still opens to **+23 MB by 25
> minutes**, against **+23 MB at 30 minutes** with 68 arenas - same trajectory, opposite arena
> counts. The ~55 MB/h below is a **warm-up** rate; past warm-up it is **6.2 MB/h** at rest and
> **221 MB/h** under load. Growth tracks work, not uptime. See ADR-0005's T7.30 addendum.

**The lever engages, and that is all that was shown.** `MALLOC_ARENA_MAX=2`: arenas **68 -> 0**,
mapped address space **7,413 -> 2,456 MB**. **Not shown: that it bounds the long-run growth** - that
needs ~1.5 days under the setting and was not run. Re-measure at 24 hours after it lands.

**Digest-locked: yes.** It is a container env var in `compose/world-arm64.override.yml`, a
`compose_digest` input. **A smaller consequence:** kafka's growth is characterised in prose inside
that same file, so **even correcting that comment moves the digest** - which is why this addendum is
here rather than beside the thing it explains.

**Not a sizing problem, which changes the fix.** 2 GB against ~600 MB of genuine JVM footprint is
nearly 3x headroom, and T7.1 already recorded that 1200M -> 2g bought about nine hours. Unbounded
growth consumes any ceiling. ~~**A bounded-allocator problem, not a limit problem.**~~
**Corrected (T7.30): an *emulation* problem.** No malloc tunable reaches it. The half about a
raise buying only time stands, and is strengthened - growth is driven by work, not bounded by a
ceiling.

**Two operational findings.** Restarting kafka **strands `accountingservice`** - it sat at 0.000
req/s until restarted, while `frauddetectionservice` reconnected on its own. And **checkout's stall
returned on schedule**, ~1 day after its restart, cleared again by ADR-0025's prescribed remedy.

**World left healthy:** no alerts firing, both Kafka consumers serving, kafka fresh at 26.85% with
no leftover env, temporary override deleted.

### T7.26 — the queue, specified *(specification only; nothing lands, no digest moves)*
**Done** ([`docs/design/t7.26-queue-specification.md`](design/t7.26-queue-specification.md)). File,
line, before, after and verification for each queued item, so the sitting that cashes the queue is
execution rather than design. **Two of the four did not survive re-measurement.**

**Item 2, kafka retention: FALSIFIED. Removed from the queue.** The premise was that a heap cap
bounds heap and not RSS, so bounding the log would bound the rest. Measured today: the log
directory is **14 MB**, the container holds **1.78 GiB of `anon`** against **52 MB of page cache**,
and the G1 heap sits exactly at its 400m cap. Retention cannot reclaim memory that is neither log
nor cache. Executing it would have moved `compose_digest`, forced twelve re-records and fixed
nothing. Replaced by a measurement task: run Native Memory Tracking.

**Item 4, checkout recycle: leaves the queue.** T7.23 established what the stall is *not* and left
the mechanism unidentified, so a periodic recycle **treats a symptom on a schedule** - it restarts
the process before unknown state accumulates. The two in-world mechanisms are both worse than the
problem (a sidecar with the docker socket enlarges the world's trust surface; a healthcheck rigged
to fail on uptime makes every health reading a lie), so it stays **operational** and moves no
digest. What would settle the mechanism is one command: **restart `frontend` instead** next time the
stall is live, which separates checkout's state from the connection's - a distinction a checkout
restart cannot make.

**Item 3, redis: specified, and the policy choice settled.** `allkeys-lru`, not `volatile-lru`:
`expires=0` still holds, so a `volatile-*` policy has nothing to evict and degrades to
`noeviction`. `maxmemory 12mb` against the 20M container, sized from the measured 2.67
fragmentation ratio.

**Item 1, otel-col: specified, and its own queue entry corrected.** It goes in
`otelcol-config-extras.yml`, the designed merge point, not the pinned clone's config. And the entry
saying *"the collector config is not a `compose_digest` input… it can be taken any day"* is **stale**
- T7.15 brought both collector configs under `observability_digest`. It still invalidates nothing
today, because no bundle on `main` carries that field.

**The cost, honestly.** As respecified, `observability_digest` moves (item 1) and `compose_digest`
moves (item 3). **Twelve bundles re-recorded**, every narrative needing T7.7's reconciliation pass
against new captures with logs read first, and every published figure returning to a superseded
world. `shipping-quote-misconfig` rejoins the re-record; **T7.24's run becomes a measurement of a
world that no longer exists** - not invalidated, and it was reported as n=1, so nothing aggregate
breaks.

**Recommendation: do not cash it now.** One item genuinely needs the re-record. A batch of one is a
bad trade against twelve re-records and a reconciliation pass over every narrative. **Wait for a
second `compose_digest` change to be genuinely needed** - the kafka native-memory finding is the
likeliest source once measured - and cash items 1 and 3 together. If nothing arrives before
`redis-cart` becomes a recurring obstruction, cash those two alone and accept the cost, because a
recorder refusing on an unrelated container is worse than a stale figure. **Item 1 is the only one
that could land alone without a re-record**, and it should not, because there is no pressure: the
collector is at 24% of its limit after two days against a 540 MiB tripwire.

### T7.25 — the pipeline has to be listening *(preflight; third discard reason)*
**Done.** The gap T7.24 fell into: a run injected while `faultline-ingest` and
`faultline-orchestrate` were down. The fault fired exactly on schedule - checkoutservice at 27.6%
errors, four `ServiceNoTraffic` alerts on the board - and no incident opened, because nothing was
listening at the webhook and nothing was consuming the stream. Left alone it would have recorded
**`no-alert`**, which reads as a fact about the scenario. It was a fact about the harness.

**Two checks, in the gate, before anything about the world is read** - because a world that alerts
perfectly into a pipeline nobody is running is exactly the case that must not reach an injection.

**Ingest: `GET /healthz`.** *Proves* a process is bound to the port, the ASGI app booted, and
routing works. *Does not prove* that `POST /api/v1/alerts` succeeds - a different route that
validates a payload and writes to Redis, which can fail while `/healthz` still answers. The
stronger check would post a real alert, and that would put a fabricated episode into the store the
run is about to measure, so it is deliberately not done.

**Orchestrator: the consumer's `idle` from `XINFO CONSUMERS`.** *Proves* something is attached to
the group and actively polling. *Does not prove* that an event would be processed once read - it
could read and then fail on the database write - nor that the attached client is the orchestrator
rather than something else using the same consumer name.

**Why `idle` and not `inactive`, which is the whole point.** Redis keeps two clocks on a consumer.
`idle` is time since the last *interaction*, which a blocking `XREADGROUP` refreshes whether or not
it returns anything. `inactive` is time since the last *successful read*, and it grows on any world
with nothing to say. **Measured on the live world:** orchestrator up, `idle` **93-905ms** against a
5000ms block while `inactive` stood at **737,918ms** because no alert had arrived in twelve minutes.
**Reading `inactive` would refuse every quiet world** - and a quiet world is the normal state before
an injection.

**`idle` was verified to be a liveness signal, not inferred.** Killed the orchestrator and watched
it grow 1:1 with wall clock: **6963, 17001, 29046ms**. Ceiling is `6 x block_ms`, read from the
orchestrator's own settings rather than copied, for T4.13's reason - a deployment that changes the
block interval moves this with it.

**Verified against T7.24's exact case:** both services stopped, and the gate named both, with the
command to start each, and raised `PipelineDownError` carrying `discard_reason: pipeline-down`.

**Three discard reasons, pinned distinct.** `no-alert` - the world had its chances and the fault did
not page. `metrics-gap` - the world stopped reporting, so nothing was measured. **`pipeline-down`** -
the world was fine and nobody was listening. A test asserts all five reasons are unique, and a
separate one asserts **a quiet world cannot produce the new refusal**, which is the conflation the
check exists to prevent. `PipelineDownError` subclasses `GateRefusedError` so it still flows through
the existing handler; `run.py` now records the reason the exception carries rather than a hardcoded
label.
### T7.24 — the first investigation of a silent culprit *(one scored run, pre-registered, judged)*
**Done** (`evals/runs/RUN-2026-08-29-shipping-quote-misconfig.md`). The first agent run against
T7.22's scenario, whose evidence shape nothing else in the catalog has.

**Verdict correct on every axis.** Fault class `bad_config` ✔, fix class `config_revert` ✔, faulty
service **`shippingservice`** ✔, confidence high, judge `same_mechanism` (6 dead ends closed / 3
missed). Triage recall **1.00** (2/2), precision 0.17 (2/12). **$0.6857 agent + $0.0328 judge.**

**The ledger: five of six confirmed, and P3 falsified.** P1 (localizes first to `checkoutservice`)
held in the planner's own words. P2 held - two round-2 dispatches against shipping. P4 held -
`change_history` on shipping is the verdict's first citation and the only evidence naming
`QUOTE_SERVICE_ADDR`. P5 and P6 held.

**P3 said it would reach shipping by the dependency graph. It reached it by the trace.** The
round-2 planner: *"Traces localized the failure to the checkoutservice client span for
ShippingService/GetQuote while the shipping server handler succeeds."* A client span carries the
callee's name, so a trace on the **alerting** service names the silent one. My prediction
enumerated metrics, logs and the graph and omitted traces - the class T7.4's census records as
used in only **2 of 10** investigations, and the one this run needed.

**The registered falsifier did not fire.** It was *answers `checkoutservice` or abstains while never
dispatching against `shippingservice`*. On this run, T4.14's return-to-locus carried the agent from
an alerting caller to a silent culprit. The judge scored the registered near-misses as avoided by
name, including *"treating shipping logs showing healthy activity as proof shipping was healthy"*.

**Contamination verified from the retrieval rows**, not inferred: `exclude_origin =
'scenario:shipping-quote-misconfig'`, and the three that came back are `shipping-wrong-image`,
`cart-redis-misconfig`, `cart-bad-image-tag`. The scenario's own narrative did not return.

**The report carries `reachability answerable by: logs`** - the first run scored against a bundle
whose reachability was derived correctly after T7.22's recorder fix. Had that bug stood, this report
would have called the evidence unanswerable while the agent was reading it.

**Three discards, all recorded rather than tidied.** `20260829T202633Z` is an ordinary gate
refusal, recorded by the harness itself (a resolved incident inside the settle window - T4.13
working). The other two are mine. `20260829T200129Z`: I misread a malformed `pgrep` as a dead
process and reverted the fault out from under a live run. `20260829T200937Z`: **`faultline-ingest`
and `faultline-orchestrate` were not running**, so alerts fired and nothing turned them into an
incident.

**That second one is a finding worth keeping.** Left alone it would have waited out T7.12's budget
and recorded a **`no-alert` discard** - which reads as a fact about the scenario. It is not: the
fault fired on schedule, checkout hit 27.6% errors, four `ServiceNoTraffic` alerts were on the
board. T7.12 separated `no-alert` from `metrics-gap` because they are different findings; **this is
a third** - the world alerted, the metrics were fine, and the platform was not assembled. **Nothing
in the harness checks before injecting that the ingest endpoint is listening or the orchestrator is
consuming**, so the failure presents as a silent scenario rather than a missing service. A preflight
of the same shape as the existing world-side checks would refuse in a second instead of injecting
and waiting. **Queued, not built** - it is a harness change and this task was an agent run.

**n=1.** One observation, not a rate. It cannot separate capability from a lucky draw and is not
averaged into any sweep figure.

### T7.23 — where the checkout time goes *(investigation; remedy found, mechanism partly open)*
**Done** (ADR-0025's T7.23 addendum). T7.14 left the mechanism open, T7.22 narrowed it to *nowhere
traced*, and this closes it far enough to act on.

**Kafka is falsified, and it was the leading hypothesis.** Kafka was recreated at `01:41`, two
minutes before the excursion's `activeAt` of `01:43`, and `PlaceOrder`'s last act **blocks on
`<-Successes()`**, a shared channel - a genuinely suspicious shape. Three measurements kill it: the
`orders send` span is 0.00s; timing checkout's own logs across 30 orders puts the step that
brackets that blocking receive at **0.001s mean, 0.00s max**; and the producer's error-drain
goroutine had been idle **747 minutes**, so no produce has ever failed.

**A blocked goroutine in the handler is falsified too.** A `SIGQUIT` dump taken while the excursion
was live shows **zero** goroutines in `PlaceOrder` or `sendToPostProcessor` - about 2.5 should have
been in flight at 0.14 orders/s against an 18s span. 46 goroutines total, no leak. Also ruled out:
a flush or lock after the last child span (only `return resp, nil` follows, and nothing is parked
there), and work before the first (the first log **is** the handler's first statement).

**Established: the handler finishes in ~20-25ms while its span reports 15-30s, with nothing
executing it.** `frontend` and `loadgenerator` report the same number because they are waiting on
it, which is exactly why the affected set is those three and everything else sits at baseline with
zero errors.

**It is accumulated in-process state, and a restart clears it.** The dumped process had been up
**27 hours**. `docker restart checkout-service` returned all three services to their committed
baselines **within one scrape** - checkout 1440-15000ms -> **37.0-37.5ms** against a committed 38ms,
frontend -> 41.8ms, loadgen -> 47.8ms, zero errors - and held for the ten minutes watched.

**Stated as not established:** the mechanism inside the process (what survives the eliminations is
a span held open after the handler returns, which is a hypothesis and is not acted on), and whether
the state is checkout's or the frontend<->checkout connection's - a checkout restart clears both.
**The test for next time is to restart `frontend` instead.**

**The remedy is operational and it will return.** No code or config change: a periodic recycle
would be a compose edit and is **digest-locked**, queuing beside `memory_limiter`, kafka retention
and the `redis-cart` bound; fixing the demo's own code is out of scope under ADR-0026. The process
re-accumulates over roughly a day, so this is a remedy rather than a fix - which is the operational
finding worth recording rather than rediscovering.

**The recorder now names it at the refusal**, the same shape the memory-headroom guard uses:
`ServiceHighLatency` on those three and nothing else, no errors, prints the container and the
command. Matching is exact - an error-rate alert or a fourth slow service prints nothing, because
advising a restart during a real incident is worse than silence. **The gate is unchanged and
deliberately so:** the alert reports a true condition and refusing is right. What changes is that
refusing no longer means waiting an unknown number of hours. T7.14 measured 12.6% duty; by T7.22 it
ran ~95% across eight hours and cost this project a day.
### T7.22 — recording A and C *(slots assigned, scenarios authored; RECORDING BLOCKED)*
Stage 2 of T7.20, carried as far as the world allows. **Nothing recorded.**

**Slots assigned by applying T7.21's rule, not by choosing.** Holdout sits at the highest indices
and existing assignments are committed, so the arithmetic has no judgement in it:
`dependency_latency` holds 3 dev + 1 holdout with `-1` dev and `-2` holdout committed, leaving `-3`
and `-4` both dev -> **A takes `dependency_latency-3`, dev**. `bad_config` holds 4 dev + 2 holdout
with `-1` and `-2` committed dev, leaving `-3`/`-4` dev and `-5`/`-6` holdout -> **C takes
`bad_config-3`, dev**. **Both dev**, which contradicts T7.20's speculation that C would land in
holdout - that assumed holdout took the next free slot, and T7.21 put it at the highest. The rule's
output stands.

**Remediations recorded as claims with their basis.** A carries `restart`, measured by T7.17 for
this *mechanism* but on `cart-service`; `also_correct_remediation` is deliberately empty, because
ADR-0027 already carries one scenario holding that field by inference and a third would make a
measured field a habit. C carries `config_revert` on the mechanism - a configuration value with a
known-good prior - and **explicitly not on a remediation measurement**, with `restart` named as the
testable rival that should not work. Both declare `answers_idle_or_absent` evaluated **under the
fault**, per the gate T7.21 added.

**Blocked: the checkout excursion has escalated from intermittent to continuous.** T7.14 measured
12.6% duty in episodes of 15-60 minutes; over the twelve hours before this task it ran **~95% duty
across eight hours**, beginning at `01:43` - the same `activeAt` T7.14 recorded for the episode it
measured as ending after 3630s. It did not end. Shape unchanged (92% of checkouts under 50ms, tail
just over 5%, zero errors, every other service at baseline); duration changed. Recorded in
CATALOG.md.

**The recorder refuses and is right to.** `alerts_over_window` is ground truth, so a pre-existing
alert would be recorded as the fault's. A probe could use a scoped relaxation because its
observable was a qdisc or an error ratio a latency excursion cannot touch; **a recording has no
honest equivalent.** Two containers were cycled as the memory guard instructed - `email-service` at
99.8%, `jaeger` at 97.4% - which is the documented remedy, not a workaround.

**A window opened, A was recorded against - and A FAILED.** Injected cleanly (pumba sidecar up,
netem applied), held for the full 900s alert budget plus 300s of steady state, reverted cleanly -
and **adservice p95 never left 1.9ms. No rule fired. No bundle written.**

**And T7.20's gate finding on A was wrong.** It claimed A passed the alerting gate *on measured
evidence*: the identical mechanism at the identical magnitude took cartservice 1.9 -> ~650ms and
fired. That evidence does not transfer. **`tc netem` delays egress, and `adservice` is a leaf** -
its logs read `received ad request` and nothing else, because it serves from memory and calls no
one - so its delayed egress lands *after* its server span has closed and never enters its own span
metrics. cartservice moves because it makes downstream calls and the delay sits inside its span
while it waits. **The magnitude is irrelevant**: there is no downstream call for the delay to sit
inside. A is marked `blocked`, which releases `dependency_latency-3`.

**Third disqualification, second of the same kind, and now a rule.** B passed reachability on a
*healthy* world and lost its evidence under its own fault; A passed alerting on a *different
target* with the same mechanism. Both validated a property somewhere it held and assumed it here.
CATALOG.md now carries it: **a gate passed on one target is evidence about that target** - name the
property the result depended on and check *that*. For `dependency_latency` the property is whether
the target makes a downstream call inside the span being measured, which both surviving scenarios
do and `adservice` does not.

**C is still being recorded.** It is the one candidate whose alerting gate was probed *on its own
target* - twice, firing at T+240s both times - which is exactly the distinction the rule above
draws. Blocked only by the excursion, with a retry loop running.

**C RECORDED. Onset 169s**, `ServiceHighErrorRate/checkoutservice` at fire - matching both probes
(240s at 60s polling granularity). `capture_set` 2, current digests including
`observability_digest` and `otel_demo_image_digest`, one driver, dev split. Checkout ran **23-29%
errors** for the fault; `alerts_over_window` is checkout 6.5m and loadgenerator 0.2m. The probes'
`ServiceNoTraffic` alerts at T+420s fell outside the 469s fault window and are not in the bundle.

**The recording corrected the scenario's own design, which is the point of recording it.** C was
authored claiming shipping's logs were "the load-bearing evidence... the address it is failing to
reach". **They are not.** The capture holds 126 shipping log lines and every one is an incoming
`GetQuoteRequest` at the ordinary rate - no error line, no retry, no mention of the unreachable
host. So the logs are **exculpatory, not diagnostic**: they establish shipping is alive and being
asked for quotes, and rule out the first thing anyone checks. `change_history` is the only class
that identifies the faulty service at all, which makes this the sharpest case in the catalog for
ADR-0019's "change history is the first tool" finding. Scenario file and narrative both corrected
to what was measured.

**A recorder bug found by recording, and it had never fired before.** The manifest recorded
`reachability: {target_log_lines: 0, none_can_answer: true}` on a bundle holding 126 log lines.
`write_bundle` derives that field from the bundle directory and was called **before** the metrics
and logs were written, so it read an empty one. It went unnoticed because **no bundle had been
recorded since T7.5 added the field** - every existing value was derived over an already-finished
bundle. **A false `none_can_answer` is the worst direction for this field to be wrong in**: T7.5
added it so a scorer could tell an abstention nothing could have answered from one caused by
reasoning. Write order fixed, C's manifest re-derived, and pinned by a test that re-derives every
bundle's reachability and compares.

**Rendered, seeded, quarantine verified.** 13 bundle pages rendered; corpus seeds **8 documents,
40 chunks** from `artifacts/dev/` alone, with `currency-cpu-throttle` and `flag-service-crashloop`
skipped as INVALID. **`holdout_chunks` 0** - no holdout origin appears.

**Per-class n: `bad_config` gains a third dev scenario and the tables do not move.** It is
**recorded but not yet run by any agent**, so it contributes no accuracy to any cell; the n in
those tables counts scored runs, not catalog entries. Annotated in place. Running the agent on it
is a separate pre-registered task and was not done here.

**Occupancy:** `bad_config-3` filled; **`dependency_latency-3` is free again**, since A took it and
then failed. `dependency_latency` still stands at one recorded dev scenario - the thing the
extension was meant to fix, still unfixed.

### T7.21 — slots before scenarios *(allocation decision; no scenario assigned)*
**Done.** SPLIT.md extended to n=20 with n=30 decided, by principle and **before any candidate was
assigned** - the rule forbidding edits that accommodate a scenario means the extension is taken on
its own terms (ADR-0008's T7.21 addendum).

**What determines a class's share - four principles.** *Diagnosis paths, not equal shares*:
`bad_deploy` has three documented shapes, `bad_config` at least three, `dependency_latency` one
bounded mechanism. ***`resource_exhaustion` grows least, and that reverses this ADR's own view*** -
CPU is retired (ADR-0013) and T7.20 measured the surviving memory mechanism as having a narrow
usable band from both sides, so one mechanism with a narrow band does not earn proportional growth.
*Per-class holdout*, `round(0.3 x slots)` minimum 1, because a global 30% that leaves `bad_config`
at zero cannot support a per-class generalisation claim - which is the sentence SPLIT.md currently
admits it cannot make. *Three dev per class as a **floor, not a sufficiency***:
`cart-bad-image-tag` measured 197s and 301s on an unchanged world, so two samples cannot show a
spread - and **n=20 does not retire the "direction, not magnitude" caveat.**

**Also stated: slots are capacity, not a promise.** Three of thirteen authored scenarios are
`blocked`, which releases the slot rather than consuming it, so the catalog is **10 valid - 7 dev,
3 holdout** against 13 authored. Growth targets are in slots; the valid count trails them.

| | n=20 | n=30 |
|---|---|---|
| `bad_deploy` | 6 (4 dev / 2 holdout) | 9 (6/3) |
| `bad_config` | 6 (4/2) | 9 (6/3) |
| `dependency_latency` | 4 (3/1) | 6 (4/2) |
| `resource_exhaustion` | 4 (3/1) | 6 (4/2) |
| **total** | **20**, 30% holdout | **30**, 33% |

**Ten slots opened**, holdout taking the highest index in each class - mechanical, so the next
extension needs no judgement either. The residual steering risk is **named rather than claimed
away**: positional holdout plus alphabetical fill means an author choosing a fault *id* could
steer, and the mitigation is ADR-0008's separation of the two decisions, not the rule being
unguessable. `tests/test_contamination.py`'s mirror is updated to n=20 and its drift check is now
anchored to a named capacity table, since SPLIT.md keeps the n=10 table as committed history.

**Explicitly not decided here: whether any proposed scenario fits.** The slots were assigned with
no candidate in view; a candidate that fits is a consequence of the table, not a reason for it.

**Two findings from T7.20's probes folded into CATALOG.md.** **Reachability is evaluated *under the
fault*, not at rest** - a candidate passed T7.5's gate on 20 runtime series that stop exporting
from T+300s once faulted, and nothing in the record had said to check that; the census is computed
from recorded bundle *windows*, which include the fault, so the error is checking a live healthy
world when a scenario has no bundle yet. And **`cart-memory-squeeze`'s disqualification is recorded
with its measurements** - invisible at 200m (killed and restarted, zero alerts, zero errors, cart
p95 flat across two attempts), and at 32m alerting across seven services while its own runtime
evidence goes null. The interval between them is refused on ADR-0013's rule.

### T7.20 — three more scenarios, gated before recording *(stage 1: design only; STOPPED for review)*
PLAN.md's original T7.1 (catalog growth), begun. **Nothing recorded, no injection, no agent**
(`docs/design/t7.20-three-scenarios.md`).

**What is actually thin: seven valid dev bundles**, not thirteen scenarios - three authored
scenarios are `blocked` and two of those also carry `INVALID.md`. Per class:
`dependency_latency` **1**, and `bad_config` / `bad_deploy` / `resource_exhaustion` **2** each.

**Three proposals, four gates each** (T7.5 reachability against T7.4's census; T7.13 alerting;
injector capability without a new handler; T7.12's 180-scrape onset budget).

**A - `ad-dependency-latency`** (`dependency_latency`). Pumba netem 300ms on `ad-service`, raising
the thinnest class. **Survives all four on measured evidence**: 48 runtime series + 731 log
lines/hr (2 classes, the best-instrumented target in the census); p95 1.9ms at rest with **0 of
2398 samples over 250ms** in T7.14's census; existing handler; onset estimated 250-450s against a
measured 229s precedent. **Its remediation ships as `restart` only** - T7.17 measured
`config_revert` on this *mechanism* but on `cart-service`, and ADR-0027 already carries one
scenario holding that field by inference. A third would make a measured field a habit.

**B - `cart-memory-squeeze`** (`resource_exhaustion`). 200m against a 400MiB ceiling, 258.8MiB
resting. Adds a **third runtime** (.NET vs two JVMs) with directly relevant evidence
(`process_runtime_dotnet_gc_heap_size`, `gc_committed_memory_size`) and completes a four-class
discrimination set on cartservice. **Survives three of four.** The alerting gate is *plausible but
unmeasured*: .NET's Server GC reads the cgroup limit and may **collect harder and survive** rather
than OOM, which is exactly the shape ADR-0013 retired CPU throttling for - the mechanism applies
and nothing observable happens. The JVM precedents do not transfer, because a JVM sizes its heap at
startup. Also named rather than buried: it adds n to the class already carrying the most disputed
register rows.

**C - `shipping-quote-misconfig`** (`bad_config`). `QUOTE_SERVICE_ADDR` pointed at an address that
does not resolve - a third `bad_config` shape, breaking a service-to-service address rather than a
backing store or a flag. **Survives three of four.** Reachability passes *weakly*: **0 runtime
series**, logs only, so it must declare `answers_idle_or_absent: [logs]` and its narrative must not
lean on runtime metrics. The alerting gate is *plausible but unmeasured*: whether a failed
`GetQuote` surfaces as an error rate depends on how `checkoutservice` handles it, and nothing in
the record says.

**Stage 1b - the probes are run, and the verdict is two of three** (five injections, nothing
recorded, `docs/evidence/t7.20-probes/`).

**C PASSES, reproducibly.** `ServiceHighErrorRate/checkoutservice` at **T+240s** in both attempts,
checkout holding 22-28% errors, well inside T7.12's budget. **And the answer to the open question
is better than the design assumed: a failed `GetQuote` produces no error at `shippingservice` at
all** - its own error rate stays 0.000 for the whole fault, and the failure surfaces at its
*caller*. The alerting service is not the faulty one, and the faulty one looks clean by error rate,
which makes its logs-only reachability load-bearing rather than a formality. Blast radius: checkout
errors, then `ServiceNoTraffic` on quoteservice, accountingservice, emailservice and
frauddetectionservice at T+420s.

**B FAILS at both magnitudes probed, and the predicted failure mode was wrong.** At 200m the
container *is* killed and restarted - `RestartCount` 0->1, then 1->2->3, with .NET's
`gc_collections` counter resetting as the restart's fingerprint - and **nothing alerts**: zero
errors on every service and cart p95 flat at 1.9ms across two seven-minute attempts. Not the GC
surviving by collecting harder, as designed; the container comes back **faster than detection**,
the shape already recorded for `recommendation-memory-squeeze` at 48m. **B1 looked like a pass and
was not** - its alerts were on `frontend` and `loadgenerator`, two of T7.14's three known-tail
services, and B2 settles it with more kills and no alerts at all.

Following that scenario's own remedy to 32m makes it alert - and disqualifies it. **Its runtime
evidence goes null under its own fault**: `gc_heap_size` and `gc_collections_count` stop exporting
from T+300s because the container never runs long enough, so the 20 runtime series B passed T7.5's
gate on do not exist while it is faulted. It also becomes hard to separate from
`cart-bad-image-tag`. An interval may exist between 200m and 32m, but ADR-0013's rule applies:
hunting a number in an interval that narrow tunes to today's load rather than to the service.

**A gate the record did not have, and now does: reachability must be evaluated under the fault,
not at rest.** Nothing before this said so, and B is the case that shows why.

That is the gates working. Two scenarios have already been proposed and abandoned late; this cost
five probe injections and no recording session.

**A prerequisite none of them can skip: SPLIT.md has no free slots.** All ten `n=10` slots are
filled; these need `dependency_latency-3`, `resource_exhaustion-4`, `bad_config-3`, which do not
exist. SPLIT.md's rules make the extension a *separate, earlier decision* - "committed before
authoring, do not edit to accommodate a scenario", and slots fill alphabetically with "no judgement
in it". **So the split of these three is not ours to choose**, and proposing all three as dev would
be choosing it. `bad_config` has zero holdout representation and SPLIT.md's rationale sends holdout
capacity to classes that lack it, so a principled extension is *likely* to make `bad_config-3`
holdout - which would make C a holdout scenario. The extension must land first, against unnamed
slots, and decide that without these three in view. It is the task SPLIT.md already names.

**Queued for stage 2**, on approval: probe B and C's alerting gate; extend SPLIT.md against unnamed
slots; then rehearse and record whatever survives, per ADR-0014 with current digests and one
driver, narratives to ADR-0009 and the current capability stamp, pages rendered, corpus seeded.
**The agent is not run on them** - that is a separate pre-registered task.

**World note (T7.19 asked this be recorded when done): `redis-cart` was flushed just before this
task** - 35,105 keys / 7.16MB down to 17 keys / 1.78MB, by `FLUSHDB` rather than a recreate
(`RestartCount` still 0, container up since 2026-08-28T02:20:03Z). An unrecorded world change: no
digest covers accumulated runtime state, so it is written here instead.
### T7.19 — the slow fault the catalog cannot hold *(measurement; ADR-0024 closed)*
**Done.** ADR-0024's open decision is closed: **the `scale` class stays empty, with a reason.**
No agent, no injection - the world watched as it normally runs
(`docs/evidence/t7.19-redis-growth/`).

**The extrapolation was tested first, and it measured the wrong quantity.** T7.13's ~90 minutes
came from `docker stats`, which counts page cache. `redis-cart` runs RDB persistence
(`save 3600 1 300 100 60 10000`), so every bgsave writes a multi-megabyte `dump.rdb` into cache;
the kernel reclaims that before it OOM-kills. What binds is `anon + slab` - **8.1 MiB of 20 MiB,
38.7%** - on a container reading **96.2%** on `memory.current`.

**The slope, measured.** Growth is **linear**, not decelerating and not bounded: `expires=0`, every
TTL `-1`, `maxmemory 0`, `noeviction`, 204 bytes/key. Keys **+0.192/s over 27.6 hours** (container
uptime, 0 restarts) and +0.31/s over a fresh 11 minutes; `anon` **+64.8 B/s** lifetime.
**≈55 hours to the ceiling at rest**; ≈4 hours under sustained 50x load, scaling by the world's
*measured* 102 req/s throughput ceiling - 12x baseline, not 50x - and **labelled an extrapolation**.

**And T7.13's supporting claim is falsified.** It said the surge left redis "permanently 11 points
higher" and that it "did not come back down when load did." Over 11 minutes at rest
`memory.current` fell at **-2060 B/s** as cache drained. It came back down; T7.13 looked once.

**Decision: it does not belong.** Four constraints, the last fatal alone. T7.12's correlate budget
is 180 scrapes (900s) from a catalog whose onsets run 166-390s - even 4 hours needs **16x** it, and
the recorder is sized to match (`DEFAULT_ALERT_TIMEOUT` 420s, `CLEAR_TIMEOUT` 600s). Seven
scenarios already take over two hours, and every stamp move re-pays the sweep. T7.14 measured the
gate refusing ~11% of readings at rest in 15-60 minute episodes, so over four hours the question is
how many, not whether. **And the fault does not revert**: only `FLUSHDB` or recreating the container
clears it, so the world after is not the world before - which contradicts the catalog's central
claim and no digest can see it, since it is accumulated runtime state rather than file content.

**An empty class with a stated reason is a result** - ADR-0013's precedent, retired on measurement
rather than retuned against an interval the evidence says is empty.

**If anyone revisits it, the remediation is unknown too.** `FLUSHDB`, recreating the container, and
raising `maxmemory` are three candidates spanning two classes, and T7.17 showed what guessing costs
- a ground truth that stood wrong for three stamps. Any label here needs T7.17's treatment first.

**Queued, not left:** a bound on `redis-cart` joins the digest-locked queue beside `memory_limiter`
and the kafka retention change (above), because `maxmemory` edits `world/docker-compose.yml` and
moves `compose_digest`. The immediate consequence is documented at
`rehearse.MEMORY_HEADROOM_PERCENT`, where it will fire.

### T7.18 — the proposer, and what it would take to act *(design ADR; nothing built)*
**Done** (ADR-0028). The design for ADR-0020's ninth role, and for the action plane that has never
had a task number. No implementation, no world, no model calls.

**Why now: T7.17.** Every fix-class number in this repository says the agent **named** a fix. Not
one says a fix was carried out - and T7.17 had to establish by hand, over eight live injections,
that one of the named fixes even works. A benchmark that scores remediation without ever executing
one is scoring vocabulary.

**Six marked decisions**, two of which revise ADR-0020's original sketch:

1. **A proposal is a predicate, not a command string** - class, graph-resolved target,
   `rests_on` by `result_id`, `expected_effect` as a predicate over the four tools' surfaces,
   `confirm_within`, `if_wrong`. A command can be diffed against ground truth and nothing else; a
   predicate can be *evaluated against the world*, which is the only thing that would make this
   measure remediation rather than phrasing. **Revises ADR-0020's "a concrete action".**
2. **The proposer does not act.** A separate executor, a human between them, per-proposal approval,
   no confidence threshold - a threshold makes the model's own calibration the safety boundary,
   which ADR-0020 declines to trust anywhere else. Argued from: no false-positive rate exists
   because no proposal has ever been made; T7.17 shows the project's own fix understanding was
   wrong for three stamps; and ADR-0013 measured what a wrong `restart` costs.
3. **No write tool in the investigation runtime.** ADR-0019 §4 measured that read-only here is a
   property of the **tool surface**, not the credential - Prometheus and Loki are unauthenticated.
   So one write tool removes the property for the whole runtime, not for one role, and the four
   specialists gain a capability by neighbourhood. The executor is a separate process outside the
   runtime. **Revises ADR-0020's sketch of where the action plane lives.**
4. **Four scored axes, never collapsed**: class (ADR-0027's accepted set), target, grounding, and
   **prediction - decidable only by executing**. Until an executor exists the fourth is reported
   **not measured**, not passed and not omitted. `unexecutable` is a scored outcome, not an error.
   A proposal right by an untested route is **correct and a catalog defect**, and promotes to
   `also_correct_remediation` only after a deliberate re-test - never from one run, because n=1
   against a varying world is what T7.17 spent eight attempts avoiding.
5. **A third contamination axis: the world as an oracle.** If a proposal can be executed and
   observed, a propose-execute-observe loop converts diagnosis into search and would score well
   without diagnosing anything. **One proposal per incident, executed at most once, and the outcome
   never re-enters agent context.** Belongs in ADR-0008, which anticipated a further axis; folded
   in when the role is built.
6. **The stamp moves the moment `PROPOSER_SYSTEM` exists**, and the `Proposal` contract enters the
   hash. Every recorded run becomes incomparable with everything after, which is the stamp working.
   So the role lands **with** a re-sweep, as T7.10 re-founded the benchmark when the world moved.

### The implementation this would need, and it is not queued
Task numbers named so the shape is visible; none is started, and each is a separate decision.

- **T8.1 - the proposal contract and the role.** `Proposal`, `PROPOSER_SYSTEM`, wired after the
  synthesizer into the `PROPOSING` state ADR-0020 already reserves. Stamp moves here.
- **T8.2 - the trajectory table.** `trajectory_proposals`, with an `ALTER` beside the
  `CREATE TABLE IF NOT EXISTS` - T7.10 lost a scenario to `UndefinedColumn` because the in-memory
  double the tests use does not catch a missing migration.
- **T8.3 - the proposer's budget, measured.** A tenth per-agent bound, set from its first sweep
  rather than guessed; T4.7 measured what a wrong bound costs.
- **T8.4 - scoring on three axes**, with prediction reported `not measured`.
- **T8.5 - the re-sweep**, because the stamp moved. Without it the record has a discontinuity
  nobody measured.

**Not queued at all, and deliberately: the executor, any write tool, any credential on the world,
the approval interface, and the prediction axis.** ADR-0028 §3 is the argument for why those are a
second system rather than a later commit in this one.

### T7.17 — which fix actually works *(experiment; 8 live attempts, pre-registered)*
**Settled by measurement, and the register was wrong** (ADR-0027,
`docs/evidence/t7.17-fix-class/`). Protocol registered and committed before the first injection.

**Both fixes work, 3/3 each.** Read from the qdisc directly rather than inferred from a percentile
that lags two minutes: `restart` clears the netem durably 3/3, and so does **deleting the qdisc**
(`tc qdisc del dev eth0 root`) with the container never restarted and the pumba sidecar still `Up`
at +120s. Pumba applies its rule once and waits out `--duration` rather than reconciling, so
nothing reapplies it. p95 642-671ms under fault; back to **1.9ms**, the committed baseline, on all
three qdisc-delete attempts. The injector's own revert (control) 2/2.

**So `config_revert` names something real here, and the register said it did not.** Its entry was
resolved against the agent on the premise *"there is no configuration to revert"*. There is: the
network configuration on the affected service. It is also the **less disruptive** fix - it restores
p95 to exactly 1.9ms where restart leaves 3.8-4.8ms, the post-restart warming CATALOG.md documents.

**Neither label is wrong; ADR-0022 §1.2's tiebreak just cannot decide.** It says the class is
decided by which remediation works, and assumes one does. Two do. Scoring against whichever the
author wrote first is grading on taste, not on the rule.

**What the scorer does now:** `Scenario.also_correct_remediation`, a list of remediations
**measured** to fix the fault durably; `LabelScore.correct` accepts the labelled class or any
member; `correct_by_alternative` keeps it visible that the answer was right by the second route.
Deliberately **not** in `scenario_fingerprint` - `expected_remediation_class` is unchanged and the
fingerprint verified identical (`c982653939a5c1ff`), so **no bundle is invalidated**.

**The register keeps both entries.** The fix-class one is resolved *for the agent*, kept rather
than deleted because it records a disagreement settled wrongly for three stamps. The fault-class
one keeps `dependency_latency` and **loses its reasoning**: it was resolved by the same fix test,
which both readings now pass, so it discriminates nothing. It stands on other grounds - nothing on
cartservice was *set wrong*. Corrected rather than left, because a falsified premise under a
conclusion one agrees with is how a register stops being evidence.

**Tables corrected, originals struck and visible** (T7.3's precedent). RESULTS.md S6 class of fix
**4/5 -> 5/5**; SWEEP-2026-08-26 **6/7 -> 7/7**; taxonomy `dependency_latency` fix **0/1 -> 1/1**
in both sweeps and totals **6/7 -> 7/7**, **3/4 -> 4/4**; evidence and locus arms **5/6 -> 6/6**,
**3/4 -> 4/4**, **6/7 -> 7/7**. **The holdout moves too**: `productcatalog-dependency-latency` ran
the same mechanism, so held-out fix class goes **2/3 -> 3/3** and entry 1 **0/1 -> 1/1**. A
correction that improves a headline deserves more scepticism than one that worsens it, which is
why it rests on eight recorded attempts and a protocol registered first.

**Stated rather than buried:** every attempt ran with the gate **RELAXED, not PASS** -
`ServiceHighLatency/checkoutservice` (T7.14's characterised excursion) fired throughout, 90+
minutes. The relaxation was written before it was used and is scoped: proceed only when every
refusal is that excursion on services other than the target and `cartservice` is at baseline,
which it was, 1.9ms before every injection. A checkout latency excursion cannot put or remove a
qdisc on cartservice. **And `productcatalog-dependency-latency` was not tested directly** - it
carries the field by inference from the identical mechanism, which is what was tested. **The agent
still performed no remediation**; it holds four read-only tools. This settles whether the label was
true, not whether the agent could carry the fix out.

### T7.16 — the world is somebody else's repository *(provenance; one field added, the clone gets none)*
**Done** (ADR-0026). T7.15's last set-aside hole, and it turned out not to be the hole.

**The facts.** The clone is exactly at `v1.2.1` (`9d9056d3…`) with **no tracked file modified**.
The untracked file is `world/src/grafana/provisioning/datasources/loki.yml` and it is **empty, 0
bytes** - a Docker mount point, not something anyone wrote. The demo's Grafana bind-mounts
`src/grafana/provisioning/` as a directory and `telemetry.yml` mounts a single file at
`datasources/loki.yml` inside it; Docker materialises that target and, the parent being a host
bind mount, the empty file lands in the clone. Verified from the container's mount table: Grafana
reads the real content from `compose/grafana-loki-datasource.yml`, which overlays it. **Nothing
reads the empty file.** The other untracked file is `.cloned`, our own marker.

**What `compose_digest` covers by residence:** one of its three inputs lives in the clone
(`world/docker-compose.yml`), two in this repo. `observability_digest` adds four here and two more
in the clone. So **three clone-resident files reach a bundle and all three are already content-
digested.**

**And the clone is not the source of what runs** - `make world-up` passes `--no-build`, so all
sixteen demo images are pulled. The clone's service source and Dockerfiles are inert.

**Decision 1: record nothing about the clone.** A commit SHA catches nothing a bundle can see - a
commit touching any of the three digested files already moves a digest, and one touching anything
else touched inert build context. A dirty flag is redundant where it matters and noise where it
does not. An untracked-file count would be **actively harmful**: it would flip on a Docker artifact
that reappears every `world-up`, which is the `ffs_stub_image_id` failure ADR-0014 already names.
**This was untidy, not a provenance gap.**

**Decision 2: the real gap is that `otel_demo_image` records a mutable tag.** What runs is a pulled
image identified as `...demo:v1.2.1-cartservice`. If upstream republished that tag, every bundle
would claim the same world while running different code and **nothing recorded would move** -
`compose_digest`, `ffs_stub_source_digest` and `observability_digest` would all agree, because none
describes image contents. Added `world.otel_demo_image_digest` (`...demo@sha256:97d55955…`),
additive, absence meaning unknown. This does not contradict ADR-0014's refusal to compare
`ffs_stub_image_id`: the stub is **built** here so its id churns; these are **pulled**, so the
digest is stable and is a content identifier. Same principle, opposite situation.

**Honest about the odds:** a released tag being republished is unlikely, and the field records one
image as a proxy for a release published atomically, not proof of the other fifteen. Recorded
because it is free, stable, and the last mutable link - not because it is expected.

**Decision 3: the untracked file is documented, not removed or adopted.** Removal is a no-op the
next `world-up` undoes; adoption is wrong for an empty file Docker made and nothing reads. The
explanation sits in the Makefile beside the clone target, where someone checking the clone will be.

**Pinned:** a test fails if a clone SHA or dirty flag is ever added, sending the reader to the
argument rather than letting it in by habit; and a test pins the premise - `--no-build` must stay,
and the clone-resident digest inputs must stay the three named. **If the world is ever built from
the clone rather than pulled, ADR-0026 is invalid** and the SHA argument reverses.

### T7.15 — the rules were never under cover *(provenance; additive)*
**Done.** T7.14's hole closed, and five more of the same kind found beside it.

**The decision: an additive sibling, not an extension.** Adding these paths to `compose_digest`
changes the value it computes, so the twelve recorded bundles would keep asserting the old value
while a recomputation produced a new one. The guard on them rests on a property stated in its own
comment - the digests *"are reproducible from the repository and move only when the world's
definition moves"* - and extending breaks both halves: recorded values stop being reproducible, and
the digest moves for something that is not a world change. Two bundles either side of the
redefinition would compare unequal on an unchanged world. **By ADR-0014's own bar that is a change
that makes existing bundles false**, arriving by a quieter route than usual.

So: `world.observability_digest` plus `world.observability_files`, siblings of `compose_digest`.
Nothing is rewritten and no bundle is invalidated.

**Which kind of field, on T7.5's test: the asserting kind.** A bundle does not contain the alert
rules, the scrape config or the collector pipeline, so nothing in a capture can settle what
`alert-rules.yml` said when it was recorded. `reachability` was backfillable because it only read
what the bundle already held; this cannot be, and computing today's digest into an older bundle
would assert something unverifiable - the identical argument ADR-0014 already made refusing to
backfill `compose_digest`. **Absence means unknown, not unchanged.**

**Every hole found, all six now covered** (`provenance.OBSERVABILITY_FILES`): the alert rules
(T7.14's); `prometheus-config.yaml` - `scrape_interval: 5s`, evaluation interval, `rule_files`, and
`run.SCRAPE_INTERVAL_SECONDS` is pinned against it; `alertmanager.yml` - whether a firing alert
reaches the orchestrator at all and how it is deduped (ADR-0015); `promtail-config.yml` - which
containers ship logs and under what `service` label, so it decides every `logql_query` result and
T7.4's log census with it; and both **otel collector configs** - the spanmetrics connector, which
decides whether `calls_total` and `latency_bucket` exist and, by not overriding them, the histogram
bucket boundaries **T7.14's entire analysis turned on**. One digest rather than six, because they
are one pipeline; the per-file map is what makes a mismatch name the file.

**Excluded, as decisions rather than oversights:** Grafana provisioning (human-only), the world's
service source (covered by `otel_demo_image` and the upstream tag), and
`world/src/prometheus/prometheus-config.yaml`, which is **dead** - `telemetry.yml` points Prometheus
at `--config.file=/etc/prometheus/faultline-prometheus.yaml`, so the demo's own config is mounted
and never read.

**Noted while surveying:** `world/` is gitignored and is its own clone pinned at tag `v1.2.1`, so
`compose_digest` already reaches outside this repository's version control for
`world/docker-compose.yml`. The clone is not verified clean at its tag, and it currently carries an
untracked extra file. Not fixed here; it is a different mechanism from a digest.

**The guard fires where a person will see it** - against the repository as it stands, not
bundle-against-bundle, because the drift worth catching happens when somebody edits a rule rather
than months later at the next recording. It names the file that moved, says what each file decides,
and says what it means for older bundles: not wrong about what happened, but no longer comparable
with anything recorded after. **It is vacuous today and that is correct** - no existing bundle
carries the field, so it goes live with the first bundle recorded after this. What is live now is
the shape test: it edits `alert-rules.yml` for real, asserts the digest moves, asserts only that
file's digest moves, and asserts the message names it.

### T7.14 — the rule that fires at rest *(diagnosis + gate-side fix)*
**Done, and it corrects T7.13's diagnosis rather than building on it** (ADR-0025).

**T7.13 said degenerate histogram; it is a real tail.** `checkoutservice` at rest carries ~136
observations, not too few: 93% of checkouts finish inside 50ms and the rest are genuinely slow,
~1.5% over fifteen seconds. That tail sits within a percentage point of 5%, which is where p95
reads - so p95 lands at ~38ms or in the thousands depending on which side of 5% it fell, and the
jump is three orders of magnitude because the buckets up there run 1000→5000→10000→15000→∞.
**A min-sample guard would not have suppressed one of these firings.**

**Which services, how often.** Twelve hours at 15s: `checkoutservice` median **37.8ms** with 11.0%
of samples over the gate's ceiling, `frontend` 42.3ms / 3.9%, `loadgenerator` 48.0ms / 4.8%. The
other eleven services: **zero** samples over 250ms. All three are the checkout path, and their
medians are their committed baseline (`20260824T033742Z`: checkout 38ms, frontend 42ms). The
excursions are episodes - **two in twelve hours, 3630s and 900s, 12.6% of wall clock** - and the
first begins at `01:43:03Z`, the `activeAt` of the alert T7.13 saw.

**Yes, a past refusal traces to this.** Both 2026-08-27 gate refusals recorded
`p95_over_ceiling_ms: {checkoutservice: 15000.0}` beside their genuine causes (a silent
`accountingservice`, a stranded incident). Those causes were repaired; this one was never
diagnosed and hid inside "world not quiet". It goes back further: `evalharness.gate`'s own
docstring cites T3.4 finding the world *"already degraded (checkoutservice and frontend pinned at
15000ms p95)"* as founding evidence. The `accountingservice` half of that reading was real; the
p95 half was this, and the docstring now says so.

**Fixed gate-side, and the rule is deliberately untouched.** The rule reports a true condition, and
changing it would falsify two recorded bundles - `cart-dependency-latency` and
`productcatalog-dependency-latency` carry `ServiceHighLatency/checkoutservice` as genuine fault
evidence (all 9 latency entries in the catalog come from those two). The gate is not softened
either: it still refuses, because injecting during an excursion would put a pre-existing alert into
the fault's blast radius. Roughly one attempt in eight is refused and retried.

**A robust statistic was tried and rejected on measurement**: median-over-window moves the refusal
rate 11.3% → 11.1%, because the excursions are sustained and there is nothing to smooth.

**What changed is that the gate records the window it already fetched.** `_latest_by_service`
pulled 180s of p95 and threw away eleven of twelve samples; four refusals were recorded as one
scalar each, so none of them can say spike or episode - diagnosing them meant a live probe, and by
then the windows were gone. `p95_excursions` now records samples-over, samples, sustained, median
and max per service, and a refusal on one of the three measured services says it is the
characterised excursion rather than degradation. **Naming is not exemption.**

**`alert-rules.yml` is not digest-locked**, and that is the problem rather than the reassurance:
`compose_digest` covers three compose files only, so an alert-rule change would silently alter
every future bundle's `alerts_over_window` with no manifest field to show it - the exact failure
ADR-0014 was written to prevent, on a file outside its cover. Queued, not fixed here.

**Open: why the checkout path has a multi-second slow mode.** It is not in the 2026-08-24 baseline
and the world changed at T7.1, but the pre-change series is gone, so that is a correlation and
stays labelled one.

### T7.x — redis-cart's capacity ceiling *(open decision; recorded, not acted on)*
**Recorded at T7.14, deliberately not acted on.** `redis-cart` runs `redis:alpine` with
`maxmemory: 0` and `maxmemory_policy: noeviction` against a **20MiB** container ceiling and
`restart: always`. Nothing evicts, so usage is monotonic in *cumulative* traffic rather than
current load: measured stepping 46% → 59% across T7.13's 20-minute probe and not returning when
load fell. At rest it grows ~39 B/s.

It is the one resource in the world a sustained surge does drive to a page - extrapolating, **~90
minutes**, an order of magnitude past the catalog's 166-390s onset range. That makes it the only
known route to a real `scale`-class scenario, the class ADR-0024 records as otherwise unreachable
here.

**The decision is open.** ADR-0024 §5 lays out the three options - a saturation alert rule, a long
scenario, or accepting the class stays empty as ADR-0013 left CPU throttling. **What would settle
it:** one measurement, whether sustained 50x load actually OOM-kills `redis-cart` and what the page
looks like when it does. That is a ~2h unattended run and nobody has taken it. Until then the 90
minutes is an extrapolation from a 20-minute slope, not an observation, and should be quoted that
way.

### T7.13 — the scale class gets a scenario *(design + measurement; nothing recorded)*
**Authored and blocked, on measurement.** Set out to record the catalog's first `scale` scenario.
The design stands, the recording does not exist, and the reason is measured (ADR-0024).

**`scale` is not a fault class.** `FaultClass` has four members in the scenario schema and the
same four plus `unknown` in the agent contract; SPLIT.md allocates slots by fault class and has no
`scale` slot. It exists only as a `RemediationClass`. The `scale` row in the taxonomy sweep's
*fault class* table is a mislabelled row, corrected here. Adding `scale` to `FaultClass` is not
the fix: the enum is hashed into `runtime_version` via `contracts.model_json_schema()`, so it
would move the stamp and break comparability with every recorded run - its own decision, not a
side effect of authoring a scenario.

**The boundary, stated so it does not import a second dispute.** `scale` and `resource_exhaustion`
are on different axes - the first is what fixes it, the second is what happened, and this scenario
is both. The boundary that matters is between remediations: **`config_revert` when the constrained
resource was changed, `scale` when it was not.** It is decidable by a tool call rather than by
reading - `change_history` against the service that is failing to serve shows a change in the
first case and nothing in the second. That is what makes it unlike the change-versus-symptom
dispute, where change and symptom sit on the same service and both readings are defensible.
It also forces the design demand-side: any fault that removes capacity from the target is
reversible by construction, so its honest remediation is `config_revert`.

**T7.5's gate, applied before recording**, measured live because a scenario with no bundle has no
captures for T7.4's census to read: `cartservice` 20 runtime series and 4738 log lines/hour (2
classes), `redis-cart` 0 and 72 (1 class), `loadgenerator` 0 and absent from Loki's `service` set
(0 classes). Declared `[]` with the plain statement the gate asks for: **this narrative must not
turn on idle-or-absent** - not because the evidence is unreachable but because nothing goes idle
or absent under this fault.

**The blocker: 50x offered load for twenty minutes tripped no alert.** Throughput saturated at
**102.4 req/s** and stopped responding to load - 100 to 500 concurrent shoppers bought 11% more
throughput, which is a capacity ceiling. Behind it cart-service went 70%→83% of its 400MiB and
settled; frontend 67%→76% and settled; no OOM, no restart, frontend CPU 22.9% of one core of ten.
All three alert rules are structurally blind to this shape: saturation queues rather than errors,
span metrics score only requests that completed (ADR-0013 from the other direction), and traffic
plateaus rather than stopping. **A fault that opens no incident can never dispatch an agent.**

**A third obstacle, found trying to commit it: the schema cannot express it either.**
`test_scenario_injections_match_the_fault_they_cite` binds a scenario's `fault_class` to the
injector definition's, and `injector.catalog` is authoritative. The only way to steer the load
driver is an env var, which is `BadConfigFault` - so a demand-side scale scenario can only be
committed as `bad_config`, i.e. as a claim that the load generator was misconfigured. It was not,
and the boundary argument above depends on that being true. **No scenario file is committed**: the
guard is right and the label would be false. `blocked: true` was not the right home either - that
flag is for injectable-but-not-observable, and this is that *and* unlabellable. SPLIT.md unchanged.
**`scale` stays n=0, now with a reason rather than an absence.** The injector keeps the load-surge
mechanism so the 90-minute `redis-cart` path in ADR-0024 is reproducible.

Two things found on the way. A pre-existing `ServiceHighLatency/checkoutservice` fires at baseline
from histogram degeneracy at 0.66 req/s and **cleared under load** - a false positive that can
refuse the baseline gate. And `redis-cart` is a latent capacity defect in the committed world:
`noeviction`, no `maxmemory`, 20MiB ceiling, monotonic in cumulative traffic - it stepped 46%→59%
across the probe and did not come back down.

**Not exercised: T7.12's scrape-counted wait.** The probe was manual, so `wait_for_incident` never
ran. Recording this scenario would have been its first live exercise and would have ended in a
`no-alert` discard - correctly, and distinguishably, which is the point of T7.12.

### T7.12 — the wait counts scrapes, not seconds *(mechanism; harness-side)*
**Done.** The deadline mechanism T7.11 queued. The correlate wait was denominated in wall-clock
seconds, so a suspended host spent the budget while the world produced less evidence than the
seconds implied - and a clock cannot notice. T7.11 cost `frauddetection-memory-squeeze` to exactly
this: a sixteen-minute telemetry gap inside a 900s deadline, on a scenario that pages at T+390s.

**The budget is now scrapes.** `CORRELATE_SCRAPES = 180`, derived from the catalog rather than
guessed: recorded onsets run 166-390s across the twelve current bundles and 165-469s across every
recording ever archived (n=20), and the longest `for:` clause is 3m. 180 scrapes is 900s of world
time - 1.9x the longest onset ever seen. Deliberately the same coverage the old deadline intended:
**the value was never the problem, the unit was.** On a healthy world the wait still ends at
exactly 900s; a test pins that equivalence.

Scrapes are counted as `max(count_over_time(up[Ns]))` - `up` is synthetic, present per target, and
appended once per scrape, so counting it counts chances to alert. (Not `prometheus_tsdb_head_*`:
this deployment does not scrape Prometheus itself, and that counter is absent.)

**A gap no longer ends the wait - it fails to advance it.** T7.11's sixteen minutes now cost zero
of the 180 scrapes, so the world resumes and the alert lands inside the budget.
`CORRELATE_CEILING_SECONDS = 1800` is the wall-clock backstop on a world that never returns;
`CORRELATE_GAP_SECONDS = 60` (twelve intervals) is what distinguishes a hole from jitter.

**Two discards, not one.** `WorldStoppedReportingError` records `metrics-gap`; `NoAlertError`
records `no-alert`. The manifest says which, because they are different findings and T7.11's was
recorded under the wrong one. Only `no-alert` is evidence about a scenario.

**The stamp does not move** - `1b0e7cbb4c47`, unchanged. The stamp hashes role prompts and
contract schemas; no part of `evalharness` reaches it, so runs before and after T7.12 stay
comparable. Same precedent as T4.7 excluding budget bounds. Pinned by a test.

Not re-run: `frauddetection-memory-squeeze`'s S6 discard stands as recorded (T7.11's position).
This changes how the *next* sweep behaves, not what the last one measured.

### T7.11 — the control that did not page *(characterisation; no agent, no model calls)*
T7.10's discard, explained. **contract not written.** Two direct injections with the alert path
watched, plus the historical record Prometheus still holds
(`docs/evidence/t7.11-control/README.md`).

**It does not reproduce.** Two attempts, both firing: `pending` at T+201s in both, `firing` at
**T+382s** and **T+381s** against the bundle's **390s** - within nine seconds of the recording and
of each other. The rule is `rate[3m] == 0` for `3m`, so pending at T+201s predicts T+381s, which
attempt 2 hit exactly. The paging path is arithmetic and the arithmetic holds.

**What actually happened is a suspended host, and the evidence is decisive.** T7.1's retention
change bought the ability to answer this - the run is four days old and would have been
unanswerable at 6h. `ALERTS{ServiceNoTraffic, frauddetectionservice}` over the window returns one
series, `alertstate="pending"`, from 09:11:00 to 09:15:30, never firing; the run's 900s deadline
expired at ~09:08. And the metrics store has a **sixteen-minute hole from 08:55 to 09:11 in which
all fifteen services vanish and return together** - a shape no fault on one service can produce.
The scenario was about three minutes from paging when the harness gave up.

**The kafka hypothesis is not supported.** The bundle it matches was recorded *after* the heap
cap, so the cap cannot have moved the timing; and the failure was not scenario-shaped.

**A separate kafka finding, and it falsifies T7.1's own prediction.** The heap cap is in effect
and irrelevant: `KAFKA_HEAP_OPTS=-Xmx400m` with container RSS at **1866 MiB of 2048 - 93.3%**,
**4.7x the heap cap**, having been 585 MiB shortly after T7.1's rebuild ~14.5 hours earlier. T7.1
argued a cap would stop growth that a limit raise only deferred; **it did not**, because the growth
is outside the Java heap - kafka mmaps its index files and its log-segment page cache counts
against the cgroup, and no `-Xmx` bounds either. The shape matches what CATALOG.md recorded
*before* the cap. Two points rather than a curve, but the endpoint is already past the pre-flight
gate's 90% threshold.

**The real fix is bounding retention** - `log.retention.bytes`, `log.segment.bytes` - or accepting
the documented cycle-between-batches. **Digest-locked**: it edits the compose files feeding
`world.compose_digest`, so it would invalidate all twelve bundles and need another uniform
re-record. It queues beside the `memory_limiter` change and does **not** land here.

**What it means.** For the S6 table: the discard was **environmental, not a result** - not evidence
about the world, the agent, or the scenario, and S6 stands as six scored runs. For the catalog:
the scenario and the catalog are healthy; kafka is not, and will trip the gate roughly daily until
the retention change lands, which is a standing tax on every rehearsal and every scored run rather
than one scenario's problem.

#### Queued: the correlate deadline is not robust to a suspended host

**The defect is that the deadline is denominated in wall-clock seconds.** The run spent its full
900s wait while the world produced ~16 minutes less evidence than that wait implies, and a deadline
measured in time cannot notice. From inside the harness a suspended host and a world that will not
alert are the same event: a deadline expiring with no incident, and the same discard message.

**A better deadline keys on elapsed scrape samples rather than wall clock** - what the wait is
really asking is whether the world has had enough chances to alert, and a scrape is that unit, so
a suspended host stops the clock instead of exhausting it. **A cheaper backstop is a gate on a
metrics gap**: if the store has a hole inside the wait window, the honest outcome is "the world
stopped reporting", which is a different finding from "the fault did not fire" and arguably not a
discard at all. Both are harness-side, neither moves the stamp, and **neither is built here** -
changing how every scored run decides it has waited long enough deserves its own task.

#### ~~Queued: kafka's growth is not bounded by a heap cap — the real fix is retention~~

> **FALSIFIED at T7.26 by re-measurement. Do not execute this.** Retention bounds log data; the log
> directory is **14 MB**. The container holds **1.78 GiB of `anon`** against **52 MB of page cache**,
> and the G1 heap is exactly at its 400m cap. The growth is JVM *native* memory, which neither a
> heap cap nor a retention bound touches. Executing this would have moved `compose_digest`, forced
> twelve re-records, and fixed nothing. **Replaced by a measurement task** — run Native Memory
> Tracking and find which arena holds the 1.4 GiB the heap does not. See
> [`docs/design/t7.26-queue-specification.md`](../design/t7.26-queue-specification.md) item 2.
>
> **ANSWERED at T7.27, and the compose change T7.26 was waiting for now exists.** No NMT category
> holds it: filling every one to its reserved ceiling caps the JVM at **0.87 GiB** against
> **1.86 GiB** observed, and the heap sits exactly at its 400m cap. Measured in the act, ~55 MB/hour
> accumulates **outside NMT entirely**. The container is glibc 2.28 with 97 threads and **68
> anonymous regions of 63.9 MB** - the per-thread arena signature. **The JVM is not leaking; glibc
> is holding freed pages.** `MALLOC_ARENA_MAX=2` takes the arenas 68 -> 0 and mapped address space
> 7,413 -> 2,456 MB. It is a `compose_digest` input, so it is digest-locked. Full breakdown:
> [`docs/evidence/t7.27-kafka-memory/`](../evidence/t7.27-kafka-memory/).

The original entry, kept because the reasoning that produced it is the record:


**Digest-locked.** Bounding what kafka retains (`log.retention.bytes`, `log.segment.bytes`) so
there is less on disk to map and cache edits the compose files feeding `world.compose_digest`, so
it would invalidate all twelve bundles and need another uniform re-record. It queues beside the
`memory_limiter` change.

**The tripwire has already been crossed once.** Kafka was at **89.69%** when T7.11 began, a hair
under the pre-flight gate's 90% threshold, and **93.37%** twenty minutes later - it crossed during
the task's two injections. **The next sweep may start refusing at the gate**, and the documented
interim remedy remains `docker restart kafka` followed by the consumers, which do not reconnect on
their own.

#### The discard stands, and the S6 table is corrected rather than qualified

**Position taken.** It stands as recorded: it happened, ADR-0022 3.3 keeps discards visible "so the
number of runs is a fact nobody can hide by tidying", and T7.10's pre-registration said
discard-and-continue with no re-runs. Re-running it now that the cause is known to be environmental
would be re-running to improve a number, and that the improvement would be *fair* is not the test.
S6 was a seven-scenario sweep that scored six.

**What the table needed was not softening but a falsified claim removed.** T7.10 published a kafka
hypothesis for that row; it has been tested and refuted, so the row is relabelled from "possibly
the world" to "environmental - not a result", with the original reasoning left visible beneath the
correction in both `SWEEP-2026-08-28-refound.md` and `RESULTS.md`. **Coverage stays quoted over the
six runs that produced a verdict** - the denominator was never seven, and inflating it now would be
the same error pointing the other way. The five-of-six agreement and the triage identity never
included this row.

The seventh scenario says "the host slept" - not "the control failed", not "the world changed".

### T7.10 — the benchmark, re-founded on the world that exists *(run)*
Every published figure was measured on the pre-T7.1 world and the re-recorded world had no sweep
at all. **contract not written.** Pre-registered before running
(`evals/runs/PREREGISTRATION-2026-08-28-refound.md`); results in
`evals/runs/SWEEP-2026-08-28-refound.md`. $3.37 agent + $0.22 judge.

**Not an experiment on the agent, and the file says so.** Stamp and budget identical to S5; the
world is the only thing that moved. Every S5-to-S6 comparison crosses a world boundary and cannot
separate the world's effect from run-to-run variance at n=1 per side.

**Result: 6 of 7 scored, coverage 5/6, fault class 5/5, and no fault class changed.** Every
scenario that produced a verdict produced the same verdict as on the old world.

**Two scenarios did not produce a comparable result, and they attribute differently.**
`shipping-wrong-image` abstained with **zero** dispatches at the failing service against three in
S5 - the collapse T4.12 identified as the predictor - and it is **not** traceable to the capture,
because the service was in its blast radius both times and both runs made seven calls. That is
planner allocation, which T4.9 and T4.10 measured as the least stable thing here.
`frauddetection-memory-squeeze` never alerted within 900s, outside its recorded 390-469s range,
on one of the three scenarios whose alert set did **not** change. T7.1 capped kafka's JVM heap and
this scenario's alert is a `ServiceNoTraffic` on a Kafka consumer, which is **a plausible path and
not a measurement**; separating it from the scenario's known instability needs repeats this sweep
does not have.

**Triage is unchanged, once a confound is removed.** S5's stored triage was computed by the
pre-T7.3 scorer. Rescoring S5 under the current one, **five of six scenarios are identical to two
decimal places**; the only movement is on the run that abstained. The apparent precision gain
0.54 -> 0.57 in the raw stored figures is entirely T7.3's fix, not the world.

**A defect found by running it**, fixed and committed separately: T7.9's `rendered` columns never
reached the live database, because `create_schema` runs only `CREATE TABLE IF NOT EXISTS`, which
does nothing to an existing table. The first scenario died on `UndefinedColumn`. Fixed with
idempotent `ALTER ... ADD COLUMN IF NOT EXISTS` and a guard; the unit tests could not have caught
it, because `PostgresTrajectoryStore`'s own docstring says the suite uses the in-memory double.
Cost: one discarded run whose model spend is **unrecoverable**, since the write that failed is the
one that would have recorded it.

#### What a fourth holdout entry would need

**Not taken here, and nothing in this sweep licenses one.** ADR-0022's T4.15 addendum already
records that the set should not be entered again before it is re-authored or extended, and the
exposure table there stands at 3/2/2. A fourth entry would have to answer four things the third
did not:

1. **What reported result entitles it.** S6 is not a new pipeline - the stamp is unchanged, so
   under 3.3's "once per reported result" this sweep is the *same* agent as S5, which entry 3
   already covered. **The world is not a reported result about the agent**, and an entry claiming
   otherwise would be measuring the world with the holdout set, which is not what it is for.
2. **Why the exposure cost is worth paying now.** `email-wrong-image` would reach a fourth
   exposure and the other two a third, against a set of three. The T4.15 addendum's arithmetic
   says a three-scenario set read four times is not a holdout in any sense a reader would
   recognise.
3. **Whether the holdout bundles' own re-record changed what they measure.** They were
   re-recorded at T7.1 alongside the dev ones and **have not been read since** - entry 3 ran
   before that. That is a real question, and it is a question about the *bundles*, answerable by
   reading them rather than by spending an entry.
4. **What T7.0 would cost instead.** Four more fault classes with holdout representation is the
   honest way to buy more holdout, and it does not spend what exists.

### T7.9 — retrieval is evidence too *(decision, with the implementation it requires)*
**contract not written.** ADR-0020 §3 states the principle - *"reconstructing what the model saw
means storing the rendered text, not the object it was rendered from"* - and applies it to tool
envelopes only. Retrieval rows were specified for ADR-0008's contamination assertion rather than
for replay, so the principle was never carried across, and **retrieval was the only evidence in a
trajectory not stored as read**.

It mattered rather than being untidy because chunk ids do not keep pointing at the same text: the
corpus is re-seeded whenever a narrative is corrected, and **60 of 62 stored trajectories name
chunks whose prose has since changed** - the union across T7.6's three rewritten documents (39
trajectories) and T7.7's two (41), re-derived rather than carried over, because each of those
tasks reported only its own.

**Decision: store the rendered retrieval text on the row with a hash beside it**, the same shape
as `envelope` / `envelope_sha256`. Three points settle it.

*Rendered, not the chunk body.* The synthesizer reads
`f"{scenario_id} / {section}: {text[:280]}"` - the body is the object, that line is the text. It
also means a hash of the body would have hashed the wrong thing.

*Text and hash, not one or the other.* The asymmetry is real, and ADR-0020 already resolved it
once for envelopes, rejecting content-addressing because a hash used as key is "a place for a hash
to disagree with its content". **Measured rather than argued**: the rendered form averages 319
bytes, so every retrieval in the project's history costs **57 KiB - 5.3% of the 1.1 MiB already
spent on envelopes.** There is no trade-off at this scale.

*Snapshot-per-stamp rejected on evidence.* The corpus drifted three times **without
`runtime_version` moving**, because narrative corrections are not prompt changes - so a per-stamp
snapshot would have detected none of them.

**Nothing is repaired backwards, and RESULTS.md says so beside the corpus discussion rather than
in a footnote.** For a pre-T7.9 run you can still say what was retrieved (ids, and the
`exclude_origin` proving the filter fired) and what the tools returned (verbatim); you cannot say
what the retrieval *said*. That text is gone, not stale - the corpus that produced it was
overwritten, and `superseded/` archives manifests and metrics, never narratives. `rendered` is
empty on every older row and reads as "not kept", never as "nothing retrieved", which `returned`
contradicts.

### T7.8 — a narrative is only as current as the last capability change *(built; based on T7.7)*
The guard T7.7 proposed. **contract not written.** Built because discipline has now failed at
exactly this twice: T2.6 left four narratives asserting *"what changed: nothing"* after a change
log existed, and T7.1 forced a narrative rewrite and **still** missed sixteen restart lines,
because the review compared front matter against the manifest and never opened `logs/`.

**`CAPABILITY_VERSION` = `cap:9c416e0a`**, a digest over three inputs, two of them derived so they
cannot drift:

| input | source | moves when |
|---|---|---|
| tool surface | read off `Tools` at runtime | a tool is added, removed or renamed |
| `CAPTURE_SET` | `evalharness.provenance` | a bundle gains or loses a capture |
| `TOOL_BEHAVIOUR_REVISION` | next to the tools in `tools.py` | a tool returns materially different evidence without changing its name |

The third input is hand-maintained and exists because the derivable parts miss real capability
changes: **two-ended truncation kept `logql_query`'s name and signature** and started returning the
oldest lines too, which re-opened every claim of the form "the logs showed nothing before onset".
A digest over method names would not have moved. Its bump bar is written beside it, and explicitly
excludes refactors and docstrings - a version that moves when nothing a narrative could cite has
moved is the `ffs_stub_image_id` mistake ADR-0014 names.

**What it deliberately does not cover:** prompts and contracts (that is `runtime_version` - five
prompt experiments changed nothing about what a responder could *see*), the world (that is
`world.compose_digest`, whose re-record has its own guard; double-firing teaches people to ignore
both), and whether a tool works *well* - a tool returning the wrong answer has the same capability
version as one returning the right answer.

**Wired in two places.** `make check` fails on any narrative whose stamp is older than the current
set. The recorder prints the same debt at the end of a re-record, warning rather than refusing -
refusing would block a recording over prose, and the standing rule is that a person rewrites a
narrative afterwards. The failing test is what stops it landing; the warning is what tells whoever
is standing at the recorder that they owe a review.

**It checks a stamp, not the prose, and the failure message says so** - a green check means
somebody reviewed the narrative, never that a claim was verified. The message then names what
changed and what a review must cover, in order: **the captures and `logs/` first**, claims a newly
added tool may now answer, claims resting on a series' edge, and **front matter last**, because
checking it first is exactly what let T7.1's review pass while the prose was wrong.

All twelve narratives are stamped at `cap:9c416e0a`, which T7.7 reviewed.

### T7.7 — what was true when it was written *(built; based on T7.6)*
The audit T7.6's two findings implied. **contract not written.** No world, no model calls.
**Branched off `t7.6-narratives-reachable` rather than main**, because four narratives are
rewritten in that unmerged PR and auditing on main would have re-fixed them and conflicted.

**The class: a claim true when written, silently falsified by capability arriving later.** Two
distinct triggers, and only one is guarded. A **re-record** changes what was seen - already caught
by `recorded_from`, which is absolute precisely so it breaks. A **capability arriving** changes
what *could have been* seen, and **nothing catches that**: the change log (T2.6), the trace tool,
two-ended truncation and `runtime.json` each silently re-opened claims about what a responder could
not reach.

| narrative | claim | verdict |
|---|---|---|
| `ad-memory-squeeze` | *"logs say nothing at all… not even a startup banner"* | **Unsupportable — false.** The capture holds **16** truncated JVM startups from T+0 to T+8m27s. Removed; the loop is now the narrative's strongest evidence. |
| `ad-memory-squeeze` | *"the runtime series outlived the traffic - a process can be alive and useless"* | **Unsupportable.** The tail is the metrics store, not the process. Removed. |
| `ad-memory-squeeze` | *"ran for a few minutes on the heap it had already committed"* | **Unsupportable.** The logs show it dying from T+0. Corrected. |
| `ad-memory-squeeze` | series *"stopped entirely at T+4m30s"* | **True but uncertain.** Qualified: visible stop, true stop up to 5 min earlier. |
| `frauddetection-memory-squeeze` | *"Eighteen startup attempts"* | **Wrong count.** 19 in this recording. |
| `frauddetection-memory-squeeze` | series *"stopped at onset"* | **True but uncertain.** Qualified; its logs date it properly at T+0. |
| `recommendation-memory-squeeze` | series *"stopped at onset and did not resume"* | **True but uncertain.** Qualified - and nothing else dates it, since this service leaves no logs when it dies. |
| `recommendation-memory-squeeze` | *"leaves no logs when it dies"* | **Still true.** Silent T+0 to T+591s against a revert at T+570s. |
| `product-catalog-flag-failure` | *"what changed on productcatalogservice: nothing"* | **Still true.** The record is filed under `featureflagservice`, which the narrative goes on to find. |

**The staleness finding generalises, and is measured.** Prometheus scrapes every 5s and serves the
last sample forward for 5 minutes, so **a series appearing is sharp and a series disappearing is
late by up to five minutes**, always in the same direction. Proven inside a bundle:
`cart-bad-image-tag`'s runtime series stay visible to T+300s while its logs place the shutdown at
T+0, and resume 73s after the revert. **A narrative may say a series stopped; it may not date a
death from one** without something else pinning the moment.

**The check that closes the loop, argued and recorded in ARTIFACTS.md.** Two parts, because
neither works alone. **What a review must cover**: T7.1 did force a narrative rewrite and still
missed `ad-memory-squeeze`, because the reviewer checked front matter and alert sets against the
manifest and never opened `logs/` - so the review is not done until every claim is checked against
the **captures**, log content first. **What forces the review**: discipline alone failed twice, so
the proposal is a `CAPABILITY_VERSION` bumped when the tool surface or capture set changes,
stamped into narrative front matter the way `recorded_from` pins the recording, guarded on
mismatch. It cannot check prose and does not try - it makes the review mandatory rather than
remembered. **Proposed, not built.**

**Corpus re-seeded**: 35 chunks, 7 documents, `holdout_chunks` **0**. Both changed narratives are
dev; **62 retrievals across 41 of 62 trajectories** now point at text that reads differently - the
largest overlap yet, because `ad-memory-squeeze` is the most-retrieved document in the corpus.

### T7.6 — the narratives say only what the tools can reach *(built)*
The debt T7.5 recorded, discharged. **contract not written.** No world, no model calls.

**The heavy pair turned out not to be heavy, and T7.5's framing was wrong.** It recorded both
`dependency_latency` narratives as resting on container inspection no agent can perform, and
flagged `productcatalog-dependency-latency` as possibly having no substitute evidence at all.
Both flags were wrong. The emitted change record for a `dependency_latency` fault reads
**`container created: traffic-shaping container attached to cart-service's network namespace`**
with `None -> eth0 delay=300ms jitter=0ms`, filed under the target's own name and reachable
through `change_history`. That is the decisive finding, verbatim, in one of the four tools.

T7.5 reasoned from T7.4's reachability table, which answers *"was the target idle or absent"*.
These narratives turn on *"what changed beneath it"*. **Different questions, different answers,
and the table was only ever built for the first** - a caution about reusing a measurement outside
what it measured.

**What the narratives were actually wrong about** is worse and simpler: both were written at T1.5,
before a change log existed, and both assert *"what changed: nothing"*. That has been false since
T2.6 built change history, and nobody went back. Both now open the change section with the four
familiar shapes of change coming back empty and a fifth that does not, which is a sharper lesson
than the original: **"nothing changed" is a conclusion about a query, not about a service.**

**The light pair lost nothing and gained precision.** `cart-redis-misconfig` replaced "the
container was restarting repeatedly" with what its own log shows - **eight** `Connecting to Redis`
attempts naming `redis-cart:6380` and **seven** crashes between them, so the restart loop is read
off repetition in the stream rather than off a restart count nobody can query.
`cart-bad-image-tag` dropped "there was no container" and now rests on the log stopping dead at
T+0 plus its runtime series ceasing; whether a container was created and died instantly or never
created at all is not visible from the tools, is not needed for the fix, and the narrative says
so and stops there.

**One measurement the rewrite produced, from inside a bundle.** `cart-bad-image-tag`'s runtime
series continue for five minutes past a shutdown its logs place exactly at T+0, at an unchanging
value, then cease. **That tail is the metrics store holding a stale sample forward, not the
process living** - proven here rather than supposed, because the logs independently date the
death. Runtime series therefore answer *whether* a service is running and are worth up to five
minutes of slack on *when* it stopped.

**A debt this uncovered and did not fix:** `ad-memory-squeeze`'s narrative reads its heap series
ending at T+4m30s as dating the death, and the staleness finding above means that reading carries
up to five minutes of uncertainty it does not acknowledge. Its series ending near T+4m30s is
*consistent with* a death much earlier. Owned by ADR-0009 as a narrative correction, unmeasured
and unrewritten here.

**ADR-0019's container-inspection question is closed**, with the answer that it was already built
at T2.6 and never checked. No tool was added.

**Corpus re-seeded**: 35 chunks across 7 documents, `holdout_chunks` **0**. Three of the four
rewritten narratives are dev and therefore corpus material; the fourth is holdout and correctly
absent. **39 of 62 stored trajectories retrieved a chunk whose text has now changed** - recorded
in RESULTS.md, because a stored retrieval row now points at prose that reads differently.

### T7.5 — reachability is a property of the scenario *(built)*
T7.4's first proposal, taken: reachability becomes a recorded field rather than a scorer
exemption. **contract not written.**

**Schema decision: additive optional field, no `bundle_schema_version` bump**, following
`CAPTURE_SET`'s precedent exactly. ADR-0014's recorded bar is *a change that makes existing
bundles false*, and this makes none false - a manifest without `reachability` still correctly
describes what it holds, and no guard that passed starts failing.

**Existing bundles get the field computed from their own captures, which is derivation and not
backfill.** The distinction is ADR-0014's own: it refused to backfill `compose_digest` because a
digest asserts something about the world *outside* the capture, so writing one in afterwards would
claim a capture was taken against a world that did not exist when it was taken. Reachability
asserts nothing outside the bundle - it is a reading of files the bundle already contains, the way
counting a log's lines is, and it adds no claim that was not already sitting in `metrics/`.

**The scorer reports it and acts on nothing.** A run's report and manifest carry the target's
reachability beside the verdict, so an abstention on a zero-class scenario is visibly different
from one where the evidence was available - and nothing is forgiven, weighted or excluded. Pinned
by a test that scores two runs identical but for reachability and asserts every field but
reachability itself is byte-identical, coverage included. A scorer deciding which abstentions were
excusable would be grading on sympathy, which is the failure ADR-0022 names for the dispute
register.

**The catalog gate is in CATALOG.md and enforced.** A new scenario declares
`answers_idle_or_absent` before it is rehearsed; the declaration is checked against what its bundle
actually recorded, and disagreeing in **either** direction fails - over-claiming is what the gate
exists for, under-claiming is a stale claim. A zero-class scenario is recordable but only
deliberately, and then its narrative must not turn on the question. All twelve existing scenarios
now carry the declaration, derived rather than asserted.

#### Narrative corrections owed — **not made here**

T7.4 named four narratives that teach a check the agent cannot perform. **ADR-0009 owns the
decision** - it is the ADR that governs what a narrative may claim, having established that the
narrative is written blind from the responder's chair. The underlying question of whether the tool
surface should grow is **ADR-0019's**, which already carries container inspection as *marked for
decision*; either ADR can discharge the first pair, and they discharge it differently.

| narrative | what is owed | weight |
|---|---|---|
| `cart-dependency-latency` | Its **decisive** check is *"a container was attached to cart's network namespace that is not part of any service definition"* - container inspection, which is not one of the four tools. **No agent can ever reproduce this finding**, so the correction must either rest the narrative on evidence that is reachable, or ADR-0019 must add the tool. Rewriting it to hedge would leave a narrative that still points nowhere. | **Heavy** - the conclusion depends on it |
| `productcatalog-dependency-latency` | Same claim, same tool gap, and worse: T7.4 measured this target at **zero** answering classes, so there is no substitute evidence to move the check onto. If the tool is not added, this narrative's decisive step may not be expressible at all, and that is a finding about the scenario rather than the prose. | **Heavy**, and possibly unfixable without ADR-0019 |
| `cart-bad-image-tag` | Names container state as **framing** - *"no exit code and no restart count"* - around evidence that is genuinely in its 500 log lines. The correction is to describe what the logs show without asserting a check that was not made. | Light |
| `cart-redis-misconfig` | Same shape, same mitigation: *"cartservice container state, and its logs"*, where the logs carry it. | Light |

Not rewritten here for the reason T7.4 gave: these are corpus material, three of them are seeded
into the retrieval store, and **whether they cost dispatches is unmeasured**. Editing them and the
corpus together would move the prose and the numbers in one step and settle nothing.

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

#### Queued: a bound on `redis-cart` — **it fills on its own, and the recorder will refuse first**

> **Specified at T7.26**, with the eviction policy settled: `allkeys-lru`, not `volatile-lru`.
> `expires=0` still holds, so a `volatile-*` policy would have nothing to evict and would degrade to
> `noeviction` — the same failure arriving as cart errors instead of a container kill. Exact file,
> line, before/after and verification in
> [`docs/design/t7.26-queue-specification.md`](../design/t7.26-queue-specification.md) item 3.

Measured at T7.19, queued rather than applied because setting `maxmemory` edits
`world/docker-compose.yml` and moves `compose_digest`, obsoleting the comparability of every
current bundle. It batches with the `memory_limiter` and kafka changes and lands with one
re-record, as T7.1 did.

`redis-cart` runs `maxmemory 0` with `noeviction` against a **20MiB** ceiling and its keys carry no
TTL (`expires=0`). Cart state therefore accumulates in *cumulative* traffic rather than current
load: **0.192 keys/s over a 27.6-hour window**, 204 bytes per key, `anon` +64.8 B/s, linear across
windows from 90 seconds to 27.6 hours. It reaches the 20MiB ceiling in **≈55 hours at rest** with
nobody doing anything, and every long sweep walks it closer.

**The recorder refuses before the container dies.** `MEMORY_HEADROOM_PERCENT = 90.0` refuses a
rehearsal when any container passes 90% of its limit, and `redis-cart` gets there in **23-46
hours**. The refusal will name a container no scenario touches, in the middle of an unrelated
sweep. Documented at that constant so it is found where it fires.

**Interim, and not a fix:** flush `redis-cart` before a long sweep. It discards accumulated cart
state, so it is itself a world change - one no digest records. Say so in the run notes.

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

> **Corrected at T7.26: that is no longer true.** T7.15 brought both collector configs under
> `observability_digest`, so this change now moves a digest. It still invalidates nothing *today*,
> because no bundle on `main` carries that field yet — but "it can be taken any day" is stale, and
> the specification supersedes this paragraph. See
> [`docs/design/t7.26-queue-specification.md`](../design/t7.26-queue-specification.md).

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
