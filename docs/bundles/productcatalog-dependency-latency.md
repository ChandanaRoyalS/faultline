# Product catalog network path acquires 300ms of delay, slowing every caller

## The scenario

| | |
|---|---|
| scenario | `productcatalog-dependency-latency` |
| fault class | **`dependency_latency`** |
| expected remediation | `restart` |
| split | `holdout` |
| injected at | `product-catalog-service` via `productcatalog-dependency-latency` |
| time to page | 3m49s |
| steady state captured | 300s |
| capture window | 2026-08-28T05:04:23+00:00 → 2026-08-28T05:22:44+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m49s |
| `t_revert` | T+8m49s |
| all clear | T+11m21s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `checkoutservice` | ServiceHighLatency | 6.8 min | **paged** |
| T+3m30s | `frontend` | ServiceHighLatency | 7.2 min | **paged** |
| T+3m30s | `loadgenerator` | ServiceHighLatency | 7.2 min | **paged** |
| T+3m30s | `recommendationservice` | ServiceHighLatency | 7.5 min | **paged** |
| T+4m30s | `productcatalogservice` | ServiceHighLatency | 6.2 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="productcatalogservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/product-catalog-service.txt` — 7 lines.

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

Four `ServiceHighLatency` alerts fired together: **checkoutservice**, **frontend**,
**loadgenerator** and **recommendationservice**. The page arrived 3m49s after things
started slowing.

**productcatalogservice** — the service the delay was actually on — joined a full minute
after the others, last of the five.

No errors anywhere. Every request succeeded; they took longer. The storefront worked
end to end, sluggishly. Product pages were slow to render and the recommendation strip
was slower still.

Five alerts across five services, and the blast radius never grew beyond them.

### What was checked

**The page, and what it implied.** Three services slow at once, none of them obviously
upstream or downstream of the others at a glance. frontend and loadgenerator are the
edge; recommendationservice looked like a third, separate problem.

**Whether this was noise.** It persisted through a three-minute clause and kept
persisting. Duration ruled out the world's own variability before any single reading
did.

**The error dashboards.** Clean throughout. Nothing failing, nothing retrying, nothing
timing out — which argues against most causes at once and against urgency too.

**Direction of propagation, which is where the page misled.** recommendationservice was
among the loudest, and it is a caller of product catalog, not a dependency of it.
Reading the page as "three peers are slow" invites looking for something all three
share — the network, the collector, the host. The actual shape is one leaf with several
callers, and the callers were louder than the leaf.

**Why the culprit was quietest.** productcatalogservice's own p95 rose by roughly the
per-hop delay. Its callers rose by a multiple of it, because a single page render makes
several catalog lookups and each one pays the delay separately. The service with the
largest absolute latency was the one making the most calls to the slow thing — not the
slow thing. That is why it crossed the threshold last.

**What changed on productcatalogservice.** Nothing. No deploy, no image change, no
environment difference, no configuration edit. The dead end that cost the most time,
because "what changed" is the first question and the answer was empty.

**Running containers.** A container was attached to product catalog's network namespace
that no service definition creates. It was applying traffic shaping to the interface.
The change sat one level below anything a service specification describes, which is why
inspecting the service found nothing.

### Root cause

An unauthorized container was shaping productcatalogservice's egress traffic, adding
300ms of delay per packet leaving the container. The service's own code, image and
configuration were untouched.

### Resolution

Recreating the container cleared the shaping — the rule binds to the container
instance, so a replacement comes up on a clean network path. Everything was quiet 2m32s
later, which is the metric window emptying rather than a gradual recovery.

Class of fix: **restart**. Nothing was deployed and no configuration was wrong, so
there was nothing to roll back or revert.

### Detection notes

- Onset to first page: **3m49s**, against a three-minute persistence clause. Detection
  is dominated by the clause.
- Services alerting at the page: **4**. Over the whole incident: **5**. The blast radius
  never grew.
- Alerts that fired only during recovery: **none**.
- **The culprit alerted last**, a full minute after the page and after all four of its
  own callers. A slow service does report its own latency, but it reports the smallest
  number in the incident, so it crosses the threshold last and looks least urgent. The
  gap is wide enough that a responder triaging on arrival order would have spent a
  minute with the culprit entirely absent from the incident.
- Did the loudest service turn out to be the culprit? **No** — and the reason
  generalises. Latency accumulates upward through fan-out: a caller that makes N calls
  to a slow dependency is N times slower than the dependency is. **Rank by position in
  the call graph, not by magnitude.**
- The clearing order said nothing useful here. The culprit cleared fourth of five, ahead
  of the edge services and behind checkout — a spread of forty-five seconds with no
  structure to it. Recovery ordering is dominated by how full each service's rolling
  window happened to be, and reading causation into it would have been guessing.
- The signal that mattered was **persistence**, and after that, the **shape of the
  affected set**: one leaf and its callers, with nothing beside them touched.

---

Rendered from [`evals/scenarios/artifacts/holdout/productcatalog-dependency-latency/`](../../evals/scenarios/artifacts/holdout/productcatalog-dependency-latency/) by `faultline-render`. [All bundles](README.md).
