# A feature flag makes the product catalog fail one product

## The scenario

| | |
|---|---|
| scenario | `v2-product-catalog-flag-failure` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `product-catalog` via `v2-product-catalog-flag-failure` |
| time to page | 5m31s |
| steady state captured | 300s |
| capture window | 2026-09-27T04:35:26+00:00 → 2026-09-27T04:55:57+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+5m31s |
| `t_revert` | T+10m31s |
| all clear | T+13m31s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+5m15s | `frontend` | ServiceHighErrorRate | 7.0 min | **paged** |
| T+5m15s | `frontend-proxy` | ServiceHighErrorRate | 8.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="product-catalog"}` |

`logs/product-catalog.txt` — 9 lines.

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

The page was two alerts in the same moment, `ServiceHighErrorRate` on **frontend** and on
**frontend-proxy**, 5m31s after the trouble started. Nothing else fired, then or later, and nothing
fired after the fix.

Both error ratios had been zero. They rose from about two minutes in and held between about 6.5%
and 9% for frontend, and 7% and 10% for frontend-proxy. Load-generator, the synthetic shoppers, saw
about 4-5% of its requests fail. Nothing got slower: no latency alert fired, the catalog's and the
frontend's p95 did not move, and request rates stayed within their usual swing. The storefront
worked for most pages and most orders. Some failed quickly, over and over.

### What was checked

**The page names the edge, not a cause.** Frontend-proxy only forwards what frontend returns, and
frontend is the application the shoppers talk to. Both were reporting failures from somewhere
below them.

**The frontend's log, which named the cause in its own words.** From the first minute of the
trouble, the frontend logged `Error: 13 INTERNAL: Error: Product Catalog Fail Feature Flag
Enabled`, and it kept logging it until the fix: 272 lines naming it over about eleven minutes, 12
to 40 a minute (the log gives each error two lines), with none in the five minutes before and none
in the five after. Now and then beside it, checkout's error for an order came up the same way:
`failed to prepare order: failed to get product #"OLJCESPC7Z"`, 34 lines in all, up to 8 a minute.
Both stopped with the fix.

**The traces, to see who said it.** The failing traces ended at the product catalog: 153 of them
touched it over the ten minutes, from recommendation pages, product pages, cart additions and
orders. `frontend/grpc.oteldemo.ProductCatalogService/GetProduct` errored, and beneath it the
catalog's own `GetProduct` span was in error with the status message `Error: Product Catalog Fail
Feature Flag Enabled`, usually in no measurable time and with no database query beneath it. In the
same traces the other `GetProduct` calls succeeded: a recommendations page that looked up four
products failed on one of them and got the other three back normally, each with its database query
beneath it. One failing lookup failed the whole page. Checkout's failed orders had the same shape:
the cart read worked, a first product lookup and its currency conversion went through, and then the
catalog refused the next lookup with the same message.

**Whether the catalog was broken or struggling.** It was not. Its error ratio rose only to between
about 4% and 5%, because one product failing is a small share of everything it serves: every
product list and every other product lookup counts too. It crossed the 5% line twice, for about a
minute each time, never for the two minutes the alert waits, so the service with the failing span
never paged. Its latency held at about 5ms, its request rate did not move, and its Go runtime
series, 9 of them, reported without a gap. It writes no log the tools can read, so its own log is
not available. A catalog that was down or overloaded would have failed everything, or slowed. This
one answered almost everything normally and refused one lookup, fast, every time.

**The frontend's amplification.** One failing product is under 5% of the catalog's work but nearly
twice that at the frontend, because a page asks for several products and fails if any one fails.
That is why the alert landed a hop above the service that failed.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart, on the catalog or anywhere else. The error message is the change record here. It says a
feature flag is enabled, and a flag's value lives in the flag service, whose changes leave no
record.

### Root cause

The `productCatalogFailure` feature flag was turned on in the flag service. The product catalog
checks it on every lookup of one product, OLJCESPC7Z, and refuses that product while it is on. Every
page and order that includes that product failed, fast, and every other product was served
normally. Nothing was deployed or reconfigured, and the catalog behaved exactly as it is written
to. The fault was the flag's value.

### Resolution

The flag was turned back off. The flag service picks up the change on its own, so nothing was
restarted or redeployed. The refusals stopped at once, and the error ratios drained with their
five-minute windows. Everything was quiet 3m00s after the fix, and nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back. Rolling back or
restarting the catalog would have changed nothing: it was doing what the flag told it to.

### Detection notes

- Onset to first page: **5m31s**. Services on the page: **two**, neither of them the one with the
  failing span. By the fix: **two**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** Frontend-proxy and frontend paged; the
  catalog, where the failure happens, touched the line twice but never held above it long enough
  to page.
- Would the page alone have led you to the right service? **No.** It names the edge. The frontend's
  log names the catalog's error and the flag from the first minute, and the traces put it on the
  catalog's own span.
- **A partial, steady error ratio with unchanged latency is a branch, not a breakdown.** A service
  that is overloaded or broken fails broadly and slows. One that refuses a specific input fails the
  same small share, fast, for as long as the condition holds.
- **One failure per page is amplified by every caller that fans out.** The same fault read 4-5% at
  the catalog and 7-9% at the frontend. The service with the highest error ratio is not necessarily
  the one failing.
- **An empty change history is not "nothing changed".** Feature flags change behaviour without a
  deploy and without a change record. When the error text names a flag, the flag's value is the
  change to look for.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-product-catalog-flag-failure/`](../../evals/scenarios/artifacts/dev/v2-product-catalog-flag-failure/) by `faultline-render`. [All bundles](README.md).
