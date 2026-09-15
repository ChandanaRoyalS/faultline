---
scenario_id: ad-memory-squeeze
origin: scenario:ad-memory-squeeze
split: dev
incident_id: fdd89423-af39-4ad4-8890-ca332028f827
recorded_from: 2026-09-09T14:50:26.119361+00:00
---

# Frontend shipping-quote calls failing at connection setup to a callee with nothing bound to its serving port

## What the investigation concluded

The shipping-quote dependency was not reachable at the transport layer: dials to the callee's serving port were refused, and later calls surfaced as UNAVAILABLE with 'no connection established' — i.e. no listener on the port, not a slow or erroring handler. The change record for that callee showed its container image reference oscillating between its own tag and a foreign, adservice-tagged demo artifact roughly five times across the preceding ~19 hours; the first frontend refusal followed one such image swap by seconds. Conclusion held at medium confidence: the wrong artifact occupying the callee's slot, which does not bind the expected port. The flapping also accounts for why the frontend error ratio only shifted mildly and never sustainably left its baseline envelope.

## What ruled the alternatives out

Three discriminations did the work. (1) Status shape, not magnitude: connection-refused and 'no connection established' live below the application — they eliminate latency, saturation, and handler-logic hypotheses on the callee, all of which would have produced a served error or a slow-but-answered span. (2) A misdirected outbound address on the callee (a quote host that did not exist on another port) was eliminated by the same signature: a bad egress target yields an error returned *by* the callee, not a refused TCP connect to the callee's own port — and that override was already off the books ~40m before onset. (3) 'Alert is just noise in a chronically degraded environment' was eliminated because a refused connection is a concrete broken edge regardless of its rate; the flat ratio proves the fault is chronic, not that it is absent. The caller was exonerated as origin by an empty change history and by its spans showing only self-time with no errored children.

## What the proposal rested on

No action was proposed, so nothing rested on preconditions in the usual sense — but the reasoning for abstaining is the part worth carrying. The mechanism pointed squarely at the callee's running artifact, and that service was outside the set this system may act on; the only change that could plausibly move the observed signal (the refusal lines ceasing, the caller's error ratio settling back toward its ~1.6% floor) could not be issued from here. Acting on any service that *was* in range would have been a guess against the evidence: the caller had no change history to undo and its own telemetry cleared it. Blast radius of doing nothing: the refusals were a minority slice of traffic and already present in baseline. The falsifier for the abstention is three-part — the callee becoming a legal target; direct observation showing the foreign artifact live and nothing bound to the serving port at onset; and resolution of the trace/log contradiction below. Until the second and third hold, the mechanism is inferred, not verified.

## What happened at the approval boundary

Nothing reached the boundary. No proposal was formed, because the service the mechanism implicated was not one this system is permitted to target, and no in-range service had evidence against it. The abstention was the decision.

## What was never measured

The callee's actual image and port state at onset was never observed directly — the change record had the foreign artifact already swapped away ~19m before onset, so an unrecorded re-application or a stale pod is assumed, not shown. The later UNAVAILABLE lines carry no target address or method, so the callee at onset is inferred from the earlier, addressed refusals. No telemetry was pulled from the callee or the quote host at all, and the fan-out across five peer services was dropped by planner errors, leaving a broader network or platform cause untested. Most uncomfortably, the one 25-second trace sample taken during the loudest log window shows the shipping quote path completing in ~7ms with zero errored spans — in direct tension with 'nothing is listening', and unexplained when this closed.
