# The bundles, rendered

Every recorded rehearsal in this repository as a readable page — 44 in all: **40 runnable** (30 dev, 10 holdout) and **4 that could not fire** (4 dev).

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
| [`ad-memory-squeeze`](ad-memory-squeeze.md) | `resource_exhaustion` | Ad service memory limit cut below the working set its JVM was sized for — 5 alerts over the window |
| [`cart-bad-image-tag`](cart-bad-image-tag.md) | `bad_deploy` | Cart service deployed on an image tag that was never published — 11 alerts over the window |
| [`cart-dependency-latency`](cart-dependency-latency.md) | `dependency_latency` | Cart service network path acquires 300ms of delay — 4 alerts over the window |
| [`cart-redis-misconfig`](cart-redis-misconfig.md) | `bad_config` | Cart service pointed at the wrong Redis port — 11 alerts over the window |
| [`currency-cpu-throttle`](currency-cpu-throttle.md) | `resource_exhaustion` | **⚠ nothing fired** — the fault could not bind |
| [`flag-service-crashloop`](flag-service-crashloop.md) | `bad_deploy` | **⚠ nothing fired** — the fault could not bind |
| [`frauddetection-memory-squeeze`](frauddetection-memory-squeeze.md) | `resource_exhaustion` | Fraud detection service memory limit cut below its working set — 1 alerts over the window |
| [`payment-telemetry-blackout`](payment-telemetry-blackout.md) | `bad_config` | Payment service healthy, serving, and invisible in the traffic metric — 1 alerts over the window |
| [`product-catalog-flag-failure`](product-catalog-flag-failure.md) | `bad_config` | A feature flag turned on at the flag service makes product catalog fail one product — 3 alerts over the window |
| [`redis-cart-dependency-latency`](redis-cart-dependency-latency.md) | `dependency_latency` | Cart is slow because its datastore is, and the datastore has no spans — 4 alerts over the window |
| [`shipping-quote-misconfig`](shipping-quote-misconfig.md) | `bad_config` | Checkout failed a quarter of its orders, and the service at fault reported nothing — 5 alerts over the window |
| [`shipping-wrong-image`](shipping-wrong-image.md) | `bad_deploy` | Shipping service deployed with another service's image — 8 alerts over the window |
| [`v2-accounting-bad-credential`](v2-accounting-bad-credential.md) | `bad_config` | Accounting's database password rotated to one the database does not accept — 1 alerts over the window |
| [`v2-ad-bad-image-tag`](v2-ad-bad-image-tag.md) | `bad_deploy` | Ad deployed on an image tag that was never published — 4 alerts over the window |
| [`v2-ad-flag-failure`](v2-ad-flag-failure.md) | `feature_flag` | A feature flag makes the ad service fail one request in ten — 1 alerts over the window |
| [`v2-ad-memory-squeeze`](v2-ad-memory-squeeze.md) | `resource_exhaustion` | Ad service memory limit cut below what its JVM needs to run — 3 alerts over the window |
| [`v2-cart-bad-image-tag`](v2-cart-bad-image-tag.md) | `bad_deploy` | Cart deployed on an image tag that was never published — 14 alerts over the window |
| [`v2-cart-dependency-latency`](v2-cart-dependency-latency.md) | `dependency_latency` | Cart service network path acquires 300ms of delay — 5 alerts over the window |
| [`v2-cart-flag-failure`](v2-cart-flag-failure.md) | `feature_flag` | A feature flag makes the cart fail to empty after an order — 1 alerts over the window |
| [`v2-cart-freeze`](v2-cart-freeze.md) | `process_freeze` | The cart process is frozen - its socket accepts and nothing answers — 16 alerts over the window |
| [`v2-cart-memory-squeeze`](v2-cart-memory-squeeze.md) | `resource_exhaustion` | **⚠ nothing fired** — the fault could not bind |
| [`v2-cart-valkey-misconfig`](v2-cart-valkey-misconfig.md) | `bad_config` | **⚠ nothing fired** — the fault could not bind |
| [`v2-currency-freeze`](v2-currency-freeze.md) | `process_freeze` | The currency process is frozen - its socket accepts and nothing answers — 9 alerts over the window |
| [`v2-fraud-detection-flag-queue-lag`](v2-fraud-detection-flag-queue-lag.md) | `feature_flag` | A feature flag floods the orders queue, slows its consumer and breaks accounting — 1 alerts over the window |
| [`v2-fraud-detection-memory-squeeze`](v2-fraud-detection-memory-squeeze.md) | `resource_exhaustion` | Fraud detection memory limit cut below what its JVM needs to run — 1 alerts over the window |
| [`v2-frontend-cart-misconfig`](v2-frontend-cart-misconfig.md) | `bad_config` | Frontend pointed at a cart port where nothing listens — 12 alerts over the window |
| [`v2-payment-dependency-latency`](v2-payment-dependency-latency.md) | `dependency_latency` | Payment's replies are late, and only checkout can tell — 1 alerts over the window |
| [`v2-payment-memory-squeeze`](v2-payment-memory-squeeze.md) | `resource_exhaustion` | Payment service memory limit cut to what its runtime can barely run in — 1 alerts over the window |
| [`v2-payment-telemetry-blackout`](v2-payment-telemetry-blackout.md) | `bad_config` | Payment service healthy, serving, and invisible in the traffic metric — 1 alerts over the window |
| [`v2-product-catalog-flag-failure`](v2-product-catalog-flag-failure.md) | `feature_flag` | A feature flag makes the product catalog fail one product — 2 alerts over the window |
| [`v2-product-catalog-freeze`](v2-product-catalog-freeze.md) | `process_freeze` | The product catalog process is frozen - its socket accepts and nothing answers — 20 alerts over the window |
| [`v2-shipping-quote-misconfig`](v2-shipping-quote-misconfig.md) | `bad_config` | Shipping service pointed at a quote service that does not resolve — 9 alerts over the window |
| [`v2-shipping-wrong-image`](v2-shipping-wrong-image.md) | `bad_deploy` | Shipping deployed with another service's image — 8 alerts over the window |
| [`v2-valkey-cart-dependency-latency`](v2-valkey-cart-dependency-latency.md) | `dependency_latency` | Cart is slow because its store is, and the store has no spans — 5 alerts over the window |

