---
scenario_id: shipping-wrong-image
origin: scenario:shipping-wrong-image
split: dev
incident_id: 961cb1ad-1136-4919-b461-91d5b1909899
recorded_from: 2026-09-09T17:53:06.340860+00:00
---

# Shipping hop fails at the client span while shipping's own logs show a bootstrap-only Java process

## What the investigation concluded

shippingservice was running an artifact that was not the shipping binary. About two minutes before onset (T-2m), platform-automation moved shippingservice's image reference to a demo artifact whose tag names a different service entirely (adservice). Four earlier change records in the same window came in paired apply/undo cycles that cancelled out; this one is unpaired. What came up never reached serving state, so checkoutservice's GetQuote calls landed on nothing listening, checkout aborted order preparation before the payment stage, and the error ratio rose roughly 19x — which is why checkout, not shipping, alerted first. Confidence high; checkoutservice itself had no changes at all.

## What ruled the alternatives out

Three discriminators, and they are the part worth carrying forward. (1) Where the error terminates: in every failing trace the deepest error span is checkout's ShippingService/GetQuote *client* span, ~2ms, with no shippingservice server child. That is the shape of nothing accepting the connection — it eliminates both a slow shipping handler and a shipping handler that errors on its own upstream, because either of those still produces a server span under the client span. It is what separated this from the earlier-in-window hypothesis that shipping's QUOTE_SERVICE_ADDR pointed at a non-existent quote host (that pointer was also absent from the change record ~13m before onset). (2) Runtime identity in the logs: earlier in the window shipping logs normal Rust/tonic GetQuote handler pairs; from onset onward it emits a repeating JVM/OTel bootstrap block roughly every 60s with zero handler activity. A wrong *runtime* under the shipping label is not something a resource or probe problem produces — it points at a wrong artifact, not a sick correct one. (3) Sibling spans: cart, currency, product-catalog and Redis spans are clean in the same traces, which kept this from being read as a shared-infrastructure or network-wide problem. Platform-side death by memory limit or failing probe was considered and set below: no kill, OOM, or limit evidence surfaced, and it explains neither the runtime mismatch nor the two-minute coincidence with a recorded image change.

## What the proposal rested on

Proposal targeted shippingservice, on the premise that the image reference decides which binary comes up, so the running process is wrong at the source and not merely unhealthy — a bare process bounce would land on the same wrong artifact again. No preconditions were recorded, which is itself notable. Blast radius named: shippingservice unavailable through the change window; checkoutservice sees resets propagating up to frontend and loadgenerator checkout traffic; quoteservice regains inbound GetQuote traffic; payment and email see order completions again. Named risks: the prior image reference is recorded as 'None' rather than a concrete tag, so the target artifact is not pinned; the container carrying the evidence that would settle the co-label question is destroyed in the process; and if any replicas were still serving the correct image (consistent with bursty errors, floor 0, peak ~0.30) they go down too and errors approach total during the window. It also does nothing to stop platform-automation re-applying the same reference on its next cycle. Falsifier as mechanism: if checkout's error ratio stays elevated while shipping logs show Rust/tonic handler pairs again, the cause sits at the earlier change point rather than here; and if the JVM bootstrap block keeps repeating even once shipping is running its own artifact, that loop belongs to a co-labelled Java workload and the log evidence was misattributed. Confirmation window 300s.

## What happened at the approval boundary

The record does not say what became of the proposal. It is not marked accepted, refused, escalated or declined — that field is simply absent, and no outcome should be inferred from the fact that the incident is closed.

## What was never measured

Three things stayed open. The earliest metric change point sits ~25 minutes before the image reference moved, coincident with the QUOTE_SERVICE_ADDR override being set — so whether this is one continuous failure with two successive causes, or a partial return to normal in between, was never settled. Errors are bursty, dipping to zero with a peak near 0.30, which does not match a shipping that is uniformly not serving; whether some replicas still carried the correct image is unresolved, and shippingservice emits no calls_total series, so there is no server-side confirmation of onset. And the shipping log selector returns two runtimes under one label with a truncated interval before onset, so attributing the JVM bootstrap block to shipping rather than a co-labelled Java workload rests on timing and elimination, not on direct pod/image inspection — which was never performed.
