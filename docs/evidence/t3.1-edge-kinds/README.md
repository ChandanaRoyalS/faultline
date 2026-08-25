# T3.1 pre-work — edge kinds, measured from the recorded bundles

ADR-0017 deferred one question to T3.1 and T3.1 is blocked on it: for each edge in the
dependency graph, does the callee's failure reach the caller? The graph cannot say. It records
**call causality, not failure propagation** — an edge says A's work reaches B, never that A
waits for B — and the two behave in opposite ways under failure, which the catalog had already
measured.

Answered here for all fifteen edges: **9 synchronous, 1 asynchronous, 5 unmeasured.**

## The preferred source does not exist

ADR-0017 preferred `span.kind` — `CLIENT`/`SERVER` pairs versus `PRODUCER`/`CONSUMER` pairs —
and expected to read it from trace data in the recorded bundles.

**The bundles contain no trace data at all.** A bundle is:

```
manifest.json  incident.md  queries.md
metrics/{error-ratio, call-rate, latency-p95, alerts-firing, runtime}.json
logs/<container>.txt
superseded/
```

ADR-0009 never put traces in a bundle. The metric captures *are* span-derived — `calls_total`
and `latency_bucket` come from the collector's spanmetrics processor — but `queries.md` shows
every one of them aggregated `sum by(service_name)`, so `span.kind` was dropped at query time
and is not recoverable from the capture. There is no `span.kind`, `PRODUCER` or `CONSUMER`
string anywhere under `evals/scenarios/artifacts/`.

So this is measured a different way, and the difference is worth stating rather than glossing:

| | `span.kind` | what the bundles hold |
|---|---|---|
| measures | the messaging pattern | **failure propagation itself** |
| covers | every edge with traffic | only edges whose callee some bundle broke |
| relation to the question | a proxy | the property directly |

`span.kind` is a proxy for the property blast radius needs; the bundles contain ten incidents
in which a named service was broken on purpose, which is the property itself. So where evidence
exists it is **stronger** than the preferred source, and where it does not exist there is
nothing — which is why five edges are `unmeasured` rather than inferred.

## Method

For each of the ten valid bundles: take `t_inject` and `t_revert` from the manifest, and
compare each service's **error ratio** and **p95 latency** in the pre-fault part of the window
against the fault window.

- **Failure test.** The callee is broken and the caller's error ratio rises → the caller was
  waiting on it → **sync**. The callee is broken and the caller's error ratio does not move →
  **async**.
- **Latency test.** The callee is slowed (the two `dependency_latency` faults) and the caller's
  p95 rises with it → the caller was blocked on it → **sync**. A caller that does not wait
  cannot be slowed by a slow callee.

Both tests answer the same question and neither can produce a false `async`: an edge only
reads async when the callee was *demonstrably dead* — throughput at or near zero for the whole
fault — and the caller kept serving.

## The fifteen edges

| Edge | Kind | Evidence | Bundle |
|---|---|---|---|
| `frontend → cartservice` | **sync** | caller err 0 → 0.27; p95 43.5× | `cart-redis-misconfig`, `cart-dependency-latency` |
| `checkoutservice → cartservice` | **sync** | caller err 0 → 0.54; p95 66.9× | `cart-redis-misconfig`, `cart-dependency-latency` |
| `frontend → adservice` | **sync** | caller err 0 → 0.069 | `ad-memory-squeeze` |
| `frontend → recommendationservice` | **sync** | caller err 0.013 → 0.077 | `recommendation-memory-squeeze` |
| `checkoutservice → shippingservice` | **sync** | caller err 0 → 0.227 | `shipping-wrong-image` |
| `checkoutservice → emailservice` | **sync** | caller err 0 → 0.061 | `email-wrong-image` |
| `frontend → productcatalogservice` | **sync** | caller p95 43.1 → 1191.5ms (27.7×) | `productcatalog-dependency-latency` |
| `checkoutservice → productcatalogservice` | **sync** | caller p95 42.7 → 1482.5ms (34.7×) | `productcatalog-dependency-latency` |
| `recommendationservice → productcatalogservice` | **sync** | caller p95 3.9 → 360.6ms (91.9×) | `productcatalog-dependency-latency` |
| `checkoutservice → frauddetectionservice` | **async** | callee 0.196 → 0.014 req/s; caller err 0 → 0 | `frauddetection-memory-squeeze` |
| `checkoutservice → currencyservice` | *unmeasured* | `currency-cpu-throttle` is the only fault on it and is **INVALID** — it produced no measurable effect (ADR-0013) | — |
| `checkoutservice → accountingservice` | *unmeasured* | no bundle breaks `accountingservice` | — |
| `checkoutservice → paymentservice` | *unmeasured* | no bundle breaks `paymentservice` | — |
| `frontend → checkoutservice` | *unmeasured* | no bundle breaks `checkoutservice` | — |
| `shippingservice → quoteservice` | *unmeasured* | no bundle breaks `quoteservice` | — |

