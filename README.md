# Faultline

**An open, benchmarked incident-investigation agent system for the OpenTelemetry stack.**

When a production alert fires, Faultline's agents investigate it the way a good on-call
engineer would — querying logs, metrics, traces, and recent deploys in parallel — and
produce a root-cause report in which **every claim cites verifiable evidence**. Remediation
is proposed, never executed, until a human approves. The whole system is evaluated against
a fault-injection harness with ground-truth labels: we break the environment on purpose,
so we can measure whether the investigation was *right*.

> **Status: pre-v0.1 · building toward Gate 1.** This repo is built gate by gate against a
> published execution plan. Nothing is claimed that a clean clone can't demonstrate.

## Roadmap (gates)

| Gate | Condition | Status |
|------|-----------|--------|
| G0 | CI green on the walking skeleton | 🔨 in progress |
| G1 | injected fault → alert fires → visible on dashboards (zero AI) | ⬜ |
| G2 | alert → agent → persisted, cited finding | ⬜ |
| G3 | full multi-agent pipeline on 3 of 4 fault classes | ⬜ |
| G4 | `make eval` scores 10 scenarios; A/A check declares null | ⬜ |
| G5 | MVP shipped: demo from clean clone + live deploy | ⬜ |
| G6 | approval-gated remediation; thresholds re-held | ⬜ |
| G7 | benchmark report + ablations + launch | ⬜ |

## Layout

```
src/faultline/     the platform: ingest, orchestrator, agents, context, tools
src/injector/      chaos injector CLI — reversible faults with ground-truth labels
src/evalharness/   the measurement layer: scenarios, scoring, variance protocol
evals/scenarios/   the labeled scenario catalog (dev/holdout split at authoring)
docs/adr/          every non-obvious decision, recorded
```

## Development

```bash
uv sync          # install everything
make check       # lint + types + tests — what CI runs
```

## License

MIT — see [LICENSE](LICENSE).
