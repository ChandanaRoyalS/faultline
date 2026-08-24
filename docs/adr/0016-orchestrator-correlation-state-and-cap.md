# ADR-0016: Incident correlation, the state machine, consumption, and the cap

- **Status:** accepted
- **Date:** 2026-08-24
- **Task:** T2.2 / T2.3 (orchestrator), with T3.5 (state machine)
- **Design only.** Nothing here is built. It exists so T2.2 starts from a decision rather
  than from `src/faultline/orchestrator/__init__.py`'s one-line docstring.

## Context

Four things were already committed and nowhere reconciled.

ADR-0001 chose Redis Streams with consumer groups and explicit acks, and committed to "a
global investigation concurrency cap with severity-ordered overflow" without saying what
the cap is, where severity comes from, or what overflow does. ADR-0015 built ingest and
**explicitly refused incident correlation**, recording that it needs the dependency graph,
the state machine and a policy ingest does not hold. `docs/ARCHITECTURE.md` says "eleven-state
incident machine" and the repo lists no states — `docs/PLAN.md` carries that as
**contract not written**. And `docs/evidence/t2.1-live-smoke/` now holds eight real events
on the stream, which is the first time the input to any of this has been something other
than a description.

Everything below is grounded in one of those, in the alert rules, or in a measurement. Where
the plan is silent and the choice is genuinely open, the options are laid out and **marked
for decision** rather than settled by whichever one got written first.

## The evidence this is designed against

Two injections of `cart-redis-misconfig`, ~40 minutes apart, captured end to end
(`docs/evidence/t2.1-webhook/`, `docs/evidence/t2.1-live-smoke/`). Both produced the same
shape:

| | baseline (~10:32 inject) | live smoke (~11:08 inject) |
|---|---|---|
| alerts | 4, all `ServiceHighErrorRate` | identical |
| services | checkout, frontend, loadgenerator, email | identical |
| fingerprints | four | **byte-identical to the baseline's** |
| `emailservice` | fires after the revert | fires after the revert |

Three facts from that matter here.

**One fault produced four alerts.** This is the alert-storm-to-one-incident case
`docs/evidence/gate-1/README.md:19` named. Correlation is not optional; without it this
system opens four incidents for one fault and investigates the same root cause four times.

**`emailservice` fires after the fault is reverted, twice.** Its condition crosses the
threshold at about the revert instant — recovery traffic failing — and with `for: 2m` its
alert arrives ~2m30s later, interleaved with the other alerts resolving. In the live smoke
it arrived 15 seconds *after* `checkoutservice`'s resolution and resolved last of the four.
**This is the hard case, and it is reproducible rather than anecdotal.**

**The four fingerprints are identical across two separate incidents.** The fingerprint is a
pure function of the alert's labels (ADR-0015, confirmed by the smoke), so **correlating on
fingerprint alone would merge an incident with every previous incident on the same service.**
Whatever correlation does, it keys on `episode_key` — which carries `startsAt` — and never on
`fingerprint` alone.

---

## 1. Incident correlation

### The decision

**A `firing` episode joins the open incident it overlaps in time; otherwise it opens one.**

Concretely, on a `firing` event whose `episode_key` the orchestrator has not seen:

1. If an incident is **open** (not `RESOLVED`/`FAILED`) — join it.
2. If no incident is open but one closed within the **settle window** — join that one,
   reopening it.
3. Otherwise — open a new incident.

A `resolved` event marks its episode closed inside whichever incident holds it. A `resolved`
naming an episode no incident holds is recorded and otherwise ignored: ADR-0015 publishes
those deliberately (a receiver that was down for the firing, or restarted), and inventing an
incident to close is worse than dropping a close for one that never opened here.

~~An incident closes when **every episode in it is resolved and the settle window has elapsed
with no new firing**.~~

**Corrected at implementation (T2.2).** An incident closes when **every episode in it is
resolved** — and the settle window governs *reopening* rather than closing.

