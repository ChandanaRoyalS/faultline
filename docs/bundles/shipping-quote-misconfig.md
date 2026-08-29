# Checkout failed a quarter of its orders, and the service at fault reported nothing

## The scenario

| | |
|---|---|
| scenario | `shipping-quote-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `shippingservice` via `shipping-quote-misconfig` |
| time to page | 2m49s |
| steady state captured | 300s |
| capture window | 2026-08-29T18:34:54+00:00 → 2026-08-29T18:51:17+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+2m49s |
| `t_revert` | T+7m49s |
| all clear | T+9m23s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+2m45s | `checkoutservice` | ServiceHighErrorRate | 6.5 min | **paged** |
| T+6m30s | `loadgenerator` | ServiceHighErrorRate | 0.2 min | joined later |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(calls_total{status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total[2m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(latency_bucket[2m])))` |
| `metrics/runtime.json` | `{exported_job="shippingservice", __name__=~"process_runtime_.*|runtime_.*|system_memory_.*"}` |

`logs/shipping-service.txt` — 132 lines.

## A look at the logs

From `logs/shipping-service.txt` (126 lines):

```
2026-08-29T18:39:58+00:00  18:39:58 [INFO] OTel pipeline created
2026-08-29T18:39:58+00:00  18:39:58 [INFO] listening on 0.0.0.0:50050
2026-08-29T18:40:14+00:00  18:40:14 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-a2151be9f929597f5e49e00aaa87c01b-2b61d6ced37c75ef-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "L9ECAV7KIM", quantity: 1 }, CartItem { product_id: "OLJCESPC7Z", quantity: 2 }, CartItem { product_id: "0PUK6V6EV0", quantity: 3 }] }, extensions: Extensions }
2026-08-29T18:40:15+00:00  18:40:15 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-dbbd6dcea0531e78fb74c501e37df370-82cbb8e148a93f7d-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Apple Park Way", city: "Cupertino", state: "CA", country: "United States", zip_code: "95014" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 10 }, CartItem { product_id: "66VCHSJNUP", quantity: 2 }] }, extensions: Extensions }
2026-08-29T18:40:26+00:00  18:40:26 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-d1b21121a8ffdff070995a13b4a0d8d9-8bd1deea3aaadc06-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "410 Terry Ave N", city: "Seattle", state: "WA", country: "United States", zip_code: "98109" }), items: [CartItem { product_id: "OLJCESPC7Z", quantity: 5 }] }, extensions: Extensions }
2026-08-29T18:40:30+00:00  18:40:30 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-a175efcf79b2b1d6081a2fa1814e41e1-3621cfa047d25f03-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "2ZYFJ3GM2N", quantity: 2 }, CartItem { product_id: "OLJCESPC7Z", quantity: 2 }] }, extensions: Extensions }
2026-08-29T18:40:40+00:00  18:40:40 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-fc5f2f6a4ba26709c3cc2ee8793f8fe2-3b7ff75d7427a9ba-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "100 Winchester Circle", city: "Los Gatos", state: "CA", country: "United States", zip_code: "95032" }), items: [CartItem { product_id: "1YMWWN1N4O", quantity: 3 }, CartItem { product_id: "0PUK6V6EV0", quantity: 2 }, CartItem { product_id: "9SIQT8TOJO", quantity: 4 }, CartItem { product_id: "LS4PSXUNUM", quantity: 3 }] }, extensions: Extensions }
2026-08-29T18:40:48+00:00  18:40:48 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-3137e1f76cc1b5a96b75da6d2f4c1a51-3cb8eae4810487d6-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "100 Winchester Circle", city: "Los Gatos", state: "CA", country: "United States", zip_code: "95032" }), items: [CartItem { product_id: "OLJCESPC7Z", quantity: 4 }] }, extensions: Extensions }
2026-08-29T18:40:50+00:00  18:40:50 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-215dee88a4787c694bd1bd9dab75fe89-57256c8abf8a21d0-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1600 Amphitheatre Parkway", city: "Mountain View", state: "CA", country: "United States", zip_code: "94043" }), items: [CartItem { product_id: "OLJCESPC7Z", quantity: 4 }] }, extensions: Extensions }
2026-08-29T18:40:53+00:00  18:40:53 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-6d7c452ff2ac3479610b87fded5968fd-e94aea140c01ef25-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 4 }, CartItem { product_id: "1YMWWN1N4O", quantity: 1 }] }, extensions: Extensions }
2026-08-29T18:40:54+00:00  18:40:54 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-7340c61537794eb8a8bb41d971d223dc-dc3f78cff357df8e-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "1 Hacker Way", city: "Menlo Park", state: "CA", country: "United States", zip_code: "94025" }), items: [CartItem { product_id: "LS4PSXUNUM", quantity: 5 }] }, extensions: Extensions }
2026-08-29T18:41:15+00:00  18:41:15 [INFO] GetQuoteRequest: Request { metadata: MetadataMap { headers: {"content-type": "application/grpc", "user-agent": "grpc-go/1.46.2", "te": "trailers", "traceparent": "00-11934e5aead52e8f3a971b83ef55827e-13958a036bd4824a-01", "baggage": "synthetic_request=true"} }, message: GetQuoteRequest { address: Some(Address { street_address: "One Microsoft Way", city: "Redmond", state: "WA", country: "United States", zip_code: "98052" }), items: [CartItem { product_id: "0PUK6V6EV0", quantity: 1 }] }, extensions: Extensions }
```

_114 further lines are in the bundle._

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

The page named **checkoutservice**: `ServiceHighErrorRate`, 2m49s after the first failing
request. **loadgenerator** joined briefly. Nothing else alerted for the length of the incident.

Checkout's error ratio climbed to **27%** within a minute of the page and stayed between
**23% and 29%** until the fix — steady, not a spike, and about a quarter of every order placed.

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