## Both cross-checks reproduce

**`email-wrong-image` — sync.** `emailservice` collapsed from 0.408 to 0.093 req/s and
`checkoutservice`'s error ratio went from 0 to **0.061**. The incident's only alert was
`ServiceHighErrorRate` on `checkoutservice` — a *healthy* service paging because the broken one
could not. Checkout was waiting on email.

**`frauddetection-memory-squeeze` — async.** `frauddetectionservice` went from 0.196 to
**0.014** req/s and stayed there for the full 852-second fault. `checkoutservice`'s error ratio
was **0 before and 0 during**, and its throughput held at 1.73 → 1.63 req/s. Orders completed
normally and were not screened — which is what that bundle's narrative says in prose: "the work
was not failing — it was accumulating unprocessed".

Two edges out of one service, identical in the graph — same parent, both at 286 calls in the
snapshot — and opposite here. That is the finding ADR-0017 recorded qualitatively, now with
numbers on both sides.

## One classification worth flagging

`frontend → recommendationservice` reads **sync**, and `recommendation-memory-squeeze`'s
narrative opens with "frontend does not fail when recommendations fail". Both are right: the
frontend degrades rather than erroring outright, and it *does* error — 0.013 → 0.077, enough
that `ServiceHighErrorRate` fired on `frontend` and `loadgenerator`. Partial propagation is
still propagation, and for blast radius the caller belongs in the radius. The narrative's point
is about *detection latency*, not about whether the edge blocks.

## What the numbers do not support

**A modest latency rise appears on services that are not callers.** In both `dependency_latency`
bundles, `quoteservice` (5.3–5.5×) and `shippingservice` (2.7–2.9×) rose while sitting
*downstream* of the slowed path. Neither is a caller of the slowed service, so this is not edge
evidence — most likely contention on an emulated host. Recorded so nobody reads it as one.

**Nothing here measures the two Kafka consumers as a pair.** `accountingservice` shares the
consumer group with `frauddetectionservice` (`CATALOG.md`, the kafka-cycling note names both),
so `checkoutservice → accountingservice` is *probably* async by the same mechanism. It stays
**unmeasured**: probably-async on a structural argument is exactly the inference this exercise
exists to avoid making.

## Where it lands

`src/faultline/context/graph.py` — `EdgeKind` and `EDGE_KINDS`, with `kind` on every `Edge`.
An edge absent from the table is `UNMEASURED`, never defaulted to `SYNC`.

**No policy behaviour changed.** `DependencyPolicy` still correlates on call causality and
still joins `emailservice` at two hops; a test pins that. Using edge kinds is T3.1's, and this
is the data it was blocked on.

Anything reporting blast radius should quote the **five unmeasured edges** — a third of the
graph — the way every other figure in this project carries its `n`.

## Reproducing

No live services. Every number above comes from `metrics/error-ratio.json` and
`metrics/latency-p95.json` in the committed bundles, compared across `t_inject`/`t_revert` from
each `manifest.json`.
