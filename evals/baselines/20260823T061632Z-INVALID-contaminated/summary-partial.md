# Partial baseline — quiet spans only

Re-derived from the captured JSON in this directory, over **29 minutes** in
two spans:

| Span | Covers |
|---|---|
| A | 06:16:32Z – 06:36:00Z |
| B | 06:52:00Z – 07:01:32Z |

**Excluded: 06:36:00Z – 06:52:00Z.** A `cart-redis-misconfig` rehearsal ran
06:38:03Z–06:48:50Z. The exclusion is padded by ~2 minutes on each side because the
alert rules read `rate(...[2m])`, so samples adjacent to the fault still carry its
traffic inside their own window. See INVALID.md.

This is a partial baseline and says so. It is not a substitute for a clean 45-minute
run; it is what could honestly be recovered from a contaminated one.

## Error ratio (alert threshold 5%)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `loadgenerator` | 0.03% | 0.00% | 0.33% | 0.32% | 0.0 |
| `frontend` | 0.02% | 0.00% | 0.36% | 0.00% | 0.0 |
| `checkoutservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `emailservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `productcatalogservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |
| `recommendationservice` | 0.00% | 0.00% | 0.00% | 0.00% | 0.0 |

## p95 latency (alert threshold 250ms)

| Service | mean | min | max | p95 | min over threshold |
|---|---:|---:|---:|---:|---:|
| `loadgenerator` | 50ms | 47ms | 93ms | 68ms | 0.0 |
| `checkoutservice` | 47ms | 36ms | 1060ms | 48ms | 0.2 |
| `frontend` | 43ms | 41ms | 53ms | 49ms | 0.0 |
| `cartservice` | 22ms | 2ms | 353ms | 337ms | 1.8 |
| `shippingservice` | 13ms | 10ms | 36ms | 30ms | 0.0 |
| `quoteservice` | 8ms | 7ms | 10ms | 9ms | 0.0 |
| `recommendationservice` | 4ms | 4ms | 6ms | 5ms | 0.0 |
| `paymentservice` | 2ms | 2ms | 5ms | 3ms | 0.0 |
| `productcatalogservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `emailservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `adservice` | 2ms | 2ms | 3ms | 2ms | 0.0 |
| `accountingservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `currencyservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
| `frauddetectionservice` | 2ms | 2ms | 2ms | 2ms | 0.0 |
