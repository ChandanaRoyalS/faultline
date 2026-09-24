# Accounting's database password rotated to one the database does not accept

## The scenario

| | |
|---|---|
| scenario | `v2-accounting-bad-credential` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `accounting` via `v2-accounting-bad-credential` |
| time to page | 4m16s |
| steady state captured | 300s |
| capture window | 2026-09-24T17:48:56+00:00 → 2026-09-24T18:09:13+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+4m16s |
| `t_revert` | T+9m16s |
| all clear | T+13m17s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+4m15s | `accounting` | ServiceHighErrorRate | 9.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="accounting"}` |

`logs/accounting.txt` — 506 lines.

## A look at the logs

From `logs/accounting.txt` (500 lines):

```
2026-09-24T17:54:39+00:00  Cannot load library libgssapi_krb5.so.2
2026-09-24T17:54:39+00:00  Error: libgssapi_krb5.so.2: cannot open shared object file: No such file or directory
2026-09-24T17:49:06+00:00  info: Accounting.Consumer[174880625]
2026-09-24T17:49:06+00:00        Order details: { "orderId": "3cfab54b-b840-11f1-a862-4659f9156b51", "shippingTrackingId": "daf6cab6-7c9e-47bb-ab3f-11e80e859455", "shippingCost": { "currencyCode": "USD", "units": "26", "nanos": 969999999 }, "shippingAddress": { "streetAddress": "1 Hacker Way", "city": "Menlo Park", "state": "CA", "country": "United States", "zipCode": "94025" }, "items": [ { "item": { "productId": "L9ECAV7KIM", "quantity": 3 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } } ] }.
2026-09-24T17:49:12+00:00  info: Accounting.Consumer[174880625]
2026-09-24T17:49:12+00:00        Order details: { "orderId": "406a4f86-b840-11f1-a862-4659f9156b51", "shippingTrackingId": "c5a197ab-2e90-4681-9c4a-120477bb0310", "shippingCost": { "currencyCode": "USD", "units": "62", "nanos": 929999999 }, "shippingAddress": { "streetAddress": "410 Terry Ave N", "city": "Seattle", "state": "WA", "country": "United States", "zipCode": "98109" }, "items": [ { "item": { "productId": "9SIQT8TOJO", "quantity": 4 }, "cost": { "currencyCode": "USD", "units": "3599" } }, { "item": { "productId": "1YMWWN1N4O", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "129", "nanos": 949999999 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 1 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-09-24T17:49:21+00:00  info: Accounting.Consumer[174880625]
2026-09-24T17:49:21+00:00        Order details: { "orderId": "45e30336-b840-11f1-a862-4659f9156b51", "shippingTrackingId": "02944945-19b5-4ffa-a7b1-8c256eaee7ca", "shippingCost": { "currencyCode": "USD", "units": "62", "nanos": 929999999 }, "shippingAddress": { "streetAddress": "1355 Market St", "city": "San Francisco", "state": "CA", "country": "United States", "zipCode": "94103" }, "items": [ { "item": { "productId": "HQTGWGPNH4", "quantity": 2 }, "cost": { "currencyCode": "USD", "nanos": 990000000 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 5 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-09-24T17:49:32+00:00  info: Accounting.Consumer[174880625]
2026-09-24T17:49:32+00:00        Order details: { "orderId": "4c386689-b840-11f1-a862-4659f9156b51", "shippingTrackingId": "eba1b591-ced2-424d-8eb3-d4ddc1f786ce", "shippingCost": { "currencyCode": "USD", "units": "89", "nanos": 900000000 }, "shippingAddress": { "streetAddress": "100 Winchester Circle", "city": "Los Gatos", "state": "CA", "country": "United States", "zipCode": "95032" }, "items": [ { "item": { "productId": "2ZYFJ3GM2N", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } } ] }.
2026-09-24T17:49:39+00:00  info: Accounting.Consumer[174880625]
2026-09-24T17:49:39+00:00        Order details: { "orderId": "5089732a-b840-11f1-a862-4659f9156b51", "shippingTrackingId": "09311168-779b-4bae-9f39-9a0814914985", "shippingCost": { "currencyCode": "CAD", "units": "72", "nanos": 180833259 }, "shippingAddress": { "streetAddress": "150 Elgin St", "city": "Ottawa", "state": "ON", "country": "Canada", "zipCode": "K2P1L4" }, "items": [ { "item": { "productId": "2ZYFJ3GM2N", "quantity": 5 }, "cost": { "currencyCode": "CAD", "units": "280", "nanos": 948571428 } }, { "item": { "productId": "66VCHSJNUP", "quantity": 1 }, "cost": { "currencyCode": "CAD", "units": "468", "nanos": 292224679 } } ] }.
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

The page was a single alert, `ServiceHighErrorRate` on **accounting**, 4m16s after the
trouble started. Nothing else fired then, and nothing else fired afterwards. Its error
ratio had no series at all before the incident, because accounting had not recorded an
error in the window. It appeared a little over two minutes in, climbed, and settled at
**exactly one third** of its spans once the rate window filled. It held there, flat, until
the fix.

Nothing around accounting moved. Its own request rate held at its usual level, a little
under half a request a second, and its latency did not change. Checkout was placing orders
at about its usual rate, with no change in latency. The storefront showed nothing, and neither did the other
services that read and write the same database.

### What was checked

**Whether accounting was down, restarting or starved.** It was not. Its .NET runtime series
never dropped out, and it kept taking orders off the topic at the rate it always does. A
service that pages on errors while its traffic and latency look normal is one that is
running and failing at something specific. The container had been recreated at the start
of the incident, and it was running normally since.

**Its logs, first over the whole incident.** That showed nothing wrong. The log tool returns
the oldest and newest lines of a window, and both ends were ordinary `Order details` lines:
the start before the trouble, the end after the fix. The failures were all in the middle it
does not return. Narrowed to the minute after the start, the log was unambiguous. Every order
accounting received was followed by `fail: Accounting.Consumer … Order parsing failed:`
wrapping `Npgsql.PostgresException: 28P01: password authentication failed for user "otelu"`,
about forty lines of stack trace per order. Every order in that minute failed the same way,
and none before it had.

**The "Order parsing failed" label.** It reads like a malformed message on the orders topic,
something checkout started producing, and that is the dead end it invites. The other
consumer of the same topic answered it: fraud-detection read the same orders throughout with
no change in its errors or latency. The messages were fine. The label is the consumer's
catch-all, and the exception inside it is the real error.

**The database.** Postgres was up and serving. product-catalog and product-reviews, which use
the same database, showed no change in errors or latency. The database was healthy and one
client could not get in.

**The traces.** Each order is three spans: `order-consumed`, `orders receive`, and a `CONNECT
otel` to the database. The connect span was the error, and its status read `28P01`, the
Postgres code for a failed password authentication. The consumer span around it did not
error. That is also the one-third: one span of three fails on every order, so an error ratio
of exactly 0.333 means every order was failing, not a third of them.

**Its runtime counters.** `PostgresException` in the .NET exception counter climbed at about two
a second through the incident, from almost none before it. That is many times the rate orders
arrive, so each failure is counted more than once on its way up.

**What changed.** One record, at the start: `DB_CONNECTION_STRING updated on accounting`. That is
the credential the failing connect span uses.

### Root cause

Accounting's database connection string was changed to a password the database does not
accept. Postgres itself was healthy and every other client of it was unaffected. Accounting
kept consuming orders as normal, and every attempt to write one failed at authentication,
before any query ran. Nothing upstream waits on accounting, so nothing upstream noticed.

### Resolution

The connection string was set back to the working password and accounting was recreated
with it. The orders that arrived while it was being replaced were picked up together a
few seconds after it came back, and wrote normally. The error ratio drained with its
five-minute window, and the alert cleared 4m01s after the fix. Nothing fired during
recovery.

Class of fix: **config_revert**. Nothing was deployed and no code was wrong. One
configuration value was wrong, and it was set back.

### Detection notes

- Onset to first page: **4m16s**. Services on the page: **one**. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one. A
  failure in a pure consumer stays where it is, because nothing calls it and nothing waits
  on it.
- Would the page alone have led you to the right service? **Yes, but not to the cause.** The
  cause was in three places, none on the page: the log line inside a misleading label, the
  connect span's status code, and the change record.
- **An error ratio of exactly one third is a count, not a severity.** It is one failing span
  per three-span order. Read as "a third of orders fail", it undersells a total failure.
- **A log query over the whole incident showed only healthy lines.** Both ends of the window
  were fine; the failures filled the middle. Narrow the window to the start before
  concluding that a service's log is clean.
- **Authentication refused is not connection refused.** A wrong host or port fails at the
  socket, with no Postgres error code. `28P01` means the database was reached and said no,
  which points at the credential and away from the network.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-accounting-bad-credential/`](../../evals/scenarios/artifacts/dev/v2-accounting-bad-credential/) by `faultline-render`. [All bundles](README.md).
