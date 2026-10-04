# Deviations from the execution plan

**The register of every place this repository departs from
[`docs/spec/execution-plan-rev9.pdf`](spec/execution-plan-rev9.pdf)**:

- a task built differently from its row, scaled down, substituted, deferred, or closed;
- a plan rule not followed.

Kept by the owner's instruction of 2026-10-04 (CLAUDE.md rule 9). **A deviation is added here in
the same commit that makes it.** It names who decided, where the record is, and the date where the
record gives one.

- **Compiled 2026-10-04** from `docs/PLAN.md`, the ADRs, `docs/GATES.md`, `docs/QUEUE.md` and
  `docs/design/t7.62-audit-against-the-plan.md`.
- PLAN.md's line numbers move as entries are added at the top of each phase's log, so **rows cite
  the entry or the task's section, not a line**.
- **IDs are the plan PDF's.** The repository's own task headings reuse plan IDs for other work
  (below).

## The numbering collisions

| repository heading | the plan's task with that ID |
|---|---|
| "T7.1" the digest-locked change queue and re-record | T7.1, catalog to 30+ |
| "T7.3 — the blast radius counts alerts, not services" | T7.3, ablation studies |
| "T7.4 — evidence reachability" | T7.4, eval dashboard |
| "T7.5 — reachability is a property of the scenario" | T7.5, launch pack |
| "T7.6" to "T7.62" | no such plan tasks |
| "T4.3" to "T4.7" headings (sweep decisions, the judge, the taxonomy, the holdout run, the budget confound) and "T4.8" to "T4.15" | T4.3 metric suite, T4.4 eval DB, T4.5 CI, T4.6 variance, T4.7 baselines; no T4.8+ in the plan |
| "T5.3 — demo" | T5.3, docs pack |

**On 2026-10-03 a cost row was labelled "T7.1 headline"**, and the 2026-10-04 registration was
written under that name. The plan's T7.1 is the catalog, and it is delivered. The headline run is
what T1.6, T4.7, T5.3 and T7.5 need, and it is T7.3's first step
([`PREREGISTRATION-headline-v2.md`](../evals/runs/PREREGISTRATION-headline-v2.md)). Corrected
before anything ran, at $0.

## Phase 0 to Phase 2

| plan task | the plan says | what was done instead | decided | in force? |
|---|---|---|---|---|
| T0.2 | build artifacts published per commit | images built and discarded; fixed | audit, #113 | no |
| T0.3 | `platform`, `full-world`, `eval` profiles | `eval` aliased `platform`; fixed | #114 | no |
| T0.5 | clone the benchmark harness | contract first inferred from docs, harness cloned later; verdict *Adapt* | ADR-0004 addendum | no |
| T1.1 | pin a demo version (v1.2.1) | the world moved to OTel Demo 2.2.0 for Phase 7; v1 kept for v1 figures | ADR-0042, 2026-09-22 | yes |
| T1.2 | a "shop health" dashboard | missing at G1; added | #121 | no |
| T1.3 | error-rate, latency **SLO burn** and **saturation** rules | latency is a p95 threshold; **no saturation rule** (Q13 declined); on v2 the thresholds carried over as not-evidence, windows 2m → 5m, load raised to 25 users | Q13; T7.1 migration, 2026-09-22 | yes |
| T1.6 | ~70/30 split balanced across classes; holdout-only headline at 30+ | v1: 3 holdout, no `bad_config` holdout, full-set headline made permanent **for v1**. v2: 10 holdout of 39, holdout-only headline restored (2026-10-04); `datastore_corruption` and `disk_fill` have no holdout | ADR-0008 addenda | yes |
| T2.2 | a cap with severity-ordered overflow, exercised by T6.7's storm | the cap is unreachable by construction; the storm made one incident | ADR-0016 correction; T6.7 | yes |
| T2.3 | an eleven-state incident machine | fourteen states, not the same eleven | ADR-0016 Addendum 2 | yes |
| T2.4b | runbook corpus, past-incident store, allowlist | only the store at first; runbooks and allowlist added 2026-09-01 | audit; ADR-0032, ADR-0036 | no |
| T2.5 | provider routing; the seam proven on a vLLM endpoint | **provider routing not built**; a stub endpoint, not vLLM | ADR-0031 | yes |

## Phase 3 to Phase 5

| plan task | the plan says | what was done instead | decided | in force? |
|---|---|---|---|---|
| T3.1 | a small model as triage's cheap-model routing tier | one model for every role; `role_models` is recorded but **not applied** (found 2026-10-04) | Q24, reopened under rule 7 | yes; T7.3's build wires it for the tier experiment |
| T3.4 | deploy-history **and repo-compare** tools | repo-compare not built | Q19, reopened | yes |
| T4.2 | ~30 manually graded runs | 5; the judge is labelled *not calibrated* | PLAN, T4.2's section (`JUDGE NOT CALIBRATED — 5 of ~30`) | yes |
| T4.5 | the full catalog nightly | nightly on demand only (cost); smoke dispatch-only | owner, 2026-09-11 | yes |
| T4.6 | scored comparisons at R = 5 | nothing has run at R = 5; a printed comparison names its tier (Q65). **Phase 7 runs at R = 1** | Q65, 2026-09-18; owner, 2026-10-03 | yes |
| T4.7 | baselines in every headline table; a manual-RCA reference on five dev scenarios | baselines run 2026-09-21 on v1 with four classes and no culprit service; **0 of 5** manual RCA (the only investigator wrote the scenarios). The nine-class update and `service` are owed by the headline build | PLAN, 2026-09-21; owner, 2026-10-04 | yes |
| G4 | median time to report ≤ 3 minutes | fails: 251.6 s, and 232.8 s over 139 runs; G4 not declared | GATES, 2026-09-20 | yes |
| T5.2 | lifecycle notifications | built; the Slack webhook is unset | owner, who has not created one (PLAN, T5.2) | yes |
| T5.3 | a 4-minute demo | 4 min 25 s, and now out of date | GATES, G5's declaration, 2026-09-07 | yes; T7.5 re-records |