## Holdout split

Never fitted against, never in any retrieval corpus, and run only under a
pre-registered entry.

| scenario | fault class | what happened |
|---|---|---|
| [`email-wrong-image`](email-wrong-image.md) | `bad_deploy` | Email service deployed with another service's image — 2 alerts over the window |
| [`productcatalog-dependency-latency`](productcatalog-dependency-latency.md) | `dependency_latency` | Product catalog network path acquires 300ms of delay, slowing every caller — 5 alerts over the window |
| [`recommendation-memory-squeeze`](recommendation-memory-squeeze.md) | `resource_exhaustion` | Recommendation service memory limit cut below what its runtime needs to start — 3 alerts over the window |
| [`v2-accounting-kafka-misconfig`](v2-accounting-kafka-misconfig.md) | `bad_config` | Accounting pointed at a Kafka port where nothing listens — 1 alerts over the window |
| [`v2-checkout-currency-misconfig`](v2-checkout-currency-misconfig.md) | `bad_config` | Checkout pointed at a currency host that does not exist — 12 alerts over the window |
| [`v2-email-flag-memory-leak`](v2-email-flag-memory-leak.md) | `feature_flag` | A feature flag makes the email service keep every confirmation it sends — 2 alerts over the window |
| [`v2-email-wrong-image`](v2-email-wrong-image.md) | `bad_deploy` | Email deployed with another service's image — 2 alerts over the window |
| [`v2-payment-flag-unreachable`](v2-payment-flag-unreachable.md) | `feature_flag` | A feature flag makes checkout charge cards at an address that does not exist — 7 alerts over the window |
| [`v2-product-catalog-dependency-latency`](v2-product-catalog-dependency-latency.md) | `dependency_latency` | The product catalog's network path acquires 300ms of delay, and every page slows — 6 alerts over the window |
| [`v2-recommendation-memory-squeeze`](v2-recommendation-memory-squeeze.md) | `resource_exhaustion` | Recommendation service memory limit cut below what its interpreter needs to start — 3 alerts over the window |

---

Regenerate with `faultline-render --all`. No model calls and no live services.
