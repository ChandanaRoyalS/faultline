# Pre-registration — T6.7, the alert storm: what 200 alerts do to the platform, with the model off

**Written and committed before `faultline-storm` has run.** The harness exists in the same commit
as this file and has been exercised only against fakes; the numbers below are predictions about
the first run against the development platform, made from reading the code, and the run's
evidence directory will score each one. **$0.00**: the storm runs with the orchestrator's
investigation disabled (the development default), and the harness refuses any receiver that is
not on the loopback interface, so it cannot be pointed at the deployment - whose orchestrator
investigates every incident it admits - by mistake.

This is T6.7 piece 4 (design note §2). What it measures is the **platform**, not the agent:
whether two hundred alerts at once become a handful of incidents, how deep the queue gets, how
long the stream takes to drain, what the receiver's latency does, and whether anything falls
over. The spec's failure row 5 - *alert storm: cascading failure fires 200 alerts at once* -
names its Mitigation as *dedupe + correlation groups alerts into few incidents; global
investigation concurrency cap; overflow queued* and its Recovery as *storm drains from queue by
severity; post-hoc merge of duplicate incidents*. The merge is not built and this run does not
claim it; it counts what a merge would have had to do.

---

## 1. The storm

`faultline-storm --n 200` generates **exactly 200 distinct alerts** in Alertmanager v4 webhook
shape: cycling over every catalog service (`ServiceCatalog.from_snapshot()`, 18 services) and the
three rules in `compose/prometheus/alert-rules.yml` (`ServiceHighErrorRate` critical,
`ServiceHighLatency` warning, `ServiceNoTraffic` critical) - 54 pairs - with a `replica` label that
increments each full cycle, so fingerprints are distinct and each service carries every alertname.
One `startsAt` for the whole storm (the cascade's onset), one alert per POST, sixteen POSTs in
flight at a time. Seeded, so the same storm can be sent again.

Then **the same 200 again** - a re-notification storm, every fingerprint and `startsAt` repeated -
which the receiver's dedupe must fold to nothing. Then **200 resolves**, so the incidents close
and the development database is left as it was found, with the resolved incidents on its record.

Between phases the harness waits for the stream to drain (consumer-group `lag` and `pending` both
zero) and samples `/metrics`, `XLEN` and `XINFO GROUPS` once a second throughout.

## 2. Predictions, scored by the evidence directory

| # | prediction | falsified by |
|---|---|---|
| P1 | Every one of the 600 POSTs returns 200; no 5xx, no connection error | any other status |
| P2 | Pass 1 publishes exactly 200 and deduplicates 0; pass 2 publishes 0 and deduplicates 200; pass 3 publishes 200 (a resolve is a new transition) | any other counts |
| P3 | **Incidents opened: between 1 and 6.** The world is one connected component through `frontend` and `checkoutservice`, `DependencyPolicy` joins within 2 hops, and every service with graph presence is within 2 hops of one of those two; the uninstrumented and synthetic services (`kafka`, `redis-cart`, `loadgenerator`, `frontendproxy`, `featureflagservice`) defer to time overlap, which joins anything live. The honest range is wide because the join order depends on which alert arrives first | fewer than 1 or more than 6 |
| P4 | No fingerprint appears in two incidents | any episode key in two incidents |
| P5 | `faultline_incidents_queued` peaks at `max(0, incidents − free)`, where `free = 3 − (slots already held when the storm began)` - the cap is 3 and a `triaging` incident holds its slot until it resolves, so with the model off the queue **holds** its peak through passes 1 and 2 and reads 0 only after the resolves; the last sample of the run reads 0 | a different peak, or a non-zero last sample |
| P6 | The stream drains (lag 0, pending 0) within **60 s** of the last POST of each pass | later |
| P7 | Receiver latency p99 under **500 ms** at 16 in flight | higher |
| P8 | After pass 3 every storm incident is `resolved` within 60 s | any other state |
| P9 | No platform container restarts and neither host daemon dies; the orchestrator logs no ERROR | a restart or an ERROR line |
| P10 | Pass 2 opens **no** incident and joins **no** episode - dedupe stops it at the receiver | any change to the incident table during pass 2 |

P3 is the one that is a measurement rather than a check, and it is the number the design note
says decides whether a post-hoc merge is worth a row: if it lands near 1, the correlation is doing
the merge's job already; if it lands near 6, the storm made near-duplicates that nothing folds.

## 3. What is not claimed

No throughput figure beyond this machine's; no severity-ordered drain (every storm alert but one
alertname is `critical`, so the ordering has nothing to discriminate - `cap.py` says the same);
no investigation of anything. A run whose harness or platform is changed after this file is a
different run; the evidence directory records the commit.
