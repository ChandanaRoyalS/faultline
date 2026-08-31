# The bundles, rendered

Every recorded rehearsal in this repository as a readable page — 15 in all: **13 runnable** (10 dev, 3 holdout) and **2 that could not fire** (2 dev).

A bundle is what one rehearsal left behind — the manifest, the Prometheus captures,
a slice of one service's logs, the exact queries, and the narrative a responder wrote
afterwards without being told what had been done to the world. These pages are
generated from those files by `faultline-render` and are byte-reproducible: the same
bundle renders to the same page.

**On the holdout pages.** They are here to be read by people, and that is not a
contamination event. [ADR-0008](../adr/0008-contamination-model.md)'s quarantine
is about two things: the holdout scenarios never enter a retrieval corpus, and no
agent is run against them outside a pre-registered holdout entry. Neither is affected
by a human reading a narrative that has been committed to this repository since it was
recorded. What would break the quarantine is seeding these into the store or pointing
the agent at them — and both are refused structurally, not by convention.

## Dev split

Where prompts and retrieval were fitted. Results on these scenarios are **not a
benchmark** — see [RESULTS.md](../RESULTS.md).

| scenario | fault class | what happened |
|---|---|---|
| [`ad-memory-squeeze`](ad-memory-squeeze.md) | `resource_exhaustion` | Ad service memory limit cut below the working set its JVM was sized for — 3 alerts over the window |
| [`cart-bad-image-tag`](cart-bad-image-tag.md) | `bad_deploy` | Cart service deployed on an image tag that was never published — 12 alerts over the window |
| [`cart-dependency-latency`](cart-dependency-latency.md) | `dependency_latency` | Cart service network path acquires 300ms of delay — 4 alerts over the window |
| [`cart-redis-misconfig`](cart-redis-misconfig.md) | `bad_config` | Cart service pointed at the wrong Redis port — 10 alerts over the window |
| [`currency-cpu-throttle`](currency-cpu-throttle.md) | `resource_exhaustion` | **⚠ nothing fired** — the fault could not bind |
| [`flag-service-crashloop`](flag-service-crashloop.md) | `bad_deploy` | **⚠ nothing fired** — the fault could not bind |
| [`frauddetection-memory-squeeze`](frauddetection-memory-squeeze.md) | `resource_exhaustion` | Fraud detection service memory limit cut below its working set — 1 alerts over the window |
| [`payment-telemetry-blackout`](payment-telemetry-blackout.md) | `bad_config` | Payment service healthy, serving, and invisible in the traffic metric — 1 alerts over the window |
| [`product-catalog-flag-failure`](product-catalog-flag-failure.md) | `bad_config` | A feature flag turned on at the flag service makes product catalog fail one product — 4 alerts over the window |
| [`redis-cart-dependency-latency`](redis-cart-dependency-latency.md) | `dependency_latency` | Cart is slow because its datastore is, and the datastore has no spans — 4 alerts over the window |
| [`shipping-quote-misconfig`](shipping-quote-misconfig.md) | `bad_config` | Checkout failed a quarter of its orders, and the service at fault reported nothing — 7 alerts over the window |
| [`shipping-wrong-image`](shipping-wrong-image.md) | `bad_deploy` | Shipping service deployed with another service's image — 8 alerts over the window |

## Holdout split

Never fitted against, never in any retrieval corpus, and run only under a
pre-registered entry.

| scenario | fault class | what happened |
|---|---|---|
| [`email-wrong-image`](email-wrong-image.md) | `bad_deploy` | Email service deployed with another service's image — 2 alerts over the window |
| [`productcatalog-dependency-latency`](productcatalog-dependency-latency.md) | `dependency_latency` | Product catalog network path acquires 300ms of delay, slowing every caller — 5 alerts over the window |
| [`recommendation-memory-squeeze`](recommendation-memory-squeeze.md) | `resource_exhaustion` | Recommendation service memory limit cut below what its runtime needs to start — 3 alerts over the window |

---

Regenerate with `faultline-render --all`. No model calls and no live services.
