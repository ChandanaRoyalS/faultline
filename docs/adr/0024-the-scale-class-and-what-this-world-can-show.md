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

## Addendum (T7.19): the open decision is closed — the scale class stays empty

§5 left three options and took none. T7.19 measured the one they all rested on and closes it.

### The measurement retires the figure the options were weighed against

T7.13 offered `redis-cart` as "the only known route to a real `scale`-class scenario", at roughly
90 minutes to page, and flagged that as an extrapolation from a 20-minute slope. It is worse than
an extrapolation: **it extrapolated the wrong quantity.**

`redis-cart` runs RDB persistence (`save 3600 1 300 100 60 10000`). Every bgsave writes a
multi-megabyte `dump.rdb` into page cache, which `docker stats` counts. The kernel reclaims page
cache before it OOM-kills, so what binds is `anon + slab` — **8.1 MiB of 20 MiB, 38.7%**, on a
container whose `memory.current` reads 96.2%.

Measured at rest, and the growth **is** real and **is** linear — `expires=0`, every TTL `-1`,
`maxmemory 0`, `noeviction`, 204 bytes per key:

| window | keys | anon |
|---|---:|---:|
| 11 minutes | +0.31 /s | +129.9 B/s |
| **27.6 hours** (container uptime) | **+0.192 /s** | **+64.8 B/s** |

**Time to the ceiling: ≈ 55 hours at rest.** Under sustained 50x load, scaling by the world's
*measured* throughput ceiling of 102 req/s (12x baseline, not 50x): **≈ 4 hours** — still an
extrapolation, and labelled one. Not 90 minutes.

**And T7.13's supporting claim is falsified.** It reported the surge left redis "permanently 11
points higher" and that it "did not come back down when load did." Over 11 minutes at rest,
`memory.current` fell at **−2060 B/s** as page cache drained. It came back down; T7.13 looked once.
Full evidence in `docs/evidence/t7.19-redis-growth/`.

### The decision, against the harness rather than in the abstract

**The catalog is shaped for fast-onset, reversible faults. This one is neither. `scale` stays
empty, with a reason.**

Four constraints, and the last is fatal on its own:

**The wait.** T7.12 set the correlate budget at 180 scrapes — 900s of world time — derived from a
catalog whose onsets run 166–390s. Even the optimistic 4-hour figure needs ~2,880 scrapes, **16x**
the budget; the at-rest 55 hours needs 40,000. The recorder is sized the same way:
`DEFAULT_ALERT_TIMEOUT` 420s, `CLEAR_TIMEOUT` 600s.

**The sweep.** Seven scenarios already run over two hours. One scenario at four hours triples the
sweep, and every re-sweep after every stamp move pays it again — and stamp moves are routine here
(ADR-0028 §6 has the next one queued).

**The gate between scenarios.** T7.14 measured `ServiceHighLatency/checkoutservice` refusing ~11%
of gate readings at rest, in episodes lasting 15–60 minutes. Over a four-hour run the question is
not whether an excursion occurs but how many; and `MIN_CONTAINER_UPTIME_SECONDS` plus the settle
window have to be satisfied *after* it.

**The fault does not revert, and this alone disqualifies it.** Every other fault in the catalog is
undone by removing what was added. This one is undone only by `FLUSHDB` or recreating the
container — the keys written during the run do not leave. **The world after the scenario is not the
world before it**, which contradicts the catalog's central claim that its scenarios were measured
under the same conditions, and would invalidate the bundles recorded around it. A digest cannot see
it, either: `compose_digest` covers file content, and this is accumulated runtime state.

### On §5's three options

1. **A saturation alert rule** — still the smallest change that would make the class *scoreable*,
   and it is unaffected by this measurement, because it addresses T7.13's throughput plateau rather
   than redis. Not taken here; it changes the alert path every recorded bundle was measured
   against (T7.14's argument, and T7.15's digest now covers the file).
2. **A long scenario built on `redis-cart`** — **rejected**, on the four constraints above.
3. **Accept the class stays empty** — **taken**, as ADR-0013 left CPU throttling: retired on
   measurement rather than retuned against an interval the evidence says is empty.

**An empty class with a stated reason is a result.** `scale` reads: this world cannot page on one
inside any window the harness is built to wait, and the one candidate that eventually would is not
reversible.

### If anyone revisits it, the remediation is not known either

Nobody has tested what fixes it. There are at least three candidates — `FLUSHDB`, recreating the
container, raising `maxmemory` with an eviction policy — and they are not obviously the same class:
the first two are `restart`-shaped, the third `scale`-shaped, and T7.17 showed that guessing which
of several plausible fixes is "the" one produces a ground truth that stands wrong for three stamps.
**Any ground truth here needs T7.17's treatment first**: each candidate applied to a live
injection, several attempts, measured for whether the fault clears and stays cleared.

### What must not be left as it is

**`redis-cart` accumulating unbounded against a hard ceiling is a property of this world, and every
long run walks toward it.** Two consequences, one immediate:

**The recorder will begin refusing rehearsals, and it will look like something else.**
`MEMORY_HEADROOM_PERCENT = 90.0` refuses when any container exceeds 90% of its limit.
`redis-cart` reaches that on its own in **23–46 hours** at the measured rates. The refusal will
name a container no scenario touches, during a sweep that has nothing to do with it. Documented at
that constant, so whoever hits it finds the explanation where it fires rather than here.

> **Landed at T7.28, noticed at T7.45's sweep.** `redis-cart` runs
> `--maxmemory 12mb --maxmemory-policy allkeys-lru`, and T7.38 measured it holding at 3.65M of 12M
> with zero evictions under a fault. The paragraph below is the reasoning that queued it and is kept
> as the record of why; it is **no longer pending**. See `docs/QUEUE.md`.

**A bound belongs in the digest-locked queue, beside the otel-col `memory_limiter` and the kafka
retention change.** `maxmemory` with an eviction policy, or a `--save ''`-style change, is a change
to `world/docker-compose.yml`: it moves `compose_digest` and obsoletes the comparability of every
current bundle. That is precisely why it is queued rather than applied — it batches with the other
queued world changes and lands with one re-record, as T7.1 did.

**Interim, and it is not a fix:** flush `redis-cart` before a long sweep. That is a workaround with
a real cost — it discards accumulated cart state, so it is itself a world change, just one no digest
records. Say it in the run notes when it is done.

Revisit if: the queued world changes land (the bound goes in with them), or a saturation alert rule
makes the class scoreable by a route that does not involve redis.
