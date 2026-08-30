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

## Extension to n=20 and n=30 (T7.21)

**Committed before any candidate was assigned, and argued without reference to one.** The rule
above — do not edit to accommodate a scenario — means this table is decided on its own terms, so
the reasoning below cites classes and the record, never a proposed scenario.

### What determines a class's slot count

**1. Distinct diagnosis paths, not equal shares.** ADR-0008 makes fault selection a
diagnostic-diversity choice; slot counts should follow how many genuinely different investigation
paths a class supports, and the record now measures that unevenly.

`bad_deploy` has three documented shapes and the injector says so in as many words — never starts,
starts then fails every call, flaps. `bad_config` has at least three: a wrong backing store, a
service that breaks without being the service that changed, and a broken service-to-service address
where the **caller** alerts while the faulty service reports no errors at all. `dependency_latency`
has one mechanism, and ADR-0007 bounds its magnitude — past the caller's timeout the signal inverts
from latency to absence and the class silently changes.

**`resource_exhaustion` should grow least, and this is the change of view.** CPU is retired
(ADR-0013), leaving memory, and T7.20's probes measured that memory's observable window is narrow
from both sides: too gentle and the container restarts faster than detection with nothing alerting
at all; too harsh and it never starts, alerts far too widely, and its own runtime evidence stops
exporting. A class whose one surviving mechanism has a narrow usable band does not deserve
proportional growth.

**2. Every class gets holdout representation, and the share is per class.** ADR-0008 deferred this
here explicitly. A global 30% that leaves a class at zero cannot support "generalises to held-out
`bad_config`" — which is exactly the sentence the current table cannot say. **Per class:
`round(0.3 × slots)`, minimum 1.** The global ratio is a consequence of that, not a target, and it
rounds to 33% at n=30.

**3. Three dev scenarios per class is the floor, because two cannot show a spread.** CATALOG.md
measured why: `cart-bad-image-tag` recorded **197s and 301s** on the same scenario against an
unchanged world — 53% of the smaller value. *"Two samples cannot describe a distribution."* Three
is where a spread becomes visible at all. **It is a floor, not a sufficiency**: n=3 does not earn a
magnitude claim, and the "direction, not magnitude" caveat on every per-class figure stays until
the record says otherwise — n=20 does not retire it.

**4. Slots are capacity, not a promise.** Three of thirteen authored scenarios (23%) proved
unrecordable and carry `blocked`, which releases the slot rather than consuming it. The catalog is
**10 valid scenarios — 7 dev and 3 holdout** — against 13 authored. Growth targets are stated in
slots; the valid count will trail them, and slots will turn over.

### Allocation at n=20

| Fault class | Slots | Dev | Holdout |
|---|---:|---:|---:|
| `bad_deploy` | 6 | 4 | 2 |
| `bad_config` | 6 | 4 | 2 |
| `dependency_latency` | 4 | 3 | 1 |
| `resource_exhaustion` | 4 | 3 | 1 |
| **Total** | **20** | **14** | **6** (30%) |

Every class clears the dev floor of 3 and has holdout representation. `bad_config` gains the most
because it starts with zero holdout and has the most unexplored paths; `dependency_latency` gains
dev depth because it is the class the record shows at one dev scenario;
`resource_exhaustion` gains one slot, for the reason above.

### Allocation at n=30

| Fault class | Slots | Dev | Holdout |
|---|---:|---:|---:|
| `bad_deploy` | 9 | 6 | 3 |
| `bad_config` | 9 | 6 | 3 |
| `dependency_latency` | 6 | 4 | 2 |
| `resource_exhaustion` | 6 | 4 | 2 |
| **Total** | **30** | **20** | **10** (33%) |

The ratio drifts above 30% because the per-class rounding binds. That is the intended precedence:
a per-class holdout claim is worth more than a round global number.

### Current capacity — the table the guards read

`tests/test_contamination.py` mirrors this and asserts the two have not drifted. It is the n=20
allocation above, restated in the shape the guard parses; the n=10 table stays above as the
committed record of what was decided first.

| Fault class | Dev | Holdout |
|-------------|-----|---------|
| `bad_deploy` | 4 | 2 |
| `dependency_latency` | 3 | 1 |
| `resource_exhaustion` | 3 | 1 |
| `bad_config` | 4 | 2 |

**Totals:** 14 dev / 6 holdout (30% holdout).

### Occupancy (T7.22)

| Slot | Scenario | State |
|------|----------|-------|
| `bad_config-3` | `shipping-quote-misconfig` | **recorded**, dev |
| `dependency_latency-3` | — | **free again**: `ad-dependency-latency` took it, then failed on measurement and is `blocked`, which releases the slot |

Nine slots of twenty remain unfilled. `dependency_latency` still stands at **one recorded dev
scenario**, which is what the extension was meant to fix and has not yet.

### The slots this creates

Ten new slots. **Holdout takes the highest-numbered slots within each class** — a mechanical rule,
stated so future extensions need no judgement either.

| Slot | Fault class | Split |
|------|-------------|-------|
| `bad_deploy-4` | `bad_deploy` | dev |
| `bad_deploy-5` | `bad_deploy` | dev |
| `bad_deploy-6` | `bad_deploy` | **holdout** |
| `bad_config-3` | `bad_config` | dev |
| `bad_config-4` | `bad_config` | dev |
| `bad_config-5` | `bad_config` | **holdout** |
| `bad_config-6` | `bad_config` | **holdout** |
| `dependency_latency-3` | `dependency_latency` | dev |
| `dependency_latency-4` | `dependency_latency` | dev |
| `resource_exhaustion-4` | `resource_exhaustion` | dev |

**The residual steering risk, named.** Positional holdout plus alphabetical fill means the
alphabetically-last authored faults in a class land in holdout, which is predictable — so an author
who chose a fault *id* to steer a scenario could bias the split. Fault ids are set when the injector
definition is written, which ADR-0008 makes the separate earlier decision; the mitigation is that
the two decisions stay separate and reviewable, not that the rule is unguessable.

**Whether any proposed scenario fits these slots is not this decision's question.** The slots are
assigned here without candidates in view; which faults fill them is the fault-selection decision
that comes first and separately, and if a candidate happens to fit, that is a consequence of this
table rather than a reason for it.

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
