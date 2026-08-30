# T7.24 — the first investigation of a silent culprit

> **World: superseded (T7.28).** Every figure on this page was measured against
> `compose_digest 299d791c5e0d…`. The world moved on 2026-08-30 - kafka's allocator bounded, a
> `maxmemory`/`allkeys-lru` bound on redis-cart, and a `memory_limiter` on the collector - and the
> catalog was re-recorded under `compose_digest f5bd108f…` / `observability_digest 857d95b4…`.
>
> **This run is additionally superseded in its subject, not only its world.** T7.28 re-recorded
> `shipping-quote-misconfig` itself, so the bundle scored below no longer exists in that form. The
> verdict, the ledger and the six-of-six axes describe the old bundle in the old world, and
> **nothing has been re-run against the new one.** Whether to re-run it is a separate
> pre-registered decision.

One scored run of `shipping-quote-misconfig`, the scenario T7.22 recorded and nobody had
investigated. Pre-registered in
[`docs/evidence/t7.24-silent-culprit/PREREGISTRATION.md`](../../docs/evidence/t7.24-silent-culprit/PREREGISTRATION.md),
committed before the run.

| | |
|---|---|
| run | `20260829T202910Z-shipping-quote-misconfig` |
| stamp | `faultline/0.0.1+prompts:1b0e7cbb4c47` |
| budget | `changes` 8, others 4, 120k tokens, 600s, 2 rounds (T4.7) |
| models | `claude-opus-5` for every role |
| judge | `claude-haiku-4-5` — **SHARED LINEAGE**, opted into by name, as every prior judged run |
| cost | **$0.6857 agent + $0.0328 judge = $0.7185** · in 51,798 / out 17,067 tokens |

## Verdict against ground truth

| | ground truth | returned | |
|---|---|---|---|
| fault class | `bad_config` | **`bad_config`** | ✔ |
| fix class | `config_revert` | **`config_revert`** | ✔ |
| faulty service | `shippingservice` | **`shippingservice`** | ✔ |
| confidence | — | high | — |

The root cause names the variable: *"an environment/config update to shippingservice that set
`QUOTE_SERVICE_ADDR` … to an address naming a decommissioned/non-existent quote backend"*, cited to
`tr_8eb4ad4bdd98`, a change-history result. Eight evidence citations, all resolvable.

**Triage:** recall **1.00** (2/2 alerted services predicted), precision **0.17** (2/12). Four
unmeasured edges crossed. **Judge:** `same_mechanism`, 6 dead ends closed / 3 missed.

## The prediction ledger, scored as written

| # | prediction | outcome |
|---|---|---|
| **P1** | localizes first to `checkoutservice` | **CONFIRMED** — the planner's own words: *"checkoutservice alerted first and remains the localization target, so I exhaust all four of its evidence classes rather than scattering probes across nine candidate dependencies."* All four round-1 dispatches went there. |
| **P2** | reaches `shippingservice` | **CONFIRMED** — two dispatches in round 2: `changes` and `logs`. |
| **P3** | reaches it **by the dependency graph** | **FALSIFIED** — see below. |
| **P4** | `change_history` on shipping is what identifies it | **CONFIRMED** — `tr_8eb4ad4bdd98` is the verdict's first citation and the only evidence naming the variable. |
| **P5** | root cause `bad_config` on `shippingservice` | **CONFIRMED** |
| **P6** | fix class `config_revert` | **CONFIRMED** |

**Five of six. P3 is the one I got wrong, and it is the interesting one.**

I predicted the graph because no *metric or log* signal points at shipping — and that much held. What
I did not consider is that **the trace does**. The round-2 planner:

> *"Traces localized the failure to the checkoutservice client span for `ShippingService/GetQuote`
> while the shipping server handler succeeds, so the open question is what shipping returns that
> checkout rejects — which means asking shippingservice the two evidence classes never put to it,
> changes and logs."*

The client span carries the callee's name, so a trace on the *alerting* service names the silent
one. My prediction enumerated metrics, logs and the graph and simply omitted traces — the class
T7.4's census records as used in only **2 of 10** investigations, and the one this run needed.

**The registered falsifier did not fire.** It was: *answers `checkoutservice` or abstains while
never dispatching a specialist against `shippingservice`*. The agent dispatched twice against
shipping and named it. On this one run, T4.14's return-to-locus instruction did carry the agent from
an alerting caller to a silent culprit.

**The registered near-miss did not fire either**, and the judge scored exactly those traps as
avoided: *"shipping reported no errors and logged nothing to suggest failure: **avoided**"*,
*"looking at change history only on the alerting service (checkout): **avoided**"*, *"treating
shipping logs showing healthy activity as proof shipping was healthy: **avoided**"*.

## Contamination — verified from the retrieval rows

The corpus holds this scenario's own narrative as a dev document (T7.22 seeded 8 documents, 40
chunks). From `trajectory_retrievals`, seq 19:

```
exclude_origin = 'scenario:shipping-quote-misconfig'   k=3
  [0.016] scenario:shipping-wrong-image
  [0.016] scenario:cart-redis-misconfig
  [0.016] scenario:cart-bad-image-tag
```

**The filter fired and the scenario's own narrative did not come back.** The three that did are
other dev scenarios. ADR-0008 axis 2 holds for this run.

## Reachability — the report carries it

`reachability answerable by: logs`. This is the **first run scored against a bundle whose
reachability was derived correctly**: T7.22 found the recorder deriving it before writing the
captures, which had stamped `target_log_lines: 0, none_can_answer: true` onto a bundle holding 126
log lines. Had that stood, this report would have said the scenario's evidence was unanswerable
while the agent was reading it.

## Protocol

Baseline gate clean before injection (15 services, 0 alerts). Reverted at 20:39:43, recovery
confirmed, `QUOTE_SERVICE_ADDR` restored. No flags, no failed dispatches, no narrative refusal, no
budget exhaustion. **The gate did not refuse on the checkout excursion**, so T7.23's remedy was not
needed.

## One discarded run, recorded

`20260829T200129Z-shipping-quote-misconfig` is discarded for **operator error**: I misread a
malformed `pgrep` as a dead process and reverted the fault out from under a live run. Its
`DISCARDED.md` carries the full account. Nothing about the scenario is in question — it never
reached the investigation.

## Scope

**n=1. This is one observation, not a rate.** It cannot distinguish a capability from a lucky draw,
and it says nothing about how often the agent would cross from an alerting caller to a silent
culprit. The only claim here is that it did so once, on this scenario, at this stamp, under this
budget — and that the route it took was one the pre-registration did not anticipate.
