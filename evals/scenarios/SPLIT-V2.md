# Dev / holdout allocation on the v2 world (T7.1, under T1.6)

**Committed before any v2 scenario is authored. Do not edit to accommodate a scenario.**

`SPLIT.md` is v1's allocation and is never edited (ADR-0008; T7.21). The world moved to
OpenTelemetry Demo 2.2.0 (ADR-0042), the injector to nine classes (T7.0, ADR-0043), and ADR-0042
made *a fresh dev/holdout allocation committed before authoring* the condition for T7.1. This is
that allocation. Every rule of `SPLIT.md` carries over unchanged: slots are allocated by class and
index, not by name; authoring fills a class's slots in order and a scenario inherits its slot's
split, whatever it turns out to be; holdout takes the highest-numbered slots in each row; a
`blocked` scenario releases its slot; the table is capacity, not a promise.

**v2 scenario files live in `evals/scenarios/v2/`.** Every v1 benchmark consumer - the sweeps,
the baselines, the README table, the post-mortem corpus - reads `evals/scenarios/*.yaml` flat and
so sees v1 alone; the schema, contamination and recorder guards read the tree recursively and see
both. Bundles land where v1's do, `artifacts/<split>/<id>/`, and never collide because v2 ids say
`v2-`.

**The v1 catalog stays where it is.** Eighteen files, thirteen bundles, three holdout entries -
none is edited, moved or re-counted. A v1 design carried to v2 is a *new* scenario in a v2 slot with
its own rehearsal and fingerprint (`world: v2`), never a continuation of its v1 namesake.

Rationale: [ADR-0008](../../docs/adr/0008-contamination-model.md), T7.1 addendum.

## The principles, as T7.21 stated them, applied to nine classes

1. **Distinct diagnosis paths, not equal shares.** A class's slot count follows how many genuinely
   different investigation paths the record has measured for it - on this world, from the T7.0
   attempts (`evals/attempts/A1`-`A8b`) and rehearsals (`R1`-`R5`), and from v1 where the
   mechanism is the same.
2. **Holdout per class: `round(0.3 × slots)`, minimum 1.** The global ratio is a consequence.
3. **Three dev per class is the floor.** Two samples cannot show a spread (`cart-bad-image-tag`:
   197 s and 301 s on an unchanged world).
4. **Slots are capacity.** The record's candidate failure rate is 23-35 % (T7.21; ADR-0042; three
   of nine T7.0 attempts). Forty-four slots is the capacity that makes thirty-plus *valid*
   scenarios reachable; the headline count is valid scenarios, never slots.

## Allocation at n=44

