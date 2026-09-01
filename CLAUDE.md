# Faultline — instructions for Claude Code sessions

This repo is built against a fixed execution plan — `docs/spec/` holds it, along with the
project proposal, and both govern. Do not improvise scope. When asked to work on a task,
implement that task's deliverable and nothing beyond it.

`CONTRIBUTING.md` is the human-facing companion to this file: setup, the workflow the hooks
enforce, the invariants that break silently, and which document answers which question. It
applies here too. This file covers what is specific to an agent working in this repo.

## Working rules (non-negotiable)

1. **Eval before opinion** — from Gate 2 onward, no prompt/context/architecture change
   lands without an eval comparison.
2. **The demo always works** — never leave the scripted demo path broken at HEAD.
3. **Every decision gets an ADR** — if you had to think about it, write `docs/adr/NNNN-*.md`.
4. **Gates are hard** — a task is done when its gate condition passes from a clean clone.
5. **Scope is a feature** — see the do-not-build list below.
6. **No number without an interval** — any figure that leaves the repo carries n, R, and a
   95% CI, next to a baseline. Below-MDE deltas are "no measurable effect."

## Do NOT build

No Kubernetes for Faultline itself. No Kafka (Redis Streams). No multi-tenancy, RBAC, SSO.
No chat UI. No fine-tuning. No heavyweight agent framework — the runtime is in-house.
No custom vector DB (pgvector). No agent roles beyond the nine specified.

## Authorship

All commits are authored solely by Chandana Sorakundla. Never add `Co-Authored-By`
trailers, "Generated with" lines, or any AI attribution to commits, PRs, or docs.
This is enforced by a commit-msg hook and a CI history check - do not bypass either.

## Conventions

Setup, tooling, branch-and-PR discipline and `make check`: see `CONTRIBUTING.md`.

Specific to code written here:

- Everything typed; every agent I/O is a Pydantic model. Tool results are untrusted data.
- Secrets never in code and never in prompts; config via pydantic-settings and `.env`
  (see `.env.example`).

## Contamination rules (eval integrity)

See `CONTRIBUTING.md` — "Rules that break things silently". Scenario artifacts carry
`origin` provenance; holdout scenarios never enter any retrieval corpus; a scenario's own
artifacts are unreachable while it is being scored. Breaking these silently invalidates the
project's headline numbers — treat as a P0 bug.
