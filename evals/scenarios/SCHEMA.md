# Scenario catalog schema (T1.5 / T1.6)

Every scenario is one YAML file in this directory. The schema is enforced by
`evalharness.scenario.Scenario` (Pydantic) — `make test` validates every file here.

| Field | Meaning |
|-------|---------|
| `id` | stable slug, e.g. `checkout-pool-exhaustion` |
| `title` | one line, human |
| `fault_class` | one of: `bad_deploy`, `dependency_latency`, `resource_exhaustion`, `bad_config` (T7.0 adds four more) |
| `split` | `dev` or `holdout` — **assigned at authoring, before any rehearsal** (T1.6). Holdout artifacts never enter any corpus; headline numbers are holdout-only once the catalog reaches 30+. |
| `injection` | what the injector does: `target` service, `method`, `params` |
| `ground_truth` | `root_cause` (prose, the answer key) + `category` |
| `expected_evidence` | list of evidence the investigation should surface |
| `expected_remediation_class` | e.g. `rollback`, `restart`, `config_revert`, `scale` |
| `rehearsed` | `false` until the scenario has been run end-to-end manually (T1.5) |
| `alert_timeout_seconds` | optional. How long the recorder waits for this scenario's first alert, overriding the 420s default. A rehearsal hint, not a fault parameter — it is outside `injection`, so it does not enter `scenario_fingerprint` and is not compared against the injector catalog. Needed where the target's traffic rate is low enough to delay detection. |
| `blocked` | `false` by default. `true` marks a scenario whose fault cannot be injected or observed on this world — a retired mechanism, or a target with no telemetry. The file is kept for history, but the allocation guards skip it so its replacement can fill the slot without widening `SPLIT.md`. Put the reason in a comment at the top of the file. |

Rehearsal artifacts land in `evals/scenarios/artifacts/<split>/<id>/` so quarantine is
mechanical. A scenario's own artifacts are never retrievable while it is scored (T4.1b).
