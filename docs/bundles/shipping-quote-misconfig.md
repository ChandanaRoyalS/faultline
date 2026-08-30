# Checkout failed a quarter of its orders, and the service at fault reported nothing

## The scenario

| | |
|---|---|
| scenario | `shipping-quote-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `shippingservice` via `shipping-quote-misconfig` |
| time to page | 3m18s |
| steady state captured | 300s |
| capture window | 2026-08-30T01:15:48+00:00 → 2026-08-30T01:33:25+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m18s |
| `t_revert` | T+8m18s |
| all clear | T+10m37s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m00s | `checkoutservice` | ServiceHighErrorRate | 7.2 min | **paged** |
| T+6m15s | `accountingservice` | ServiceNoTraffic | 2.5 min | joined later |
| T+6m15s | `emailservice` | ServiceNoTraffic | 2.5 min | joined later |
| T+6m15s | `frauddetectionservice` | ServiceNoTraffic | 2.5 min | joined later |
| T+6m15s | `quoteservice` | ServiceNoTraffic | 2.5 min | joined later |
| T+8m15s | `loadgenerator` | ServiceHighErrorRate | 1.0 min | joined later |
| T+8m45s | `frontend` | ServiceHighErrorRate | 0.2 min | began after the revert |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="shippingservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/shipping-service.txt` — 393 lines.

## A look at the logs

From `logs/shipping-service.txt` (387 lines):

```
2026-08-30T01:15:57+00:00  01:15:57 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-e62f4bed8414a6472177fc867f075db4-dfb53665d106d704-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "LS4PSXUNUM", quantity: 3 }, CartItem { product_id: "66VCHSJNUP", quantity: 10 }] }, extensions: Extensions }
2026-08-30T01:15:57+00:00  01:15:57 [INFO] Sending Quote: 142.40
2026-08-30T01:15:57+00:00  01:15:57 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-e62f4bed8414a6472177fc867f075db4-6d0a7ea261302fd7-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "9SIQT8TOJO", quantity: 3 }, CartItem { product_id: "LS4PSXUNUM", quantity: 3 }, CartItem { product_id: "66VCHSJNUP", quantity: 10 }] }, extensions: Extensions }
2026-08-30T01:15:57+00:00  01:15:57 [INFO] Tracking ID Created: b9d18955-9a6f-4bd1-bf3e-22c11d0139d9
2026-08-30T01:16:12+00:00  01:16:12 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-1936655c2a2a3a4d40ad74e70d68a8cf-db1e61867e6a4b25-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 2 }] }, extensions: Extensions }
2026-08-30T01:16:12+00:00  01:16:12 [INFO] Sending Quote: 53.40
2026-08-30T01:16:12+00:00  01:16:12 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-1936655c2a2a3a4d40ad74e70d68a8cf-3ded1693402eb69e-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "66VCHSJNUP", quantity: 4 }, CartItem { product_id: "2ZYFJ3GM2N", quantity: 2 }] }, extensions: Extensions }
2026-08-30T01:16:12+00:00  01:16:12 [INFO] Tracking ID Created: 3c2aa94a-a74f-4bd7-b05b-14beac3d41b7
2026-08-30T01:16:14+00:00  01:16:14 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-25d4771b927b2045dc1810d7263a3ed0-1e6dddaad319e6a5-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "1YMWWN1N4O", quantity: 2 }, CartItem { product_id: "LS4PSXUNUM", quantity: 2 }] }, extensions: Extensions }
2026-08-30T01:16:14+00:00  01:16:14 [INFO] Sending Quote: 35.60
2026-08-30T01:16:14+00:00  01:16:14 [INFO] ShipOrderRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-25d4771b927b2045dc1810d7263a3ed0-fe721a71ab1f3019-01", "baggage": "synthetic_request=true"} }, message: ShipOrderRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "1YMWWN1N4O", quantity: 2 }, CartItem { product_id: "LS4PSXUNUM", quantity: 2 }] }, extensions: Extensions }
2026-08-30T01:16:14+00:00  01:16:14 [INFO] Tracking ID Created: ddffa048-1109-4f4b-95ee-624e5cc3c9de
```

_375 further lines are in the bundle._

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

The page named **checkoutservice**: `ServiceHighErrorRate`, 3m18s after the first failing
request. **loadgenerator** joined briefly. Later in the fault, five services fell silent together as
orders stopped completing — accounting, email, fraud detection, quote and shipping itself —
for seven alerts across seven services.

Checkout's error ratio climbed to **27%** within a minute of the page and stayed between
**25% and 29%** until the fix — steady, not a spike, and about a quarter of every order placed.

### What was checked

**Checkout was failing, and checkout was fine.** Its own dependencies were all fast and all
succeeding: cart, product catalog, currency, payment, email and the order publish each completed
in single-digit milliseconds. A quarter of orders were failing and none of checkout's calls
were slow.

**The shipping service reported nothing at all.** No errors — its error ratio never left zero for
the entire incident, so it never appears in an error query and never came close to a rule. It is
not silent either: it logged an incoming `GetQuoteRequest` throughout, at its ordinary rate, right
through the window in which checkout was failing a quarter of its orders.

**And its logs never mention a failure.** This is the part worth carrying: shipping logs each
request it receives and writes nothing when it cannot service one. There is no error line, no
retry, no name of anything it failed to reach. Reading them tells you only that shipping was alive
and being asked for quotes — which is real evidence, and it is the evidence that rules out the
first thing anyone checks. It is not evidence of what went wrong.

**So no signal points at shipping.** Metrics say checkout. Logs say shipping is healthy. The
service that was misconfigured is invisible to both.

**Change history is what closed it.** Asked of checkout, it returns nothing in the window. Asked
of the services *around* the failure rather than the one alerting, it returns a configuration
change on shipping: the address it uses to reach the quote service was changed to one that does
not resolve. Nothing else changed anywhere.

### Root cause

Shipping's quote-service address was pointed at a host that does not exist. Shipping cannot price
a delivery, so every order that reaches the quote step fails — and it fails *upward*, into
checkout, which is where the errors appear and where the page came from.

### Resolution

The address was restored to its previous value.

### Detection notes

**The alerting service was not the faulty service, and nothing in the alert path could have said
so.** The whole page was about checkout. Checkout was healthy.

**A service can fail without reporting anything.** Shipping produced no errors and no error logs.
An investigation that treats "no errors here" as "nothing wrong here" clears it immediately and
correctly, and is then out of evidence.

**When the failing service's own history is empty, the question is not finished — it has moved.**
Correlating onset against changes *on the service that alerted* finds nothing here. The change
existed the whole time, on a service one hop away that never raised its voice.

---

Rendered from [`evals/scenarios/artifacts/dev/shipping-quote-misconfig/`](../../evals/scenarios/artifacts/dev/shipping-quote-misconfig/) by `faultline-render`. [All bundles](README.md).
