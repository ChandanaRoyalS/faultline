# ADR-0004: Benchmark target — SREGym primary, ITBench secondary

- **Status:** accepted
- **Date:** 2026-08-21
- **Task:** T0.5 (benchmark feasibility spike)

## Context
Faultline's positioning rests on being *benchmarked*: measured against an independent,
public suite rather than only against its own fault-injection harness. That claim carries
a resume bullet and the project's answer to the sharpest available criticism — that a
system authoring its own world, its own faults, and its own grader is self-referential.

The spike asked four questions of the two candidate benchmarks: what the harness hands an
agent, what it expects back, what runtime it needs, and whether an external agent can plug
in at all.

## Findings

**SREGym** (github.com/SREGym/SREGym) — 90 SRE problems, absorbing problems from AIOpsLab
and ITBench. Requires Python 3.12, Docker, Helm, kubectl, kind, and a self-managed
Kubernetes cluster; managed cloud Kubernetes is not supported out of the box, though an
emulated kind cluster works locally with limited problem coverage. The agent runs in an
isolated Docker container with no access to benchmark internals; models are routed through
LiteLLM, so any provider works. Results are graded by a configurable judge model.

**ITBench** (IBM) — Kubernetes-based sandboxed scenarios, fewer in the open release
(6 SRE scenarios, 21 mechanisms), with IBM-managed environments and a public leaderboard.
Baseline agents use CrewAI, but no SDK is mandated; researchers bring their own agent.

Both are therefore *open to an external agent*. Neither is free of Kubernetes.

## Decision
**Adapt.** Target SREGym as the primary benchmark and ITBench as a secondary leaderboard
submission, subject to two conditions.

1. **Kubernetes carve-out.** kind/k3d is permitted solely to run a benchmark harness. It is
   never introduced into Faultline's own deployment, which remains Docker Compose
   (see the do-not-build list). The boundary is the point: benchmark infrastructure is not
   product infrastructure.

2. **Runtime contract (binding on T2.6).** The agent runtime must be packageable as a
   standalone container that (a) receives telemetry and tool endpoints from configuration
   rather than assuming Faultline's compose network, (b) accepts a problem statement as
   input, and (c) emits a structured verdict independent of Faultline's web UI and
   database. Designing this in Phase 2 is nearly free; retrofitting it in Phase 7 is not.

## Consequences
Easier: the external-validity leg of the project survives, and T7.2 becomes ordinary
engineering against a known interface rather than an open-ended discovery task.

Harder: benchmark runs need a Kubernetes-capable host with more headroom than the
development environment; expect to resize the VM temporarily for benchmark days.

Confidence: this contract is provisional. It is derived from published documentation, not
from the harness source. T7.2 confirms it, and this ADR is amended if the interface differs.

Revisit if: SREGym's agent-container interface changes materially, or ITBench's managed
environments become available without a self-managed cluster.

## Addendum (T0.5 completion): read against the harness source

The contract above closes by admitting it is "derived from published documentation, not
from the harness source." That was the half of T0.5 the plan asked for first — *clone the
target benchmark harness, read its agent interface* — and it had not been done, so the risk
T0.5 exists to retire was still open. SREGym has now been cloned and read at
`fe4f8c7c0e390954bf1f3dd43fbf8b0da5949c19` (2026-08-31).

**Confirmed.** Endpoints come from configuration (`API_HOSTNAME`, `MCP_SERVER_PORT`,
`API_PORT`). Problem identity arrives as `SREGYM_ARTIFACT_ID` / `SREGYM_PROBLEM_ID`, with
application detail from a `/get_app` endpoint. The verdict is submitted through an MCP tool,
independent of any Faultline surface. Kubernetes is required; every grading oracle is
Kubernetes-native. Requirement (a) in particular paid for itself — see below.

**Correction 1 — registration is cheaper than assumed.** An agent is a row in `agents.yaml`
(`kickoff_command`, `kickoff_workdir`, `kickoff_env`, `install_script`,
`container_isolation`) plus a driver module. T7.2 is a driver, not a port.

**Correction 2 — tools are MCP over SSE, not HTTP APIs.** Five servers are mounted:
`/kubectl`, `/prometheus`, `/loki`, `/jaeger`, `/submit`. Faultline's tools call Prometheus
and Loki over HTTP directly, so the tool layer needs a second implementation behind the same
interface. This is exactly what the runtime contract's requirement (a) was written to keep
possible, and it is the reason that requirement was worth binding on T2.6.

**Correction 3 — modality coverage is three of four.** Metrics map directly (Prometheus).
Logs map directly (Loki). Traces need a second implementation: SREGym serves **Jaeger**,
Faultline queries **Tempo**. Change history has **no counterpart** — the harness exposes no
deploy or config-change surface, so the change analyst has nothing to call. That is not a
small gap: `redis-cart-dependency-latency`'s own catalog entry records `change_history` as
the only class that can name its culprit.

**Correction 4 — scoring is two-staged, and mitigation is graded on live cluster state.**
Submissions carry `stage` of `diagnosis` or `mitigation`, and `sregym/results/report.py`
prints both pass rates. Mitigation oracles inspect the cluster after the fact
(`postgres_lock_mitigation.py` spawns a check pod; `network_policy_oracle.py` verifies a
NetworkPolicy). The agent must have actually changed the world.

Faultline proposes and never executes (ADR-0028 §2), and the proposer is unbuilt. **It
therefore scores zero on mitigation by construction, not by weakness.** Consequences:

- The verdict stays **Adapt**. Nothing found here blocks a run.
- What T7.2 may claim is a **diagnosis pass rate on SREGym**, never a combined score. A
  combined figure would understate the system for a reason unrelated to investigation
  quality, and this project does not publish figures that mislead in its own favour or
  against it.
- Any resume bullet citing the benchmark carries the word *diagnosis*.
- Two of Faultline's tool implementations (Jaeger traces, and an MCP transport for metrics
  and logs) are prerequisites of T7.2 and should be costed there, not discovered in it.
- The absent change-history surface means a SREGym result exercises a narrower system than
  the in-house harness does. That belongs beside the number when it is published.
