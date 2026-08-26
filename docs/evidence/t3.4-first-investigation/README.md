# T3.4 live smoke — the first end-to-end investigation

One investigation, run against the live world, from triage through the synthesizer's verdict to
the scribe's rendered narrative. Scenario: `shipping-wrong-image` (dev split), chosen so that
T3.3's `cart-redis-misconfig` sits in the retrieval corpus as a **past** incident rather than as
the excluded origin.

Files here: `investigation.txt` is the full run output as captured; `narrative.md` is the
rendered narrative alone, as the scribe emitted it.

## Baseline before injection

Checked explicitly, and the checking was manual — **this path has no baseline gate.** The
rehearsal recorder (T1.5) refuses to record against a dirty world; the agent-run path has no
equivalent, so nothing would have stopped an injection onto an already-degraded world. Recorded
as a T4 item in `docs/PLAN.md`.

What the check found, before this run: the world *was* degraded — checkoutservice and frontend
pinned at 15000ms p95, accountingservice at 0.000 req/s. This is the state CATALOG.md documents,
with a documented repair. Applied it:

    docker restart accounting-service frauddetection-service checkout-service

which cleared it. Injection went onto a clean world.

## What ran

| | |
|---|---|
| incident | `fb7ad21e-1e76-4ef6-9efa-35f45902a029`, 8 episodes across 7 services |
| triage | 12 services, severity critical, start from checkoutservice, 5 unmeasured edges crossed |
| trajectory | `e7739dec-8ad2-453d-9ab7-8fd1f039f435` — 17 steps, 6 tool calls, 1 retrieval row |
| budget | 4 tool calls per specialist, 120k tokens, 600s, 2 dispatch rounds |
| rounds | 2 planning rounds, 6 dispatches, 2 explicit skips in round 2 |
| tokens | in 32,123 / out 12,892 / total 45,015 |
| cost | **$0.4829** at $5/$25 per Mtok |
| re-asks | 2 of 10 model turns needed the one bounded re-ask (`logs`, `scribe`); the rest were valid first try |

Injection started 01:39:24Z, reverted 02:02:00Z.

## Retrieval — the first live consumption

One `trajectory_retrievals` row, carrying the exclusion:

    exclude_origin='scenario:shipping-wrong-image'
    k=3
    returned=['scenario:cart-redis-misconfig', 'scenario:ad-memory-squeeze', 'scenario:cart-bad-image-tag']

The corpus holds all five chunks of `scenario:shipping-wrong-image` (see
`docs/evidence/t2.4b-corpus-smoke/store-state.txt`). None of them came back. The scenario under
test was excluded from its own investigation — ADR-0008 axis 2, exercised live for the first
time.

`exclude_origin` is set from `FAULTLINE_EVAL_SCENARIO`. **Marked decision:** the harness knows
which scenario is under test and the product does not, so the exclusion enters through the
environment rather than through any product-side field. In production the variable is unset, the
exclusion is `None`, and retrieval returns everything — a distinct code path, pinned by
`test_production_retrieval_carries_no_exclusion_and_that_is_distinct`.

## The verdict, as produced

    fault class : bad_deploy
    fix class   : rollback
    confidence  : medium
    evidence    : tr_8657d00962e4, tr_2ccf8bd687ef, tr_bf1ed807067d, tr_1c0655065fe4
    flags       : none

Ground truth for `shipping-wrong-image` is `fault_class: bad_deploy`, class of fix `rollback`.
Both match. The agent also named the right service: the page named checkoutservice, and the
verdict says checkoutservice is not itself broken.

Full root-cause text and six open questions are in `investigation.txt`.

## Leak guard

Run over the finished narrative, 16 banned terms, 1 world-owned token exempted:

    LEAK GUARD: PASS - no banned term in the final narrative

Worth noting what it had to survive: the change-history envelope the narrative reasons from
contains the literal string `ghcr.io/open-telemetry/demo:v1.2.1-adservice`, which is the
injected image. The guard bans the vocabulary of the injector (`inject`, `scenario`, `fault`,
`bad_deploy`, …), not the artifacts the world legitimately exposes, and the narrative names the
mechanism without naming the mechanism's author.

## Compared against the recorded `incident.md`

`evals/scenarios/artifacts/dev/shipping-wrong-image/incident.md`, dev split, so reading it is
allowed. Agreements and misses, factually. **This is evidence, not a score** — no scoring
harness exists yet (T5).

### Agreements

- **Class and fix.** `bad_deploy` / `rollback`, matching the recorded front matter.
- **The page named the caller, not the culprit.** incident.md: "the page named the caller, not
  the edge and not the culprit." The agent's round-1 plan opened on checkoutservice and its
  round-2 plan moved to shippingservice on trace evidence.
- **The restart loop, measured the same way.** incident.md records fifteen three-line startup
  attempts with gaps lengthening from five seconds to a minute. The agent measured ~13
  attempts, gaps 5–6s → ~18s → ~30s → ~56s, plateauing near 65s, and read the plateau correctly
  as supervisor backoff rather than as a severity signal.