The original wording and the reopen clause below were two routes to the same outcome, and
building it forced the choice. Closing on the last resolution turns on an observable event
and needs no timer; the original needs a periodic tick, which makes an incident's closing
time depend on when that tick happens to run rather than on anything the world did, and puts
a sweeper in the critical path of every incident's lifecycle. The recovery alert is caught
either way: under the original by delaying the close past its arrival, under this one by
reopening. `faultline.orchestrator.core` records the same reasoning at the point of the code.

### What this does with `emailservice`

**It joins the cart incident**, in both captured runs, because the incident was still open
when it fired — `frontend` and `loadgenerator` had not resolved yet. That is the right
answer: the alert is a consequence of remediating that fault, and an investigation that
treats it as a separate incident is investigating the first incident's recovery as though it
were a second fault.

The settle-window clause exists for the case the captures do not contain: the recovery alert
arriving *after* the last original alert resolved. That is timing, not kind — nothing about
`emailservice` guarantees it fires before the others clear.

### What evidence the rule uses, and what it does not

**It uses time overlap only.** Not the dependency graph, not the service set, not the alert
labels beyond identity. That is a deliberately weak rule and it is worth being exact about
what makes it acceptable *here* and not in general:

- **It cannot mis-merge in any scored run.** `evalharness.rehearse.require_no_active_faults`
  refuses to inject into a world that already has a fault in it, so the benchmark world never
  holds two concurrent incidents. Time overlap is therefore exactly as precise as a graph
  rule would be, on the only workload we measure against.
- **It would mis-merge in production**, and obviously so: two unrelated faults starting
  within minutes of each other become one incident, and the investigation is handed a
  service set with no common cause.

So the rule is right for the benchmark and wrong for the product, which is a statement of
where it sits rather than an argument that it is fine.

### The seam for the graph-based rule (T2.4)

Correlation is a **`CorrelationPolicy`** with one method — *does this episode belong to any of
these open incidents?* — and T2.2 ships `TimeOverlapPolicy`. T2.4 builds the dependency graph
and adds `DependencyPolicy`: join when the new episode's service is within *n* hops of a
service already in the incident, falling back to time overlap when the service is unknown to
the graph.

The graph rule would reach the same answer on `emailservice`: `checkoutservice` calls both
`cartservice` and `emailservice`, so they are two hops apart through a common caller. **That
is a prediction, written down before the graph exists, and T2.4 should check it rather than
assume it.**

### The consequence nobody should discover later

**The catalog cannot test correlation.** Every scenario injects one fault into a world the
gates keep otherwise quiet, so no scored run will ever contain two incidents that *should not*
merge. Every correlation rule scores identically on this benchmark, including a broken one
that merges everything. Whatever T4.2 reports about accuracy says nothing about correlation.

Closing that needs a scenario with two concurrent independent faults, which contradicts
`require_no_active_faults` and would need its own recording path. **Marked for T7.1**, and
stated here so the gap is not mistaken for coverage.

### Marked for decision: the settle window

The floor is arithmetic from `compose/prometheus/alert-rules.yml`. A recovery-caused alert
cannot appear sooner than its rule's `for` clause after the remediation: 2m for
`ServiceHighErrorRate`, 3m for `ServiceHighLatency`, and ~6m for `ServiceNoTraffic` — 3m of
`for` on top of a `[3m]` zero-rate window that has to empty first.

| Window | Catches | Costs |
|---|---|---|
| **5m** (proposed) | every recovery-caused error-rate and latency alert | a recovery-caused `ServiceNoTraffic` opens a second incident |
| **7m** | all three rules | every incident's closure, and the eval loop's cycle time, is 7 minutes behind the world |

Proposed: **5m**, because `ServiceNoTraffic` has never once appeared in a captured recovery
and the two recovery alerts we have measured are both `ServiceHighErrorRate`. This is a real
trade-off with a thin evidence base on one side, so it is flagged rather than asserted.

---

## 2. The state machine