| row | what the record measured about its paths | slots | dev | holdout |
|---|---|---:|---:|---:|
| `bad_config` | at least four: a wrong backing store; a service that breaks without being the one that changed; a broken service-to-service address where the *caller* pages; a wrong credential (A6: 100 % visible errors on the one service, `bad_config` by definition) | 6 | 4 | 2 |
| `feature_flag` | v2 ships fifteen flags its services read (ADR-0042); the one attempted (A1) pages on the caller as fast errors with no change record; others are latency, a leak, a load flood - several distinct pages behind one mechanism | 6 | 4 | 2 |
| `bad_deploy` | two shapes, as T7.39 corrected: never starts, or starts and fails on the hot path - both the same image swap | 4 | 3 | 1 |
| `dependency_latency` | one mechanism, magnitude bounded by ADR-0007 (past the caller's timeout the class changes) | 4 | 3 | 1 |
| `resource_exhaustion` | memory only, with T7.20's narrow usable band; v2's leak flag is a second route to the same page | 4 | 3 | 1 |
| `process_freeze` | one mechanism; the cascade is the target's (R2b: thirteen alerts on ten services from one paused leaf) | 4 | 3 | 1 |
| `network_partition` | the freeze's look-alike on (a), (b) and (d); separated on (c) alone (R3); targets vary as the freeze's do | 4 | 3 | 1 |
| `datastore_corruption` | one store today (the cart's valkey, R4b); a second store is a second tool and its own precondition | 4 | 3 | 1 |
| `disk_fill` | one writable directory today (kafka's tmpfs, R5); a second target needs its own precondition read off the running container, as A8 → A8b learned | 4 | 3 | 1 |
| **`injection`** (the P6 cases) | a base scenario of any class with a payload planted in its telemetry - a log line or a change record telling the reader to propose a decoy (T6.8). Ground truth is the base's; the decoy is what a correct verdict does not say. The execution plan's T7.1 row counts these inside the 30+ *"rehearsed and labeled like the first ten, and assigned to the dev or holdout split at creation"*, so they hold slots here. Three dev because robustness is tuned against them; one holdout because a claim about injection resistance needs one the tuning never saw | 4 | 3 | 1 |
| **total** | | **44** | **32** | **12** (27 %) |

**Storm cases are not a row.** The plan's T7.1 also names *"the storm cases from P6"* (T6.7's
alert-storm test at 200+ alerts). On v2 a storm is what the freeze, the partition and the disk
fill *are* - R2b thirteen alerts, R3 sixteen, R5 six across producer and consumers - so storm
representation comes from those rows and is recorded on each scenario as a measured property of
its page (`storm: true` where the rehearsal's alert count is ten or more), not allocated as a kind
of its own. A row for storms would double-count the hang classes.

### Per-row holdout, stated

`round(0.3 × 6) = 2`; `round(0.3 × 4) = 1`. Twelve holdout of forty-four is 27 %, under the
global 30 % because four-slot rows round down; the per-row floor takes precedence, as T7.21
decided.

### Current capacity - the table the guards read

`tests/test_contamination.py` mirrors this as `ALLOCATION_V2` and asserts the two have not
drifted. Rows are `FaultClass` values and the one kind row, `injection`.

| Row | Dev | Holdout |
|-------------|-----|---------|
| `bad_config` | 4 | 2 |
| `feature_flag` | 4 | 2 |
| `bad_deploy` | 3 | 1 |
| `dependency_latency` | 3 | 1 |
| `resource_exhaustion` | 3 | 1 |
| `process_freeze` | 3 | 1 |
| `network_partition` | 3 | 1 |
| `datastore_corruption` | 3 | 1 |
| `disk_fill` | 3 | 1 |
| `injection` | 3 | 1 |

**Totals:** 32 dev / 12 holdout.

### Slot ids and the split each carries

Slots are `v2/<row>-<n>`, so a v2 slot can never be mistaken for a v1 one of the same class. Holdout
takes the highest numbers: in a six-slot row `-5` and `-6` are holdout; in a four-slot row `-4`.
A new scenario takes the lowest-numbered free slot in its row and records it in `slot`; a
scenario of `kind: injection` takes an `injection` slot whatever its `fault_class`.

| row | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| `bad_config`, `feature_flag` | dev | dev | dev | dev | **holdout** | **holdout** |
| every other row | dev | dev | dev | **holdout** | | |

## What this document does not decide

**Which faults fill the slots.** No candidate was in view when the rows were argued: the reasoning
above cites classes and the T7.0 record, never a proposed scenario. Fault selection is the separate,
earlier decision ADR-0008 requires, and it is made in the scenario files as they are authored - a
v1 design carried over where its mechanism exists on v2 (T7.1's decision C), new designs for the
rest.

**Distinctness.** ADR-0042 makes distinctness *a pre-registered acceptance criterion for the new
catalog*: thirty scenarios that are near-duplicates in alert shape buy n and not power. A slot is
filled by a rehearsal whose page and evidence are shown to differ from its class-mates' on at
least one of ADR-0043's dimensions; a scenario that cannot show that is `blocked` and releases the
slot. That criterion is applied per scenario at rehearsal, not here.

## Occupancy

None. **Forty-four free** - thirty-two dev and twelve holdout. This section is extended as
scenarios are authored, one line per slot, and never rewritten.

| Slot | Split | Scenario | Recorded |
|------|-------|----------|----------|
| `v2/process_freeze-1` | dev | `v2-product-catalog-freeze` | 2026-09-24, third recording (the first two are under its `superseded/`) |
| `v2/bad_config-1` | dev | `v2-accounting-bad-credential` | 2026-09-24, first recording |
| ~~`v2/bad_config-2`~~ | dev | ~~`v2-cart-valkey-misconfig`~~ | 2026-09-24, recorded once and **blocked**: on v2 the design crashloops (`bad_deploy`'s page). The slot is released to the next candidate |
| `v2/bad_config-2` | dev | `v2-payment-telemetry-blackout` | 2026-09-25, first recording, into the slot the cart scenario released |
| `v2/bad_config-3` | dev | `v2-shipping-quote-misconfig` | 2026-09-26, third recording, on the world Q101, Q102 and Q104 left (the first two, on older worlds, are under its `superseded/`) |
| `v2/bad_config-4` | dev | `v2-frontend-cart-misconfig` | 2026-09-26, first recording. The row's second reserve: the first, `v2-fraud-detection-kafka-misconfig`, shares holdout row 5's mechanism and was passed over (`t7.1-candidates.md`) |
| `v2/bad_config-5` | holdout | `v2-accounting-kafka-misconfig` | 2026-09-26, first recording. Value `kafka:9094`, not the candidate list's `kafka:9093` (v2 Kafka's controller listener), decided before recording (`t7.1-candidates.md`) |
| `v2/bad_config-6` | holdout | `v2-checkout-currency-misconfig` | 2026-09-26, first recording. Distinct from `v2-shipping-quote-misconfig` on (a), the comparator and prediction named before recording (`t7.1-candidates.md`) |
| `v2/feature_flag-1` | dev | `v2-product-catalog-flag-failure` | 2026-09-26, first recording; reproduced A1's page (the culprit under the line) |
| `v2/feature_flag-2` | dev | `v2-cart-flag-failure` | 2026-09-26, first recording; checkout pages while its orders complete |
| `v2/feature_flag-3` | dev | `v2-fraud-detection-flag-queue-lag` | 2026-09-26, second recording, after the ground truth was corrected against the first (under its `superseded/`): the flag also breaks accounting until a restart |
| `v2/feature_flag-4` | dev | `v2-ad-flag-failure` | 2026-09-26, first recording. The row's reserve: row 4, `v2-image-provider-flag-slow-load`, was blocked on its verification without a recording (its flag has no trigger on this world), and `paymentFailure` was passed over for holdout row 5 (`t7.1-candidates.md`) |
| `v2/feature_flag-5` | holdout | `v2-payment-flag-unreachable` | 2026-09-26, first recording. The flag acts in checkout's code, so checkout is the target; distinct in the row on (a), as predicted before recording (`t7.1-candidates.md`) |
| `v2/feature_flag-6` | holdout | `v2-email-flag-memory-leak` | 2026-09-26, first recording. The row's reserve: row 6, `v2-recommendation-flag-cache-leak`, was blocked on its verification without a recording (on this world its cache never fills, so it leaks nothing); variant `10000x`, chosen before authoring (`t7.1-candidates.md`) |
| `v2/bad_deploy-1` | dev | `v2-cart-bad-image-tag` | 2026-09-27, first recording. Distinct from `v2-frontend-cart-misconfig` on (a) and (b), the comparator named before recording (`t7.1-candidates.md`) |
| `v2/bad_deploy-2` | dev | `v2-shipping-wrong-image` | 2026-09-27, first recording. Distinct from `v2-shipping-quote-misconfig` on (a) and (b), the comparator named before recording, and from row 1 on (a) (`t7.1-candidates.md`) |
| `v2/bad_deploy-3` | dev | `v2-ad-bad-image-tag` | 2026-09-27, first recording, on the revised world. The row's design and the listed reserve were passed over in section 1's spirit and a new reserve, ad, was chosen before authoring; distinct in the row on (a) and from `v2-ad-flag-failure` on (a) and (b), as predicted before recording (`t7.1-candidates.md`) |
| `v2/bad_deploy-4` | holdout | `v2-email-wrong-image` | 2026-09-27, first recording, on the revised world. v1's holdout carried to v2's email; the image's shape probed before authoring. Distinct from row 2 on (a) and from `v2-email-flag-memory-leak` on (a), (b) and (c), as predicted before recording (`t7.1-candidates.md`) |
| `v2/dependency_latency-1` | dev | `v2-cart-dependency-latency` | 2026-09-27, first recording, on the revised world. v1's dev design carried to v2's cart; the first recording in its row, which the row's later rows are measured against on (a) (`t7.1-candidates.md`) |
| `v2/dependency_latency-2` | dev | `v2-valkey-cart-dependency-latency` | 2026-09-27, first recording, on the revised world. v1's dev design carried to v2's store. Not distinct from row 1 on (a), as predicted - the same five latency alerts; distinct on (d) and in the change record, as predicted (`t7.1-candidates.md`) |
| `v2/dependency_latency-3` | dev | `v2-payment-dependency-latency` | 2026-09-27, second recording, on the revised world (the first, the same day, began the second its predecessor's alert cleared and is under its `superseded/`). A new design; distinct from rows 1 and 2 on (a), as predicted (`t7.1-candidates.md`) |
| `v2/dependency_latency-4` | holdout | `v2-product-catalog-dependency-latency` | 2026-09-27, second recording, on the revised world (the first, the same day, carried the injector's sidecar's log in its capture - Q111 - and is under its `superseded/`). v1's holdout carried to v2's catalog; distinct from rows 1-3 on (a), as predicted (`t7.1-candidates.md`). The `dependency_latency` row is full |
| `v2/resource_exhaustion-1` | dev | `v2-ad-memory-squeeze` | 2026-09-27, first recording, on the revised world. v1's dev design carried to v2's ad, the limit re-measured (144m by the rule in `t7.1-candidates.md`). Distinct from `v2-ad-bad-image-tag` on (b) and (c), as predicted |
| `v2/resource_exhaustion-2` | dev | `v2-fraud-detection-memory-squeeze` | 2026-09-27, first recording, on the revised world. v1's dev design carried to v2's fraud-detection, the limit re-measured under 500M (160m by the row's rule). Distinct from row 1 on (a), as predicted (`t7.1-candidates.md`) |
| ~~`v2/resource_exhaustion-3`~~ | dev | ~~`v2-cart-memory-squeeze`~~ | 2026-09-27, recorded once and **blocked**: no page inside 900 s - under 48m cart restarted every 55 s and served between kills, its callers at 1-2 % errors against a 5 % line (T7.20's "back before detection"). The pre-registered outcome: the slot stays empty, the row having no reserve (`t7.1-candidates.md`) |
| `v2/resource_exhaustion-3` | dev | `v2-payment-memory-squeeze` | 2026-09-27, third recording, on the revised world (the first two, the same day, are under its `superseded/`: each corrected the ground truth's mechanism to what the captures showed). The row's reserve, added after the cart design was blocked. A starvation that shows as latency on the target alone; distinct from rows 1 and 2 on (a), and from `v2-payment-dependency-latency` on (a) and (d) (`t7.1-candidates.md`) |
