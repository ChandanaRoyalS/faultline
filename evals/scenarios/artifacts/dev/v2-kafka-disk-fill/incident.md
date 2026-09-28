---
origin: scenario:v2-kafka-disk-fill
split: dev
fault_class: disk_fill
recorded_from: 2026-09-28T13:54:45+00:00
capability: cap:91279a09
onset_to_page: 5m31s
page_to_fix: 5m00s
fix_to_all_clear: 3m02s
---

# The broker's only disk is full - it halts and restarts, halts again, and every order hangs

## What was observed

The page came 5m31s after onset and it named the wrong service: `ServiceHighErrorRate` on
**fraud-detection**, a consumer of orders that nobody calls. Forty-five seconds later
`ServiceHighErrorRate` on **checkout**, and at the minute `ServiceHighLatency` on both; then
`ServiceNoTraffic` on **accounting** at T+2m from the page, and on fraud-detection at T+5m,
seconds before the fix. Six alerts on three services by the fix, and not one of them on the
service that was broken, which has no rule of its own and no requests to fail.

The storefront looked well. The frontend's error ratio read zero for the whole fault and its p95
sat at 36 to 47ms; product pages, carts, recommendations and ads served as before. At the edge,
the proxy's error ratio rose to 2.4% and the load generator's to 2.8%, both under their line -
64 requests in ten minutes cut at the proxy's fifteen-second timeout, every one of them a
checkout. Checkout's own 95th percentile went to the histogram's ceiling, **15000ms**, from T+3
and stayed there; its error ratio climbed from 2.7% at T+2 to a peak of 7.7% at T+5 and held
between 6 and 7% to the fix; its span rate fell from 2.5 a second to 1.1 to 1.5.

And yet **no order failed**. 115 orders completed in the fault's ten and a half minutes, zero
ended in error, and every one of them was charged, shipped and confirmed by email. Something in
checkout was slow and failing without failing the order, and the two services that read orders
after checkout had gone quiet: accounting's rate to zero by T+4 with no error of any kind - no
samples, not zero errors - and fraud-detection's error ratio to **100%** from T+4, then to
nothing at all from T+7.

## What was checked

**Fraud-detection, because it paged first.** It has no callers; it reads orders off a topic. Its
error ratio at 100% meant every span it produced was failing, and from T+7 it produced none. Its
log had nothing to say about that: its `Consumed record` lines, one per order, stopped in the
fault's first seconds, and it wrote no line of any kind for the rest of it. A consumer that fails
loudly in its spans and silently in its log.

