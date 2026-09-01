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

## Prerequisites

- **Docker**, running, with room for ~20 containers. `make world-up` clones the pinned
  OpenTelemetry demo into `world/` and starts it.
- **[uv](https://docs.astral.sh/uv/)** and **Python 3.12**. `uv sync` installs everything else.
- **git**, for the world clone.
- **An Anthropic API key** — only for the demo and for scored runs. `make check` is offline.

**Platform note.** Every figure in this repository was produced on **Apple Silicon (arm64)**, where
roughly twenty of the demo's images are amd64-only and run under Rosetta emulation
([ADR-0005](docs/adr/0005-arm64-emulation-and-feature-flag-service.md)). That is not incidental to
the numbers: emulation changes container memory behaviour measurably
([T7.30](docs/PLAN.md)). **A run on x86 hardware is a different world and its figures are not
comparable to these.**

## Demo

One command runs the whole system against the live world and narrates it for a first-time
viewer — baseline gate, injection, correlation, the planner's dispatches, the specialists'
queries, the verdict, the narrative, the revert, and the confirmed recovery.

```bash
make world-up    # the pinned OpenTelemetry demo; give it ~5 minutes to settle
make demo        # ~15 minutes, real model calls
```

**Five minutes, not two.** The baseline gate refuses to inject into a world whose containers are
younger than **300 seconds** — a container still warming up produces readings that are not a
baseline. Running `make demo` too early is refused with that reason, not broken.

**This world has known pathologies** — a checkout stall, kafka growing under emulation — that
produce refusals on a world you have not touched. They are properties of the environment, not
bugs in your setup: [what the refusals mean](docs/TROUBLESHOOTING.md).

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

**The recorded run declined to name a fault class.** Six prior runs under this exact
configuration answered correctly
([T4.10's table](evals/runs/VARIANCE-2026-08-27.md#the-five-repeats), n = 5, plus dev sweep 3's
row); this one localized correctly to the checkout→cart hop, then exhausted its metrics budget
without ever spending a change-history query on `cartservice`, which is where the answer was, and
returned `unknown`. **Saying `unknown` rather than guessing is a designed behaviour, not a
breakdown** — an abstention is reported as coverage and kept out of the accuracy figure entirely,
so the system is never rewarded for a confident wrong answer. What the run leaves open — why the
planner sometimes spends its budget without reaching the one service that holds the answer — is
the next experiment queued in [`docs/PLAN.md`](docs/PLAN.md).

Counting it, the record at this configuration is **6 correct out of 7**. It is left as it fell
rather than re-run until it looked better: a demo that is re-rolled until it impresses is an
advertisement.

**Would rather read than run?** A full transcript of a real run, with the narrative the scribe
wrote, is in [`docs/demo/`](docs/demo/) — [`transcript.txt`](docs/demo/transcript.txt) and the
[`narrative.md`](docs/demo/narrative.md) beside it.

The demo run is an ordinary run — same gate, same revert, same recovery check, recorded in
`evals/runs/` like any other — but it is marked `demo` in its manifest and **no aggregate ever
counts it**, because a run made to be watched is not a sample. A test pins that exclusion.

## Scoring a scenario

The demo is one narrated run. **This is the command every figure in the results section came
from** — one scenario, gated, injected, investigated, reverted, scored.

```bash
make eval SCENARIO=cart-redis-misconfig INTENT=--single-run
uv run faultline-inject list        # the scenario ids
```

**`INTENT` is mandatory and has no default.** It is either `--single-run`, or
`--runs-remaining N` counting down across a sweep — 6 on the first of six, 1 on the last. The
baseline gate projects kafka's memory forward over the work still to come and cannot do that
unless told what the work is, and **defaulting silently to the weaker check would be a guard that
protects you only if you remembered it**. A run without it refuses having injected nothing.

**Exit codes:** `0` scored · `2` refused before anything was injected · `3` the baseline gate
refused · `4` discarded, with the reason in the run directory's `DISCARDED.md` · `5` paused on a
clearable precondition. **A refusal is not a failure of your setup** — see
[what the refusals mean](docs/TROUBLESHOOTING.md).

The run lands in `evals/runs/<timestamp>-<scenario>/` with its manifest, verdict, narrative and
score. **Recording a *new* scenario is a different job** with a contract worth reading first —
which steps wait and for how long, and why a recorder that looks stuck is usually working:
[the rehearsal contract](evals/scenarios/ARTIFACTS.md).

## Bundles

Every recorded rehearsal, rendered as a readable page — what broke, what paged and in what
order, what the capture set holds, and the narrative the responder wrote:
**[docs/bundles/](docs/bundles/)**. Seventeen scenarios authored, **thirteen valid and four blocked** — a blocked scenario is one that could not fire, kept with its `INVALID.md` rather than deleted.

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

> **The current benchmark — dev sweep 7, on the bounded world that exists now.** Under stamp
> `prompts:1b0e7cbb4c47` against `compose_digest f5bd108f…` / `observability_digest 857d95b4…`:
> **8 of 8 scenarios scored with no discards, coverage 8/8, fault class 7/8, class of fix 7/8**
> ([`SWEEP-2026-08-30-refound-again.md`](evals/runs/SWEEP-2026-08-30-refound-again.md)). The
> cleanest sweep the project has run, and the first measurement of any kind on this world.
>
> **One verdict was wrong.** `shipping-quote-misconfig` returned `bad_deploy` against a truth of
> `bad_config`, at **low** confidence, with **zero dispatches at the failing service** — the
> collapse T4.12 named. The agent wrote in its own open questions that a bad config value "would
> look identical from the caller". Two explanations are available, a changed capture and a known
> planner instability, and **n = 1 per side separates neither**; the sweep says so rather than
> picking one.
>
> **On `n`: it is the number of slots filled, not the number allocated.** The catalog runs against
> **11 valid scenarios** (8 dev / 3 holdout) of 20 allocated slots. One dev slot, `bad_deploy-5`, is
> **deliberately empty** - the available mechanism space for that class is exhausted and a fourth
> entry would add a row without adding anything the benchmark can tell apart
> ([CATALOG.md](evals/scenarios/CATALOG.md)). Empty slots here are stated choices, not unfinished
> work, and are not to be closed by inventing a scenario to fill them.
>
> **Every figure below this banner, and in [`docs/RESULTS.md`](docs/RESULTS.md) except where it
> says otherwise, was measured on an earlier world and is labelled as such.** Comparing across
> those boundaries compares worlds, not agents. The immediately preceding world
> (`299d791c5e0d…`, dev sweep 6) is the one most of them describe.
>
> **The world moved on 2026-08-28** (T7.1: kafka heap capped, `otel-col` raised, Prometheus
> retention 6h → 15d, stub variants renamed) **and again on 2026-08-30** (T7.28: kafka's glibc
> allocator bounded, a `maxmemory`/`allkeys-lru` bound on redis-cart, a `memory_limiter` on the
> collector). Each move re-recorded every runnable bundle. See
> [docs/RESULTS.md](docs/RESULTS.md) and the
> [reconciliation record](docs/evidence/t7.1-reconciliation/README.md).

Full method and findings: **[docs/RESULTS.md](docs/RESULTS.md)**. Raw runs and reports:
[`evals/runs/`](evals/runs/).

Every figure below was produced by **agent `claude-opus-5`**, judged by **`claude-haiku-4-5`**.
The judge shares a vendor family with the agent, so **every judged figure carries a
`SHARED LINEAGE` label** — this repository holds one provider's credentials and the violation is
declared rather than hidden.

### Holdout — three scenarios, never run before, never in any corpus

Pipeline stamp **`prompts:53fafe9c12bc`**, frozen before the run
([`FREEZE-2026-08-26-holdout.json`](evals/runs/FREEZE-2026-08-26-holdout.json)).
**The holdout has been entered three times, under two stamps.** The figures above are entry 1,
under `53fafe9c12bc`. **Entry 3, under the current stamp `prompts:1b0e7cbb4c47`, answered all
three and got all three right** — 3/3 coverage, 3/3 fault class, 3/3 judged `same_mechanism`
([`HOLDOUT-2026-08-27-entry3.md`](evals/runs/HOLDOUT-2026-08-27-entry3.md)). Two caveats travel
with that number and are stated in full there: `email-wrong-image`'s row is corroborative rather
than confirmatory, and **n = 3 with no interval is not a benchmark**. Every entry is numbered and
counted in ADR-0022's ledger; entries 1 and 2 stand unedited.

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
| triage recall / precision | ~~0.94 / 0.56~~ **0.94 / 0.60** | ~~0.95 / 0.57~~ **0.95 / 0.60** | _(rescored 2026-08-28 under T7.3's fixed per-episode exclusion; the original figures are struck)_
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

n is 3 on holdout and 7–8 per dev sweep, with 0–3 scenarios per fault class, and the two most recent scenarios are scored at n = 2. A 95% confidence
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
