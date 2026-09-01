# Faultline Architecture

> Skeleton — grows with each gate. The authoritative design is the Faultline proposal
> (rev 8) and execution plan (rev 9); this file records what is *actually built*.

## System at a glance

Target environment (OTel demo + Prometheus/Loki/Tempo/Grafana + Alertmanager)
→ ingest API → Redis Streams (concurrency-capped) → orchestrator + eleven-state incident
machine (Postgres) → agent runtime: triage → planner → [log · metrics · change · trace]
specialists → synthesizer (cited RCA, citation-validated) → remediation proposer →
action plane (separate service, allowlist + approval tokens) — with the eval harness
injecting labeled faults and scoring everything.

## Component map

| Path | Component | Arrives |
|------|-----------|---------|
| `src/faultline/ingest` | webhook receiver, fingerprint dedupe | T2.1 |
| `src/faultline/orchestrator` | event consumption, state machine, fan-out | T2.2–T2.3 |
| `src/faultline/context` | service catalog, dependency graph, retrieval | T2.4, T6.4 |
| `src/faultline/agents` | the nine agent roles | T3.x |
| `src/faultline/tools` | PromQL/LogQL/trace/change-history tools, trust-labeled I/O | T2.6, T3.x |
| `src/injector` | reversible fault injection, four classes (ADR-0029) | T1.4 |
| `src/evalharness` | scenario runner, scoring, variance protocol, baselines | T4.x |

## Decision log

See `docs/adr/`. Start with 0001 (Redis Streams), 0002 (pgvector), 0003 (in-house runtime).