## Phase 6

| plan task | the plan says | what was done instead | decided | in force? |
|---|---|---|---|---|
| T6.1 | accuracy delta measured | at R = 3, not R = 5 | owner (PLAN, T6.1's delivery: *"delivered, on the sweep document's reading"*) | yes |
| T6.2 | rollback, restart, flag toggle, scale | four actions unperformable (`scale_service`, `reconnect_service`, `restore_store`, `free_storage`); flag toggle covered by `revert_config` | ADR-0029, ADR-0032, ADR-0043 | yes |
| T6.3 | the miss auto-drafted as a dev scenario | deferred by name; not built | T6.3 registration | yes |
| T6.4 | rerank, recency, summaries, deprecated filter, git-synced ingest | all five deferred (Q41-Q45); recall@5 and MRR below their floors. **Rerank is built by T7.3** (owner, 2026-10-04) | T6.4 registration | partly |
| T6.5 | the comparison at the scored tier | R = 3; no transfer effect | amendment 3 | yes |
| T6.6 | Prometheus metrics for eval scores | declined, not deferred | PLAN, T6.6's entry | yes |
| T6.7 | a test or drill per failure row | rows 5, 6, 7 and 11 not met; storm on loopback with investigation off | PLAN, T6.7's entry; GATES, G6 | yes |
| T6.8 | egress, secrets, hardening | store credentials, executor credential and minting key closed as decisions; fabricated-record defence unbuilt (Q81) | 2026-09-20 (PLAN, T6.8's entries; Q4, Q81) | yes |
| G6 | injection scenarios pass; latency ≤ 3 min with rerank | no injection pass condition registered; latency fails; G6 not declared | GATES, G6's assessment, 2026-09-20 | yes |

## Phase 7

| plan task | the plan says | what was done instead | decided | in force? |
|---|---|---|---|---|
| T7.0 | four new classes: cert expiry, cache stampede, disk fill, N+1, so eight | **nine classes**, five new: `feature_flag`, `process_freeze`, `network_partition`, `datastore_corruption`, `disk_fill`. Of the plan's four: disk fill built; cache stampede (A5) and N+1 (A7) attempted live and never paged; cert expiry is `bad_config` by the class criterion | ADR-0042, ADR-0043; rule 7 (attempted) | yes |
| T7.1 | 30+ across ~8 classes, including the injection **and storm** cases | 39 valid of 44 slots, 9 classes, 29 dev and 10 holdout, 4 injection scenarios. **Storms are a measured label, not a row**, labelled on 7 scenarios (6 dev, 1 holdout) on 2026-10-04. Five slots empty; two classes without holdout | ADR-0008 T7.1 addendum; owner, 2026-09-30 | yes |
| T7.2 | run the benchmark (and R = 5 per T4.6) | 33 of 108 problems, R = 1, $50 cap; diagnosis only; per application; Faultline unchanged under SREGym's modalities (no describe, no traces on two applications, three minutes of history) | owner, 2026-10-02 and 2026-10-03 | yes |
| T7.2 | the re-check's 5 s condition per tool | corrected to per request after the result, recorded as a correction | owner, 2026-10-03 | yes |
| T7.3 | every experiment over the **full catalog at R = 5**, order randomized | **12 dev scenarios, R = 1**, order randomized, the control and B1 re-run inside the batch | owner, 2026-10-03 and 2026-10-04 | yes |
| T7.3 | progressive disclosure vs push-everything briefings | push reaches the five roles that are briefed; **the specialists are not briefed** (each gets a dispatch question), so push leaves them unchanged | build part C, 2026-10-04 (PLAN entry) | yes |
| T7.3 | nothing in the harness changes between the registrations and the run, except its own defects by addendum | **the kafka headroom projection's growth rate made per world** before the trial: v2 had v1's 151 MB/h and refused the trial at its first slot; v2's measured rate is 1.3 MB/h, v1 unchanged. **And the gate's expected-silent services made per world** after the first attempt: v2's broker emits no spans at rest (Q118), so kafka at zero is excused on v2 only | owner, 2026-10-04 (`PREREGISTRATION-trial-v2.md`) | yes |
| T7.3 | (the headline registration, item 8) the corpus of record is the repository's corpus, every runbook included | **a v2 corpus for the v2 runs**: v2's 29 dev narratives and 14 world-neutral runbooks; no v1 narrative, postmortem, service or world runbook. The v1 corpus stays as pinned for v1 | owner, 2026-10-04 (`PREREGISTRATION-trial-v2.md`, Addendum 4) | yes |
| T7.3 | (T4.1b) a run whose leave-one-out exclusion removes nothing is invalid | **accepted when the scenario's own narrative is absent by design** (holdout, or another world's corpus) **and counted absent at run time**; an expected narrative still invalidates | the trial's Addendum 4, 2026-10-04 | yes |
| T7.3 | the headline's trial: three dev scenarios, all four arms | the baselines' nine trial runs stand; **F's three run again** on the v2 corpus (the corpus does not touch the baselines) | the trial's Addendum 4, 2026-10-04 | yes |
| T7.3 | single-agent-all-tools vs parallel specialists | B1, which also has no retrieval, proposer or scribe; the confound is stated with every result | the B1 design (`baseline_agent.py`) | yes |
| T7.4 | the eval dashboard | not built; $0 at the owner's scale | owner, 2026-10-03 | pending |
| T7.5 | launch pack | not built; writeup $0, demo about $3 | owner, 2026-10-03 | pending |
