# Discarded run

**Reason:** the alert-to-incident path was not running, so no incident could ever be correlated.

Recorded rather than deleted, per ADR-0022 §3.3.

## What happened

The run passed the baseline gate and injected at 20:09:41Z. The fault worked exactly as recorded:
within minutes Prometheus had `ServiceHighErrorRate/checkoutservice` firing at 27.6% errors, plus
`ServiceNoTraffic` on quoteservice, frauddetectionservice, emailservice and accountingservice —
the blast radius T7.20's probes measured.

**No incident existed.** `faultline-ingest` and `faultline-orchestrate` were not running. Only
`postgres` and `redis` were up. Alertmanager posts to `host.docker.internal:8000/api/v1/alerts`
and nothing was listening, so the alerts never became episodes and the orchestrator never opened
an incident for `wait_for_incident` to find.

Killed at ~20:22Z, the fault reverted, and both services started before the run that succeeded.

## Why this matters beyond one discard

Left alone it would have waited out T7.12's scrape budget and recorded a **`no-alert` discard** —
which reads as a finding about the scenario. It is not one: this scenario fired at T+169s when
recorded and at T+240s in both probes, and it fired here too. The alerts were on the board the
whole time.

**T7.12 separated `no-alert` from `metrics-gap` because they are different findings. This is a
third:** the world alerted, the metrics were fine, and the *platform* was not assembled. Nothing in
the harness checks before injecting that the ingest endpoint is listening or that the orchestrator
is consuming, so the failure presents as a silent scenario rather than as a missing service.

A preflight on those two — the same shape as the existing world-side gate checks — would have
refused in a second instead of injecting and waiting. Recorded here rather than built, because it
is a harness change and this task was an agent run.
