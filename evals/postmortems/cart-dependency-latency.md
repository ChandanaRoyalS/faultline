---
scenario_id: cart-dependency-latency
origin: scenario:cart-dependency-latency
split: dev
incident_id: a92e0e40-8fe2-4996-9668-62fb952bcbd7
recorded_from: 2026-09-09T15:31:50.247816+00:00
---

# Fixed per-hop delay floor on cart path, traced to an unterminated traffic-shaping attachment

## What the investigation concluded

About three minutes before onset (T-3m), platform automation attached a traffic-shaping sidecar into cartservice's network namespace imposing a fixed 300ms egress delay with zero jitter on eth0. In five earlier passes of the same automated cycle the attachment was always paired with a matching teardown; in this pass the teardown never appeared, so the shaping rule was still live at onset. The delay is additive per network crossing, which is why AddItem hops land near 904ms and frontend requests near 1.5s. Checkout, frontend and loadgenerator alerted only because they block on cartservice; checkout's ~9.5x error-ratio rise is deadline expiry on the cart hop, i.e. propagation, not origin. Confidence medium.

## What ruled the alternatives out

The discriminator was the shape of the latency, not its size. Every cartservice Redis leaf sat in a tight 300-310ms band across ~20 operations with almost no spread, while cartservice's own in-process work stayed under ~1.2ms and non-cart dependencies in the same traces stayed sub-millisecond to ~18ms. A near-constant floor that ignores which command is running eliminates application code paths (they vary with work), cluster-wide network degradation (it would not spare the non-cart dependencies in the same traces), and contention-driven queuing (which produces a long tail, not a flat band). The cartservice hotfix image was no longer the running reference ~13 minutes before onset, and a code regression cannot manufacture identical delay on the caller's side of the wire. A slow Redis backend was eliminated because the same 300ms unit appears independently in each caller's client-span self-time into cartservice, not only in the Redis leaves - at least two crossings are penalised, so a single slow downstream does not cover it. Caller-side fault was eliminated by checkout logs: no error, DNS or refused-connection text, payments and emails continuing, queue offsets sequential, order steps merely separated by ~1.2s instead of tens of ms. cartservice itself served cart operations continuously with no boot banners and no backend failure.

## What the proposal rested on

Nothing was proposed, and the reason is the useful part. The mechanism sits in a network namespace attachment; the two candidate levers both addressed state that was already current. The only cartservice config change in the window was the REDIS_ADDR pair, whose prior value was restored ~3.1h before onset - acting on config would have re-established an already-live state while the 300-310ms floor persisted in both Redis leaves and caller self-time. The image reference was likewise already back to its prior value ~13m before onset. Blast radius of either lever was therefore a no-op on the floor plus an unnecessary disruption of a service that was answering every request correctly. The falsifier, if the shaping attachment ceases out of band: cartservice Redis leaf spans leave the 300-310ms band for sub-millisecond, and checkout's per-order log steps close from ~1.2s back to tens of ms, both within ~120s. If that does not follow, the flat floor was never the shaping rule.

## What happened at the approval boundary

Nothing reached the boundary. Abstention was on the reasoning that no available lever touched the mechanism the evidence named, and that a lever whose precondition is already satisfied cannot change the observed floor. The abstention is wrong if change history holds a cartservice config entry that itself carries the eth0 delay as restorable configuration, or if the unexplained checkout error change point resolves to a config or image state a listed lever could reach - both checkable in change history before touching anything.

## What was never measured

Checkout's error-ratio change point sits ~19 minutes before the shaping attachment, overlapping the hotfix apply-and-restore window; that gap is unexplained and may be a second, independent story. No latency or request-rate series returned for either service, and traces cover only a ~37-second slice with both log queries truncated across the preceding half hour, so the transition into the degraded state was never directly observed - only its steady state. And why checkout's client spans into cartservice carry ~905ms of self-time (three 300ms units) above a ~305ms server span is not accounted for by a single egress delay on one namespace.
