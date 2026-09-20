# ADR-0029: four fault classes, and why this world has no fifth

- **Status:** accepted
- **Date:** 2026-09-01
- **Task:** T7.57 (is there a fifth fault class in this world?)
- **Relates to:** ADR-0022 §1.2 (a class is settled by which fix works), ADR-0024 (`scale` is a
  remediation, and this world cannot alert on one), ADR-0026 (the world is somebody else's
  repository), ADR-0027 (two working fixes)

## Context

T7.56 abandoned the fifth `bad_config` scenario and concluded that the shortest path to holdout
entry 4 is further fault classes — which is what ADR-0022's T4.15 addendum named. **This is the
audit that was supposed to come first.** It is written to be read *before* anyone designs a
scenario, because two of its findings will otherwise be rediscovered the expensive way.

It also gives T7.56's topology finding a home. That finding is half an argument on its own — *your
new scenario will have an existing page* — and the other half is here: *and an existing fix*.
Splitting them across two documents would make the next author read both to learn one thing.

## 1. What individuates a fault class here

ADR-0022 §1.2's marked decision: **"A fault's class is settled by which fix actually works."**

Applied to the catalog, from the scenario files rather than from prose:

| class | measured working fix(es) |
|---|---|
| `bad_deploy` | `rollback` |
| `dependency_latency` | `restart` **and** `config_revert` — both measured 3/3 at T7.17 (ADR-0027) |
| `resource_exhaustion` | `config_revert` |
| `bad_config` | `config_revert` |

**The criterion does not individuate the four classes that exist.** `config_revert` is a working
fix for three of the four. It separates `bad_deploy` from the rest and nothing else. This is not a
new complaint — it is the same boundary `CLASS_DISPUTES` registers, and T7.52 found the judge,
never told the label, independently agreeing with the agent on exactly those disputed rows.

**Consequence for a fifth class: the fix test cannot license one.** A candidate whose fix is
`rollback`, `restart` or `config_revert` is not distinguishable from an existing class by the
project's own criterion, however novel its mechanism feels. That kills most candidates before any
world time is spent, which is the cheap outcome.

## 2. The remaining remediation is `scale`, and it is unreachable — measured

`RemediationClass` has four members, read from `evalharness.scenario`: `rollback`, `restart`,
`config_revert`, `scale`. **`scale` is used by no scenario in the catalog**, so it is the only
value a fifth class could claim without a taxonomy change.

ADR-0024 (T7.13) already established that the *demand* side cannot page: 50× load for twenty
minutes, throughput saturating at ~102 req/s, nothing crossing a limit, and **all three alert rules
blind, each for its own reason** — error rate does not fire because saturation queues rather than
errors, latency does not fire because span metrics are emitted on completion, no-traffic does not
fire because traffic plateaus rather than stopping.

T7.57 adds the *supply* side, probed rather than asserted:

```
$ docker compose … up -d --no-build --dry-run --scale cartservice=2
WARNING: The "cartservice" service is using the custom container name "cart-service".
Docker requires each container to have a unique name. Remove the custom name to scale the service
```

**25 of the demo's services carry `container_name`.** Compose refuses to scale any of them, and
`container_name` is upstream's file, which ADR-0026 says this project does not edit. So `scale` is
not merely unused: **the world can neither produce a fault it fixes nor perform the fix.**

## 3. Fault class ≡ injector mechanism, and it is enforced by a test

`tests/test_scenario_schema.py::test_scenario_injections_match_the_fault_they_cite` binds a
scenario's `fault_class` to the `fault_class` of the injector definition it cites, and
`injector.catalog` is authoritative. The injector's `fault_class` selects the **mechanism**:

| mechanism class in `injector.faults` | class |
|---|---|
| `BadDeployFault` (compose override, image) | `bad_deploy` |
| `BadConfigFault` (compose override, env var) | `bad_config` |
| `ResourceExhaustionFault` (compose override, memory or CPU) | `resource_exhaustion` |
| `DependencyLatencyFault` (pumba sidecar, `tc netem`) | `dependency_latency` |

