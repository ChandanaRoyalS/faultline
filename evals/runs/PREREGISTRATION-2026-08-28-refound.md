# Pre-registration — dev sweep 6, the benchmark re-founded on the world that exists

**Written and committed before any scenario ran.**

## What this is, and what it is not

T7.1 moved the world — kafka heap capped, `otel-col` raised, Prometheus retention 6h → 15d, stub
variants renamed — and re-recorded all twelve bundles against it. **`world.compose_digest` moved
`4a7690c6fdda…` → `299d791c5e0d…`.** Every published figure in this repository was measured on the
old world, and the new one has no sweep at all.

**This is not an experiment on the agent.** The stamp is unchanged at
`faultline/0.0.1+prompts:1b0e7cbb4c47`, which is the pipeline dev sweep 5 measured. The budget is
unchanged at T4.7's. **One thing moved, and it is the world.** So the registered question is not
"is the agent better" — nothing about the agent is different — but:

> **What did the world change do to the results?**

S5 and this sweep are **not the same experiment** and the comparison between them crosses a world
boundary. Any difference is attributable to the world, to run-to-run variance, or to both, and
this sweep cannot separate those two from each other.

| | dev sweep 5 | **dev sweep 6** |
|---|---|---|
| stamp | `1b0e7cbb4c47` | **identical** |
| budget | `changes` 8, others 4, 120k, 600s, 2 rounds | **identical** |
| world | `4a7690c6fdda…` | **`299d791c5e0d…`** |
| bundles | pre-T7.1 recordings | re-recorded |

## The prediction: verdicts hold

The faults are the same faults. **Registered: all seven fault classes come back as S5 returned
them** — six correct and one correct-with-a-wrong-fix — for coverage **7/7** and accuracy **7/7**.

## What would surprise me, and where

**Triage figures are expected to move, and that is not a surprise — it is arithmetic.** Triage
compares the predicted blast radius to `alerts_over_window`, and the re-record changed that set on
four of seven scenarios. Movement there traces to the capture, not to the agent:

| scenario | what the re-record changed | expected effect |
|---|---|---|
| `cart-bad-image-tag` | `ServiceHighErrorRate/emailservice` **gone** (11 → 10 alerts) | the recovery-phase alert that T7.3's exclusion handled is simply absent; `n_alerted` falls by one |
| `cart-redis-misconfig` | same alert **gone**; page narrows 2 → 1 service | same, plus a thinner page |
| `shipping-wrong-image` | 10 → 8 alerts; frontend and loadgenerator now alert **last**, at T+6m30s rather than second | blast radius unchanged in membership, ordering inverted |
| `cart-dependency-latency` | page narrows **4 → 2** | the culprit is now one of only two services named at the page |

**These would surprise me:**

1. **Any fault class changing.** The world moved; the faults did not. A different class means either
   the re-record changed what the fault *does* — which T7.1's narrative reconciliation should have
   caught — or the agent is less stable than five sweeps suggest.
2. **`product-catalog-flag-failure` abstaining.** It answered in S5 under this stamp, and T4.14's
   instruction is what unlocked it. Its alert set is unchanged. An abstention here would say the
   win was fragile to something nobody registered.
3. **A triage change on a scenario whose alert set did *not* move** — `ad-memory-squeeze`,
   `frauddetection-memory-squeeze`, `product-catalog-flag-failure`. Those three are the closest
   thing to a control in this sweep: same fault, same alert set, same agent. Movement there is
   run-to-run variance and should be reported as such rather than attributed to the world.
4. **Coverage below 6/7.** S5 achieved 7/7 and S3 6/7; below six would mean the new world is harder
   in a way nothing predicted.

**The falsifier for the headline claim** — "the verdicts hold across the world change" — is any
scenario returning a different fault class, or coverage below 6/7.

## What this sweep cannot show

n = 1 per scenario. T4.10 measured a 2.6× breadth spread on a single scenario and T5.3's demo
produced a 1-in-7 abstention on a scenario with a 6/6 record, so **a single per-scenario difference
is not separable from variance**. What the sweep can establish is whether the benchmark still
stands up on the world that exists, not a measurement of the world change's size.

**Holdout is not re-entered.** That is a separate decision needing its own argument under
ADR-0022's protocol, and the T4.15 addendum already records that the set should not be entered a
fourth time before it is re-authored or extended. Nothing here licenses one.
