# Contributing to Faultline

Faultline is built against a fixed specification: `docs/spec/` holds the project proposal
and the execution plan, and they govern. `docs/PLAN.md` is the execution log against them,
not a substitute for them. If a change is not traceable to a task in the plan, it needs a
reason that is written down somewhere before it lands.

This document is for a person who has just cloned the repo. `CLAUDE.md` covers the same
project from the other side — it is the brief for an agent working here — and where the two
overlap, this file is the one that owns the rule.

## Getting set up

```bash
uv sync          # Python 3.12, all dependencies
make check       # lint, types, tests
```

`make check` is offline. It needs no Docker, no API key, and no network beyond the install.
If it passes on a fresh clone, your environment is correct.

Anything that touches the world needs more: Docker with room for roughly twenty containers,
and `make world-up`, which clones the pinned OpenTelemetry demo into `world/` and starts it.
`world/` is gitignored — it is somebody else's repository and we do not vendor it. Scored
runs and the demo additionally need an Anthropic API key; see the README for where it lives
and how it is read. It is never written into a file in this repo, never echoed, never
committed.

The README is the front door and covers the demo, the scored harness, and what a refusal
means. `docs/TROUBLESHOOTING.md` covers the failures that look like breakage and are not.

## Working here

**Branch before you commit.** A pre-commit hook refuses commits on `main`. Merges happen on
GitHub, where the hook does not run, so nothing legitimate commits to `main` locally. One
task per branch, one PR per task.

**`make check` before every push.** CI runs lint, format check, `mypy --strict`, the test
suite, and a container build. Everything it runs, `make check` runs first — except the
container build, which only CI does.

**Commit messages explain why.** The diff already says what changed.

**No AI attribution in commit messages.** No `Co-Authored-By` trailers naming a model, no
"Generated with" lines, in commits, PRs, or docs. A commit-msg hook blocks it locally and a
CI job scans the whole history. Do not bypass either. Authorship of this repository is a
deliberate position, not an oversight.

**Every decision that took thought gets an ADR.** `docs/adr/NNNN-title.md`, following
`0000-template.md`. The ADRs are the record of why this repo looks the way it does, and
they are read far more often than the code.

## Rules that break things silently

These are the ones worth reading twice. Breaking any of them produces no error, no failing
test, and a published figure that is wrong.

**Captured evidence is never rewritten.** Anything recorded from the running world —
rehearsal bundles under `evals/scenarios/artifacts/`, quiet-world captures under
`evals/baselines/`, and payloads and dumps under `docs/evidence/` — is a record of what the
world produced. A formatting hook that strips a trailing newline makes the committed file
something other than that. The rewriting pre-commit hooks exclude those three trees by
directory; the read-only guards still apply. If you add a tree that holds captures, add it
to the exclusion list in `.pre-commit-config.yaml` and say so in your PR.

**Holdout scenarios never enter any corpus.** Not the retrieval corpus, not a prompt, not
an example. Their artifacts are quarantined from the moment they are authored. Related: a
scenario's own artifacts are unreachable while that scenario is being scored — leave-one-out
is enforced at run time, not assumed. Both are treated as P0. Silently breaking either
invalidates every headline number in the repository without anything appearing to fail.

**One driver of the world at a time.** The harness takes a lock before it changes anything.
Scratch scripts that call `docker` directly are outside that lock, so if you write one, you
are the lock — do not run it alongside a recording.

**Changes that move a world digest are queued, not landed.** The compose files, the
observability configuration, the pinned images: changing any of them re-founds the world
that every recorded figure describes. Such a change goes into `docs/QUEUE.md` with its
trigger and lands batched with a single re-record. `docs/QUEUE.md` is also where a deferred
decision goes so that the next person finds a decision rather than a gap.

**Experiments are pre-registered, and numbers are never re-run to improve them.** Anything
that spends money on live model calls commits its predictions, its repeat count, and its
disqualification criteria *before* it runs. A run that fails for an environmental reason is
recorded as a discard with its reason and is not silently replaced. An experiment cut short
reports at the n it reached. This is the rule that makes the rest of the evaluation worth
anything, and it is the easiest one to break with good intentions.

**No number leaves the repository without its n.** Figures carry the number of runs behind
them and the world they were measured on. A number without that context is not a result.

## Where things live

| Path | What it is |
|---|---|
| `docs/spec/` | The proposal and execution plan. These govern. Never amended to match what was built. |
| `docs/PLAN.md` | The execution log: one entry per task, newest first. |
| `docs/adr/` | Numbered decision records. The answer to "why is it like this?" |
| `docs/QUEUE.md` | Deferred changes, each with what triggers it. |
| `docs/ARCHITECTURE.md` | How the pieces fit together. |
| `docs/THREAT-MODEL.md` | Telemetry is untrusted input, and what follows from that. |
| `docs/TROUBLESHOOTING.md` | Refusals that look like breakage. Read this before filing a bug. |
| `docs/RESULTS.md` | Published figures, current world first. |
| `evals/scenarios/` | The scenario catalog, its split, and the recorder contract in `ARTIFACTS.md`. |
| `src/faultline/` | The product: ingest, orchestrator, context, tools, agents. |
| `src/injector/` | The fault injector and the world lock. |
| `src/evalharness/` | The scoring harness. Benchmark infrastructure lives here, never in the product. |

## Scope

The specification names what not to build as carefully as what to build, and that list is
load-bearing rather than aspirational — see `CLAUDE.md`. When a change is tempting and out
of scope, it goes in the extensions section of the spec, not into the repository.
