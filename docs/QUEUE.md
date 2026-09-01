# The queue — changes deferred, and what would trigger them

**This file is the register, and it is meant to be updated rather than re-derived.** Before T7.45
each deferred change lived only in the PLAN entry of the task that deferred it, which meant the
batch that eventually lands would be whatever someone remembered.

**Where a new item goes:** a task that defers a change adds a row here in the same commit that
writes its PLAN entry, and a task that lands one strikes the row rather than deleting it. A PLAN
entry saying "queued" with no row here is the defect this file exists to prevent.

---

## Live items

| # | change | why deferred | locked behind | invalidates on landing | trigger |
|---|---|---|---|---|---|
| **Q1** | **Capture the container exit reason** — record *that* a container was replaced and when, without recording *why* it died | T7.40 decided the exclusion is deliberate: a capture printing `OOMKilled: true` deletes the inference three `resource_exhaustion` items exist to test | **`CAPTURE_SET` → `CAPABILITY_VERSION`** | 15 narrative capability stamps need re-review; 13 bundles hold the old set with **no backfill possible**; **permanently strands 3 spent holdout entries** | A design that adds the *fact* of replacement without the *cause* — T7.40 §5 calls this the reversal most likely to be right. Also: a world move already forcing a re-record, though the holdout stranding still needs its own argument |
| **Q2** | **Synthesizer prompt: distinguish a change with no demonstrated mechanism from a change whose value is self-evidently wrong** | T7.43 found the two runs diverged on exactly this, at n = 1 vs n = 1 | **role prompts → `runtime_version`** | comparability with **six dev sweeps, three holdout entries and both new scenarios**, all recorded under `prompts:1b0e7cbb4c47` | The traceability split T7.43 specified: this scenario against `cart-redis-misconfig`, whose mechanism *is* traceable. **~$5.5, ~3.5 h, n = 10.** Not run |
| **Q3** | **A warrant check in scoring** — compare a verdict's stated causal path against `GroundTruth.root_cause`, which every scenario carries and **nothing reads** | T7.44: adopting it on one pair of runs would tune the benchmark to its last result | **scoring semantics** (no digest; re-scoring is computational) | every stored verdict would need re-scoring to stay comparable | A measurement showing correct answers split by warrant — that agents reach right conclusions by proximity often enough to move a published figure. Same test as Q2 |
| **Q4** | **Credentials on Prometheus and Loki, network policy, egress restriction** | ADR-0019 §deferred: defensible only because the world is a local benchmark | **nothing — task-gated** | nothing recorded; it is additive | **T6.8**, where all three are already listed |
| **Q5** | **Detect a container restart while a latency fault is live** | ADR-0007: detecting it means the injector polling container identity for the lifetime of every pumba fault, a background process this codebase does not otherwise have | **nothing but caution** | nothing | *"Revisit if a scenario ever needs a container restart while a latency fault is live."* No catalog item does today |
| **Q7** | **ADR-0028 §5 and §4 amendment** — state that the oracle control is *sequencing* (the agent's last read must precede any execution), not *withholding* the executor's return value; and record that `expected_effect` + `confirm_within` are what make a repair benchmark scoreable | T7.50 found §5's control stated as withholding, which is insufficient on its own: the agent's own read tools observe the changed world, so the return value is not the channel. An implementer could satisfy the letter of §5 and build something unsound | **nothing — an ADR rewrite is a decision** | nothing; the proposer is unbuilt (`roles.py` has no proposer) | **the first task that proposes to build any part of the action plane.** Until then nothing depends on it |
| **Q8** | **Re-attach `CLASS_DISPUTES` to manifests scored before the register grew** — `ad-memory-squeeze` and `frauddetection-memory-squeeze` each hold one run recording `dispute: null` for a triple `dispute_for` matches today | T7.52 found it while judging the corpus, and **fixing it would alter a recorded score block**, which is the thing that task refused to do | **nothing — it is a re-score** | the two manifests' recorded `score` blocks; no published figure moves, because a disputed miss is still a miss either way | **any task that re-scores the corpus** — the same trigger as Q3, and it should ride along rather than justify a rewrite of its own |
| **Q9** | **Author a scenario into a free holdout slot** — `bad_config-5`, `bad_config-6` or `bad_deploy-6`, all allocated at T7.35 and never filled | T7.53 assessed holdout entry 4 and declined it: **the four conditions pass, but T4.15 requires the set be re-authored or extended first**, and it never was | **nothing - it is authoring work**, plus a rehearsal against the current world | nothing published moves; the holdout arm gains capacity it does not have | **it is the trigger, not the blocked thing.** Filling one slot unblocks holdout entry 4, whose entitlement (T7.29's dev sweep 7) and prediction are already drafted in `HOLDOUT-2026-09-01-entry4-NOT-OPENED.md` §6. `bad_config` first - zero holdout representation, most unexplored paths. **T7.56 attempted this and failed, and the route changed.** `bad_config-5` was the target: `accounting-kafka-misconfig` was designed against the recorded page space, gated, injected and **abandoned at its first gate** - the consumer logs `severity: fatal` on an unreachable broker and crashloops, 9 restarts in ~58 s. Criteria were committed first and said abandon rather than tune; there was nothing to tune. **No filler was authored and the slot is released.** Every `bad_config` candidate is now disposed of with a reason in `docs/design/t7.56-holdout-bad-config.md` and **no distinct fifth exists**, so `bad_config` is the *least* promising route rather than the most. `bad_deploy-6` inherits the exhausted-mechanism problem behind Q1. T7.56 concluded the shortest remaining path was T7.0's further fault classes. **T7.57 audited that and closed it: there is no fifth fault class in this world (ADR-0029, Q11).** So this row is no longer a task waiting to be done - **it is blocked on a world this project does not have.** Entry 4 is blocked *indefinitely*, not pending; the holdout arm stays at three entries against a world two generations superseded, and that is the benchmark's holdout claim. **T7.55: still the only blocker, and it no longer has a route.** ADR-0022's T7.55 addendum states all six conditions for entry 4 in one table; five are met. The freeze path is built and `faultline-eval` produces the manifest itself, so entry 4 must not hand-write one; and entry 4 is a **new comparability generation** - entries 1-3 ran on `4a7690c6fdda…`, two worlds back - so it must be published with its own world digests and **not** tabled beside them |
| ~~**Q10**~~ | ~~**An invocation path for the freeze check**~~ — **LANDED T7.55.** `faultline-eval` builds the freeze manifest after the baseline gate and before injection; `world:unverifiable` refuses, a changed world labels a new comparability generation, and `judge.judged_rows` groups by world so two generations are never rows of one table. **Struck rather than deleted** — the register records that this was deferred and then landed, and by whom. Its trigger was *the next holdout entry*; T7.55 discharged it early on the ground that a freeze path built under the pressure of an entry someone wants to run is a freeze path that gets relaxed | — | — | — |
| **Q11** | **A fifth fault class** — a fifth injector mechanism *and* a fifth `RemediationClass` value | T7.57 audited it and **concluded this world has no fifth class**: four mechanisms bound one-to-one to four classes by test, a remediation set where `config_revert` already fixes three of the four, one unused remediation (`scale`) the world can neither cause nor perform (**measured**: compose refuses, 25 services carry `container_name`), and a topology that flattens every page. See ADR-0029 | **`FaultClass` → `contracts` → `runtime_version`.** Adding a member **moves the stamp** | comparability with **six dev sweeps and all three holdout entries** - and entry 4 would then also be incomparable with dev sweep 7, so it would compare to nothing at all | **a different demo world**, not a cleverer scenario. Doing this for one scenario spends the comparability of six sweeps, so it is worth doing only alongside a world change that re-founds everything anyway |

### An item with no trigger, named rather than given one

| # | change | status |
|---|---|---|
| **Q6** | **A `redis-cart` eviction / `maxmemory` scenario** | **Digest-locked with no trigger.** T7.34 rejected it as a candidate because `maxmemory` now lives in a `compose_digest` input, and nothing states what would revive it. **This is not queued; it is a rejected candidate**, and it is listed here so it is not re-proposed as though it were pending. If someone wants it, it needs a fresh argument, not a trigger |

---

## Dropped from the queue at T7.45

| # | change | why dropped rather than deferred |
|---|---|---|
| **~~Q0~~** | **Remove `MALLOC_ARENA_MAX=2`** | **The removal has no demonstrated benefit and the setting has no demonstrated harm.** T7.30 measured that the lever does not bound growth; T7.40 kept it because removal costs a digest move and a re-record while its effect is nil. **Tracking a cosmetic tidy-up as a pending change misrepresents what this register is for.** The reasoning stays in ADR-0005's T7.30 addendum, where a reader of the setting finds it. **If a digest move happens for another reason, dropping the line then is free and needs no register entry to remember it** |

---

## Closed — items that read as queued and are already done

**Found by this sweep. Each still reads as pending in its source document**, which is the failure
mode this register exists to catch; the sources are corrected in the same commit.

| item | queued in | closed by |
|---|---|---|
| Bring the alert rules under a digest | ADR-0025 | **T7.15** — `observability_digest` covers `compose/prometheus/alert-rules.yml` |
| A `maxmemory` bound on `redis-cart` | ADR-0024 | **T7.28** — `--maxmemory 12mb --maxmemory-policy allkeys-lru` |
| Rename the ffs-stub tags off the answer key | ADR-0019 | **T7.1** — `ffs-stub:1/:2/:3` over `server.py`/`_v2`/`_v3` |
| Correlate deadline robust to a suspended host | PLAN, pre-T7.12 | **T7.12** — `CORRELATE_SCRAPES` and `WorldStoppedReportingError` |
| Harness preflight that ingest and the orchestrator are up | PLAN, T7.24 | **T7.25** — `PipelineDownError` |
| `scale` as an injectable class | ADR-0008 | **ADR-0024** — resolved differently: retired as unfillable on this world, not built |

---

## What the batch costs, and what actually shares a re-record

**The grouping is not by what an item is locked behind — it is by whether landing it forces a
re-record.**

| group | items | forces a re-record? |
|---|---|---|
| **A — world/capture** | **Q1**, and any future digest-locked change | **Yes.** A `compose_digest` move and a `CAPTURE_SET` bump both invalidate every bundle, and **a new capture cannot be backfilled** — the containers are gone |
| **B — pipeline stamp** | **Q2** | **No.** Bundles record the *world*, not the agent. A stamp move invalidates **comparability of figures**, which no re-record repairs — only re-running the figures does |
| **C — scoring** | **Q3** | **No world time.** Re-scoring stored verdicts is computational |
| **D — independent** | **Q4**, **Q5** | No |

**So A is the only group that batches**, and it batches with any future world move for the reason
T7.1 and T7.28 both demonstrated: one re-record covers everything landing at once.

**Cost of a group-A landing:** **13 bundles × ~25–30 min ≈ 6 hours** (T7.34's measured figure), plus
kafka recycles, inter-scenario settles, and a **31–35% historical candidate failure rate**. A
`CAPTURE_SET` bump adds **15 narrative re-reviews** and **permanently strands three spent holdout
entries**, which is the cost that does not recover and the reason Q1 is not scheduled.

**B and C cannot be batched with A and should not wait for it.** Their costs are in a different
currency — comparability and re-scoring, not world time — and holding them for a world move buys
nothing.

**And Q2 and Q3 share one trigger**: the traceability measurement T7.43 specified. Neither should
land without it, and if it is run, both become decidable at once.

---

## Should this file have a guard?

**Not yet, and not on speculation.** A guard could check that every PLAN entry containing "queued"
has a matching row here. It would have caught the six closed items above only if it also checked
their *sources*, which are ADRs rather than PLAN entries — so the useful guard is broader than the
obvious one and its shape is not yet clear from one sweep.

**What would justify building it:** a second sweep finding items this one missed, which would show
the manual pass is unreliable rather than merely tedious. **One sweep is not that evidence.**
