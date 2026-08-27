# Ad service memory limit cut below the working set its JVM was sized for

## The scenario

| | |
|---|---|
| scenario | `ad-memory-squeeze` |
| fault class | **`resource_exhaustion`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `ad-service` via `ad-memory-squeeze` |
| time to page | 3m30s |
| steady state captured | 300s |
| capture window | 2026-08-24T10:00:13+00:00 → 2026-08-24T10:17:58+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m30s |
| `t_revert` | T+8m30s |
| all clear | T+10m45s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `frontend` | ServiceHighErrorRate | 0.5 min | **paged** |
| T+3m30s | `loadgenerator` | ServiceHighErrorRate | 7.0 min | **paged** |
| T+6m15s | `adservice` | ServiceNoTraffic | 4.0 min | joined later |
| T+6m15s | `frontend` | ServiceHighErrorRate | 4.5 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="adservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/ad-service.txt` — 97 lines.

## A look at the logs

From `logs/ad-service.txt` (91 lines):

```
2026-08-24T10:00:20+00:00  2026-08-24 10:00:20 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=a463a1cf432c71f22a2a279aa72c219c span_id=c67f408706824cbf trace_flags=01
2026-08-24T10:00:22+00:00  2026-08-24 10:00:22 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=84fa96308da7e457dfc19dad3f2beeda span_id=238c8ab7a98cdb68 trace_flags=01
2026-08-24T10:00:30+00:00  2026-08-24 10:00:30 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=c51c5e01b44f842e18968cd3188ff168 span_id=0ed32d72627b8ef4 trace_flags=01
2026-08-24T10:00:33+00:00  2026-08-24 10:00:33 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=a198c9cc5717e253c21bae69cd60ceb0 span_id=b8909a20194a3dc8 trace_flags=01
2026-08-24T10:00:35+00:00  2026-08-24 10:00:35 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=e287fa4b589b09692a450f20ac12c9bd span_id=c93518ae7acb45a2 trace_flags=01
2026-08-24T10:00:36+00:00  2026-08-24 10:00:36 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=11b6078a75758e5a1b9286fe92d02bf8 span_id=21033b8cab52cef1 trace_flags=01
2026-08-24T10:00:38+00:00  2026-08-24 10:00:38 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=1f0a8700718691e265e840161964abff span_id=372d3f7739d2f48b trace_flags=01
2026-08-24T10:00:41+00:00  2026-08-24 10:00:41 - hipstershop.AdService - received ad request (context_words=[binoculars]) trace_id=dded1ba4acb90a18a27b49a6b081e77c span_id=12a2895eb9c638d3 trace_flags=01
2026-08-24T10:00:43+00:00  2026-08-24 10:00:43 - hipstershop.AdService - received ad request (context_words=[assembly]) trace_id=21c0b04f3f003db7071ec233e25acdb4 span_id=973b58ae15478418 trace_flags=01
2026-08-24T10:00:52+00:00  2026-08-24 10:00:52 - hipstershop.AdService - received ad request (context_words=[travel]) trace_id=526f07a4897eec1e6122c9749dd64ceb span_id=df6c0423d413a61b trace_flags=01
2026-08-24T10:00:53+00:00  2026-08-24 10:00:53 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=ee456f83a105f7df2eaa6ac3a930ae4d span_id=598377bd58d23307 trace_flags=01
2026-08-24T10:00:55+00:00  2026-08-24 10:00:55 - hipstershop.AdService - received ad request (context_words=[accessories]) trace_id=72e3ec97160d3dd0897ff5db19edfd0d span_id=96c4ec260aebb620 trace_flags=01
```

_79 further lines are in the bundle._

## The incident record

Written from the responder's chair, by someone who did not know the fault class
or that anything had been injected. This text is also corpus material, which is
why it never names the injector.

**It keeps its own clock.** The table above is measured from the injection, which
is the only origin the manifest records; a narrative's `T+` offsets are the
responder's own and start wherever that responder started counting — usually the
page, sometimes the injection, sometimes an event in the logs. The same moment can
therefore carry two different offsets on this page. The absolute timestamps in the
bundle are the tiebreak.

### What was observed

The page was `ServiceHighErrorRate` on **frontend** and **loadgenerator** together,
3m30s after onset. No service between them and the edge was named.

frontend's alert then did something worth recording: it dropped back under the
threshold after thirty seconds, stayed clear for nearly three minutes, and fired again
at **T+6m15s** for the rest of the incident. An error ratio that crosses, falls back,
and crosses again is a partial failure hovering at the threshold — one dependency
failing out of many — not a flapping monitor.