- **Killed, not failing.** incident.md: a process that objects to its own configuration prints
  the reason; this one is stopped before it gets there. The agent: "the process dies before it
  ever binds its gRPC server", and separately that no application-level init line follows any
  banner.
- **The memory-limit trap, named and not taken.** incident.md warns that this signature is
  identical to a memory ceiling set too low and that "the diagnosis writes itself". The agent
  listed OOM-at-startup among four indistinguishable causes in its open questions and did not
  classify on it.
- **Dead ends the recorded narrative does not cover**, and which hold up: currencyservice is on
  the path in every failing trace and uniformly clean; paymentservice appears in none of the 200
  sampled spans because checkout aborts before the payment stage.

### Misses

- **The decisive signal was never seen.** incident.md's separator between `bad_deploy` and
  `resource_exhaustion` is the log content *before* onset: the container emits Rust
  (`ShipOrderRequest`, `Tracking ID Created`) until the boundary and JVM banners after it. "The
  service changed language across the boundary. No resource limit does that."

  The agent's logs specialist reported instead: "The first log line in the window appears at
  01:39:30Z; the window opens at 01:32:15, so the service emitted nothing for the first ~7
  minutes", and the synthesizer carried that forward as an open question about missing
  collection.

  That is false, and checkably so. Querying Loki directly for
  `{service="shipping-service"}` over 01:30:00–01:39:24 returns **312 lines**, Rust, running to
  01:39:22 — inside the specialist's own query window. They were not returned because the log
  tool caps at `max_log_lines` and, since the T2.6 truncation-direction fix, **keeps the newest
  lines**. The pre-onset lines are the oldest, so they were the ones dropped.

  The envelope said so — `truncated="true"` — and the specialist read the absence as a positive
  finding anyway. Two things are worth separating here: the T2.6 fix is right for the common
  case (the newest lines are the ones near the failure), and it is exactly wrong for the one
  question that resolves this scenario. Recorded as a finding, not fixed under T3.4.

- **The synthesizer contradicted its own trajectory.** The verdict says: "the changes specialist
  queried quoteservice, not shippingservice … no change record for shippingservice has actually
  been examined", and repeats it as the first open question and in the narrative's dead-ends
  section.

  It had. `tr_f536225dc17d`, recorded at seq 9, is `change_history` for **shippingservice**, and
  it returned the ground truth outright:

      2026-08-26T01:39:24  platform-automation  image updated: image reference updated on shippingservice
          None  ->  ghcr.io/open-telemetry/demo:v1.2.1-adservice

  The changes specialist read it correctly and at high confidence, including that "the deployed
  artifact name does not match the service it was applied to". The synthesizer then dropped that
  run and reported its absence. The verdict landed on the right class regardless — but on
  weaker grounds than the evidence in its own store supported, and its single highest-value
  "missing check" was already answered.

- **The memory-ceiling reasoning is absent.** incident.md's account is that the image moved and
  the limit did not, and that raising the limit would have stopped the alert and been worse. The
  agent has no container-limit tool and never reached this; it stopped at "something in the
  deployed artifact or its launch environment".
- **No timing figures.** incident.md reports onset-to-page 2m49s, page-to-fix 5m00s. The agent
  computed no such interval.

### Not comparable

The two runs are different incidents of the same scenario. incident.md records 10 alerts across
8 services including frontend; this run's incident carried 8 episodes across 7 services and no
frontend episode — the frontend's diluted error ratio sat under threshold this time. Alert-count
differences between runs are world variation, not agent behaviour.

## Two defects found live, both fixed on this branch

1. **The narrative renderer ran before the trajectory was saved.** The scribe cited four real
   `result_id`s and every one was refused: `RENDER REFUSED: tr_59ffd37dd314 is not in the
   trajectory store`. The trajectory existed only in memory when the renderer resolved
   citations. The guard fired correctly on evidence that genuinely existed, which is the worst
   kind of correct — it is indistinguishable from the fabricated-citation case it is there to
   catch. Fixed by saving before the scribe runs (idempotent with the save that follows);
   pinned by `test_the_trajectory_is_persisted_before_the_scribe_resolves_citations`.

2. **A crippled budget produced a flagged verdict, which is the designed behaviour.** The first
   pass ran with `max_tool_calls_per_specialist=2` and exhausted it, producing
   `fault_class: unknown`, `confidence: low`, and
   `flags: ['budget exhausted: metrics tool calls: 2 of 2 used']` — a verdict that reasons about
   its own incompleteness rather than an exception or a silence. Not a defect in itself; it is
   the flagged path working, and it is why the second pass was run at 4 calls per specialist.

## Housekeeping

Injection reverted at 02:02:00Z. Recovery confirmed at 02:04:07Z: checkoutservice and frontend
error ratios at 0.0000, all five previously-silent services serving (shippingservice 0.443,
emailservice 0.591, quoteservice 0.313, accountingservice 0.148, frauddetectionservice 0.148
req/s), **0 active alerts** in Alertmanager. The smoke's ingest process was stopped.

Incident `fb7ad21e` remains in state `triaging`. The agent path does not resolve incidents — the
orchestrator resolves on alert resolution and the investigation loop writes no state back. That
join is T4 work.
