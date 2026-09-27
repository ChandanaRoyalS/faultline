# Accounting's database password rotated to one the database does not accept

## The scenario

| | |
|---|---|
| scenario | `v2-accounting-bad-credential` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `accounting` via `v2-accounting-bad-credential` |
| time to page | 3m16s |
| steady state captured | 300s |
| capture window | 2026-09-27T02:32:31+00:00 → 2026-09-27T02:51:48+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m16s |
| `t_revert` | T+8m16s |
| all clear | T+12m17s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m15s | `accounting` | ServiceHighErrorRate | 9.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="accounting"}` |

`logs/accounting.txt` — 483 lines.

## A look at the logs

From `logs/accounting.txt` (---- onset 2026-09-27T02:37:31+00:00 ----):

```
2026-09-27T02:32:41+00:00  info: Accounting.Consumer[174880625]
2026-09-27T02:32:41+00:00        Order details: { "orderId": "b665db78-ba1b-11f1-9ff9-1ec936a133aa", "shippingTrackingId": "b1cda55b-0d58-4b22-aa30-daa2f05ba695", "shippingCost": { "currencyCode": "USD", "units": "143", "nanos": 840000000 }, "shippingAddress": { "streetAddress": "100 Winchester Circle", "city": "Los Gatos", "state": "CA", "country": "United States", "zipCode": "95032" }, "items": [ { "item": { "productId": "66VCHSJNUP", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "349", "nanos": 949999999 } }, { "item": { "productId": "2ZYFJ3GM2N", "quantity": 1 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } }, { "item": { "productId": "L9ECAV7KIM", "quantity": 5 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } } ] }.
2026-09-27T02:32:47+00:00  info: Accounting.Consumer[174880625]
2026-09-27T02:32:47+00:00        Order details: { "orderId": "b9ea4ed8-ba1b-11f1-9ff9-1ec936a133aa", "shippingTrackingId": "68ca29e0-947b-4dbc-b75b-9a89e3be86e3", "shippingCost": { "currencyCode": "USD", "units": "269", "nanos": 699999999 }, "shippingAddress": { "streetAddress": "One Apple Park Way", "city": "Cupertino", "state": "CA", "country": "United States", "zipCode": "95014" }, "items": [ { "item": { "productId": "LS4PSXUNUM", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "57", "nanos": 799999999 } }, { "item": { "productId": "1YMWWN1N4O", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "129", "nanos": 949999999 } }, { "item": { "productId": "0PUK6V6EV0", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "175" } } ] }.
2026-09-27T02:32:53+00:00  info: Accounting.Consumer[174880625]
2026-09-27T02:32:53+00:00        Order details: { "orderId": "bd6fbe17-ba1b-11f1-9ff9-1ec936a133aa", "shippingTrackingId": "c70c1080-7958-45ee-be14-e4f1b7197b70", "shippingCost": { "currencyCode": "CAD", "units": "48", "nanos": 120555506 }, "shippingAddress": { "streetAddress": "150 Elgin St", "city": "Ottawa", "state": "ON", "country": "Canada", "zipCode": "K2P1L4" }, "items": [ { "item": { "productId": "9SIQT8TOJO", "quantity": 4 }, "cost": { "currencyCode": "CAD", "units": "4816", "nanos": 70057496 } } ] }.
2026-09-27T02:32:58+00:00  info: Accounting.Consumer[174880625]
2026-09-27T02:32:58+00:00        Order details: { "orderId": "c0682ad1-ba1b-11f1-9ff9-1ec936a133aa", "shippingTrackingId": "6afab349-673f-40d4-a465-dc6893e855d8", "shippingCost": { "currencyCode": "USD", "units": "125", "nanos": 859999999 }, "shippingAddress": { "streetAddress": "100 Winchester Circle", "city": "Los Gatos", "state": "CA", "country": "United States", "zipCode": "95032" }, "items": [ { "item": { "productId": "HQTGWGPNH4", "quantity": 4 }, "cost": { "currencyCode": "USD", "nanos": 990000000 } }, { "item": { "productId": "66VCHSJNUP", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "349", "nanos": 949999999 } } ] }.
2026-09-27T02:33:14+00:00  info: Accounting.Consumer[174880625]
2026-09-27T02:33:14+00:00        Order details: { "orderId": "ca6df9bb-ba1b-11f1-9ff9-1ec936a133aa", "shippingTrackingId": "9d902fe0-2b7d-4bb8-a60e-d1ce39f2ffd4", "shippingCost": { "currencyCode": "USD", "units": "80", "nanos": 909999999 }, "shippingAddress": { "streetAddress": "One Apple Park Way", "city": "Cupertino", "state": "CA", "country": "United States", "zipCode": "95014" }, "items": [ { "item": { "productId": "HQTGWGPNH4", "quantity": 2 }, "cost": { "currencyCode": "USD", "nanos": 990000000 } }, { "item": { "productId": "9SIQT8TOJO", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "3599" } }, { "item": { "productId": "L9ECAV7KIM", "quantity": 3 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } }, { "item": { "productId": "1YMWWN1N4O", "quantity": 2 }, "cost": { "currencyCode": "USD", "units": "129", "nanos": 949999999 } } ] }.
2026-09-27T02:33:30+00:00  info: Accounting.Consumer[174880625]
2026-09-27T02:33:30+00:00        Order details: { "orderId": "d38a4ca5-ba1b-11f1-9ff9-1ec936a133aa", "shippingTrackingId": "464c24c5-c223-4237-b577-326b0885c050", "shippingCost": { "currencyCode": "USD", "units": "179", "nanos": 800000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "2ZYFJ3GM2N", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "209", "nanos": 949999999 } }, { "item": { "productId": "L9ECAV7KIM", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } } ] }.
```

_462 further lines are in the bundle._

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

The page was a single alert, `ServiceHighErrorRate` on **accounting**, 3m16s after the trouble
started. Nothing else fired then, and nothing else fired afterwards. Its error ratio had read
zero before the incident. It rose from about a minute in, climbed, and settled at **exactly one
third** of its spans about four minutes in, once the rate window filled. It held there, flat,
until the fix.

Nothing around accounting moved. Its own request rate held at its usual level, a little under
half a request a second, and its latency did not change. Checkout was placing orders at its
usual rate. The storefront showed nothing, and neither did the other services that read and
write the same database. fraud-detection, the other reader of the orders, kept its usual rate
and latency.

### What was checked

**Whether accounting was down, restarting or starved.** It was not. Its .NET runtime series never
dropped out, and it kept taking orders off the topic at the rate it always does. A service that
pages on errors while its traffic and latency look normal is one that is running and failing at
something specific. The container had been recreated at the start of the incident, and it had
been running normally since.

**Its logs, first over the whole incident.** The log tool returns the oldest and newest lines of a
window. From the start to the fix, the oldest were the service's own startup banner and environment
dump, the trace of the recreate, and the newest were the bottom of one stack trace: `SqlState:
28P01`, `MessageText: password authentication failed for user "otelu"`. The exception's name and the
label around it were in the forty lines above, in the part the tool does not return. Narrowed to the
minutes after the start, the log was unambiguous. The recreated service connected to Kafka, took its
first order 44 seconds after the change, and every order from then on was followed by `fail:
Accounting.Consumer … Order parsing failed:` wrapping `Npgsql.PostgresException: 28P01: password
authentication failed for user "otelu"`, about forty lines of stack trace per order. Over the
incident that was 66 failures, up to 11 a minute, with none in the five minutes before the change
and none after the fix.

**A library error on the way.** Just before the first failure the log says `Cannot load library
libgssapi_krb5.so.2`. That reads like a broken image, but it appeared once, the orders before the
change had not needed it, and the failures after it all name the password. It is the database
driver reaching for another way to authenticate after the password was refused, not the cause.

**The "Order parsing failed" label.** It reads like a malformed message on the orders topic,
something checkout started producing, and that is the dead end it invites. The other consumer of the
same topic answered it: fraud-detection read the same orders throughout at its usual rate and
latency. Its error ratio did twitch, to about 1.5%, but flagd, ad, recommendation and
product-reviews twitched in the same minutes and again ten minutes later, after the fix, so it had
nothing to do with orders. The messages were fine. The label is the consumer's catch-all, and the
exception inside it is the real error.

**The database.** Postgres was up and serving. product-catalog and product-reviews, which use the
same database, showed no change in latency, and the catalog no errors at all. The database was
healthy and one client could not get in.

**The traces.** Each order is three spans: `order-consumed`, `orders receive`, and a `CONNECT otel`
to the database. All ten error traces drawn named the connect span under `order-consumed` as the
failing hop, and its status read `28P01`, the Postgres code for a failed password
authentication. The consumer span around it did not error. That is also
the one-third: one span of three fails on every order, so an error ratio of exactly 0.333 means
every order was failing, not a third of them.

**Its runtime counters.** `PostgresException` in the .NET exception counter had not moved before
the change. From the second minute it climbed at about two and a half a second, to 1,188 by
the fix. That is many times the rate orders arrive, so each failure is counted more than once on
its way up.

**What changed.** One record, at the start: `DB_CONNECTION_STRING updated on accounting`. That is
the credential the failing connect span uses.

### Root cause

Accounting's database connection string was changed to a password the database does not accept.
Postgres itself was healthy and every other client of it was unaffected. Accounting kept consuming
orders as normal, and every attempt to write one failed at authentication, before any query ran.
Nothing upstream waits on accounting, so nothing upstream noticed.

### Resolution

The connection string was set back to the working password and accounting was recreated with it.
It wrote orders normally again. The error ratio drained with its five-minute window, and the
alert cleared 4m01s after the fix. Nothing fired during recovery.

Class of fix: **config_revert**. Nothing was deployed and no code was wrong. One configuration
value was wrong, and it was set back.

### Detection notes

- Onset to first page: **3m16s**. Services on the page: **one**. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one. A failure
  in a pure consumer stays where it is, because nothing calls it and nothing waits on it.
- Would the page alone have led you to the right service? **Yes, but not to the cause.** The
  cause was in three places, none on the page: the log line inside a misleading label, the
  connect span's status code, and the change record.
- **An error ratio of exactly one third is a count, not a severity.** It is one failing span per
  three-span order. Read as "a third of orders fail", it undersells a total failure.
- **A log read over the whole incident shows its ends, not its middle.** Here the newest lines
  happened to be the bottom of a failing stack trace, and the label and the exception's name were
  in the middle the tool does not return. Where the ends are healthy, the failures can all be in
  that middle. Narrow the window to the start before concluding that a service's log is clean.
- **Authentication refused is not connection refused.** A wrong host or port fails at the socket,
  with no Postgres error code. `28P01` means the database was reached and said no, which points
  at the credential and away from the network.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-accounting-bad-credential/`](../../evals/scenarios/artifacts/dev/v2-accounting-bad-credential/) by `faultline-render`. [All bundles](README.md).