At the same moment frontend's alert returned, `ServiceNoTraffic` fired on
**adservice** — the first time anything named a service other than the edge.

Four alerts across three services. The storefront was mostly usable throughout:
product pages loaded, baskets worked, checkout completed. The advertisement panel was
missing.

### What was checked

**loadgenerator.** The page named it and it explains nothing. It is the synthetic
client; its error rate restates whatever the storefront is failing to do.

**Error rate by service.** frontend intermittently over threshold, loadgenerator over,
everything else flat. adservice itself: zero errors, then no data at all.

**Which page elements were failing.** The store worked apart from the ad panel. That
narrowed it faster than any metric did — frontend's errors were confined to one
dependency, and the storefront said which one before the alerting did.

**Whether adservice was idle or absent.** `ServiceNoTraffic` cannot tell those apart:
both look like a call rate of zero. The runtime metrics can. adservice exports its own
JVM heap series, and a process that is merely idle keeps exporting them. **Those
series continued for the first four and a half minutes of the incident and then
stopped entirely, not returning until after the fix.** A service that has stopped
reporting how much heap it is using does not have a heap. That is the moment the
investigation stopped being about traffic and started being about the process.

**adservice's logs, which say nothing at all.** Ordinary request lines up to seconds
before onset, then total silence until two minutes after the fix. No error, no crash
message, not even a startup banner from a restart attempt. **An empty log is not
evidence of a healthy service; it is evidence that nothing survived long enough to
speak.** The silence here is total where other incidents on this system have at least
left truncated startup attempts — which restart supervision produces is not
guaranteed, and its absence must not be read as the absence of restarts.

**What changed.** Not the image, not the environment, not the code, not any
dependency. The change history shows one edit: the container's memory ceiling was
reduced to 256 MiB. Steady-state usage is around 350 MiB, and the JVM's heap was sized
against the previous ceiling of 700 MiB — so the runtime ran until it grew into the
new wall, was killed, and never got back up.

### Root cause

adservice's container memory limit was reduced below the footprint its JVM was
configured for. Nothing about the service changed — only the ceiling it was allowed to
occupy. The process ran for a few minutes on the heap it had already committed, grew,
was killed by the kernel, and could not complete a restart inside the new limit.

This is why it produced no errors of its own: a process that is killed records no
calls, and therefore no errored ones. Its evidence was absence, three times over — of
traffic, of logs, and of the runtime metrics it publishes about itself.

### Resolution

The memory limit was restored to its previous value. adservice came back and the ad
panel returned. Everything was clear 2m15s after the fix.

Class of fix: **config_revert**. Nothing was deployed and nothing needed rolling back;
one resource limit was wrong and was put back.

### Detection notes

- Onset to first page: **3m30s**.
- Services alerting at the page: **2**. Over the whole incident: **3**, across 4
  alerts.
- Alerts that fired only during recovery: **none**.
- **The page named the edge, twice over, and the culprit only as an absence three
  minutes later.** The strongest early signal was not in the alerting at all: the
  storefront worked except for one panel.
- Did the loudest service turn out to be the culprit? **No.** loadgenerator alerted
  longest at seven minutes and is not a service in any meaningful sense.
- **An alert that crosses, clears, and crosses again is a partial failure, not a flaky
  monitor.** frontend's ratio hovered at the threshold because only the requests
  touching the ad panel were failing. Dismissing the first thirty-second firing as
  noise would have cost three minutes.
- **A service's own runtime metrics disappearing is stronger evidence than its traffic
  disappearing.** An idle service still reports its heap; a dead one reports nothing.
  This incident's bundle carries that evidence directly: the heap series run to
  T+4m45s and stop.
- **The runtime series also outlived the traffic.** The heap kept reporting for
  minutes after calls stopped being served — a process can be alive and useless. The
  reverse transition, from reporting to gone, is the one that dates the death.
- **Silence in the logs carries no timestamp of its cause and no cause at all.** This
  run left no crash message and no restart banners — nothing between the last ordinary
  request and the post-fix recovery. What filled that gap was the runtime metrics
  stopping. The failure signature does not name its cause either way: only the change
  history distinguishes a lowered ceiling from a service that grew.
- **Blast radius shape was the useful clue.** Only adservice and its single consumer
  were affected. A leaf consumed by one caller produces exactly this narrow spread;
  nothing on the critical path can.

---

Rendered from [`evals/scenarios/artifacts/dev/ad-memory-squeeze/`](../../evals/scenarios/artifacts/dev/ad-memory-squeeze/) by `faultline-render`. [All bundles](README.md).
