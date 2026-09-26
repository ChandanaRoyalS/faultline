---
origin: scenario:v2-accounting-kafka-misconfig
split: holdout
fault_class: bad_config
recorded_from: 2026-09-26T06:42:40+00:00
capability: cap:d2b243e0
onset_to_page: 7m47s
page_to_fix: 5m00s
fix_to_all_clear: 1m01s
---

# Accounting pointed at a Kafka port where nothing listens

## What was observed

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

## What was checked

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

## Root cause

Accounting's `KAFKA_ADDR` was changed to a port on the Kafka host where nothing listens. The service
came up normally, subscribed, and then waited for orders from a broker it could never reach, its
client retrying and logging the failure many times a second. It did not crash, so it did not
restart. Kafka was healthy, checkout kept publishing orders and fraud-detection kept reading them.
Nothing calls accounting, so nothing failed: orders simply stopped being recorded. The only signal
the alerting could see was accounting's own traffic going to zero. The fault was the broker address
accounting held.

## Resolution

`KAFKA_ADDR` was set back to Kafka's address and accounting was recreated with it. It rejoined its
consumer group and resumed from the last order it had committed. In the first minute after the fix
it logged **116** orders, against 6 to 11 in a normal minute: the same number fraud-detection had
read during the incident and that minute together. Each took about a millisecond, with its database
write beneath it. The group's lag was zero afterwards. The orders written during the incident were
**delayed, not lost**. The alert cleared 1m01s after the fix, and nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

## Detection notes

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