**Four mechanisms, four classes, one-to-one and test-enforced.** So the question *"is there a fifth
fault class?"* is not a question about phenomena. It is: **can the injector gain a fifth mechanism
whose working fix is not already taken?**

## 4. The topology flattens the page, so evidence cannot rescue a candidate either

T7.56's finding, promoted here because it is the constraint every future author meets first.

Read off all fifteen recorded bundles, `alerts_at_fire` clusters into nine shapes, and **every one
is occupied by more than one fault class**. Anything breaking a service on the checkout hot path
produces `{frontend, loadgenerator, checkout}` errors plus `NoTraffic` on the tail, whatever broke
and however. Two worked examples of the cost:

- T7.56's strongest candidate — a service listening on the wrong port, up and healthy — died
  because **`ServiceNoTraffic/cartservice` is already in `cart-redis-misconfig`'s *and*
  `cart-bad-image-tag`'s recorded alert windows.** Its claim to novelty was false against the
  record.
- The feature-flag store is excluded by `flag-service-crashloop`'s recorded `alerts_at_fire = []`:
  breaking the flag service pages **nothing**.

**A new class therefore has to be distinguished by remediation, and §1 shows remediation is
exhausted.** The two halves close on each other. That is the shape of the limit.

## 5. The candidates, and how each dies

| candidate | what the injector could do | why it dies |
|---|---|---|
| **Partition / DNS failure** | DNS: an env var. Partition: `pumba netem loss`, the sidecar already in use | DNS is an env var → `bad_config`/`config_revert`. A partition is cleared by recreating the target or deleting the qdisc — **`dependency_latency`'s two measured fixes** (ADR-0027) |
| **Expired or wrong credential** | the world's only credentialed link is `DATABASE_URL` / `POSTGRES_PASSWORD` on the flag store; both env vars | env var → `bad_config`/`config_revert`. **And** breaking the flag service pages nothing. Dead twice |
| **Clock skew** | **nothing** | containers share the host kernel clock; skewing one needs `CAP_SYS_TIME` and moves the host's. Faking it needs `libfaketime` baked into an image, and ADR-0026 pins images as pulled, never built |
| **Queue or pool exhausted** | **nothing** — the demo exposes no pool-size or queue-depth knob; the env surface is addresses (T7.39) and ports | reachable only by load, and ADR-0024 measured that load pages nothing |
| **Downstream returns wrong data** | real: swap `ffs-stub:1` → `:3` | an image swap is `BadDeployFault` → **`bad_deploy`/`rollback`** by the test-enforced binding in §3 |
| **Rate limit** | **nothing** — nothing in the demo rate-limits. Envoy could, but its config is a world file | editing it moves `compose_digest` / `observability_digest`: that is a **world move**, not an injection |

