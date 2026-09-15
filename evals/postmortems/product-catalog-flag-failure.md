---
scenario_id: product-catalog-flag-failure
origin: scenario:product-catalog-flag-failure
split: dev
incident_id: 425cf24a-dcbc-48c6-a9e9-b03a625b8663
recorded_from: 2026-09-09T16:52:30.920061+00:00
---

# Partial INTERNAL rejections on catalog GetProduct driven by an enabled failure flag

## What the investigation concluded

productcatalogservice was itself marking a fraction of GetProduct calls as failed because a failure-behavior feature flag was in its enabled state. The status the frontend saw was authored by the catalog service: gRPC status 13 with a details string that names the enabled flag. The wrong value is the flag's enabled state, not code, not capacity, not a downstream.

## What ruled the alternatives out

Three discriminators did the work. (1) Frontend errors were raised on the grpc-js status-receive path, meaning frontend transcribed a peer-supplied status rather than manufacturing one; frontend also had no recorded change of any kind across the 24h spanning onset. That eliminates the noticing tier as origin. (2) The ERROR marking sits on the productcatalogservice GetProduct server span, while its single child (FeatureFlagService/GetFlag) completed cleanly in ~2.1ms. A downstream that answers successfully and fast cannot be the source of an error stamped above it — that eliminates propagation from the flag store, and it eliminates the flag store as a faulty component. (3) Failures were fast rejections around 2.4ms with span durations indistinguishable from healthy traces — no long tail, no queueing shape, no near-constant floor. That eliminates slow-dependency and saturation stories, which would have left a duration signature. A fourth, subtler one: the GetFlag child span appears only beneath the errored GetProduct and not beneath the nine healthy sampled ones, so the failing path is flag-conditioned rather than randomly defective — that separates a deliberate conditional branch from an organic intermittent bug. Finally, there was no image rollout or deploy record for the catalog service in the window; the only recorded changes were a traffic-shaping sidecar attached and detached roughly 10.8h before onset, far outside any plausible causal reach given the flat-zero error baseline right up to the change point. Ratio climbed from flat zero to ~9% peak at T+0; frontend aggregate error ratio stayed flat because the mean effect was near 1%, which is why user-visible catalog errors fired without tripping the top-level indicator.

## What the proposal rested on

Nothing was proposed. The permitted class of change had two preconditions: a recorded prior configuration state, and a recorded mutation of that state inside the incident window. Neither existed — no change record anywhere shows the failure flag moving to enabled, in the catalog service or in the flag store. Without a prior state there is no defined target to move toward, so the blast radius of acting blind would be an unbounded edit to a config surface whose baseline is unknown, against a fault that is currently partial and bounded. The abstention falsifies in two ways, both mechanical: if change history for the catalog service or the flag store surfaces a prior value plus a mutation inside the window, the preconditions are met and the case for acting exists; or if the error fraction climbs materially past the observed ~9% peak or goes total, the cost of waiting for provenance exceeds the cost of acting without it. Note the diagnosis is not what is in doubt — the mechanism evidence is strong. What is missing is the recorded prior state.

## What happened at the approval boundary

Nothing reached the boundary. No action was formulated, so there was nothing to accept, refuse, or escalate. The blocking reasoning was provenance, not confidence in cause.

## What was never measured

Who enabled the failure flag, when, and in which system — never established; no change record was found. The catalog service's own logs were never actually read: the log selector used a hyphenated label variant and returned zero lines, so the correct label value was never queried. Trace coverage has a gap across the two minutes bracketing the change point and frontend logs were truncated, so the precise onset is inferential rather than observed. Whether the flag store's own contents or history would show the edit was never examined.
