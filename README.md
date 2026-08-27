# Faultline

**An open, benchmarked incident-investigation agent system for the OpenTelemetry stack.**

When a production alert fires, Faultline's agents investigate it the way a good on-call engineer
would — querying logs, metrics, traces and recent deploys in parallel — and produce a root-cause
report in which **every claim cites verifiable evidence**. Remediation is proposed, never
executed. It is built measurement-first: the environment is broken on purpose with labelled,
reversible faults, held-out scenarios are quarantined from every prompt and corpus from the day
they are authored, and no figure leaves the repository without its n. The point is not that the
agent works; it is that you can find out whether it does, and so can we.

> **Status: pre-v0.1.** Built gate by gate against a published execution plan. Nothing is claimed
> that a clean clone cannot demonstrate.

## Demo

One command runs the whole system against the live world and narrates it for a first-time
viewer — baseline gate, injection, correlation, the planner's dispatches, the specialists'
queries, the verdict, the narrative, the revert, and the confirmed recovery.

```bash
make world-up    # the pinned OpenTelemetry demo; give it ~2 minutes to settle
make demo        # ~15 minutes, real model calls
```

It needs an Anthropic key in `~/.faultline-anthropic-key` or `ANTHROPIC_API_KEY`, and it
refuses with instructions if the world is down or the key is missing. Nothing else here needs
a key — `make check` runs offline.

**The recorded run cost $0.3978.** That is one draw, not a point estimate: repeats of this
scenario under the same configuration have ranged **$0.4794–$0.7017**
([`VARIANCE-2026-08-27.md`](evals/runs/VARIANCE-2026-08-27.md), n = 5).

The scenario is `cart-redis-misconfig`, chosen because it is the most watchable *and* the
best-evidenced: nine services alert, the blast radius narrows to a single hop, **the service
that alerts loudest is not the service that broke**, and the answer is a change record rather
than an inference. It is also the only scenario whose repeat behaviour has been measured.

**What that measured record actually says, including the demo run: 6 correct verdicts out of 7
runs at this configuration.** The seventh is the recorded demo run itself, and it **abstained** —
it localized correctly to the checkout→cart hop, then exhausted its metrics budget without ever
spending a change-history query on `cartservice`, which is where the answer was. So the
transcript below shows the system declining to name a cause rather than naming the right one.
That is left as it fell rather than re-run until it looked better: an abstention is a result
here, and a demo that is re-rolled until it impresses is an advertisement.

**Would rather read than run?** A full transcript of a real run, with the narrative the scribe
wrote, is in [`docs/demo/`](docs/demo/) — [`transcript.txt`](docs/demo/transcript.txt) and the
[`narrative.md`](docs/demo/narrative.md) beside it.

The demo run is an ordinary run — same gate, same revert, same recovery check, recorded in
`evals/runs/` like any other — but it is marked `demo` in its manifest and **no aggregate ever
counts it**, because a run made to be watched is not a sample. A test pins that exclusion.

## Architecture in brief

```
alert → ingest → orchestrator → triage → planner → specialists → synthesizer → scribe
                      │                      │          │            │
                  incidents             blast radius  4 tools    past incidents
```

| Piece | What it does | Decision record |
|---|---|---|
| **Ingest** | Alertmanager webhook, fingerprint dedupe, Redis Streams | [ADR-0015](docs/adr/0015-alert-ingest-identity-and-dedupe.md), [ADR-0001](docs/adr/0001-redis-streams-over-kafka.md) |
| **Orchestrator** | Correlates alert episodes into incidents; an eleven-state machine | [ADR-0016](docs/adr/0016-orchestrator-correlation-state-and-cap.md) |
| **Context** | Service graph, blast radius, past-incident corpus in pgvector | [ADR-0017](docs/adr/0017-context-layer-graph-and-dependency-policy.md), [ADR-0018](docs/adr/0018-past-incident-corpus.md), [ADR-0002](docs/adr/0002-pgvector-over-dedicated-vector-db.md) |
| **Tools** | PromQL, LogQL, traces, change history — every result in an untrusted envelope | [ADR-0019](docs/adr/0019-tool-layer.md) |
| **Agents** | Planner, four specialists, synthesizer, scribe; in-house runtime, bounded budget | [ADR-0020](docs/adr/0020-agent-layer.md), [ADR-0003](docs/adr/0003-in-house-agent-runtime.md) |
| **Injector** | Labelled, reversible faults with ground truth | [ADR-0007](docs/adr/0007-chaos-injector-mechanisms.md), [ADR-0010](docs/adr/0010-injector-second-wave-faults.md) |
| **Eval harness** | Baseline gate, one driver, scoring, judge, freeze | [ADR-0022](docs/adr/0022-evaluation-harness.md), [ADR-0009](docs/adr/0009-rehearsal-artifact-bundle.md) |
| **Contamination model** | Split quarantine and run-time self-exclusion | [ADR-0008](docs/adr/0008-contamination-model.md) |

Every non-obvious decision is in [`docs/adr/`](docs/adr/); the task-by-task record is
[`docs/PLAN.md`](docs/PLAN.md).

## Results

Full method and findings: **[docs/RESULTS.md](docs/RESULTS.md)**. Raw runs and reports:
[`evals/runs/`](evals/runs/).

