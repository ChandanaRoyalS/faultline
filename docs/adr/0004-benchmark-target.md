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
