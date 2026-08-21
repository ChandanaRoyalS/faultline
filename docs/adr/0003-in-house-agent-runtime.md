# ADR-0003: In-house agent runtime over an agent framework

- **Status:** accepted
- **Date:** 2026-08-21

## Context
The runtime must provide: typed tool contracts with per-tool scoped read-only credentials,
schema-validated structured outputs with bounded re-ask, per-agent token and tool-call
budgets, trust-labeled wrapping of all tool results (telemetry is untrusted input), full
trajectory persistence to Postgres, and a benchmark-compatible entry point (T0.5 contract).
Frameworks (LangGraph et al.) provide orchestration but hide exactly these control points,
and the JD this project targets pays for demonstrated ownership of them.

## Decision
Write the runtime in-house: a few hundred lines of typed, tested Python. Fan-out is
asyncio; state is Postgres; every control mechanism is explicit code we can point at.

## Consequences
Easier: budgets, trust labels, credential scoping, replay, and eval hooks are first-class;
every interview question about the loop has a file-and-line answer. Harder: we own the
bugs; no ecosystem of prebuilt integrations. Revisit if: the runtime's scope creeps toward
what a framework provides for free (graph editors, human-in-loop UIs, distributed executors).
