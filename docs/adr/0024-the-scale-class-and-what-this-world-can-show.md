# ADR-0024: `scale` is a remediation class, and this world cannot alert on one

- **Status:** accepted
- **Date:** 2026-08-28
- **Task:** T7.13 (the scale class gets a scenario)
- **Relates to:** ADR-0013 (retiring CPU throttling), ADR-0022 §3.3 (discards are recorded)

## Context

`scale` had n=0 in every per-class table and no scenario. T7.13 set out to close that gap by
designing, rehearsing and recording the catalog's first scale scenario. The design and the
boundary argument are below; the recording did not happen, and the measurement that stopped it
is the substance of this ADR.

## 1. `scale` is not a fault class in this project

The task was framed as "the fault class has n=0". It is not a fault class. Three independent
places in the repository agree:

| where | what it says |
|---|---|
| `evalharness.scenario.FaultClass` | four members: `bad_deploy`, `dependency_latency`, `resource_exhaustion`, `bad_config` |
| `faultline.agents.contracts.FaultClass` | the agent's answer space: the same four, plus `unknown` |
| `evals/scenarios/SPLIT.md` | slots are allocated by fault class; there is no `scale` slot |

`scale` appears only in `RemediationClass`, in both the scenario schema and the agent contract.
The `scale` row in `SWEEP-2026-08-26-taxonomy.md`'s **fault class** table is therefore a
remediation class sitting in a fault-class table — a mislabelled row, not an empty class.

**This is not fixed by adding `scale` to `FaultClass`.** That enum is hashed into
`runtime_version` through `contracts.model_json_schema()`, so adding a member moves the stamp and
makes every recorded run incomparable with every future one. Widening the agent's answer space is
a decision with its own pre-registration, not a side effect of authoring a scenario.

So the gap that can actually be closed is the empty **remediation** class, and the scenario below
is `resource_exhaustion` / `scale`.

## 2. The boundary: `scale` and `resource_exhaustion` are on different axes

The two are not rivals. `resource_exhaustion` is what happened; `scale` is what fixes it. A
scenario can be — and this one is — both.

What needs stating is the boundary between the two *remediations*, because that is where a real
ambiguity lives:

> **`config_revert` when the constrained resource was changed. `scale` when it was not.**

The three memory squeezes already in the catalog are `resource_exhaustion` / `config_revert`
because each lowered a limit that had a known-good previous value: restoring it is the fix. A
scale fault has no such value to restore. Nothing was taken away; demand arrived.

**This boundary is decidable from evidence, not from reading**, which is what keeps it from
importing a second dispute alongside the change-versus-symptom one the register already carries.
The discriminator is a tool call: run `change_history` against the service that is failing to
serve. A capacity reduction shows a change there. A demand surge shows nothing there, and the
change instead sits on a different service that is behaving correctly. The existing dispute is
irreducible because the change and the symptom are on the *same* service and both readings are
defensible; here they are on different services and the evidence says which is which.

That is also why the design has to be demand-side. Any fault that removes capacity *from the
target* is reversible by construction, and its honest remediation is `config_revert` — the label
would be a fiction maintained by the scenario file rather than a fact the evidence supports.

## 3. What was designed

`storefront-load-surge`: raise `LOCUST_USERS` from 10 to 500 on the load driver. Nothing in the
storefront is changed or broken; it simply gets more customers than it can serve. The mechanism
is the existing `bad_config` env-var handler, because that is how the driver is steered — but
`LOCUST_USERS=500` violates no invariant and the scenario's ground truth is not a
misconfiguration.

**T7.5's gate, applied before recording** and measured against the live world, since a scenario
with no bundle has no captures for T7.4's census to read:

| target | runtime series | log lines/hour | classes that can answer idle-or-absent |
|---|---|---:|---|
| `cartservice` | 20 (`process_runtime_dotnet_*`) | 4738 | 2 |
| `redis-cart` | 0 | 72 | 1 (logs) |
| `loadgenerator` (injection target) | 0 | **absent from Loki's `service` set** | **0** |

The scenario declares `answers_idle_or_absent: []`, and the plain statement the gate asks for is
this: **its narrative must not turn on whether anything was idle or absent.** Not because the
evidence is unreachable but because the question does not arise — under this fault nothing goes
idle and nothing goes absent. The world keeps serving throughout. That is the finding.

## 4. The measurement: 50x load, twenty minutes, no alert

Injected by hand as a reversible probe, world reverted afterwards, nothing recorded.

