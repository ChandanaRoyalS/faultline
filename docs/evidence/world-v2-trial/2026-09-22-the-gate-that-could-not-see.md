# The gate that could not see — 2026-09-22

**\$0, no model call, found by looking for somewhere to put an unrelated check.** The pre-flight
gate is what stands between a degraded world and an injected scenario. **On the v2 world it
approved everything, and it would have gone on approving everything through the whole scenario
sweep.**

## What it was doing

`evalharness.gate.read` took its two telemetry readings from a module-level constant:

```python
windows = _window_by_service(METRIC_QUERIES["latency-p95"])
rates   = _latest_by_service(METRIC_QUERIES["call-rate"])
```

`METRIC_QUERIES` is **v1's** capture set — `latency_bucket`, `calls_total`. Those series do not
exist on v2, where the collector runs `spanmetrics` as a connector under a
`traces_span_metrics_` namespace. **PromQL over a metric that does not exist is an empty result,
not an error**, so:

- `windows` is empty → `p95_over_ceiling` is empty → **no refusal**;
- `rates` is empty → `services_reporting = 0`, `silent_services = []` → **no refusal**.

The gate then wrote `services_reporting: 0` into the run manifest and **never looked at the
number**. A world with nothing running and a world nobody pointed the gate at produce byte-identical
readings, and both pass.

**What survived** were the world-agnostic checks: firing alerts (`ALERTS` is not world-specific),
container uptimes, memory headroom, injector status, open incidents, the alert pipeline. So the
gate was not inert — it was **selectively blind in exactly the two places that look at the world's
telemetry**, which is the half a reader would most assume was covered.

## How it was found, which is the uncomfortable part

Not by testing the gate. Three candidate shapes for the `ServiceHighLatency` fix could in principle
make a service vanish from a rule silently, and this analysis went looking for the gate in order to
add a live check against that. **The gate could not have run that check, because it could not see
the world at all.**

Nothing in `make check` was going to find this: the gate's tests stub Prometheus and assert the
logic, which is correct and was never wrong. The defect is that the logic was being fed a question
in the wrong language, and the only signal was a zero that nothing read.

## The fix

**The gate takes a world.** `read(..., world=None)` resolves to `ToolSettings().world` and builds
its queries with `metric_queries(metrics_for(world))`, the same object the capture and the alert
rules already share. `GateReading` carries `world` and it reaches the manifest, because the same
numbers mean different things on the two worlds and an empty reading means "quiet" or "asked in the
wrong language" depending only on that field.

**And one line makes the whole class loud:**

```
no service reports a call rate on world 'v2' - the gate queried '...' and got nothing back.
Either the world is not running, or it is not the world this gate was pointed at
(FAULTLINE_TOOLS_WORLD, currently 'v1'). A gate that cannot see a world must not certify it.
```

**That check is self-correcting for the mistake that caused this.** `ToolSettings().world` defaults
to `v1`, so a gate run against a v2 world with the environment unset queries v1's names, sees
nothing, and now refuses with a message naming both worlds — instead of passing.

A second guard covers the asymmetric half: traffic visible, duration histogram empty. Both series
come from the same `spanmetrics`, so that combination means the histogram specifically is gone — a
connector with histograms disabled, say — and the p95 check would otherwise pass by having nothing
to look at, which is not the same as passing.

## What was deliberately not made a refusal

The check this went looking for in the first place is **recorded, not enforced**. On v2 the p95
query carries `span_kind!="SPAN_KIND_INTERNAL"` and the call counter does not, so a service whose
spans were all internal would serve traffic, count it, and have no measurable duration — and a
latency fault injected there would score as a miss that reads as the agent's failure.
`gate.read` now computes `latency_invisible` and puts it in the manifest.

**It does not refuse, and the reason is that it is uncharacterised.** 18 of 18 services were
measured to carry a non-internal span, but that is one instant rather than a characterisation
across a gate window; a low-traffic service could plausibly hold a call-rate sample and no duration
sample over 180s with nothing wrong. **This repository's four historical gate refusals are the
reason ADR-0025 exists**, and putting an unmeasured refusal in the path of every sweep would be
repeating that. Queued as **Q87** with the measurement that would settle it — one the existing v2
baselines can answer without collecting anything new.

**A pre-existing test caught this before it shipped.** The refusal version failed
`test_the_gate_still_passes_a_world_at_its_baseline`, on a fixture that overrides `p95` without
`rates`. That is a fixture artefact rather than a real signal — but it was the prompt to notice
that the invariant being enforced was assumed rather than measured.

## `v2` has no characterised tail services, and the empty set says so

`KNOWN_TAIL_SERVICES` became `TAIL_SERVICES_BY_WORLD`, and **v2's entry is empty**. T7.14's three
names (`checkoutservice`, `frontend`, `loadgenerator`) are a measurement taken over days on the v1
world. Translating them to v2's spellings — `checkout`, `load-generator` — would assert a
measurement nobody took, inside a refusal note whose whole purpose is to tell the reader the
excursion is understood. The set fills in when v2 produces excursions and somebody characterises
them.

## The ordering was luck

The gate's own ceiling is `P95_CEILING_MS = 1000`. Making it world-aware **before** the internal-span
fix would have pointed it at `accounting` at 15000 ms and **refused every injection on v2,
permanently** — a loud failure rather than a silent one, but a blocking one, and the cause would
have looked like the gate rather than the span. The two patches happened in the order that works,
and not because anyone planned it.

## What is still v1-shaped in the harness

This patch makes `gate` world-aware. It does not survey the rest. `evalharness.rehearse`,
`evalharness.run` and the scoring path have not been examined for hard-coded v1 metric names, and
**the same failure mode applies to every one of them**: a v1 name on a v2 world is an empty result
that reads as a quiet world. That survey belongs with the scenario work and is the next thing to do
before any v2 run is scored.