Eleven states, as `ARCHITECTURE.md` commits to. They are driven by what is observable: the
event stream (built, T2.1), agent outcomes (T3.x, **not built**), and approval and execution
outcomes (the action plane, **not built, and the plan does not name the task that builds it**
— contract not written).

| # | State | Entered when | Leaves to |
|---|---|---|---|
| 1 | `OPEN` | a `firing` event correlates to no open incident | `TRIAGING` (slot free), `QUEUED` (cap full), `RESOLVED` |
| 2 | `QUEUED` | opened while the cap was full | `TRIAGING` (slot frees), `RESOLVED` |
| 3 | `TRIAGING` | a slot was taken | `PLANNING`, `FAILED` |
| 4 | `PLANNING` | triage returned a severity and a blast radius | `INVESTIGATING`, `FAILED` |
| 5 | `INVESTIGATING` | the planner emitted a plan | `SYNTHESIZING`, `FAILED` |
| 6 | `SYNTHESIZING` | every dispatched specialist returned or timed out | `PROPOSING`, `FAILED` |
| 7 | `PROPOSING` | the synthesizer produced a cited RCA | `AWAITING_APPROVAL`, `RESOLVED`, `FAILED` |
| 8 | `AWAITING_APPROVAL` | a remediation was proposed | `EXECUTING`, `RESOLVED`, `FAILED` |
| 9 | `EXECUTING` | a human approved, and the token is action-bound and single-use | `RESOLVED`, `FAILED` |
| 10 | `RESOLVED` | terminal | — |
| 11 | `FAILED` | terminal | — |

States 3–6 depend on T3.x, and 8–9 on the action plane. **They are named and their triggers
declared; they are not designed here.** What each agent returns, how a specialist timeout is
distinguished from a specialist failure, and what an approval token contains are those tasks'
contracts, and writing them from this side would be inventing them.

**Two transitions are not from the pipeline, and they are the ones that make this a machine
rather than a checklist:**

- **Alerts resolving.** From any non-terminal state, when every episode in the incident is
  resolved ~~and the settle window elapses~~, the incident goes to `RESOLVED` — corrected at
  implementation, see above: on the last resolution, with no timer. An investigation
  in flight is *not* cancelled — the fault is over, the question of what caused it is not,
  and the eval harness scores exactly that answer.
- **New alerts joining.** A `firing` event that correlates to an incident already past `OPEN`
  is attached to it without changing state. It does not restart triage. It is recorded on the
  incident so the specialists and the scribe see the full blast radius — which is what T3.1
  scores triage on (`docs/adr/0009:117`).

**A `RESOLVED` incident reopens** — back to its prior state, or to `OPEN` if it never
started — when a `firing` event correlates into it inside the settle window. This is the
`emailservice` case if it had arrived a little later. **After the correction above this is
the settle window's only job**, which is why the incident carries the state it was in when it
closed: reopening has to put it back, not restart it.

### Where the state lives

Postgres, per `ARCHITECTURE.md`. The transition and the stream ack must be in one
transaction's worth of ordering — see below.

### Marked for decision: `PROPOSING` → `RESOLVED` without a proposal

An investigation that reaches a confident root cause and proposes no action (nothing to
remediate; the fault self-cleared) can go straight to `RESOLVED`. Whether that is a
distinguishable outcome or a `FAILED` with a reason is a scoring question, and T4.2 owns
remediation-class accuracy (ADR-0008). Flagged for T4.2 rather than decided here.

---

## 3. Consumption

**One consumer group, `orchestrator`, on `faultline:alerts`**, read with `XREADGROUP` and
acked explicitly (ADR-0001).

### What "processed" means

**An event is processed when the incident state change it implies is durable in Postgres —
not when the investigation finishes.** The two cases:

- **An event that opens an incident** is processed once the incident row exists in `OPEN` or
  `QUEUED`. The investigation runs long after the ack.
- **An event that joins one** is processed once the episode is attached to that incident, or
  its resolution recorded against it.

