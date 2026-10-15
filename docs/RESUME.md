# The final resume bullets (T7.5)

**These replace [`MVP-CUT.md`](MVP-CUT.md)'s set**, which was scoped to what existed at Gate 5 and
stays as that record. The execution plan's rule for this set: *"bullets follow the spec's v2
formulas with your measured values substituted in."* The formulas are the proposal's §6
([`project-proposal-rev8.pdf`](spec/project-proposal-rev8.pdf)). Two of their clauses were
measured and came out the other way, so the measured values replace them rather than decorate
them; the table at the end shows each substitution and its source.

Figures are from the v2 world (OpenTelemetry Demo 2.2.0), `prompts:9ce16b66bbcc`, `cap:91279a09`,
unless stated, and every one is R = 1.

---

## The bullets

**Built Faultline, an open incident-investigation agent system for the OpenTelemetry stack
(Python, FastAPI, Postgres, Redis Streams): parallel specialist agents over logs, metrics, traces
and deploy history produce root-cause reports in which every claim must cite a tool result the
system resolves, or the report is regenerated once and then escalated to a human.**

**Benchmarked it against three baselines on 36 labelled fault scenarios in nine classes, with a
quarantined holdout and every run pre-registered, and externally on 33 SREGym problems, where it
passed 2 against SREGym's own agent's 30; published the per-class error analysis and a
nine-dimension ablation series, which found that a single agent with the same tools matched the
multi-agent pipeline on holdout (6/9 each) and beat it on dev (88 % vs 58 %, replicated at +40
points).**

**Designed and built the action control plane: an executor that is the only holder of the write
credential, single-use action-bound approval tokens spent through an append-only ledger,
blast-radius and kill-switch refusals demonstrated on a live world, and telemetry treated as
untrusted input. A planted log injection reached the agents in 6 runs and was followed in none.**

## One-sentence description

> Designed, built and benchmarked a multi-agent incident-investigation system for the
> OpenTelemetry stack: it takes live alerts, investigates logs, metrics, traces and deploy history
> in parallel, and writes evidence-cited root-cause reports with approval-gated remediation,
> measured against fault injection with ground-truth labels and an external benchmark.

## Short version

> Built and benchmarked an incident-investigation agent system on the OpenTelemetry stack
> (evidence-cited reports, approval-gated remediation, 36 labelled fault scenarios, SREGym).
> Its most useful result was negative and published: one agent with the same tools did as well as
> the multi-agent pipeline, and better on the dev set.

---

## Each substitution, and where its number comes from

| proposal's v2 clause | measured | source |
|---|---|---|
| *"parallel specialist agents over logs, metrics, traces, and deploy history"* | kept: four specialists, traces since T6.1 | [ARCHITECTURE](ARCHITECTURE.md) |
| *"every claim is programmatically validated against cited evidence"* | kept, said as what the check does: an unresolvable citation is refused, the narrative regenerated once, then escalated to human review | `src/faultline/agents/investigation.py` |
| *(in-house harness)* | 36 scenarios scored of the 39 registered (3 had no usable run on some arm and are out of every arm), 27 dev and 9 holdout | [headline report](../evals/runs/HEADLINE-2026-10-11-v2.md) |
| *"on SREGym/ITBench-class fault scenarios"* | SREGym, 33 of 108 eligible problems on three applications, diagnosis only, under SREGym's LLM judge | [T7.2 RESULT](../evals/attempts/T7.2-run/RESULT.md) |
| *"where frontier-model baselines fail the majority of incidents"* | **dropped: measured the other way.** SREGym's Claude Code agent (Sonnet 4.6) passed 30 of 33; Faultline 2 of 33, and its triage gate declined 20 | [T7.2 RESULT](../evals/attempts/T7.2-run/RESULT.md) |
| *"publishing per-scenario-class error analysis"* | kept: by class on holdout and dev, every miss's returned label printed | [headline report](../evals/runs/HEADLINE-2026-10-11-v2.md) |
| *"ablations showing topology-scoped evidence compression drove the largest accuracy gain (58% → 84% top-1)"* | **replaced.** Evidence compression off (E3): +0 points. Topology scoping (E2) could not show on this world and was not run. No change inside the pipeline moved accuracy beyond the 28-point MDE. The largest effect was the single agent (E1): +40 points (+10 to +70) | [ABLATIONS](ABLATIONS.md) |
| *"credential-separated read/write planes, single-use human-approval tokens, blast-radius validation"* | kept: built at T6.2 and T6.3; three refusals (spent token, kill switch, target outside the blast radius) shown on a live world | [THREAT-MODEL](THREAT-MODEL.md) |
| *"injection-tested defenses treating telemetry as untrusted input"* | kept with its count: delivered in 6 runs (3 Faultline, 3 B1), `followed: false` on all 16 | [headline report §4](../evals/runs/HEADLINE-2026-10-11-v2.md) |

## What a bullet here may not say

- **Not that the multi-agent design is better.** On this catalog it is not: tied on holdout, behind
  on dev. B1 also lacks retrieval, the proposer and the gate, so the result cannot say which part of
  the pipeline costs it.
- **Not an accuracy figure without its denominator.** 9 holdout scenarios, R = 1; every rate's
  interval spans 40 points or more; the holdout supports direction, not magnitude.
- **Not "fast".** Faultline's median time to a report is 228-235 s, over the 180 s clause Gates 4
  and 6 carry.
- **Not "passes its gates".** G0-G3 and G5 are declared; G4, G6 and G7 are not
  ([GATES](GATES.md)).
- **Not "reduces MTTR".** There is no measured human time to compare against: the manual-RCA
  reference is 0 of 5 attempts.
- **Not a leaderboard comparison.** The SREGym figures use a different commit, 33 of 108 problems,
  R = 1 and kind.
- **Not production use.** One VM, one monitored world, an uptime check that emails.

The demo video in README is still the MVP cut. The full cut the plan names (approved rollback and
recovery, the Tempo encore, the dashboard) is owed, and recording it needs the world and about $3.
