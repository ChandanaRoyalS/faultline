# Accounting pointed at a Kafka port where nothing listens

## The scenario

| | |
|---|---|
| scenario | `v2-accounting-kafka-misconfig` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `holdout` |
| injected at | `accounting` via `v2-accounting-kafka-misconfig` |
| time to page | 7m47s |
| steady state captured | 300s |
| capture window | 2026-09-26T06:37:40+00:00 → 2026-09-26T06:58:28+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+7m47s |
| `t_revert` | T+12m47s |
| all clear | T+13m48s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+7m30s | `accounting` | ServiceNoTraffic | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="accounting"}` |

`logs/accounting.txt` — 493 lines.

## A look at the logs

From `logs/accounting.txt` (---- onset 2026-09-26T06:42:40+00:00 ----):

```
2026-09-26T06:37:46+00:00  info: Accounting.Consumer[174880625]
2026-09-26T06:37:46+00:00        Order details: { "orderId": "c8e7b3d1-b974-11f1-a862-4659f9156b51", "shippingTrackingId": "42419f8e-445c-436f-826d-9cce31ea6d6c", "shippingCost": { "currencyCode": "CAD", "units": "252", "nanos": 632916408 }, "shippingAddress": { "streetAddress": "150 Elgin St", "city": "Ottawa", "state": "ON", "country": "Canada", "zipCode": "K2P1L4" }, "items": [ { "item": { "productId": "LS4PSXUNUM", "quantity": 5 }, "cost": { "currencyCode": "CAD", "units": "77", "nanos": 346165413 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 3 }, "cost": { "currencyCode": "CAD", "units": "280", "nanos": 948571428 } }, { "item": { "productId": "6E92ZMYYFZ", "quantity": 10 }, "cost": { "currencyCode": "CAD", "units": "93", "nanos": 604918177 } }, { "item": { "productId": "9SIQT8TOJO", "quantity": 3 }, "cost": { "currencyCode": "CAD", "units": "4816", "nanos": 70057496 } } ] }.
2026-09-26T06:37:47+00:00  info: Accounting.Consumer[174880625]
2026-09-26T06:37:47+00:00        Order details: { "orderId": "c9909d41-b974-11f1-a862-4659f9156b51", "shippingTrackingId": "f7f34855-0968-4897-8b6b-4eec95bf3a91", "shippingCost": { "currencyCode": "USD", "units": "17", "nanos": 980000000 }, "shippingAddress": { "streetAddress": "One Apple Park Way", "city": "Cupertino", "state": "CA", "country": "United States", "zipCode": "95014" }, "items": [ { "item": { "productId": "1YMWWN1N4O", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "129", "nanos": 949999999 } } ] }.
2026-09-26T06:38:06+00:00  info: Accounting.Consumer[174880625]
2026-09-26T06:38:06+00:00        Order details: { "orderId": "d50e95f0-b974-11f1-a862-4659f9156b51", "shippingTrackingId": "ab7c6cc1-e340-437a-bde3-0d657e579cb5", "shippingCost": { "currencyCode": "USD", "units": "89", "nanos": 900000000 }, "shippingAddress": { "streetAddress": "410 Terry Ave N", "city": "Seattle", "state": "WA", "country": "United States", "zipCode": "98109" }, "items": [ { "item": { "productId": "OLJCESPC7Z", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "101", "nanos": 959999999 } } ] }.
2026-09-26T06:38:15+00:00  info: Accounting.Consumer[174880625]
2026-09-26T06:38:15+00:00        Order details: { "orderId": "da293049-b974-11f1-a862-4659f9156b51", "shippingTrackingId": "dd7480eb-355f-4e95-8e74-50cef0f013f3", "shippingCost": { "currencyCode": "USD", "units": "8", "nanos": 990000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "HQTGWGPNH4", "quantity": 1 }, "cost": { "currencyCode": "USD", "nanos": 990000000 } } ] }.
2026-09-26T06:38:18+00:00  info: Accounting.Consumer[174880625]
2026-09-26T06:38:18+00:00        Order details: { "orderId": "dbf43e72-b974-11f1-a862-4659f9156b51", "shippingTrackingId": "554174c8-119a-42a0-a583-6cb133d4da5a", "shippingCost": { "currencyCode": "USD", "units": "233", "nanos": 740000000 }, "shippingAddress": { "streetAddress": "1 Hacker Way", "city": "Menlo Park", "state": "CA", "country": "United States", "zipCode": "94025" }, "items": [ { "item": { "productId": "2ZYFJ3GM2N", "quantity": 14 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } }, { "item": { "productId": "0PUK6V6EV0", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "175" } }, { "item": { "productId": "66VCHSJNUP", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "349", "nanos": 949999999 } } ] }.
2026-09-26T06:38:31+00:00  info: Accounting.Consumer[174880625]
2026-09-26T06:38:31+00:00        Order details: { "orderId": "e3d5641b-b974-11f1-a862-4659f9156b51", "shippingTrackingId": "fedab8d5-0cf1-4ca6-b588-72976af26d7f", "shippingCost": { "currencyCode": "USD", "units": "35", "nanos": 960000000 }, "shippingAddress": { "streetAddress": "410 Terry Ave N", "city": "Seattle", "state": "WA", "country": "United States", "zipCode": "98109" }, "items": [ { "item": { "productId": "9SIQT8TOJO", "quantity": 4 }, "cost": { "currencyCode": "USD", "units": "3599" } } ] }.
```

_472 further lines are in the bundle._

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

The page was one alert, `ServiceNoTraffic` on **accounting**, 7m47s after the trouble started.
Nothing else fired then, and nothing fired afterwards: no error-rate alert and no latency alert on
any service, during the incident or after the fix.

Accounting's request rate had been steady at about 0.4 a second. It fell from about a minute in and
reached zero at about five minutes. From then on its error ratio and its latency had **no values**
at all: no errors, no slow requests, nothing. The alert waits for the silence to hold before it
fires.

Everything around it looked normal. The storefront browsed and took orders at its usual rate.
Checkout's error ratio stayed at zero and its latency did not move. Payment, email, shipping and
fraud-detection kept their usual traffic.

### What was checked

**Whether accounting was down or restarting.** It was not. Its .NET runtime series, 42 of them,
reported without a gap through the whole incident. A process that had exited or was restarting
would have left holes. This one was running the whole time. The container had been recreated at
the start and had not restarted since.

**Who calls it.** Nobody. Accounting is a consumer: it reads each placed order from the `orders`
topic on Kafka and writes it to the database. Nothing waits on it, so nothing upstream could fail
or slow down because of it. The traffic it had lost was its own consumption.

**Its logs, first over the whole incident.** The log tool returns the oldest and newest lines of a
window, and over the whole incident both ends were the same line, repeated:
`%3|...|ERROR|rdkafka#consumer-1| [thrd:kafka:9094/bootstrap]: 1/1 brokers are down`. It was being
written about 1,160 times a minute, nineteen a second, from the start until the fix. That is the
Kafka client saying it has no broker to talk to, and the thread name carries the address it was
using: `kafka:9094`.