Every figure below was produced by **agent `claude-opus-5`**, judged by **`claude-haiku-4-5`**.
The judge shares a vendor family with the agent, so **every judged figure carries a
`SHARED LINEAGE` label** — this repository holds one provider's credentials and the violation is
declared rather than hidden.

### Holdout — three scenarios, never run before, never in any corpus

Pipeline stamp **`prompts:53fafe9c12bc`**, frozen before the run
([`FREEZE-2026-08-26-holdout.json`](evals/runs/FREEZE-2026-08-26-holdout.json)).
That stamp is also HEAD. T4.12 built a successor, `prompts:bf7605651ef2`, measured it as net
harmful — it won the one abstention it targeted and cost three other scenarios
([`SWEEP-2026-08-27-evidence.md`](evals/runs/SWEEP-2026-08-27-evidence.md)) — and **reverted it**.
The holdout has not been re-entered under any other stamp.

| scenario | ground truth | fault class | class of fix | judge (SHARED LINEAGE) |
|---|---|---|---|---|
| email-wrong-image | `bad_deploy` / `rollback` | `unknown` — **abstained** | abstained | `different` |
| productcatalog-dependency-latency | `dependency_latency` / `restart` | **`dependency_latency`** ✔ | `config_revert` ✘ | `same_mechanism` |
| recommendation-memory-squeeze | `resource_exhaustion` / `config_revert` | `unknown` — **abstained** | abstained | `different` |

| per fault class | n | fault correct / answered | fix correct / answered | abstained |
|---|---|---|---|---|
| `bad_deploy` | 1 | — / 0 | — / 0 | 1 |
| `dependency_latency` | 1 | **1 / 1** | 0 / 1 | 0 |
| `resource_exhaustion` | 1 | — / 0 | — / 0 | 1 |
| `bad_config` | **0** | no holdout scenario | | |
| `scale` | **0** | no scenario at all | | |

**n = 3 runs, 1 per class.** Triage recall **1.00** (n=3), precision 0.32. Cost $1.08 + $0.12
judged. Two of three runs exhausted their `changes` tool-call budget.
[`HOLDOUT-2026-08-26.md`](evals/runs/HOLDOUT-2026-08-26.md)

### Dev — where prompts and retrieval were fitted, so **not a benchmark**

Shown for context only. Same seven scenarios, two pipelines.

| | **dev sweep 1** | **dev sweep 2** |
|---|---|---|
| stamp | `prompts:59bf438b2a96` | `prompts:53fafe9c12bc` |
| difference | — | 28 lines added to the synthesizer's instructions |
| fault class, of answered | **4 / 7** | **4 / 4** |
| coverage (reached a class) | 7 / 7 | 4 / 7 |
| class of fix, of answered | 6 / 7 | 3 / 4 |
| triage recall / precision | 0.94 / 0.56 | 0.95 / 0.57 |
| judge: same_mechanism / adjacent / different | **7 / 0 / 0** | 4 / 0 / 3 |
| budget exhausted | 1 of 7 | 2 of 7 |
| cost | $2.92 | $3.27 |
| **n** | **7 runs** | **7 runs** |

| per fault class | n | sweep 1 fault | sweep 2 fault | sweep 2 abstained |
|---|---|---|---|---|
| `bad_config` | 2 | 2 / 2 | 1 / 1 | 1 |
| `bad_deploy` | 2 | 2 / 2 | 1 / 1 | 1 |
| `dependency_latency` | 1 | **0 / 1** | **1 / 1** | 0 |
| `resource_exhaustion` | 2 | **0 / 2** | **1 / 1** | 1 |
| `scale` | **0** | no scenario | | |

[`SWEEP-2026-08-26.md`](evals/runs/SWEEP-2026-08-26.md) ·
[`SWEEP-2026-08-26-taxonomy.md`](evals/runs/SWEEP-2026-08-26-taxonomy.md)

### Coverage and abstention

A verdict of `unknown` is an **abstention, not a wrong answer**: it is excluded from the accuracy
ratio entirely and reported as coverage, because a system that says "I do not know" and one that
guesses confidently wrong should not produce the same number. **Accuracy and coverage are
therefore never quoted apart** — "4 / 4 of answered" and "coverage 4 / 7" are one figure in two
halves, and either alone is misleading.

### What these numbers are not

n is 3 on holdout and 7 per dev sweep, with 0–2 scenarios per fault class. A 95% confidence
interval on any cell above spans most of the unit interval. **The tables support direction, not
magnitude**, and no aggregate appears anywhere without the per-class table beside it.

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

The gate marks above are deliberately not updated from the results section. A gate passes when
its condition is demonstrated **from a clean clone**, and that has not been re-run since these
measurements were taken. What the results show is what the results show.

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

### Breaking the world on purpose

With the world up (`make world-up`), the injector applies labelled, reversible faults:

```bash
uv run faultline-inject list                     # the fault catalog
uv run faultline-inject start cart-redis-misconfig
uv run faultline-inject status                   # what is broken right now
uv run faultline-inject stop --all               # put everything back
```

Active injections live in `.faultline/`, so `status` and `stop --all` work from any shell.
Stopping something that is not active is a no-op that succeeds. See
[ADR-0007](docs/adr/0007-chaos-injector-mechanisms.md) for what each fault class does.

## License

MIT — see [LICENSE](LICENSE).
