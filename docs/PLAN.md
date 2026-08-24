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

### T2.1 — alert ingestion
Alertmanager webhook receiver, fingerprint dedupe.
`src/faultline/ingest/__init__.py:1`, `docs/evidence/gate-1/README.md:19`

### T2.2 / T2.3 — orchestrator
Event consumption, an eleven-state incident machine, agent fan-out. ADR-0001 commits to a
global investigation concurrency cap with severity-ordered overflow.
`src/faultline/orchestrator/__init__.py:1`, `docs/adr/0001:9`

### T2.4 — context layer
Service catalog, dependency-graph scoping, retrieval.
`src/faultline/context/__init__.py:1`, `docs/ARCHITECTURE.md:21`

### T2.4b — corpus seeding
Seeds the past-incident store from `evals/scenarios/artifacts/dev/` **only**. The input is
`incident.md` — the hand-written narrative in each bundle.
`docs/adr/0008:80`, `evals/scenarios/ARTIFACTS.md:127`, `evals/scenarios/SPLIT.md:62`

**contract not written** — the repo does not state how narratives are chunked, embedded,
or ranked, nor what else besides `incident.md` enters the store.

### T2.6 — tools
Typed tools with scoped read-only credentials and trust-labelled results. Also bound by
ADR-0004's runtime contract.
`src/faultline/tools/__init__.py:1`, `docs/adr/0004:41`, `docs/THREAT-MODEL.md:8`

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
Part of the orchestrator's eleven-state machine.
`src/faultline/orchestrator/__init__.py:1`

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
