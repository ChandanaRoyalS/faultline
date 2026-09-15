---
scenario_id: frauddetection-memory-squeeze
origin: scenario:frauddetection-memory-squeeze
split: dev
incident_id: c4b6e073-86da-4a17-af17-51314cb93ed0
recorded_from: 2026-09-09T16:08:31.764177+00:00
---

# Fraud-detection JVM never reaching steady state under a lowered memory ceiling

## What the investigation concluded

About five minutes before onset, platform-automation wrote a 200m container memory ceiling onto frauddetection-service. That automation normally lowers the ceiling and raises it again a short while later; on four prior passes it did, and nothing happened. On this pass the raise never landed, and the ceiling stayed. Under it the JVM cannot get through startup: the process loads, prints its agent banner, and dies before any application-level line is emitted. The stated mechanism is the process being terminated from outside for exceeding its ceiling during heap initialisation — the unraised limit is how it began, running past the ceiling on every attempt is what kept it there. Confidence medium.

## What ruled the alternatives out

The shape that discriminated: the same three-line boot sequence (tool options, class-sharing warning, agent banner) repeating at roughly one-per-minute for ~7 minutes, with zero application output and zero order-consumption records after it — while the same service had been consuming Kafka records normally minutes earlier. No exception, no stack trace, no connection-failure line anywhere in that body. That silence eliminated a degraded-but-running instance, an agent-load failure (the banner prints every cycle), a named downstream fault (a failed call leaves a line), and a readable bad value being parsed and rejected (that too leaves a line). Log shipping was confirmed healthy in the same window, so the absence is a property of the death, not an ingestion gap. Timing eliminated the alert as the origin: the loop starts ~6 minutes before the alert fires, aligned with the limit write, not with the page. The four earlier identical-but-restored reductions are the control case — same value, same automation, no incident — which isolates the unraised ceiling as the only differing variable. The RED error-ratio series discriminated nothing in either direction: zero samples across the incident window and both baselines, a pre-existing labelling gap rather than signal.

## What the proposal rested on

Preconditions: none were recorded, which is itself worth noting. Blast radius: one service, bounded by the time the container takes to come back; in-process state is cache-only and discarded; the Kafka consumer resumes from its last committed offset, so a small window of order records may be re-read and the total-count counter may double for a moment. The service was already consuming nothing, so the incremental loss was near zero — but no consumer of frauddetection-service was examined, so anything downstream waiting on fraud-check results from the stalled consumption is unquantified. Falsifier, as mechanism: if the identical three-line boot sequence keeps recurring at roughly one-per-minute for more than ~5 minutes afterward with still no consumption records, the ceiling was not the binding constraint and the diagnosis is wrong — which would point at the alternative never positively excluded, a fatal-or-blocking startup step after agent load (e.g. a broker handshake that hangs and is cut short by a liveness timeout), since the death emits no error line at all. Three container-level facts would have settled it directly and were never fetched: count of boot attempts, the container termination reason, and working set against the ceiling. If those had shown no external kill and headroom to spare, the proposal was to be withdrawn. Named risks: (1) if the death is non-memory, touching the ceiling changes something that was not the cause and its only effect is one clean cycle, which masks the real fault and delays diagnosis; (2) if there is genuine heap growth, raising the ceiling removes the fast, loud signal and converts it into a slower failure under load later; (3) the automation itself is untouched — it runs on a ~5–6h cadence and its raise did not fire this pass for unknown reasons, so the next tick may re-lower or race. Confirmation window: 300s.

## What happened at the approval boundary

The record does not say what became of the proposal. It was not marked accepted, refused, escalated or declined, and no outcome reasoning was captured. Nothing was run. Treat the state at close as: diagnosis stated at medium confidence, proposal outstanding, no action taken.

## What was never measured

No container-level confirmation of the kill: attempt count, termination reason, and working set versus ceiling were never queried, so the external-kill mechanism is inferred from timing and log shape, never observed. The absence of any error line means a blocking startup step cut short by a liveness timeout is unsupported rather than excluded. Why the automation lowered the ceiling, and why this pass's raise did not fire — stuck, or merely late on a ~5–6h cadence — is unknown. The service's calls_total series is missing for at least six hours prior; whether that is a benign labelling artifact or a second, separate observability defect was never determined. Blast radius is reported as one service with no unmeasured edges crossed, but no consumer was actually inspected, so downstream impact of the stalled consumption is unquantified.
