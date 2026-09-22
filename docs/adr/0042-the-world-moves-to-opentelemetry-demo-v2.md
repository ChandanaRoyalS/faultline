# ADR-0042: the world moves to OpenTelemetry Demo v2, and ADR-0029's limit was a property of v1.2.1

- **Status:** accepted
- **Date:** 2026-09-22
- **Task:** T7.1 (grow the catalog to 30+ across ~8 fault classes), built as the plan promises it
- **Supersedes in part:** [ADR-0029](0029-four-fault-classes-and-why-there-is-no-fifth.md) — by
  **meeting its own reopening condition 1**, not by disputing its findings
- **Relates to:** [ADR-0026](0026-the-world-is-somebody-elses-repository.md) (the world is pinned
  at v1.2.1), [ADR-0005](0005-arm64-emulation-and-feature-flag-service.md) and
  [ADR-0006](0006-feature-flag-service-stub.md) (the flag service, and what the stub restored),
  [ADR-0004](0004-benchmark-target.md) (T7.2's benchmark target)

## Context

The execution plan's T7.1 promises **"30+ scenario catalog, the project's headline dataset"**, grown
*"to 30+ across ~8 fault classes"*, for a stated reason: *"accuracy claims over 10 scenarios are an
anecdote; over 30+, a measurement."* On 2026-09-20 it was **closed as unachievable**, on
ADR-0029's finding that this world has no fifth fault class.

**The decision now is to build T7.1 as promised.** That requires reopening the question, and
ADR-0029 says exactly how: *"Not a cleverer scenario. One of: 1. A different demo world — one with
more failure surface, more knobs that are not addresses … This is the honest answer and it is a
large piece of work."*

**This ADR does not dispute ADR-0029. It supplies condition 1.** Every finding in that document
was correct about the world it assessed, and §1's fix-test argument, §4's topology finding and §6's
stamp arithmetic all survive unchanged and are relied on below.

## The measurement that reopens it

ADR-0029 §5 kills seven candidate classes. **Four die on the same sentence — the world has no
mechanism** — and that sentence is a fact about the *version*, which nobody had checked.

Counted from both sources rather than from either's documentation:

| | OTel Demo **v1.2.1** (this world, ADR-0026) | OTel Demo **v2.2.0** (chart 0.40.4) |
|---|---|---|
| **built-in failure flags the services actually read** | **2** | **15** |
| which ones | `productCatalogFailure`, `recommendationCache` | the two above plus `llmRateLimitError`, `llmInaccurateResponse`, `kafkaQueueProblems`, `cartFailure`, `paymentFailure`, `paymentUnreachable`, `emailMemoryLeak`, `failedReadinessProbe`, `adFailure`, `adHighCpu`, `adManualGc`, `loadGeneratorFloodHomepage`, `imageSlowLoad` |

v1.2.1's figure is a grep over every service in the demo's own tree for the flag names its code
reads; v2.2.0's is the rendered `flagd-config.yaml` from the chart SREGym deploys. **Faultline uses
one of the two it has** (`product-catalog-flag-failure`). The other, `recommendationCache`, is a
**cache leak** in `recommendation_server.py` — a `resource_exhaustion` by unbounded growth rather
than by a squeezed limit — and it has been available and unused since T1.1.

**These are reachable as configuration, not as a rebuilt image.** ADR-0006's stub answers every
lookup "disabled" and `FAULTLINE_ENABLED_FLAGS` turns named flags back on, *"so the demo's own
failure modes … become injectable as configuration"*. The mechanism to use them already exists and
is already used once.

### Three of ADR-0029 §5's deaths are overturned by the version, not by an argument

| candidate | §5's verdict | v2.2.0 |
|---|---|---|
| **Rate limit** | *"**nothing** — nothing in the demo rate-limits. Envoy could, but its config is a world file"* | **`llmRateLimitError`**, a first-class flag |
| **Queue or pool exhausted** | *"**nothing** — the demo exposes no pool-size or queue-depth knob; the env surface is addresses (T7.39) and ports"* | **`kafkaQueueProblems`**, a first-class flag |
| **Downstream returns wrong data** | *"real: swap `ffs-stub:1` → `:3`"* → an image swap is `BadDeployFault` → **`bad_deploy`** | **`llmInaccurateResponse`** — the same effect as **configuration**, so the `bad_deploy` binding in §3 does not capture it |

Two further mechanisms v1.2.1 has no form of: **`emailMemoryLeak`** (a leak, mechanically distinct
from the limit-squeeze every `resource_exhaustion` scenario here injects) and
**`failedReadinessProbe`**.

**What this does not yet establish.** That each becomes a *fault class* under ADR-0022 §1.2's
criterion — *a fault's class is settled by which fix actually works* — is **not** claimed here and
cannot be claimed at desk. §1 of ADR-0029 stands: `config_revert` already fixes three of four
existing classes, and the fix test individuates poorly. **What is established is that the world
stops being the binding constraint**, which is the only thing ADR-0029 said a new world had to do.
Which classes the catalog ends up with is a measurement, made per candidate, against the new world.

### ADR-0005's prediction, tested

ADR-0005 dropped the Elixir flag service for the stub and recorded: *"We lose the demo's built-in
fault injection, which is driven by feature flags. **This costs nothing**: T1.4 builds a
purpose-built injector precisely because the catalog commits to eight fault classes rather than
whatever the demo happens to expose."*

**The purpose-built injector reached four classes, not eight**, and ADR-0029 established that the
world's own surface is what caps it. The prediction was wrong — though **not in the way it looks**:
ADR-0006's stub restored the flags as configuration, so nothing was lost. What the sentence got
wrong is the assumption underneath it, that a purpose-built injector could exceed *"whatever the
demo happens to expose."* It could not, and ADR-0029 is the proof. **The demo's exposure was the
ceiling all along**, which is why raising it is the move that works.

## Decision

**The world moves to OpenTelemetry Demo v2.x**, and T7.1 is built against it: the injector extended
over the mechanisms v2 exposes, the catalog grown toward 30+, and a fresh dev/holdout allocation
committed before authoring under T1.6's protocol.

**This is a full re-founding and is taken as one**, not as a scenario batch. It moves
`compose_digest` and `observability_digest`, and extending `FaultClass` moves `prompt_digest`
(ADR-0029 §6, and ADR-0024 before it). Both move together, deliberately, because ADR-0029 §*What
would change it* is explicit that condition 2 is *"worth doing only alongside (1)"*.

## Consequences

**Every published figure is re-founded.** 197 scored runs on `90e9f29e…`, six dev sweeps, the three
holdout entries, and the baseline panel of 2026-09-21 become incomparable with everything after.
Restoring a headline table costs a dev sweep at R = 3 (~30 runs at a \$0.713 median ≈ **\$21 an
arm**) plus the baseline panel (**\$3.46** measured), before any ablation.

**The re-record costs world time and has a known failure rate**: QUEUE.md's group-A figure is **13
bundles × ~25–30 min ≈ 6 hours**, at a **31–35% historical candidate failure rate**, plus kafka
recycles and inter-scenario settles. A `CAPTURE_SET` bump adds **15 narrative re-reviews**.

**The cost that ADR-0029 and Q1 treat as decisive is already mostly paid.** Both name *"permanently
strands three spent holdout entries"* as the loss that does not recover. Those three entries are
**already on a world two generations back**, at a stamp superseded five times, in an arm ADR-0029
itself calls *"underpowered and closed"* with entry 4 *"blocked indefinitely"*. A move strands
evidence that is already stranded for comparability, and the thing T7.1 asks for — **holdout
representation for every class** — is reachable only through the fresh allocation this decision
brings. That asymmetry is why the honest answer is now affordable and was not before.

**The queue lands with it.** QUEUE.md's group A exists for exactly this event — *"one re-record
covers everything landing at once"* — so **Q1** and every digest-locked row ride this move rather
than waiting for another. **Q80 and Q81** are stamp-locked and land here too.

**T7.1's statistical purpose is the thing to hold this to.** The plan wants 30+ because *"over 10
is an anecdote"*, and the 16.2 pp MDE that qualifies every ablation in the repository is that
sentence in numbers. A re-record that lands 30 scenarios which are **near-duplicates in alert
shape** buys n and not power — ADR-0029 §4's topology finding is the warning, and it applies to v2
until measured otherwise. **Distinctness is a pre-registered acceptance criterion for the new
catalog, not an afterthought.**

### What this does to T7.2, stated plainly because it cuts both ways

**Faultline's world becomes the same version SREGym deploys** (chart 0.40.4, appVersion 2.2.0).

- **Easier**: the version gap closes. The service-naming hazard recorded in
  [`t7.2-the-harness-read.md`](../design/t7.2-the-harness-read.md) — an agent carrying a v1 catalog
  into a v2 world reasoning about `cartservice` while the graded answer is `cart` — **disappears
  entirely**, and the Jaeger/span-tree mapping is against instrumentation this repository will then
  know first-hand.
- **Harder, and this is the real cost of choosing v2**: **42 of SREGym's 125 problems (33.6%) would
  then run on Faultline's exact world**, tuned against by its prompts and retrieval. The
  self-referential criticism ADR-0004 buys T7.2 to answer gets *stronger* on that subset, not
  weaker. The mitigation is already registered — **the score is reported per application** — and
  the **47 DeathStarBench problems remain a genuinely foreign world** and are where the external
  claim should lead. **A pooled figure was already ruled out; after this it would be indefensible.**

**Recorded rather than resolved**, because the alternative — DeathStarBench as Faultline's world —
buys a cleaner T7.2 claim at the cost of a migration with no shared instrumentation, no shared
tooling and every capture rebuilt from zero. That trade was put and v2 was chosen.

## What would change it

**A measurement, on the new world, showing the fifteen flags do not individuate into classes under
ADR-0022 §1.2.** If every new mechanism's working fix is `config_revert`, the class count does not
move and this ADR bought scenarios without buying classes — half of T7.1, at the full price. That
is the risk, it is not mitigated by anything written here, and it is measured per candidate before
the catalog is authored rather than after.

**And a `RemediationClass` that stays at four.** ADR-0029 §1's criterion is the gate: a class needs
a fix that works and that the others' fixes do not. v2 supplying a mechanism is necessary and not
sufficient, and no part of this decision assumes otherwise.