**Accounting, because it went quiet next.** The other reader of the same topic, and the mirror
image: its consumption stopped in the same first seconds - its rate read zero once the
five-minute window had drained, at T+4 - with not one span in error, while its log filled with
its client's complaints - 723 lines in ten minutes, `1/1 brokers are down` and `2/2 brokers are
down` from 6.4 seconds after onset and every few seconds after, `Connect to ipv4#172.18.0.2:9092
failed: Connection refused`, and `Failed to resolve 'kafka:9092': Name or service not known`.
Both consumers were saying the same thing in different places: the broker they read from was not
there, and at moments its name did not even resolve.

**Checkout's traces, because it paged second and its p95 was at the ceiling.** 60 error traces
in the fault, all of them orders. Each one the same shape: `PlaceOrder` prepared the order in a
few milliseconds - cart, catalog, currency, shipping quote - charged the card, booked the
shipment, emptied the cart, sent the confirmation email, and then held on its last step,
`orders publish`, for 2.8, 15, 77, 80, 89 seconds, and ended that span in error with the
producer's own message: `kafka: client has run out of available brokers to talk to: dial tcp:
lookup kafka on 127.0.0.11:53: no such host`, and once the client had given up trying,
`circuit breaker is open`. The `PlaceOrder` span above it was **not** in error: checkout logs the
failed publish, marks its producer span, and returns the order as placed. Above the ones that
took longer than fifteen seconds, the proxy's `ingress` in error at 15000ms - the customer was
told the checkout failed, for an order that had been charged and confirmed. Nothing else in any
trace was slow; the hop that hung was the publish, every time.

**Kafka's log, because everything pointed at it.** At rest it writes about fifty lines a minute,
all INFO, segment rolls and snapshots on its metadata log, every line naming `dir=/tmp/kafka-logs`.
Five seconds after onset it wrote `ERROR Error while writing to checkpoint file
/tmp/kafka-logs/replication-offset-checkpoint`, `java.io.IOException: No space left on device`
under it with the stack, `Stopping serving replicas in dir /tmp/kafka-logs`, and then
`ERROR Shutdown broker because all log dirs in /tmp/kafka-logs have failed`. The broker had
stopped itself, on purpose, six seconds into the fault, and said why and where.

**Kafka's restarts.** One second after the shutdown, its container's start-up: `===> User`,
`===> Configuring ...`, `Running in KRaft mode...`, `===> Launching ...`, the JVM's one warning -
nine lines - and then nothing. No `Kafka Server started`, no error, not a line of the broker's
own. Three seconds later the same nine lines again. Seventeen starts in ten and a half minutes,
at 6, 9, 11, 14, 18, 23, 32 and 47 seconds and then about once a minute as the supervisor's
backoff reached its ceiling, each one nine lines and silence. The restart count on the container
climbed to 19. The broker was not down; it was being started every minute against a directory it
could not write, and dying before it could say so.

**Kafka's own runtime reports.** Its 52 JVM series - memory pools, garbage collection, threads -
had stopped at the halt: the last report is from the six seconds before it, they held for the
store's lookback and dropped out of queries at T+4:30. What replaced them was stranger and more
telling: every restarted JVM reported **once**, seven series under a **new instance id**, and was
gone - nineteen instance ids in ten minutes, one per start, each a single report held for the
lookback. A service that has stopped reports nothing. A service that is crashlooping under an
agent reports a fresh identity every backoff.

**The disk.** The broker's directory sits on its own 256 MiB filesystem; it was at 10% an hour
before and at 100% from the onset to the fix, with one file in it that had not been there before.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on kafka, on
checkout, on either consumer or on anything else. The change history for the window is empty. A
disk filling is not a change anything records.

## Root cause

Kafka's only log directory filled to capacity. A broker whose every log directory has failed
halts itself within seconds - this one did at six, naming the file it could not write and the
directory that had failed - and its supervisor then restarted it against the same full directory
seventeen times, each start dying in about two seconds before the broker could log a line.
Checkout publishes every order to that broker as the last step of placing it, after the card has
been charged and the confirmation sent, with no fallback: the publish waited on a client with no
broker to talk to, then on an open circuit breaker, and failed after tens of seconds - but
checkout treats a failed publish as something to log, not as a failed order, so the order was
returned as placed and the only customer-facing failures were the checkouts the proxy cut at
fifteen seconds. The two consumers of the topic had nothing to read: fraud-detection's client
failed every fetch in its spans and said nothing in its log, accounting's said everything in its
log and produced no spans at all. Nothing was deployed, configured or flagged; the broker's
address, image and configuration were right all along. Its disk was full.

## Resolution

The fill could not be removed in place - the container was never up long enough for a command
to land - so the broker was recreated on an empty directory, and then accounting, fraud-detection
and checkout were restarted, because in this world none of them reconnects to a broker that went
away and came back. Class of fix: **free_storage**, the disk-fill class's own; the consumer
restarts are the runbook's second step, not a second fix. Restarting the broker as it stood would
have changed nothing - it had been restarted seventeen times - and there was no configuration to
revert.

The recovery was clean and it was quick. The new broker logged `Kafka Server started` 7 seconds
after the fix; accounting's first fetch, half a second later, got `Subscribed topic not
available: orders: Broker: Unknown topic or partition` - an empty broker has no topic until the
first order creates it - and its first order line came 21 seconds after the fix, fraud-detection's
in the same second. Both consumers' rates climbed back through the third and fourth minutes as
their windows refilled; accounting's error ratio read 3.3% in its second minute back, on the
fetches that found no topic yet, and fell from there. No duplicate-key wave followed the consumer
restarts: the recreated broker had no orders to redeliver. The alerts cleared in the order they
had come - both no-traffic alerts 44 seconds after the fix, checkout's error rate at 1m44s, its
latency at 2m44s as the held publishes aged out of its window - and the world was all clear
3m02s after the fix. One trace closed after the fix that had begun before it, a publish held for
99 seconds; the frontend's error ratio read 1.4 to 1.8% for four minutes after the fix, on twelve
checkout calls it had held through the fault that ended in error when they finally returned
after 17 to 91 seconds, and its p95 read 3150ms for one minute on the same, under its line.
Neither consumer restarted again; postgresql was untouched.

## Detection notes

- Onset to first page: **5m31s** - fraud-detection's error ratio at 100% for the rule's two
  minutes. The broker halted at T+6s; the world noticed five and a half minutes later.
- Services on the page: **one**, a consumer with no callers, not the culprit. By the fix: **six
  alerts across three services** - checkout twice, fraud-detection three times, accounting once
  - and the broker on none of them.
- Alerts that fired only during recovery: **none.** Fraud-detection's no-traffic alert fired one
  second before the fix and cleared 44 seconds after it.
- Did the loudest service turn out to be the culprit? **No.** Fraud-detection paged first and
  most; it was starved. Checkout paged second and longest; it was hanging on its last step. The
  broker, which was the fault, has no rule.
- Would the page alone have led you to the right service? **No.** The page named a consumer
  that had stopped consuming; a consumer that stops looks the same whether it broke, was
  starved, or was cut off. The second page named the producer. What the two have in common is
  the broker between them, and the broker's own log named its disk in the sixth second.
- **Two readers of one topic, two different silences.** Fraud-detection failed in its spans and
  said nothing in its log; accounting said everything in its log and produced no spans. Neither
  alone reads as a broker outage. Together they do: the only thing both depend on is the thing
  that is missing.
- **A failing publish is not a failing order.** No order failed, every order was charged, and
  checkout's own server spans were clean while its producer spans were not. The error ratio that
  paged was made of the publish spans, and the customer-facing failures were the proxy's
  timeouts on orders that had already gone through. Read which spans carry the errors before
  concluding what the customer saw.
- **A crashloop under an agent leaves a trail of identities.** The broker's 52 runtime series
  stopped at the halt, and nineteen new instance ids appeared behind them, seven series each,
  one report apiece. A stopped service has no runtime reports; a restarting one has a new set
  every backoff. Count the instance ids.
- **The restarts said nothing, and that was the clue.** Seventeen starts, nine lines each, no
  `Kafka Server started` and no error. A broker that starts and cannot write its directory dies
  before it can log the reason; the reason is in the one halt that did get logged, and in the
  disk.
- **The fix is neither a restart nor a revert.** The broker had been restarted seventeen times
  by its supervisor and nothing was misconfigured. Free the directory - or recreate the service
  on an empty one - and then restart what stopped consuming, because they will not come back on
  their own.