| offered load | frontend req/s | cart-service mem | frontend mem | redis-cart mem | alerts |
|---|---:|---:|---:|---:|---|
| 10 users (baseline) | 7.2 | 70.2% (281/400MiB) | 67.9% | 46% | none¹ |
| 100 users (10x) | 92.2 | 70.8% | 67.2% | 48.7% | none |
| 500 users (50x), T+3m | 99.6 | 74.6% | 68.3% | 46.7% | none |
| 500 users, T+11m | 102.4 | 82.6% | 74.6% | 53.9% | none |
| 500 users, T+20m | 102.4 | 82.8% (331MiB) | 76.4% | 56.5% | **none** |

¹ A pre-existing `ServiceHighLatency/checkoutservice` was firing at baseline from histogram
degeneracy at 0.66 req/s. It **cleared at 02:44** once the surge gave the histogram enough
samples — incidental confirmation that it was a sparse-data artifact rather than a real
condition, and a reminder that the baseline gate can refuse on it.

Three things this establishes:

**Throughput saturates at ~102 req/s.** Going from 100 to 500 concurrent shoppers — five times
the offered load — bought 11% more throughput. The world is at its capacity ceiling. The scale
fault is real and it is happening.

**Nothing crosses a limit.** cart-service climbed 70% → 83% and settled; frontend 67% → 76% and
settled. No OOM kill, no restart, no CPU quota reached (frontend used 22.9% of one core of ten at
12x load).

**No rule can see it.** All three alert rules are blind to this shape, each for its own reason:
`ServiceHighErrorRate` — saturation queues, it does not error. `ServiceHighLatency` — span
metrics are emitted on completion, so the percentile is computed from the requests that finished,
which is ADR-0013's finding arriving from the other direction. `ServiceNoTraffic` — traffic never
stops; it plateaus.

**A fault that opens no incident can never dispatch an agent.** There is nothing to score.

## 4b. The schema cannot express this scenario either

Found while trying to commit it, and it is a separate obstacle from the alert path.

`test_scenario_injections_match_the_fault_they_cite` binds a scenario's `fault_class` to the
`fault_class` of the injector definition it cites, and `injector.catalog` is authoritative. The
injector's `fault_class` selects the *mechanism*: the only way to steer the load driver is an
environment variable, which is `BadConfigFault`, which is `bad_config`.

So a demand-side scale scenario can only be committed under the label `bad_config` — that the load
generator was *misconfigured*. It was not. `LOCUST_USERS=500` violates no invariant; the driver is
doing exactly its job, and the whole boundary argument in §2 rests on that being true. A scenario
file asserting otherwise would import the change-versus-symptom dispute directly into the class
this ADR exists to keep clear of it.

**No scenario file is committed.** The guard is right and the label would be false, so the design
lives here rather than in a `blocked: true` YAML that says the wrong thing to satisfy a test. What
is committed is the injector definition — `storefront-load-surge`, whose `bad_config` class
honestly describes its mechanism rather than a phenomenon — so that the 90-minute `redis-cart`
path in §5 is reproducible rather than theoretical.

## 5. Decision

**No scale scenario is committed, and `blocked: true` was not the right home for it either.**
That flag is for a fault that is injectable but not observable; this one is both of those *and*
unlabellable (§4b). SPLIT.md is unchanged — correct twice over, since it allocates by fault class
and `scale` is not one. `scale` stays n=0 in the per-class tables, now with a reason rather than an
absence. The injector gains the load-surge mechanism, which is real and works.

**`scale` remains unreachable for the benchmark until something changes.** Three options, none
taken here because each is a larger decision than authoring a scenario:

1. **A saturation alert rule** — a plateau or queue-depth signal, since the three existing rules
   are structurally blind to this shape. This is the smallest change that makes the class
   scoreable, and it changes the alert path every recorded bundle was measured against.
2. **A much longer scenario.** `redis-cart` is the one resource that rises monotonically and does
   not recover: `noeviction`, no `maxmemory`, a 20MiB container ceiling, and it stepped from 46%
   to 59% across the probe and stayed there. Extrapolating its rate, sustained 50x load would
   OOM it in roughly 90 minutes. That is a real scale fault with a real page at the end, and an
   onset an order of magnitude longer than the catalog's current range of 166–390s.
3. **Accept that this world has no fast scale fault** and leave the class empty, as ADR-0013 left
   CPU throttling — which is the precedent for retiring a mechanism on measurement rather than
   retuning it against an interval the evidence says is empty.

## Consequences

- The catalog gains a scale scenario file and no scale *recording*; the per-class tables are
  unchanged at n=0 and now carry the reason.
- `redis-cart` is documented as a latent capacity defect in the committed world: nothing evicts,
  and its usage is monotonic in cumulative traffic rather than in current load.
- The `scale` row in the taxonomy table is corrected: it is a remediation class, and a fault-class
  table should not have had a row for it.
