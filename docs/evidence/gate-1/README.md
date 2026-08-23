# Gate 1 evidence — 2026-08-23

Fault → alert → visible → resolved, with no AI involved.

Fault: `flag-service-bad-deploy` (class `bad_deploy`, target `featureflagservice`)

| event | time (UTC) | delta |
|---|---|---|
| injected | 00:50:48 | — |
| alert condition first true | 00:51:15 | +27s |
| alert FIRING | 00:53:15 | +2m27s |
| reverted | 01:14:23 | — |
| alert cleared | ~01:16 | — |

Detection latency splits into 27s of real signal propagation
(span → spanmetrics → scrape) and the deliberate 2m `for` guard.

One fault, four firing alerts — the alert-storm-to-one-incident
case T2.1's fingerprint dedupe exists to handle:

| service | error rate |
|---|---|
| recommendationservice | 66.7% |
| frontend | 9.7% |
| loadgenerator | 9.7% |
| productcatalogservice | 8.1% |

## Files

- `01-alert-firing.jpg` — Prometheus alerts, ServiceHighErrorRate firing on 4 services
- `02-error-rate-dashboard.jpg` — Grafana, error rate across the full incident
- `03-alert-resolved.jpg` — Prometheus alerts, all inactive after revert
