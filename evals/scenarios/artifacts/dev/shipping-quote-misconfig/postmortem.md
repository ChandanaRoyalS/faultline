---
scenario_id: shipping-quote-misconfig
origin: scenario:shipping-quote-misconfig
split: dev
incident_id: e56c369e-719a-4794-8dfb-ee7fff1925b9
recorded_from: 2026-09-09T17:30:33.367265+00:00
---

# Checkout aborts on the shipping quote hop with a clean server span

## What the investigation concluded

Starting at onset, checkoutservice PlaceOrder aborts while assembling order items and the shipping quote, because its client call to hipstershop.ShippingService/GetQuote carries ERROR status in 11 of 12 sampled traces. The discriminating detail is the timing and the asymmetry: the errors come back in ~2.6-4.4ms, and the shippingservice server span in the same trace completes without error. So the failing thing is a prompt rejection at the checkout->shipping RPC boundary, not a slow or wedged dependency. The burst shape (mean ~5% span error ratio, peaks ~29%, floor still touching zero) and the clean sibling calls to cart, currency and product catalog put the fault on the quote path only. Downstream alerts on accounting, email, fraud and quote are consequences: orders never reach payment/email/broker, and the logs show those stages absent for every request from ~T+2m30s onward. Confidence stayed low, and the fault class was left unknown rather than guessed, precisely because a client-side ERROR paired with a server-side success is not one mechanism.

## What ruled the alternatives out

Gradual degradation: metrics show a sharp step at onset, not a ramp, which also excludes any trigger landing at or after T+1m45s. Slow or hung dependency: the failing call returns in single-digit milliseconds - a hang looks like a floor near the client deadline, this looks like a door slammed immediately. Process death, memory pressure, or entry-side rejection: intake logging continues through the window, requests are accepted and start work, they just stop before payment. Currency-specific path: the currency calls complete cleanly and the aborts are not partitioned by currency. Local failure inside checkoutservice: PlaceOrder self time is ~0.1ms and the ERROR is coincident with the errored child span, i.e. propagation, not local work - only one minority trace with large self time argued otherwise, which is not enough. A change-driven origin: no change record exists for checkoutservice at all, and the 34 cartservice changes are paired automation that cancels itself out, with the last event ~1h36m before onset, leaving cartservice at baseline. quoteservice as the origin: it alerted ~T+4m45s, after onset, and its HTTP child span completes without error in the affected traces - nothing yet separates it from a victim of stalled checkouts, so it was neither blamed nor cleared.

## What the proposal rested on

Nothing was proposed. The reasoning for holding: every candidate action had an unsatisfied precondition. Blast radius of acting blind on shippingservice would have been the whole checkout path, which is already the only degraded path, for a mechanism nobody had localized - a client-side ERROR with a clean server span is consistent with connection-level failure, response-validation failure at the client, or an instrumentation gap where the server does not mark its own error, and these three want incompatible treatments. The falsifier for holding was stated in advance: if the gRPC status code and message on the failing GetQuote client span came back naming a connection-level failure alongside process-state symptoms on shippingservice, or if a change record for shippingservice or quoteservice turned up landing shortly before onset, the abstention would be wrong and a targeted, precondition-satisfying intervention would exist. The confirming observation would be the error ratio decaying to baseline with nothing touched - which would also mean anything done now would have been miscredited. As of close, neither had been observed, and the signature was expected to persist: ~5% mean span error ratio with bursts to ~29%, GetQuote client spans carrying ERROR in the large majority of sampled PlaceOrder traces, shippingservice server spans still clean.

## What happened at the approval boundary

Nothing reached the boundary. No proposal was formed, so there was nothing to accept, refuse or escalate. The work that was identified as next was investigative: read the gRPC status code and message off the failing GetQuote client span, and pull logs, metrics and change history for shippingservice and quoteservice over a window beginning at least an hour before onset. That evidence was to decide, not this write-up.

## What was never measured

The gRPC status code and error message on the failing GetQuote span were never exposed, so UNAVAILABLE vs INTERNAL vs a business-logic rejection is undetermined - and that single field is what separates the three candidate mechanisms. No one examined shippingservice or quoteservice directly: no logs, no metrics, no change history for either, despite quoteservice alerting. Why the server span reports success while the client span errors is therefore open between connection-level failure, client-side response validation, and an instrumentation gap. The change-history query that was actually run started at onset and covered only the seed service, so the hours before onset and the two services on the quote path were never searched.
