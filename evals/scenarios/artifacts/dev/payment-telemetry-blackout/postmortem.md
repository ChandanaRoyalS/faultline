---
scenario_id: payment-telemetry-blackout
origin: scenario:payment-telemetry-blackout
split: dev
incident_id: 4b7410ec-81c7-4f53-aff4-63f37b49c3b7
recorded_from: 2026-09-09T16:30:30.160711+00:00
---

# Payment path healthy, span stream cut at the source: an exporter aimed at loopback

## What the investigation concluded

The paymentservice request path was never impaired. Charges were received and completed in ~1ms with paired info-level log lines running to the end of the window, and every Charge span carried sub-millisecond duration with no error status. What ended at onset was telemetry egress: roughly five minutes before the alert (T-5m), platform-automation set the OTLP traces endpoint on paymentservice to a loopback address where nothing listens. The span stream shows a step, not a ramp — full 36-42 span traces up to T-6m, then a single truncated 8-span trace, then 8-9 minutes of nothing. This is an observability blackout produced by an exporter destination that names an address with no receiver; confidence held at medium.

## What ruled the alternatives out

Crash-loop, credential rejection and charge-path failure: paired charge/completion log lines continued at info level through the end of the window — there were no repeated startup banners and no gap in request handling. paymentservice latency and errors: root latencies stayed flat at 22-36ms with no ramp across onset, so nothing in the request path was waiting; that also eliminates a downstream-wait explanation. An artifact change: the change log contains no deploy, no image change and no payment-critical config edit, and checkoutservice shows no changes at all, so the 'new code is bad' shape is absent. The most instructive discriminator was direction: checkoutservice's error ratio fell from a noisy ~0.16 baseline to exactly 0 with zero variance across 129 samples. Systems do not become noiselessly perfect; a series that pins to a constant with no jitter is the signature of samples no longer arriving, not of a workload improving. The shippingservice-to-quoteservice hop dominated self-time but did not move through onset, so hop dominance alone is not evidence of causation — it was unexamined rather than excluded, as neither service was dispatched. A collector- or pipeline-wide ingestion outage was never eliminated: it produces the same shape, and no collector health was ever queried. It was ranked below only because it does not explain a change five minutes before onset that specifically repointed this one exporter at loopback.

## What the proposal rested on

Preconditions: none were recorded, which is itself worth carrying forward. Blast radius as mechanism: the proposal touches paymentservice's running container, so for its duration checkoutservice — its direct caller — would see connection resets, and frontend would see those one hop up as failed PlaceOrder attempts; in-flight charges would fail. The value at issue is a telemetry destination, not a business dependency, so no downstream service gains or loses request traffic, but every trace-derived metric for paymentservice and checkoutservice would change what it reports once spans reach a live receiver. Falsifier, with a 600s confirmation horizon: if no paymentservice or checkout traces appear while frontend traffic is demonstrably still flowing (payment logs still emitting charge/complete pairs), the blackout is not this exporter destination and a collector-wide outage becomes the live hypothesis. Equally falsifying: traces resume but checkoutservice's error ratio stays pinned at exactly 0 with zero variance, which would mean the flat-zero series had a cause other than missing spans. Named risks: the target is a service confirmed healthy at the request layer, traded against a metrics gap on telemetry-only symptoms; ~30 minutes of paymentservice logs preceding the alert are unobserved, so an error burst in that interval cannot be excluded and in-process state carrying it would be lost; and the change history shows this variable flapping on a 5-6 hour automated cadence, so the loopback destination is very likely to be re-applied within hours. Addressing the automation that writes the value lies outside this system's reach.

## What happened at the approval boundary

The record does not state what became of the proposal — not accepted, not refused, not escalated. It simply stops. Do not read the absence as approval.

## What was never measured

Whether any user-facing failure occurred at all: every dispatch found the request path healthy and no frontend success-rate evidence was collected. Whether the export loss was confined to paymentservice or was collector-wide: collector health was never queried, and both produce the same trace-silence shape. paymentservice's own Prometheus error-ratio series was empty in both the baseline and the incident window, so it can neither confirm nor falsify anything here — only traces can. Roughly thirty minutes of paymentservice logs before the alert are missing to truncation, and no latency percentiles or saturation figures were returned for either service. Also unresolved: four prior identical toggles of this variable were undone without an attributed incident, which the medium confidence reflects.
