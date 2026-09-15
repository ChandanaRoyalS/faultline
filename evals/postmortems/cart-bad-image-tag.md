---
scenario_id: cart-bad-image-tag
origin: scenario:cart-bad-image-tag
split: dev
incident_id: 997d35d3-6f85-4c62-9fd0-c7717880a68d
recorded_from: 2026-09-09T15:11:19.179545+00:00
---

# Cart tier silent after image-reference swap; checkout GetCart leaf fast-fails

## What the investigation concluded

The artifact reference for cartservice was changed by platform automation at onset, and the cart process that had been stopped one second earlier — with an orderly shutdown notice, not a crash — never appeared again in the log stream. From that point cartservice was not serving at all. Every failing checkout trace sampled was the same 5-span shape whose deepest ERROR span was checkoutservice's outbound GetCart leaf, with nearly all self time in that leaf and none of the payment, currency, email or accounting spans ever attempted. The frontend and loadgenerator alarms were the propagated form of that single error, not independent faults. Confidence was medium: the tie between the shutdown and the reference change rests on a one-second adjacency, not on direct evidence of what the new reference did.

## What ruled the alternatives out

Trace topology did the most work. The error origin sat two levels below the alerting services, which eliminated the frontend and checkoutservice's own PlaceOrder handler; checkoutservice showed continuous traffic, no error lines, no process discontinuity, and an incident-window error mean below its own baseline with its only change point roughly two minutes after onset — late, i.e. the arrival of a downstream failure rather than a source. The absence of shipping-quote, payment, currency, email and accounting spans eliminated those paths as contributors: they were never reached. The 2-4ms failure duration is the key discriminator against the family this most resembles — a slow-but-alive dependency or deadline exhaustion would have produced a leaf near the client deadline, not a fast-fail far below it. For the cart-tier-up-but-backing-store-unreachable reading: a serving process that fails its cache lookups still logs; here the log stream terminates entirely, and the last alternate store address had been detached roughly 2.8 hours before onset. Traffic-shaping delay on the same target had likewise been detached roughly 3.1 hours before onset, so neither a settings-shape nor an added-delay reading was live at onset. What could not be separated: a defective new artifact versus the old process being stopped and never brought back by a stalled orchestration or pull backoff — both produce exactly this silence.

## What the proposal rested on

The proposal targeted cartservice and recorded no preconditions, which is itself worth noting — the intended reference value was inferred from the position in a recurring five-stage automation cycle, not observed; the pre-change value was recorded as None. Blast radius was scoped to cartservice's single inbound caller: checkoutservice would see GetCart connection resets while the cart process was replaced, propagating to frontend and loadgenerator, both already alarming; no other service's traffic would move. Named risk: if cartservice were in fact running, a working container and its in-process cache would be destroyed for nothing; if the target reference were unpullable or equally broken, cartservice would stay down in a state indistinguishable from the present one. Falsifiers, all stated as observable shape: cart logs remaining empty afterward (either the older reference also fails to come up, or the process writes under a different label — no lifecycle evidence was ever collected either way); logs appearing and then stopping again within minutes; or checkout traces retaining the identical 5-span shape with a 2-4ms ERROR GetCart leaf, which would locate the fault in the path to cart rather than in the artifact reference. A fourth, structural falsifier: because the reference change is step one of a recurring cycle, any improvement that reverses at the next iteration means the operative cause is the automation loop itself, which lies outside this system's reach. Confirmation window was 300s.

## What happened at the approval boundary

The record does not say what became of the proposal. It is not noted as accepted, refused, escalated or declined, and no reasoning at the boundary was captured. Read it as unresolved rather than inferring an outcome.

## What was never measured

No pod or container lifecycle evidence was collected for cartservice after the reference change, so whether the new artifact failed to pull, came up and looped, or came up writing under a different log label was never observed. cartservice has no calls_total series in either window, so its request rate, latency and error onset are unmeasurable — the only cart-tier evidence is the absence of log lines and the shape of the caller's leaf span. The roughly 3.5-minute gap between the shutdown notice and the first alerts is unaccounted for. Earlier iterations of the five-stage automation cycle were never examined, so whether this pattern had already occurred is unknown. No claim is made here about the system's state after the investigation closed; nothing was observed to establish it.
