# Contributing to Faultline

Orientation for a person who has just cloned this and wants to change something without breaking
what they cannot see. **It is short on purpose.** Where something is already written down, this
points at it rather than repeating it — a rule stated twice is a rule that will eventually disagree
with itself, which is a defect this repository has spent a long time correcting.

**[`CLAUDE.md`](CLAUDE.md) is not this document.** It is the instruction set for an AI agent working
in this repo — scope discipline, what not to build, and the rules an agent needs stated as
directives. **Where the two overlap, one of them owns the rule and the other links to it**; nothing
below is a restatement of anything there.

---

## Setup, and what needs no network

**`make check` is offline.** Lint, `mypy --strict` and the whole test suite run with **no API key
and no Docker**. `uv sync` and you can run it.

**Scored runs and `make demo` need both** — Docker with room for ~20 containers, and an Anthropic
key. [The README](README.md#prerequisites) has the prerequisites and the commands; they are not
repeated here.

Toolchain: **Python 3.12, `uv` for dependencies, `ruff` for lint and format, `mypy --strict`
always passing.** `make help` lists every target.

## The rules that will bite you in the first hour

Each of these is enforced by something that will stop you, and each will make more sense before it
fires than after.

**Branch before you commit.** A pre-commit hook (`scripts/no-commit-on-main.sh`) refuses commits on
`main`. It exists because a task once committed to `main` and was saved only by a push failing for
an unrelated reason. **Branch and open a PR per task**; commit messages explain *why*, not what.

**No AI attribution, anywhere.** No `Co-Authored-By` trailers naming an AI, no "Generated with"
lines, in commits, PRs or docs. **The rule and its reason belong to
[`CLAUDE.md`](CLAUDE.md#authorship)**; what matters here is that it is enforced twice — a commit-msg
hook, and a CI job that greps the entire history — so a trailer that slips past the hook fails the
build for everyone afterwards. **Do not bypass either.** If you are pasting a message from a tool
that adds trailers, strip them first.

**`make check` before every push.** CI runs the same thing; running it locally is faster than
finding out.

**Refusals are usually correct.** The harness refuses a great deal on purpose — a world that has not
settled, a container above a memory threshold, a run that will not say whether it is a single run or
part of a sweep. **A refusal is not a broken setup.**
[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) is organised by the message you got.

## The invariants whose violation is silent

**These are the rules where breaking them produces no error and a wrong published number.** That is
why they are here rather than in a comment somewhere.

**Captured evidence is never rewritten.** Anything under `evals/scenarios/artifacts/`,
`evals/runs/` and `docs/evidence/` is a record of what was observed at a moment. The rewriting
pre-commit hooks (whitespace, end-of-file) are excluded from those trees deliberately: a formatter
touching a capture makes the capture a fiction. **Fix a bad capture by re-recording it and archiving
the old one, never by editing it.**

**Holdout scenarios never enter any retrieval corpus, and a scenario cannot see its own artifacts
while it is being scored.** The rule is [`CLAUDE.md`](CLAUDE.md#contamination-rules-eval-integrity)'s
and it calls a break a P0. Two things follow for you: the corpus check is a number in every run's
freeze block that must read **zero**, and the exclusion is asserted at eval time rather than
trusted. If you add a scenario, its split is assigned **at authoring**, before any artifact exists.

**One driver of the world at a time.** The injector, the recorder and the eval harness all take a
lock before touching the world. Two drivers produce a world neither of them describes. A dead
holder is reclaimed automatically; a live one refuses.

**A change that moves a world digest does not land on its own.** Editing a compose file or an
observability config changes `compose_digest` or `observability_digest`, which makes every recorded
bundle describe a world that no longer exists and forces a re-record of the whole catalog. **Those
changes queue in [`docs/QUEUE.md`](docs/QUEUE.md)** and land together, with the re-record. The
register also holds every deferred change and what would trigger it — **add a row in the same commit
that defers something.**

**A live experiment is pre-registered before it runs, and a number is never re-run to improve it.**
Commit what you predict and what would falsify it *before* spending anything. If a run dies, record
the discard and its reason and **report at the n you achieved** — a discarded run stays in the
results directory forever rather than being tidied away. This is the difference between an
experiment and an advertisement, and it is the only rule here with no mechanism behind it.

**Every published figure carries its n**, and the intended standard —
[`CLAUDE.md`](CLAUDE.md#working-rules-non-negotiable) rule 6 — is *n, R and a 95% CI beside a
baseline*. **The repository does not currently meet that**: n is carried everywhere, intervals and
baselines are not. Read [`docs/RESULTS.md`](docs/RESULTS.md) knowing that, and do not add a figure
that makes it worse.

## Which document answers which question

| you want | read |
|---|---|
| what the project is meant to be, and what each task must deliver | **[`docs/spec/`](docs/spec/)** — the proposal and execution plan, unmodified and never amended to match what was built |
| what was actually done, task by task, and why | [`docs/PLAN.md`](docs/PLAN.md) — an execution log written *against* the spec, **not a substitute for it** |
| why something is the way it is | [`docs/adr/`](docs/adr/) — the decision record; if you had to think about it, it gets an ADR |
| what has been deferred, and what would trigger it | [`docs/QUEUE.md`](docs/QUEUE.md) |
| the refusal you just hit | [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) |
| how to record a new scenario, and which steps look stuck but are working | [`evals/scenarios/ARTIFACTS.md`](evals/scenarios/ARTIFACTS.md) — the recorder contract |
| the numbers and what they do and do not support | [`docs/RESULTS.md`](docs/RESULTS.md) |
| the shape of the system | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md) |

## Before you propose something large

**[`CLAUDE.md`](CLAUDE.md#do-not-build) holds the do-not-build list** — several plausible additions
are ruled out by decision rather than by oversight. Check it before writing a proposal that ends in
Kubernetes.