**One candidate could not be resolved at desk and is recorded as such rather than as a survivor.**
Corrupting `redis-cart`'s contents — via `docker exec redis-cli`, a mechanism the injector does not
have but could trivially gain — has a fix that is either `restart` (if a container restart clears
the data, in which case it collides with `dependency_latency`) or a genuinely new *flush*
remediation (if Redis's default RDB snapshot restores the corruption). **Which it is depends on
persistence behaviour under this exact config and needs world time to establish.** It is written
down here so nobody re-derives it, and it is **not** claimed as a fifth class: T7.56 disqualified a
candidate for resting on a signal that could not be established at desk, and that rule applies to
this one.

## 6. The cost that makes the question moot anyway

**Adding a fifth `FaultClass` member moves the pipeline stamp.** `FaultClass` is a `Literal` in
`faultline.agents.contracts`, carried by a contract model, and `runtime_version` hashes
`model_json_schema()` over every contract (`faultline.agents.stamp`). ADR-0024 said this about
`scale`; it is true of any member.

So a fifth class moves `prompts:1b0e7cbb4c47` and makes every recorded run incomparable with every
future one — **six dev sweeps and all three holdout entries.**

**And that is fatal to the purpose.** The reason to want a fifth class was to extend the holdout set
and unblock entry 4. Entry 4 is already a new comparability generation, because entries 1–3 ran two
worlds back (T7.54). Under a moved stamp it would also be incomparable with **dev sweep 7, the
current benchmark** — so it would compare to nothing at all. **Adding a fault class to unblock entry
4 destroys the thing entry 4 was for.**

## Decision

**There is no fifth fault class in this world, and the project should stop looking for one.**

Four classes over four mechanisms, a remediation set that already fails to separate three of the
four, one unused remediation the world can neither cause nor perform, a topology that flattens every
page, and a taxonomy change that costs the stamp. That is a coherent limit, not a gap.

**What follows, stated plainly rather than softened:**

- **Entry 4 is blocked indefinitely**, not pending. Q9 asked for the holdout set to be extended;
  §1–§5 say it cannot be, in `bad_config` (T7.56) or in a new class (here). `bad_deploy-6` inherits
  the exhausted-mechanism problem behind Q1, which T7.40 decided against on its merits.
- **The holdout arm stays at three entries, seven runs, four answered, against a world two
  generations superseded.** T7.53 called it underpowered; it is now underpowered *and* closed.
- **The benchmark's holdout claim is what it is** and should keep being reported the way T7.53
  reported it: three entries, the conditions, and the statement that the arm cannot support a claim.

## Consequences

Easier: no further world time is spent searching for a fifth class. Six candidate designs
are recorded above with the measured or structural reason each died, so the next person
does not re-derive them — which is the expensive way this question has been answered twice
already.

Harder: three commitments in the execution plan cannot be delivered as written, and this
ADR is what makes that a finding rather than an outstanding task. T7.0 (expand the injector
to eight fault classes) and T7.1 (grow the catalog to 30+ scenarios across ~8 classes) are
both unachievable in this world. The catalog stays at four classes and thirteen scenarios,
so per-class figures rest on an n as small as two — a limit of the benchmark, not of the
agent, and it belongs beside any per-class table.

Holdout entry 4 stays blocked. Extending the holdout set needs new scenarios; the free
slots sit in classes that cannot take a distinct one; and adding a class would move the
stamp, which would make entry 4 incomparable with the dev sweep it exists to be read
against. The holdout arm therefore remains three entries against a superseded world.

Changing any of this needs a different demo world, not a cleverer scenario. That is the
trigger recorded in `docs/QUEUE.md`, not a task anyone can pick up here.

## What would change it

Not a cleverer scenario. One of:

1. **A different demo world** — one with more failure surface, more knobs that are not addresses, a
   topology that does not funnel every failure through checkout, and services that can scale. This
   is the honest answer and it is a large piece of work: new world, new digests, a full re-record,
   and every figure in the repository re-founded.
2. **An extended injector with a new mechanism *and* a new `RemediationClass` value** — which means
   a stamp move, a pre-registration, and re-founding the benchmark. Worth doing only alongside (1),
   because doing it for one scenario spends the comparability of six sweeps.
3. **A capability change** that gives the existing pages more to distinguish — Q1's container exit
   reason is the candidate, and T7.40 decided against it on its merits and would have to be
   reversed on new evidence, not on this task's inconvenience.

**None of these is a scenario build**, which is why this ADR exists rather than another abandoned
YAML.

---

## Addendum, 2026-09-20 (T7.0's closure) — the seventh candidate: disk, and why this world has none

§5's table has six candidates. T7.0's spec row names a seventh this ADR never assessed — **disk
fill** — and it is added here rather than in the task's own note, because the next person to ask
will read §5 and not a PLAN entry. It was assessed as a **mechanism** under `resource_exhaustion`,
not as a class: disk is a resource the way memory and CPU are, ADR-0010 draws the line that a
mechanism is not a class, and a mechanism costs no stamp. §1's fix criterion therefore never had to
be reached. **It dies before that, four times, and three of the four are measured rather than
argued.**

**1. No container in this world has a disk of its own.** `docker compose config` over the three
world files, read 2026-09-20: **zero named volumes, 27 services, and six services carrying any
mount at all** — `grafana`, `prometheus`, `otelcol`, `alertmanager`, `tempo`, `promtail` — every one
of them a read-only bind of a config file, plus promtail's `docker.sock`. No shop service has a
mount. Nothing persists. So *"fill a container's disk"* has no referent here: a write goes to the
container's writable layer, which is the host's filesystem.

**2. Which makes the blast radius the host, and that alone disqualifies it.** ADR-0007's first
requirement is that **reversibility is the product**. A mechanism that fills the writable layer
fills the disk the rest of the machine is on — and on the deployment that disk also carries the
platform's own Postgres and its backups: `deploy/README.md` §4 records *"nightly snapshots on the
same disk as the database and none off the machine"*. An injector whose failure mode is *the
platform's storage is full* is not reversible in the sense that matters, and no `restore` record
can undo a disk that filled somewhere else while the fault was live. The only route that avoids
this is a **quota rather than a fill** — a sized `tmpfs` at the write path, applied by a generated
override and reverted by dropping it, which is `_ComposeOverrideFault` exactly as it stands. That
route survives to (3).

**3. The only service worth capping cannot be made to fire deterministically.** Redis is the one
process here that writes anything it needs. Read from the running container, 2026-09-20:

```
dir                         /data
appendonly                  no
save                        3600 1 300 100 60 10000
stop-writes-on-bgsave-error yes
```

The last line is the interesting one and it points the right way: with the snapshot target capped,
a failed `BGSAVE` makes Redis **refuse writes**, so `cartservice` starts erroring — a real,
documented, non-exotic failure. But the first save is on Redis's own timer: one changed key in an
hour, a hundred in five minutes, ten thousand in a minute. **The fault would land up to five
minutes after injection, and only at a change volume the load generator has to supply.** ADR-0007's
second requirement is that *"faults must fire deterministically. A fault that manifests only under a
load spike produces scenarios that fail intermittently for reasons unrelated to the agent under
test."* This is that fault. Forcing the save with `docker exec redis-cli bgsave` would make it
prompt, but that is the `docker exec` mechanism §5 already records as uncosted, and it would make
the *injector*, not the world, the thing that produced the failure.

**4. And when it did fire it would page nothing new.** §4 of this ADR: anything breaking a service
on the checkout hot path produces `{frontend, loadgenerator, checkout}` errors plus `NoTraffic` on
the tail. Cart writes refused is that shape, and `ServiceNoTraffic/cartservice` is already in both
`cart-redis-misconfig`'s and `cart-bad-image-tag`'s recorded alert windows — the same collision that
killed T7.56's wrong-port candidate. The fix would be *drop the override and recreate*, which is
`config_revert`, which is `resource_exhaustion`'s existing fix. Legitimate for a mechanism, and
worth nothing when the mechanism produces no distinguishable incident.

| candidate | what the injector could do | why it dies |
|---|---|---|
| **Disk fill / disk quota** | a sized `tmpfs` at a write path, by generated override — the existing compose-override machinery | **zero named volumes across 27 services**, so a fill targets the host's disk and takes the platform's own database and backups with it (ADR-0007: reversibility). The quota form survives that and then fails determinism: Redis's `save 3600 1 300 100 60 10000` puts the failure up to five minutes late and load-contingent. When it does fire, `stop-writes-on-bgsave-error yes` makes it cart-errors-on-the-hot-path — §4's flattened shape, already occupied twice |

**What this does not touch.** Q6 (`redis-cart` eviction / `maxmemory`) stays exactly as
`docs/QUEUE.md` records it — a rejected candidate needing a fresh argument, not a trigger. The
readings above are evidence *about* Redis's configuration and change nothing about that row; if
anyone does revive it, `stop-writes-on-bgsave-error yes` and the save policy are written down here
so the behaviour does not have to be re-established.

**The decision above is unchanged and is now better supported.** Seven candidates, seven deaths,
three of them measured in this addendum. The limit is structural: **a world with no volumes, no
scalable services, one topology and four remediations.**
