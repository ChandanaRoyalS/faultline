# Scenario catalog schema (T1.5 / T1.6)

Every scenario is one YAML file in this directory. The schema is enforced by
`evalharness.scenario.Scenario` (Pydantic) — `make test` validates every file here.

| Field | Meaning |
|-------|---------|
| `id` | stable slug, e.g. `checkout-pool-exhaustion` |
| `title` | one line, human |
| `fault_class` | one of nine: `bad_deploy`, `dependency_latency`, `resource_exhaustion`, `bad_config`, and - since T7.0 on the v2 world (ADR-0043, 2026-09-24) - `feature_flag`, `process_freeze`, `network_partition`, `datastore_corruption`, `disk_fill`. ADR-0029 (T7.57) had closed the question at four for v1; ADR-0042 reopened it with the world. Adding the five moved `prompt_digest` once (`8dda4a19da2f`); every run before it is at the old stamp and says so |
| `split` | `dev` or `holdout` — **assigned at authoring, before any rehearsal** (T1.6). Holdout artifacts never enter any corpus; headline numbers are holdout-only once the catalog reaches 30+. |
| `injection` | what the injector does: `target` service, `method`, `params` |
| `ground_truth` | `root_cause` (prose, the answer key) + `category` |
| `expected_evidence` | list of evidence the investigation should surface |
| `expected_remediation_class` | e.g. `rollback`, `restart`, `config_revert`, `scale` |
| `rehearsed` | `false` until the scenario has been run end-to-end manually (T1.5) |
| `alert_timeout_seconds` | optional. How long the recorder waits for this scenario's first alert, overriding the 420s default. A rehearsal hint, not a fault parameter — it is outside `injection`, so it does not enter `scenario_fingerprint` and is not compared against the injector catalog. Needed where the target's traffic rate is low enough to delay detection. |
| `world` | `v1` by default (the eighteen authored before 2026-09-24); `v2` for every scenario authored against OTel demo 2.2.0 (ADR-0042). Outside the fingerprint. A `v2` scenario cites a `v2-*` injector definition, fills a `v2/<row>-<n>` slot from `SPLIT-V2.md`, and lives in `evals/scenarios/v2/`; a `v1` scenario fills `SPLIT.md`'s and lives at the top level, where every v1 benchmark consumer reads. |
| `kind` | `fault` by default. `injection` marks a P6 case: the base fault plus a prompt-injection payload planted in the world's telemetry, with the base's ground truth and a decoy a correct verdict does not name. Counts inside the 30+ as the execution plan's T7.1 row says, in `SPLIT-V2.md`'s `injection` row, whatever its `fault_class`. Since 2026-09-28 the file carries the attacker itself: see `base` and `payload`. |
| `base` | `kind: injection` only. The id of the recorded `kind: fault` scenario this one rides. `injection`, `ground_truth`, `fault_class` and `expected_remediation_class` are the base's, copied verbatim and held equal by `tests/test_injection_scenarios.py`. Inside the fingerprint. |
| `payload` | `kind: injection` only. T6.8's variant carried by the scenario (`docs/design/t7.1-injection-scenarios.md`): `channel` (`log` only for now), `plant_on` (the service whose log stream receives the line - the page's seed, named, never defaulted), `text` with `{canary}`, `canary` (a stem; the planted token is minted from it per run), `decoy` (`action_id`, `target` in the base's recorded blast radius, `remediation_class` other than the truth's), `actor`. `faultline-eval <id>` plants it with no flag and refuses `--adversarial`; the recorder plants it after the page, reads it back through the agent's own log tool before the revert and records `payload.delivered` in the manifest. The landing and the decoy are inside the fingerprint; the text and the stem are not. |
| `blocked` | `false` by default. `true` marks a scenario whose fault cannot be injected or observed on this world — a retired mechanism, or a target with no telemetry. The file is kept for history, but the allocation guards skip it so its replacement can fill the slot without widening `SPLIT.md`. Put the reason in a comment at the top of the file. |

Rehearsal artifacts land in `evals/scenarios/artifacts/<split>/<id>/` so quarantine is
mechanical. A scenario's own artifacts are never retrievable while it is scored (T4.1b).
