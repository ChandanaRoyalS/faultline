# ⚠ NO ALERT FIRED — AND NONE COULD HAVE

The fault was injected and reverted normally. `alerts_at_fire` is empty,
`alerts_over_window` is empty, `seconds_to_alert` is null. Nothing fired anywhere in the
world for the whole twelve minutes.

## Verified cause: featureflagservice emits no span metrics

Queried against Prometheus directly:

```promql
count by (service_name) (calls_total)      # -> 15 services
count by (service_name) (latency_bucket)   # -> the same 15
```

| | |
|---|---|
| services with `calls_total` | accountingservice, adservice, cartservice, checkoutservice, currencyservice, emailservice, frauddetectionservice, frontend, frontend-proxy, loadgenerator, paymentservice, productcatalogservice, quoteservice, recommendationservice, shippingservice |
| `featureflagservice` among them | **no** |
| `calls_total{service_name="featureflagservice"}` | no series |
| `calls_total{service_name=~".*flag.*"}` | no series |
| `latency_bucket{service_name=~".*flag.*"}` | no series |

Two of the three alert rules are scoped by `service_name` over `calls_total`:

- `ServiceNoTraffic` — `rate(calls_total[3m]) == 0 and rate(calls_total[30m] offset 10m) > 0`
- `ServiceHighErrorRate` — a ratio of `calls_total` by `status_code`

**With no `calls_total` series, neither can evaluate for this service under any
conditions.** Not "did not fire this time" — cannot fire, ever. A crash-looping flag
service is invisible to both rules by construction.

`ServiceHighLatency` reads `latency_bucket`, which is equally absent.

## Why the series does not exist

The flag service running here is `faultline/ffs-stub` (ADR-0006), which replaced the
demo's Elixir service because it segfaults under emulation. The stub is a plain gRPC
server: `grep -c "otel\|opentelemetry\|trace"` over `compose/ffs-stub/server.py` and
`server_crash.py` returns **0** in both. It has no OpenTelemetry instrumentation, so it
emits no spans, so the collector generates no span metrics for it.

This is a consequence of the ADR-0006 stub decision that was not noticed at the time. The
stub reproduces the flag service's gRPC *contract* faithfully; it does not reproduce its
*observability*.

## Callers did not surface it either

The fault was a crash loop, so callers should have seen intermittent connection failures.
No alert fired on any of the 15 instrumented services during the window. Whatever the
callers experienced, it stayed below `ServiceHighErrorRate`'s 5%-for-2m threshold.

## What this implies for the catalog — recorded, not acted on

Three scenarios target `featureflagservice`:

| Slot | Scenario | Split | Observable |
|---|---|---|---|
| `bad_deploy-2` | `flag-service-bad-deploy` | **holdout** | the flag service and its callers |
| `bad_deploy-3` | `flag-service-crashloop` | dev | the flag service |
| `bad_config-2` | `product-catalog-flag-failure` | dev | productcatalogservice |

The first two look directly at a service that emits no metrics. Whether they are viable
depends on whether their callers surface the failure loudly enough to alert — which this
rehearsal suggests they may not, but one rehearsal of one of them is not evidence about
the other.

The third **may be unaffected**, because its observable is a different service:
`productcatalogservice` does have span metrics (4 `calls_total` series). That establishes
alerts are *possible* there. It does **not** establish that the flag-driven failure
produces enough of them to fire — that scenario is unrehearsed, and nothing here tests it.

**No decision is being made.** The scenario is not marked BLOCKED, `SPLIT.md` is untouched,
and no replacement is proposed. Which of these three survive, and what fills any slot that
does not, is a catalog design decision being deferred deliberately.
