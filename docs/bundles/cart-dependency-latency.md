# Cart service network path acquires 300ms of delay

## The scenario

| | |
|---|---|
| scenario | `cart-dependency-latency` |
| fault class | **`dependency_latency`** |
| expected remediation | `restart` |
| split | `dev` |
| injected at | `cart-service` via `cart-dependency-latency` |
| time to page | 3m50s |
| steady state captured | 300s |
| capture window | 2026-08-29T23:22:42+00:00 → 2026-08-29T23:40:48+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m50s |
| `t_revert` | T+8m50s |
| all clear | T+11m06s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m45s | `cartservice` | ServiceHighLatency | 7.2 min | **paged** |
| T+3m45s | `frontend` | ServiceHighLatency | 7.2 min | **paged** |
| T+3m45s | `loadgenerator` | ServiceHighLatency | 7.2 min | **paged** |
| T+4m00s | `checkoutservice` | ServiceHighLatency | 6.8 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="cartservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/cart-service.txt` — 506 lines.

## A look at the logs

From `logs/cart-service.txt` (500 lines):

```
2026-08-29T23:22:42+00:00  AddItemAsync called with userId=88a22f22-a400-11f1-8c4e-9e12df7a2593, productId=0PUK6V6EV0, quantity=3
2026-08-29T23:22:42+00:00  GetCartAsync called with userId=88a22f22-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:42+00:00  GetCartAsync called with userId=88a22f22-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:42+00:00  EmptyCartAsync called with userId=88a22f22-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:44+00:00  AddItemAsync called with userId=89da3600-a400-11f1-8c4e-9e12df7a2593, productId=66VCHSJNUP, quantity=5
2026-08-29T23:22:44+00:00  GetCartAsync called with userId=89da3600-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:44+00:00  GetCartAsync called with userId=89da3600-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:44+00:00  EmptyCartAsync called with userId=89da3600-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:48+00:00  AddItemAsync called with userId=8c076f60-a400-11f1-8c4e-9e12df7a2593, productId=1YMWWN1N4O, quantity=2
2026-08-29T23:22:48+00:00  GetCartAsync called with userId=8c076f60-a400-11f1-8c4e-9e12df7a2593
2026-08-29T23:22:48+00:00  AddItemAsync called with userId=8c076f60-a400-11f1-8c4e-9e12df7a2593, productId=OLJCESPC7Z, quantity=4
2026-08-29T23:22:48+00:00  GetCartAsync called with userId=8c076f60-a400-11f1-8c4e-9e12df7a2593
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

The page named three services in the same evaluation: `ServiceHighLatency` on
**cartservice**, **frontend** and **loadgenerator**, 3m50s after things started slowing.
**checkoutservice** followed fifteen seconds later, for four alerts across four services.

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

**What changed on cartservice, which is where it breaks open.** No deploy, no image
change, no environment difference, no config edit — and one record that is none of those:
a **container created**, described as a traffic-shaping container attached to
cart-service's network namespace, carrying `eth0 delay=300ms jitter=0ms`.

The trap is that the first four answers are all "nothing" and the fifth is the whole
incident. A responder scanning for the familiar shapes of change — a deploy, a config
edit, a version — reads four empty rows and concludes the service was not touched. The
change was at the network layer, one level below anything a service specification
describes, and it is in the change record under the service's own name rather than
anywhere in the service's own configuration.

### Root cause

An unauthorized container was shaping cartservice's egress traffic, adding 300ms of
delay per packet leaving the container. Cart's own code, image and configuration were
untouched.

The observed p95 was roughly double the added per-hop delay, because a cart operation
makes two round trips to Redis and each pays the delay separately. Anyone expecting the
p95 to rise by exactly 300ms would have doubted a correct measurement.

### Resolution

Recreating the cart container cleared the shaping — the rule is bound to the container
instance, so a new one comes up on a clean network path. Everything was quiet 2m32s
later.

Class of fix: **restart**. Nothing was deployed and no configuration was wrong, so
there was nothing to roll back or revert; the container simply needed replacing.

### Detection notes

- Onset to first page: **3m50s**, against a three-minute persistence clause. Detection
  is dominated by the clause, not by how long the signal took to appear — the underlying
  measurement crossed the threshold almost immediately.
- Services alerting at the page: **2**. Over the whole incident: **4**. The blast radius
  never grew beyond cart and its callers.
- Alerts that fired only during recovery: **none**.
- **The culprit was named in the page**, unlike a fault that removes a service entirely
  — a slow service still reports its own latency, so it appears in its own alert. Here it
  was one of only two services named, alongside the synthetic client, which is as close to
  being handed the answer as this system's alerting gets.
- Did the loudest service turn out to be the culprit? **Yes**, and that is worth noting
  precisely because it is unusual. Latency propagates upward through callers, so the
  slowest service in the chain is the source.
- **Detection was never the hard part; attribution was.** On a service whose entire
  operating range is 2ms, the alert is unambiguous the moment it fires. What cost time was
  that the change had been made below the level any service specification describes — so
  every question about cart's *own configuration* came back clean while the change record
  held the answer all along, filed under cart's name and not shaped like a deploy.
- **"Nothing changed" is a conclusion about a query, not about a service.** Four kinds of
  change came back empty here and a fifth did not. Reading the empty four as "the service
  was not touched" is the single most expensive move available in this incident.
- **A latency reading taken shortly after a restart is not a baseline reading.** cart
  decays from about 100ms to 2ms over roughly four minutes after being recreated. Any
  comparison against "normal" must exclude that window, and a responder who samples
  inside it will conclude the service is far noisier than it is.
- On ordering, in both directions: cart and the synthetic client alerted fifteen seconds
  before checkout and frontend, and cart's alert also cleared after its callers'. Neither
  gap is causal. Both are dominated by how full each service's rolling window happens to
  be at the moment the fault starts or stops, which has more to do with traffic rate than
  with the direction of the failure — and reading the *firing* order as causal would have
  been right here by luck, since cart genuinely was the source.

---

Rendered from [`evals/scenarios/artifacts/dev/cart-dependency-latency/`](../../evals/scenarios/artifacts/dev/cart-dependency-latency/) by `faultline-render`. [All bundles](README.md).
