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

### T2.6 — tools
Typed tools with scoped read-only credentials and trust-labelled results. Also bound by
ADR-0004's runtime contract.
`src/faultline/tools/__init__.py:1`, `docs/adr/0004:41`, `docs/THREAT-MODEL.md:8`

**Requirement derived from measurement, not a decision taken.** The third tool must be
**change history, not deploy history** — it has to report resource-limit changes, not only
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

### T3.x — nine agent roles
Triage, planner, four specialists, synthesizer, proposer, scribe.
`src/faultline/agents/__init__.py:1`

### T3.1 — triage scoring
Scores triage, and **blast radius is what it scores on**. This is why the bundle manifest
carries `alerts_over_window` with `began_after_revert` rather than only a snapshot.
`docs/adr/0009:117`, `docs/adr/0009:137`, `src/evalharness/rehearse.py:590`

### T3.5 — state machine
Part of the orchestrator's eleven-state machine. The states and their triggers are proposed
in ADR-0016; the five that depend on agent outcomes (`TRIAGING`, `PLANNING`, `INVESTIGATING`,
`SYNTHESIZING`, `PROPOSING`) are named there but deliberately not designed, since what each
agent returns is T3.x's contract.
`src/faultline/orchestrator/__init__.py:1`, `docs/adr/0016-orchestrator-correlation-state-and-cap.md`

---

## Phase 4 — the eval harness

### T4.1 — harness runner
Drives runs from the scenario catalog: **what to inject, how long to wait, how long
between runs**, reading `injection`, `seconds_to_alert`, `seconds_of_steady_state` and
`seconds_to_settle` from bundle manifests. Specified to work **through public interfaces
only**. Computes the retrieval seed at seed time rather than at record time.
`docs/adr/0009:203`, `docs/adr/0009:35`, `docs/adr/0009:229`, `docs/adr/0008:45`

### T4.1b — run-time self-exclusion
ADR-0008 axis 2. A scenario's own artifacts are never retrievable while it is scored;
leave-one-out exclusion enforced in the retrieval query itself, filtering on the `origin`
provenance stamp.
`docs/adr/0008:96`, `evals/scenarios/SCHEMA.md:21`, `docs/adr/0002:19`, `tests/test_artifact_bundle.py:121`

### T4.2 — RCA and remediation scoring
Scores runs against the recorded bundles. Must report remediation-class accuracy **broken
out by fault class**, never only in aggregate.
`docs/adr/0008:121`, `docs/adr/0009:12`

---

## Phase 5 onward

### T5.3 — demo
Renders bundles for a human audience; needs `title` and the alert summary before anyone
reads a scenario file.
`docs/adr/0009:12`, `src/evalharness/rehearse.py:739`

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
