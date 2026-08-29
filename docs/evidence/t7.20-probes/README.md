# T7.20 alerting probes — B and C

Five injections on 2026-08-29. **Nothing recorded, no bundle, no split decision, no agent.**
Each probe: gate-check, inject, watch the one open gate, revert, confirm recovery. Raw
per-attempt records are the JSON files beside this one.

Candidate A needed no probe — its alerting gate is already measured (T7.14's 12-hour census plus
the `cart-dependency-latency` precedent at the identical mechanism and magnitude).

## C — `shipping-quote-misconfig` · **PASSES, reproducibly**

| attempt | first alert | what fired | shipping's own error rate | checkout error ratio |
|---|---|---|---|---|
| **C1** | **T+240s** | `ServiceHighErrorRate/checkoutservice` | **0.000 throughout** | 25.0–27.8% |
| **C2** | **T+240s** | `ServiceHighErrorRate/checkoutservice` | **0.000 throughout** | 22.2–28.6% |

Identical onset, identical shape. Well inside T7.12's 900s budget.

**The answer to the question the gate was open on.** A failed `GetQuote` does *not* surface as an
error at `shippingservice` — its error rate stays at zero for the entire fault. It surfaces at its
**caller**: `checkoutservice` runs 22–28% errors and pages. So **the alerting service is not the
faulty service**, and the faulty one looks clean by error rate.

That makes the scenario better than designed, and it also makes T7.5's reachability gate load-
bearing rather than a formality: metrics say checkout is broken, and the only class that reaches
`shippingservice` at all is its logs — which is exactly the one class T7.4's census gives it.

**The full blast radius**, both attempts: `ServiceHighErrorRate/checkoutservice` at T+240s, then at
T+420s `ServiceNoTraffic` on `quoteservice` (it stops receiving traffic entirely from T+120s),
`accountingservice`, `emailservice` and `frauddetectionservice` — orders stop completing, so the
Kafka consumers and the mailer go quiet.

**Recovery confirmed** both times: the fault reverted cleanly and the address was restored.
C2's first attempt was **refused at the gate** because C1's `ServiceHighErrorRate` had not yet
resolved — the protocol working, and the reason the retry is recorded rather than hidden.

## B — `cart-memory-squeeze` · **FAILS, at both magnitudes probed**

### At 200m — the mechanism works and nothing sees it

| attempt | container | alerts caused | cart p95 | errors, any service |
|---|---|---|---|---|
| **B1** | `RestartCount` 0 → 1 | **none** (see below) | — | — |
| **B2** | `RestartCount` 1 → 2 → 3 | **none** | flat 1.9ms | **0.000 everywhere** |

The fault is real: the container is killed and restarted, and `.NET`'s `gc_collections` counter
resetting 8 → 1 is the restart made visible in telemetry. But nothing alerts. Over seven minutes
in B2 — with two kills inside it — every service sat at 0.000 errors and cartservice's own p95
never left 1.9ms.

**B1 looked like a pass and was not.** Alerts appeared at T+182s and T+304s, on `frontend` and
`loadgenerator` — two of the three services T7.14 measured as carrying at-rest latency excursions.
B2 settles it: same fault, more kills, **no alerts at all**. B1's were the excursion.

**My predicted failure mode was wrong.** The design expected .NET's Server GC to read the cgroup
limit and survive by collecting harder. It does not — it dies. The fault is invisible because the
container comes back *faster than detection*, which is the shape already recorded for
`recommendation-memory-squeeze` at 48m: *"the fault fired constantly and was invisible."*

### At 32m — it alerts, and disqualifies itself doing so

Following that scenario's own remedy (go below what the runtime needs to start):

- `OOMKilled=true`, **16 restarts in seven minutes**, never reaching a serving state
- T+300s: `ServiceHighErrorRate` on checkout, frontend, loadgenerator
- T+420s: **eleven alerts**, including `ServiceNoTraffic` on cartservice, currencyservice,
  shippingservice, quoteservice, accountingservice, emailservice, frauddetectionservice

Two reasons that is not a scenario, and the first is the one that matters:

**Its evidence disappears under its own fault.** `process_runtime_dotnet_gc_heap_size` and
`gc_collections_count` go null from T+300s — the container never runs long enough to export them.
B passed T7.5's reachability gate on 20 runtime series, and under the fault there are none. **A
reachability gate has to be evaluated under the fault, not at rest**, and nothing in the record
said so before this.

**And it is then hard to separate from `cart-bad-image-tag`** — container absent, same cascade,
same page. The discriminator would be `change_history` alone.

### Verdict

**B fails.** Not for the reason predicted, and not rescuable by the obvious retune: 200m is
invisible, 32m destroys the evidence the scenario would be read from. An interval may exist
between them, but ADR-0013's rule applies — hunting for a number in an interval this narrow
produces a value tuned to today's load rather than to a property of the service.

## World

Reverted and confirmed after every probe. B3's outage cleared within two minutes of revert; the
`ServiceHighLatency/checkoutservice` remaining afterwards is T7.14's characterised excursion, which
was firing before these probes began. `cart-service` ends `running` at its 400MB limit with
`RestartCount` 19 — a counter, not a fault. No active injections, no leftover overrides.
