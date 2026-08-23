# Dev / holdout allocation (T1.6)

**Committed before authoring. Do not edit to accommodate a scenario.**

Slots are allocated by fault class and index, not by scenario name — the split was fixed
while the scenarios were still unnamed, so no scenario could be routed to a convenient
side. Authoring fills slots in order: the first `bad_deploy` scenario written becomes
`bad_deploy-1` and inherits that slot's split, whatever it turns out to be.

Rationale and enforcement: [ADR-0008](../../docs/adr/0008-contamination-model.md).

## Allocation at n=10

| Slot | Fault class | Split |
|------|-------------|-------|
| `bad_deploy-1` | `bad_deploy` | dev |
| `bad_deploy-2` | `bad_deploy` | **holdout** |
| `bad_deploy-3` | `bad_deploy` | dev |
| `dependency_latency-1` | `dependency_latency` | dev |
| `dependency_latency-2` | `dependency_latency` | **holdout** |
| `resource_exhaustion-1` | `resource_exhaustion` | dev |
| `resource_exhaustion-2` | `resource_exhaustion` | dev |
| `resource_exhaustion-3` | `resource_exhaustion` | **holdout** |
| `bad_config-1` | `bad_config` | dev |
| `bad_config-2` | `bad_config` | dev |

**Totals:** 7 dev / 3 holdout (30% holdout).

| Fault class | Dev | Holdout |
|-------------|-----|---------|
| `bad_deploy` | 2 | 1 |
| `dependency_latency` | 1 | 1 |
| `resource_exhaustion` | 2 | 1 |
| `bad_config` | 2 | 0 |

## Why `bad_config` is dev-only at n=10

Three holdout slots cannot cover four classes. Holdout capacity goes to the classes whose
diagnosis paths are most distinct from each other, so the holdout measures the widest
possible range of generalisation.

`bad_config` is the cheapest coverage to defer because its diagnosis path is the closest
neighbour of one already in the holdout: both `bad_config` and `bad_deploy` are
change-driven faults, both are found by correlating onset time against change history, and
both are resolved by reverting a change. A system that generalises to held-out
`bad_deploy` is substantially more likely to handle `bad_config` than one that generalises
to, say, held-out `resource_exhaustion`.

This is a real gap, not a solved problem. State it plainly when reporting numbers at n=10.
T7.1 grows the catalog to 30+ and every class gets holdout representation there.

## Rules

- `split` is assigned at authoring, before the scenario is rehearsed even once.
- Slots are filled alphabetically by injector fault id within each class, no exceptions.
  Which faults enter the catalog at all is a separate, earlier decision, made on diagnostic
  diversity. The two are kept apart deliberately: slot assignment is the only one of them
  that can bias the split, so it is the one with no judgement in it. See ADR-0008.
- Rehearsal artifacts land in `evals/scenarios/artifacts/<split>/<id>/`. Nowhere else.
- Nothing tuned — prompts, context settings, retrieval config, corpus content — may be
  tuned against a holdout scenario. Not once, not to debug.
- T2.4b seeds knowledge stores from the dev split only.
- Headline numbers are full-set with the split labelled and `n` stated, until the catalog
  reaches 30+.

`tests/test_contamination.py` enforces the mechanical parts of this file in CI.