Acking only after a completed investigation would hold entries pending for minutes,
make every restart replay work already done, and couple stream health to model latency. Ack
early, and make the *state* the durable thing.

### Ordering: write, then ack

The state write commits before the `XACK`. A crash between them redelivers an event already
applied, which is safe; the reverse order loses it silently, which is not. Redis Streams and
Postgres are separate systems and there is no transaction across them, so the choice is which
failure to prefer — duplicate delivery is recoverable, loss is not.

### Idempotency

**The orchestrator keys idempotency on `(episode_key, status)`** — the same identity ingest
already dedupes on (ADR-0015), carried on every event. Applying an event whose
`(episode_key, status)` is already recorded against an incident is a no-op.

Note these are two different mechanisms and both are needed. Ingest's dedupe suppresses
Alertmanager repeats and retries. This one suppresses *stream redelivery* of an event that
was published exactly once and applied more than once. Neither substitutes for the other.

### Redelivery on crash

Pending entries are claimed with `XAUTOCLAIM` after an idle timeout — proposed **60s**, long
enough that a slow-but-alive consumer is not stolen from, short enough that a crashed one's
work is not stranded. Because application is idempotent, a claim that races the original
consumer costs a duplicate apply and nothing else.

An entry that has been delivered many times and never acked is a **poison event**, and it
must go to a dead-letter stream rather than cycling forever. Proposed threshold: 5
deliveries. There is no measurement behind either number; both are placeholders with a
stated reason, to be set once T4.1 has run the loop enough times to have one.

---

## 4. The cap

### Where severity comes from

`alert.labels.severity`, carried whole on every event (ADR-0015). **The alert rules define
exactly two values** (`compose/prometheus/alert-rules.yml`): `critical` for
`ServiceHighErrorRate` and `ServiceNoTraffic`, `warning` for `ServiceHighLatency`.

An incident's severity is the **maximum** across its episodes, `critical` > `warning`. It is
recomputed when an episode joins, so an incident that opens on a latency warning and acquires
an error-rate alert becomes critical.

**Being honest about what this ordering is worth today:** the catalog's scenarios alert
almost exclusively `ServiceHighErrorRate`, with one `ServiceNoTraffic`
(`frauddetection-memory-squeeze`) — both `critical`. A severity-ordered queue over entries
that nearly all share one severity is **FIFO with extra steps**. The ordering is implemented
because ADR-0001 committed to it and because it costs nothing, not because it currently
discriminates. It should not be reported as a working prioritisation until something measures
it doing work.

### What overflow does

Overflow **queues**; it never drops. Order: **severity descending, then first-seen ascending**
— strict priority, FIFO within a severity.