**Its logs, narrowed to the start.** The first lines after the recreate are the service's startup
banner and environment dump, which lists `[KAFKA_ADDR, kafka:9094]`, then `Connecting to Kafka:
kafka:9094`, then the client's first attempt: `Connect to ipv4#172.18.0.2:9094 failed: Connection
refused`. The name resolved to the Kafka host, and nothing on that host was listening on that port.
Before the change, accounting logged `Order details: {...}` for every order, 6 to 11 a minute.
After it, it logged none.

**Whether Kafka was down.** It was not. Checkout's orders completed end to end, through payment,
shipping, the confirmation email and emptying the cart, with no errors, and each order is published
to the same topic at the end. **Fraud-detection**, the other consumer of that topic, kept reading
it throughout: its log recorded `Consumed record with orderId: ...` 3 to 15 times a minute, with
its running total climbing, for the whole incident. Kafka's own log showed only its routine
housekeeping. The broker was up, the topic was being written, and one of its two consumers was
reading it. Only accounting was not.

**Its traces.** None at all from accounting in the incident. There was nothing to trace: it
received no orders, so it wrote none.

**What changed.** One record, at the start: `KAFKA_ADDR updated on accounting`, to `kafka:9094`.
That is the address in every error line. Kafka's own address is port 9092, the one the other
clients use. Nothing had changed on Kafka, on checkout or on fraud-detection.

### Root cause

Accounting's `KAFKA_ADDR` was changed to a port on the Kafka host where nothing listens. The service
came up normally, subscribed, and then waited for orders from a broker it could never reach, its
client retrying and logging the failure many times a second. It did not crash, so it did not
restart. Kafka was healthy, checkout kept publishing orders and fraud-detection kept reading them.
Nothing calls accounting, so nothing failed: orders simply stopped being recorded. The only signal
the alerting could see was accounting's own traffic going to zero. The fault was the broker address
accounting held.

### Resolution

`KAFKA_ADDR` was set back to Kafka's address and accounting was recreated with it. It rejoined its
consumer group and resumed from the last order it had committed. In the first minute after the fix
it logged **116** orders, against 6 to 11 in a normal minute: the same number fraud-detection had
read during the incident and that minute together. Each took about a millisecond, with its database
write beneath it. The group's lag was zero afterwards. The orders written during the incident were
**delayed, not lost**. The alert cleared 1m01s after the fix, and nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

- Onset to first page: **7m47s**, most of it the traffic series draining and the alert's hold.
  Services on the page: **one**. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one. A fault in
  a pure consumer stays where it is, because nothing calls it and nothing waits on it.
- Would the page alone have led you to the right service? **Yes, but not to the cause.**
  `ServiceNoTraffic` reads as down or idle, and accounting was neither: it was running and trying
  nineteen times a second. The cause is in its log, which names the address, and in the change
  record.
- **A consumer's traffic is its own consumption.** With no callers, "no traffic" means it is not
  receiving messages, which points at the broker, the topic or its connection to them, not at
  anyone upstream.
- **The other consumer of the same topic is the control.** Fraud-detection reading the same topic
  at its usual rate rules out the broker and the producer in one step, and leaves the one consumer
  that stopped.
- **A log flooded with one line still names the cause.** Over the whole incident the log tool
  returned only `1/1 brokers are down`, but that line carries the address in its thread name. The
  `Connection refused` behind it is at the start: narrow the window there.
- **Check what the fix left behind.** A consumer that commits its offsets picks up where it
  stopped. The burst of orders after the fix, and zero lag afterwards, is what shows nothing was
  lost.

---

Rendered from [`evals/scenarios/artifacts/holdout/v2-accounting-kafka-misconfig/`](../../evals/scenarios/artifacts/holdout/v2-accounting-kafka-misconfig/) by `faultline-render`. [All bundles](README.md).
