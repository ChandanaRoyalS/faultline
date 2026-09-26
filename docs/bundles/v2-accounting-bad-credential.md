# Accounting's database password rotated to one the database does not accept

## The scenario

| | |
|---|---|
| scenario | `v2-accounting-bad-credential` |
| fault class | **`bad_config`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `accounting` via `v2-accounting-bad-credential` |
| time to page | 3m46s |
| steady state captured | 300s |
| capture window | 2026-09-26T04:41:35+00:00 → 2026-09-26T05:01:23+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+3m46s |
| `t_revert` | T+8m46s |
| all clear | T+12m48s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+3m30s | `accounting` | ServiceHighErrorRate | 9.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="accounting"}` |

`logs/accounting.txt` — 499 lines.

## A look at the logs

From `logs/accounting.txt` (---- onset 2026-09-26T04:46:35+00:00 ----):

```
2026-09-26T04:41:35+00:00  info: Accounting.Consumer[174880625]
2026-09-26T04:41:35+00:00        Order details: { "orderId": "8e30ba0a-b964-11f1-a862-4659f9156b51", "shippingTrackingId": "6e83a222-8e0d-44f7-a206-d598f84cc792", "shippingCost": { "currencyCode": "USD", "units": "8", "nanos": 990000000 }, "shippingAddress": { "streetAddress": "One Microsoft Way", "city": "Redmond", "state": "WA", "country": "United States", "zipCode": "98052" }, "items": [ { "item": { "productId": "OLJCESPC7Z", "quantity": 1 }, "cost": { "currencyCode": "USD", "units": "101", "nanos": 959999999 } } ] }.
2026-09-26T04:41:36+00:00  info: Accounting.Consumer[174880625]
2026-09-26T04:41:36+00:00        Order details: { "orderId": "8e69779a-b964-11f1-a862-4659f9156b51", "shippingTrackingId": "d341e8f2-7399-42fd-80ff-41107732f1a5", "shippingCost": { "currencyCode": "USD", "units": "35", "nanos": 960000000 }, "shippingAddress": { "streetAddress": "410 Terry Ave N", "city": "Seattle", "state": "WA", "country": "United States", "zipCode": "98109" }, "items": [ { "item": { "productId": "L9ECAV7KIM", "quantity": 4 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } } ] }.
2026-09-26T04:41:39+00:00  info: Accounting.Consumer[174880625]
2026-09-26T04:41:39+00:00        Order details: { "orderId": "908fabbd-b964-11f1-a862-4659f9156b51", "shippingTrackingId": "ee53a699-955e-4d6a-939b-45d96177c8db", "shippingCost": { "currencyCode": "USD", "units": "188", "nanos": 789999999 }, "shippingAddress": { "streetAddress": "1600 Amphitheatre Parkway", "city": "Mountain View", "state": "CA", "country": "United States", "zipCode": "94043" }, "items": [ { "item": { "productId": "LS4PSXUNUM", "quantity": 10 }, "cost": { "currencyCode": "USD", "units": "57", "nanos": 799999999 } }, { "item": { "productId": "HQTGWGPNH4", "quantity": 11 }, "cost": { "currencyCode": "USD", "nanos": 990000000 } } ] }.
2026-09-26T04:41:44+00:00  info: Accounting.Consumer[174880625]
2026-09-26T04:41:44+00:00        Order details: { "orderId": "934542ec-b964-11f1-a862-4659f9156b51", "shippingTrackingId": "fc628fde-7034-49ca-8104-7c27dbab503a", "shippingCost": { "currencyCode": "USD", "units": "8", "nanos": 990000000 }, "shippingAddress": { "streetAddress": "2200 Mission College Blvd", "city": "Santa Clara", "state": "CA", "country": "United States", "zipCode": "95054" }, "items": [ { "item": { "productId": "L9ECAV7KIM", "quantity": 1 }, "cost": { "currencyCode": "USD", "units": "21", "nanos": 949999999 } } ] }.
2026-09-26T04:41:57+00:00  info: Accounting.Consumer[174880625]
2026-09-26T04:41:57+00:00        Order details: { "orderId": "9b0a3b1e-b964-11f1-a862-4659f9156b51", "shippingTrackingId": "d38a3cfe-1fe7-48b7-81e2-a6ef4abdd845", "shippingCost": { "currencyCode": "CAD", "units": "252", "nanos": 632916408 }, "shippingAddress": { "streetAddress": "150 Elgin St", "city": "Ottawa", "state": "ON", "country": "Canada", "zipCode": "K2P1L4" }, "items": [ { "item": { "productId": "1YMWWN1N4O", "quantity": 5 }, "cost": { "currencyCode": "CAD", "units": "173", "nanos": 895055285 } }, { "item": { "productId": "9SIQT8TOJO", "quantity": 6 }, "cost": { "currencyCode": "CAD", "units": "4816", "nanos": 70057496 } }, { "item": { "productId": "L9ECAV7KIM", "quantity": 10 }, "cost": { "currencyCode": "CAD", "units": "29", "nanos": 372808491 } } ] }.
2026-09-26T04:42:03+00:00  info: Accounting.Consumer[174880625]
2026-09-26T04:42:03+00:00        Order details: { "orderId": "9ede89d3-b964-11f1-a862-4659f9156b51", "shippingTrackingId": "4d8512df-7f35-4bce-a562-7277ff5266eb", "shippingCost": { "currencyCode": "USD", "units": "8", "nanos": 990000000 }, "shippingAddress": { "streetAddress": "One Apple Park Way", "city": "Cupertino", "state": "CA", "country": "United States", "zipCode": "95014" }, "items": [ { "item": { "productId": "0PUK6V6EV0", "quantity": 1 }, "cost": { "currencyCode": "USD", "units": "175" } } ] }.
```

_478 further lines are in the bundle._

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

The page was a single alert, `ServiceHighErrorRate` on **accounting**, 3m46s after the trouble
started. Nothing else fired then, and nothing else fired afterwards. Its error ratio had read
zero before the incident. It rose from about a minute and a half in, climbed, and settled at
**exactly one third** of its spans once the rate window filled. It held there, flat, until the
fix.

Nothing around accounting moved. Its own request rate held at its usual level, a little under
half a request a second, and its latency did not change. Checkout was placing orders at its
usual rate. The storefront showed nothing, and neither did the other services that read and
write the same database.

### What was checked

**Whether accounting was down, restarting or starved.** It was not. Its .NET runtime series never
dropped out, and it kept taking orders off the topic at the rate it always does. A service that
pages on errors while its traffic and latency look normal is one that is running and failing at
something specific. The container had been recreated at the start of the incident, and it had
been running normally since.

**Its logs, first over the whole incident.** The log tool returns the oldest and newest lines of a
window. From the start to the fix, the oldest were the service's own startup banner and
environment dump, the trace of the recreate, and the newest were the bottom of one stack trace:
`SqlState: 28P01`, `MessageText: password authentication failed for user "otelu"`. The exception's
name and the label around it were in the forty lines above, in the part the tool does not return.
Narrowed to the minute after the start, the log was unambiguous. Every order accounting received
was followed by `fail: Accounting.Consumer … Order parsing failed:` wrapping `Npgsql.PostgresException:
28P01: password authentication failed for user "otelu"`, about forty lines of stack trace per
order. Every order in that minute failed the same way, and none before the change had.

**A library error on the way.** Just before the first failure the log says `Cannot load library
libgssapi_krb5.so.2`. That reads like a broken image, but it appeared once, the orders before the
change had not needed it, and the failures after it all name the password. It is the database
driver reaching for another way to authenticate after the password was refused, not the cause.

**The "Order parsing failed" label.** It reads like a malformed message on the orders topic,
something checkout started producing, and that is the dead end it invites. The other consumer of
the same topic answered it: fraud-detection read the same orders throughout with no change in its
errors or latency. The messages were fine. The label is the consumer's catch-all, and the
exception inside it is the real error.

**The database.** Postgres was up and serving. product-catalog and product-reviews, which use the
same database, showed no change in errors or latency. The database was healthy and one client
could not get in.

**The traces.** Each order is three spans: `order-consumed`, `orders receive`, and a `CONNECT otel`
to the database. The connect span was the error, and its status read `28P01`, the Postgres code
for a failed password authentication. The consumer span around it did not error. That is also
the one-third: one span of three fails on every order, so an error ratio of exactly 0.333 means
every order was failing, not a third of them.

**Its runtime counters.** `PostgresException` in the .NET exception counter climbed at about two a
second through the incident, from nothing: the counter did not exist before the change. That is
many times the rate orders arrive, so each failure is counted more than once on its way up.

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
alert cleared 4m02s after the fix. Nothing fired during recovery.

Class of fix: **config_revert**. Nothing was deployed and no code was wrong. One configuration
value was wrong, and it was set back.

### Detection notes

- Onset to first page: **3m46s**. Services on the page: **one**. By the fix: **one**.
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
