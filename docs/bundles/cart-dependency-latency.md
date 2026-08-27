# Cart service network path acquires 300ms of delay

## The scenario

| | |
|---|---|
| scenario | `cart-dependency-latency` |
| fault class | **`dependency_latency`** |
| expected remediation | `restart` |
| split | `dev` |
| injected at | `cart-service` via `cart-dependency-latency` |
| time to page | 3m45s |
| steady state captured | 300s |
| capture window | 2026-08-23T15:11:15+00:00 → 2026-08-23T15:29:16+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m45s |
| `t_revert` | T+8m45s |
| all clear | T+11m01s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m45s | `cartservice` | ServiceHighLatency | 7.2 min | **paged** |
| T+3m45s | `checkoutservice` | ServiceHighLatency | 7.0 min | **paged** |
| T+3m45s | `frontend` | ServiceHighLatency | 7.0 min | **paged** |
| T+3m45s | `loadgenerator` | ServiceHighLatency | 7.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |

`logs/cart-service.txt` — 506 lines.

## A look at the logs

From `logs/cart-service.txt` (500 lines):

```
2026-08-23T15:11:16+00:00  AddItemAsync called with userId=e2e1c9a8-9f04-11f1-a06c-5acf6c7804bd, productId=OLJCESPC7Z, quantity=4
2026-08-23T15:11:16+00:00  GetCartAsync called with userId=e2e1c9a8-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:16+00:00  GetCartAsync called with userId=e2e1c9a8-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:16+00:00  EmptyCartAsync called with userId=e2e1c9a8-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:16+00:00  AddItemAsync called with userId=e2f9092e-9f04-11f1-a06c-5acf6c7804bd, productId=1YMWWN1N4O, quantity=2
2026-08-23T15:11:16+00:00  GetCartAsync called with userId=e2f9092e-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:16+00:00  GetCartAsync called with userId=e2f9092e-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:16+00:00  EmptyCartAsync called with userId=e2f9092e-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:16+00:00  AddItemAsync called with userId=e36f72d0-9f04-11f1-a06c-5acf6c7804bd, productId=0PUK6V6EV0, quantity=1
2026-08-23T15:11:16+00:00  GetCartAsync called with userId=e36f72d0-9f04-11f1-a06c-5acf6c7804bd
2026-08-23T15:11:19+00:00  GetCartAsync called with userId=
2026-08-23T15:11:19+00:00  AddItemAsync called with userId=e4e31a22-9f04-11f1-a06c-5acf6c7804bd, productId=66VCHSJNUP, quantity=1
```

_488 further lines are in the bundle._

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

Four `ServiceHighLatency` alerts fired in the same evaluation: **cartservice**,
**checkoutservice**, **frontend** and **loadgenerator**. The page arrived 3m45s after
things started slowing.

No errors. Not one. Every request succeeded; they simply took longer. The storefront
worked end to end — adding to a basket returned normally, just sluggishly.

cart's p95 sat around 650ms for the duration. Its callers were elevated in proportion
to how much of their work went through cart.

### What was checked

**Whether the reading was real.** cartservice runs at 2ms. Not approximately 2ms —
across forty-five minutes of measured quiet operation its minimum, mean and maximum are
all 2ms, and it has never been observed above 3ms on an undisturbed system. A reading of
650ms is not an excursion on this service; it is three hundred times its entire
operating range. There was nothing ambiguous to weigh.

**Whether anything had restarted recently.** This is the one check that could have made
the reading meaningless, and it is worth doing first. cartservice takes about four
minutes to settle after being recreated, decaying monotonically from around 100ms back
to 2ms. A p95 sampled inside that window looks alarming and means nothing. Nothing had
been deployed or restarted, and the elevation was flat at 650ms rather than decaying, so
this was not a warm-up.

**The error dashboards.** Clean throughout, which is misleading in both directions. It
argues against a serious problem, and it rules out most of the usual causes at once —
nothing is failing, timing out, or retrying.

**Direction of propagation.** frontend, checkout and cart all slowed together, but
frontend calls checkout and checkout calls cart. The leaf of that chain is where the
time is being spent; the other two are waiting on it. That narrowed the search to cart
within a couple of minutes.

**What changed on cartservice.** Nothing. No deploy, no image change, no environment
difference, no config edit. Its container specification was byte-identical to the
previous day's. This is the dead end that cost the most time, because "what changed" is
the first question and it returned an empty answer.

**Running containers.** A container was attached to cart's network namespace that is
not part of any service definition — nothing in the compose files creates it. It was
applying traffic shaping to cart's interface. The change was at the network layer, one
level below anything a service specification describes, which is why looking at cart's
own configuration found nothing.

### Root cause

An unauthorized container was shaping cartservice's egress traffic, adding 300ms of
delay per packet leaving the container. Cart's own code, image and configuration were
untouched.

The observed p95 was roughly double the added per-hop delay, because a cart operation
makes two round trips to Redis and each pays the delay separately. Anyone expecting the
p95 to rise by exactly 300ms would have doubted a correct measurement.

### Resolution

Recreating the cart container cleared the shaping — the rule is bound to the container
instance, so a new one comes up on a clean network path. Everything was quiet 2m16s
later.

Class of fix: **restart**. Nothing was deployed and no configuration was wrong, so
there was nothing to roll back or revert; the container simply needed replacing.

### Detection notes

- Onset to first page: **3m45s**, against a three-minute persistence clause. Detection
  is dominated by the clause, not by how long the signal took to appear — the underlying
  measurement crossed the threshold almost immediately.
- Services alerting at the page: **4**. Over the whole incident: **4**. The blast radius
  never grew, and all four alerts began in the same evaluation.
- Alerts that fired only during recovery: **none**.
- **The culprit was named in the page**, unlike a fault that removes a service entirely
  — a slow service still reports its own latency, so it appears in its own alert.
- Did the loudest service turn out to be the culprit? **Yes**, and that is worth noting
  precisely because it is unusual. Latency propagates upward through callers, so the
  slowest service in the chain is the source.
- **Detection was never the hard part; attribution was.** On a service whose entire
  operating range is 2ms, the alert is unambiguous the moment it fires. What cost time
  was that the change had been made below the level any service specification describes,
  so every question about cart itself came back clean.
- **A latency reading taken shortly after a restart is not a baseline reading.** cart
  decays from about 100ms to 2ms over roughly four minutes after being recreated. Any
  comparison against "normal" must exclude that window, and a responder who samples
  inside it will conclude the service is far noisier than it is.
- On clearing order: cart's alert cleared about fifteen seconds after its callers' did.
  That is an observation about this incident and not a rule — clearing order is
  dominated by how full each service's rolling window happens to be when the fault
  stops, which has more to do with traffic rate than with causation. Do not read
  causation into what cleared when.

---

Rendered from [`evals/scenarios/artifacts/dev/cart-dependency-latency/`](../../evals/scenarios/artifacts/dev/cart-dependency-latency/) by `faultline-render`. [All bundles](README.md).
