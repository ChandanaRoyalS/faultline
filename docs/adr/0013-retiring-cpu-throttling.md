# ADR-0013: Container CPU throttling is retired as a fault mechanism

- **Status:** accepted
- **Date:** 2026-08-23
- **Task:** T1.5 (scenario rehearsal)
- **Supersedes:** the `resource_exhaustion` / `cpus` mechanism added in ADR-0010

## Context
ADR-0010 added a CPU-quota mechanism: a compose override setting
`deploy.resources.limits.cpus`, with `currency-cpu-throttle` at 0.05 CPU as its first
scenario. The number was reasoned, not measured, and the catalog said so.

Rehearsing it produced nothing, and the probe that followed produced far too much. Between
them they establish that the problem is not the number.

## Evidence

**`currencyservice` at 0.05 CPU — no effect at all.** Quota verified applied (`cpu.max`
reading `5000 100000`). Over seven minutes of fault:

| | pre | during | post |
|---|---|---|---|
| call rate | 0.4 req/s | 0.4 req/s | 0.3 req/s |
| p95 | 1.9ms | 1.9ms | 1.9ms |
| errors | none | none | none |

At 0.4 req/s and ~2ms of CPU per request, demand is ~0.8ms/s — **0.08% of a core against a
5% ceiling, roughly 60× headroom.** The mechanism worked; there was nothing to constrain.

**The whole world is idle.** `docker stats` across all 28 containers: the busiest is
`frontend` at **4.64%** of a core, then `kafka` 3.52%, `load-generator` 2.84%. Everything
else is under 1.4%. A quota low enough to bind on any of them is a quota within a rounding
error of zero.

**`frontend` at 0.02 CPU — bound completely, and took the world down.** `cpu.stat` showed
**3022 of 3022 periods throttled**: continuous saturation, not pressure. Throughput decayed
from ~10 req/s to zero over about 100 seconds. Every service behind frontend stopped
serving at **10:11:42**, and twelve `ServiceNoTraffic` alerts fired. That is not a
resource-exhaustion scenario; it is a total outage caused from the ingress point.

## Decision

**No service in this world sits between "too idle to throttle" and "too central to
throttle".** The gap between the two probes is 0.05 CPU (no effect on a leaf) and 0.02 CPU
(total collapse at the ingress), and nothing in the container inventory occupies the middle
— the busiest service in the world uses 4.64% of one core.

The mechanism is retired rather than retuned. Continuing to hunt for a number would mean
searching an interval that the CPU inventory says is empty, and any value found would be
tuned to a load level the demo happens to run at rather than to a property of the service.

`resource_exhaustion` keeps its memory mechanism, which is unaffected: memory limits bind
on this world (`recommendation-memory-squeeze` and `ad-memory-squeeze` both fire), because
the demo's containers sit near their memory ceilings under emulation even while idle on CPU.

## Spanmetrics percentiles describe only the requests that finished

This is the finding worth carrying beyond the decision, and it changes how every
latency-based scenario in the catalog should be read.

Through frontend's entire collapse, **p95 latency stayed flat at 42ms** and
`ServiceHighLatency` never fired. Not "rose and then recovered" — flat, 41.3 to 43.0ms,
right up to the last sample before the series ended.

The reason is mechanical. Span metrics are emitted when a request *completes*. A request
slow enough to matter under saturation does not complete, so it never contributes to the
histogram. The percentile is computed from the shrinking population of requests that
survived, and those are by definition the fast ones. **A service dying by saturation
reports excellent latency until it reports nothing at all.**

So the observable signature inverts:

| | what fires | what p95 shows |
|---|---|---|
| requests slow but completing | `ServiceHighLatency` | the real degradation |
| requests too slow to complete | `ServiceNoTraffic` | flat and healthy, then absent |

`cart-dependency-latency` works precisely because 300ms of added delay still lets requests
complete: p95 goes to ~650ms and stays measurable for the whole fault. **Push a latency
fault past the completion point and the signal inverts from latency to absence** — the
scenario silently changes class, and an investigator reading a latency dashboard sees a
healthy service.

Two consequences for the catalog:

- A latency fault's magnitude must be chosen to stay under the caller's timeout, not merely
  above the alert threshold. "Bigger delay, clearer signal" is false past that point.
- Absence of a latency alert is not evidence of healthy latency. `ServiceNoTraffic` and a
  flat p95 appearing together is the signature of saturation, and any scenario whose
  expected evidence cites p95 should say what it expects to see if the service saturates
  instead.

## Consequences

`currency-cpu-throttle` cannot be rehearsed. Its bundle is marked invalid
(`evals/scenarios/artifacts/dev/currency-cpu-throttle/INVALID.md`) and its scenario file
stays at `rehearsed: false`, marked BLOCKED.

**The `resource_exhaustion-2` dev slot needs a new occupant.** `SPLIT.md` is unchanged and
must stay unchanged: the slot and its split were committed before authoring (ADR-0008), and
only the scenario written into the slot changes. A replacement should use the memory
mechanism, which is measured to work here.

The CPU code path in `injector.faults` is left in place, unused. It is correct — the quota
applied exactly as specified — and deleting it would discard a working mechanism that a
future world with real CPU load could use. It is the *world* that makes it unusable, not
the implementation.

Revisit if: the load generator is run at a level that produces meaningful CPU demand, or
the project moves to hardware where these services are not effectively idle.