Strict priority can starve a `warning` under sustained `critical` load. The alternative is
aging (a queued incident's effective priority rises with wait time). **Proposed: strict
priority**, because the cap is a small integer on a single-operator system, sustained overload
has never been observed, and aging is a mechanism whose tuning would have no evidence behind
it. Revisit when the queue is ever non-empty for a sustained period — which is itself worth a
metric.

### The cap's value

ADR-0001 names no number. The binding constraint is model spend and rate limits, not CPU, and
**no measurement of a single investigation's cost or duration exists yet** — T3.x has not been
built and T4.1 has not run.

Proposed default **3**, configurable, explicitly a placeholder. T4.1 is the task that will
have the measurement; the number should be set from it rather than defended now.

### A queued incident whose alerts all resolve before it starts

This is the question the cap makes unavoidable, and it has a real trade-off.

| Option | Behaviour | Cost |
|---|---|---|
| **A. Abandon** | `QUEUED` → `RESOLVED`, marked `never_started` | a real incident that self-cleared is never diagnosed |
| **B. Investigate anyway** | it takes a slot when one frees | the cap stops protecting anything under sustained load; a flapping alert can fill the queue with work about nothing |

**Proposed: A, with two conditions.**

The reasoning for A: a slot spent on a fault that is already over is a slot not spent on one
that is still happening, and under a cap that is the whole point. Real on-call reviews
self-cleared incidents, but not at the cost of the live one.

The two conditions are where this gets dangerous:

1. **The outcome is recorded, not silent.** `RESOLVED` carries `never_started` and the reason.
   An incident that vanished because the queue was busy must be visible as that.
2. **A scored run must never hit it.** The eval harness investigates every scenario, and every
   scenario's fault is reverted after a 300s hold — so under a full queue a scored incident
   could be abandoned and the run would look like a scoring failure rather than a dropped
   incident. **T4.1 must assert its incident was actually investigated and mark the run
   invalid otherwise.** ADR-0008 already makes exactly this argument about filter enforcement:
   silent non-enforcement is how a defect returns after being fixed once.

**Marked for decision** rather than closed, because option A is the one that loses data and
the argument for it rests on a cap value nobody has measured yet. If T4.1 shows an
investigation takes two minutes and the cap is never reached, the trade-off it is defending
does not exist.

### The cap is also untestable on this catalog

Same shape as the correlation gap: `require_no_active_faults` means one incident at a time, so
the queue is always empty in a scored run and overflow ordering never executes. Recorded here
so nobody reads a green eval as evidence that the cap works.

---

## Consequences

**Easier.** T2.2 has states, triggers, an ack rule and a queue discipline to build against,
and each one says what it is grounded in. The correlation seam means T2.4 adds a policy rather
than rewriting the orchestrator. Idempotency reuses an identity that already exists on every
event, so nothing new has to be invented to make redelivery safe.

**Harder.** Two of this ADR's mechanisms — correlation and the cap — **cannot be exercised by
the benchmark at all**, because the eval world holds one fault at a time by design. They will
be exercised for the first time in whatever runs first outside the harness, which is the worst
place to discover a mistake. Anything that can be pushed into a test rather than a design
argument should be.

**The cap is unreachable by construction, not merely untested — found at implementation
(T2.2), and stronger than the paragraph above.** That paragraph blamed the catalog:
`require_no_active_faults` means one fault at a time, so the queue stays empty in a scored
run. The reach is wider than the catalog. `TimeOverlapPolicy` joins *any* firing episode to
*any* live incident, so **at most one incident is ever non-terminal** and nothing in the
system can count to two. No workload reaches the cap, benchmark or otherwise.

It becomes reachable exactly when a correlation policy can **decline** — which is T2.4's
`DependencyPolicy`, the first thing that will ever say "this episode does not belong to the
open incident". **The cap and the graph policy are therefore coupled, and neither this ADR
nor ADR-0001 said so** until this was built: ADR-0001 committed to the cap in isolation, and
the sections above treat the two as independent mechanisms that happen to share a task.

Two consequences follow. The severity-ordered overflow ADR-0001 committed to is dead code
until T2.4, not merely inert — the note above about two severities understated it. And
`tests/test_orchestrator.py` exercises admission through a policy that always declines, which
is the shape `DependencyPolicy` will have; that is the only way to test the cap today, and it
should be read as testing the mechanism rather than the system. The fuller note lives where
it bites: `src/faultline/orchestrator/cap.py` and `src/faultline/orchestrator/correlation.py`.

**Placeholders, named as such:** the cap (3), the settle window (5m), the claim idle timeout
(60s), the poison threshold (5 deliveries). Each has a reason and none has a measurement. They
are defaults to be replaced by T4.1's numbers, not decisions.

**Unbuilt dependencies, named as such:** states 3–6 need T3.x, states 8–9 need the action
plane, and `DependencyPolicy` needs T2.4's graph. The plan does not name a task for the action
plane at all — that is a genuine gap in `docs/PLAN.md`, not an omission here.

**Revisit if:** T2.4's dependency graph disagrees with the prediction that it joins
`emailservice` to the cart incident; a second alert source appears whose events do not carry
`episode_key`; or the queue is ever observed non-empty for long enough that strict priority
starves something.
