---
scenario_id: redis-cart-dependency-latency
origin: scenario:redis-cart-dependency-latency
split: dev
incident_id: 1e7081b4-d54e-42a9-849d-7cc7b5b5c450
recorded_from: 2026-09-09T17:12:24.812221+00:00
---

# Fixed per-round-trip delay on cartservice's egress to its Redis backend

## What the investigation concluded

Cart requests stayed successful but every Redis client span inside cartservice consumed a tightly clustered ~300-310ms, while the enclosing gRPC handler self-time stayed under ~2ms. Total operation latency tracked round-trip count exactly: one command (GetCart) ~305ms, two commands (AddItem) ~600-615ms. That arithmetic - a constant additive penalty per network round trip, not per request and not per byte - places the added wait on the cart-to-Redis network path at cartservice's own egress, not in cartservice code and not in Redis's work. The platform change record shows six identical automated cycles that attached a traffic-shaping container with a fixed egress delay to the cart-service network namespace. Each is recorded as detached, and none falls within ~78 minutes of onset, but the traces sampled at onset are incompatible with an unshaped namespace; the plausible reading is a further unlogged cycle, or a detachment recorded in the ledger while the queue discipline or sidecar remained live. frontend and checkoutservice alerted seconds later purely by inheritance - they sit above cartservice and wait on it - with their own error ratios at or below baseline.

## What ruled the alternatives out

The discriminator that did the most work was the shape of the distribution, not its size. A saturated or persistence-blocked Redis server produces variable, long-tailed latency with occasional fast outliers; what we saw was a narrow 300-310ms band across all ten sampled traces and across both command types, with no error-status spans anywhere. That eliminated server-side saturation on redis-cart as an explanation, even though nothing was ever queried on the Redis side. cartservice compute of ~1ms per request eliminated its own code paths and any GC or lock story. The observed command count per operation matched exactly what the handlers should issue - one for GetCart, two for AddItem - which eliminated retry storms and client-side retry inflation, both of which would have inflated span counts, not just durations. An endpoint misdirection (cart traffic pointed at an alternate or proxied Redis address) was considered and ruled below: each address override in the change record has a logged reversal, the last one roughly 1.3h before onset, and a wrong endpoint characteristically yields refusals or a step change in shape, not a precise, uniform per-round-trip addend. cartservice logs ran continuous normal cart operations to the window edge with no panic text, no boot banners, and no connection-refused lines; checkoutservice completed full order flows at info severity in the final minute. Those negatives eliminated crash-loop and unavailability readings and confirmed this was a pure wait, not a failure.

## What the proposal rested on

The proposal's precondition - never explicitly recorded, which is itself a weakness - was that the delaying element lived inside cartservice's own network namespace, so that discarding and rebuilding that namespace's state would remove the addend. Blast radius: cartservice unavailable for the seconds it takes to come back, seen by frontend (AddItem, GetCart) and checkoutservice (GetCart, EmptyCart) as connection resets and a short user-facing cart-error blip in both services' error ratios; cartservice's in-process cart cache is discarded and not recoverable. Falsifier, stated as mechanism: if Redis client spans still show the same ~300ms band, the delay is not namespace-local and the search must move to redis-cart's own server-side timing or to host/bridge-level shaping. If latency instead drops and then returns on a ~10-20 minute cadence, a live schedule is still driving attachments. Because cartservice has no usable metric series in either window, confirmation would have rested on trace durations alone, within a 180s window. The proposal also named its own cost: it destroys the namespace state that would have confirmed the queue-discipline reading, so inspecting the namespace first would have been strictly better evidence-wise.

## What happened at the approval boundary

The record does not say what became of the proposal. It was neither recorded as accepted nor as refused, escalated, or declined, and no confirmation window was observed to open or close. Nothing here should be read as the proposal having been carried out or as the condition having cleared.

## What was never measured

Whether an unlogged seventh attachment cycle began at onset, or whether a logged detachment left the shaping element in place, was never determined - the cart-service network namespace was never inspected while the condition was live. redis-cart was never queried at all: no server-side latency, connection-count, or slowlog evidence exists, so Redis-side slowness is only argued against by the uniformity of the penalty, not measured away. cartservice had no usable metric series in either window, leaving its latency percentiles, request rate, container lifecycle events, and readiness state entirely unmeasured. Host- and bridge-level shaping was never examined and remains a live alternative if the delay were ever shown to survive namespace-local changes.
