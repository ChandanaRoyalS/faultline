---
origin: scenario:v2-kafka-disk-fill
split: dev
fault_class: disk_fill
recorded_from: 2026-09-29T02:30:05+00:00
capability: cap:91279a09
onset_to_page: 6m15s
page_to_fix: 5m00s
fix_to_all_clear: 4m02s
---

# The broker's only disk is full - it halts, cannot start again, and every order hangs

## What was observed

The page came 6m15s after onset: `ServiceHighLatency` on **checkout**. Thirty seconds later
`ServiceHighErrorRate` on checkout; at T+2m from the page `ServiceNoTraffic` on **accounting**; at
T+3m `ServiceHighErrorRate` on **fraud-detection**, and a minute after that its
`ServiceHighLatency`. Five alerts on three services by the fix, and none of them on the service
that was broken, which has no rule of its own and no requests to fail.

Checkout's 95th percentile went to the histogram's ceiling, **15000ms**, from T+3 and stayed there
to the fix. Its error ratio climbed from 2.4% at T+2 to 5.2% at T+4 and held between 6 and 7% to
the fix; its span rate fell from 2.0 a second to 1.4 to 1.8. Everything checkout calls answered as
it always does: cart, payment, shipping and email held their p95s at 2 to 6ms.

The storefront mostly looked well. The frontend's p95 rose from 33 to between 37 and 49ms and it
counted no errors of its own until the fix; product pages, carts, recommendations and ads served as
before. At the edge the proxy's error ratio rose to 3.1% and the load generator's to 3.5%, under
their line, and from T+9 their p95s went to 12 to 15 seconds: the requests being cut were
checkouts, at fifteen seconds.

The two services that read orders after checkout had gone quiet. Accounting's rate drained to zero
by T+5 with no error of any kind - no samples, not zero errors. Fraud-detection's drained the same
way, and then from T+7 to the fix its metrics held a single failing span: an error ratio of
**100%** and a p95 at the ceiling, on about one span in five minutes.

## What was checked

**Checkout, because it paged.** Its error traces were all orders, and all the same shape:
`PlaceOrder` prepared the order in a few milliseconds - cart, catalog, currency, shipping quote -
charged the card, booked the shipment, emptied the cart, sent the confirmation email, and then held
on its last step, `orders publish`, for 75 to 82 seconds, and ended that span in error with the
producer's own message: `kafka: client has run out of available brokers to talk to: dial tcp:
lookup kafka on 127.0.0.11:53: no such host`, or, once the client had given up trying, `circuit
breaker is open`. The `PlaceOrder` span above it was **not** in error. Every order the trace store
returned for the fault completed and none failed: checkout records the failed publish on its
producer span and returns the order as placed. Above them, the load generator's checkouts were cut
by the proxy's `ingress` in error at 15000ms, and the frontend's own calls into checkout held for 45
to 90 seconds - the customer was told the checkout failed, for an order that had been charged and
confirmed. Nothing else in any trace was slow; the hop that hung was the publish, every time, and
it named the broker.

**Accounting, because it went quiet.** Its consumption stopped in the fault's first seconds with
not one span in error, and its log filled with its client's complaints - 676 lines from the onset
to the fix, none of them an order. The first, five seconds in: `Disconnected: connection closed by
peer`, then `1/1 brokers are down` and `Connect to ipv4#172.18.0.24:9092 failed: Connection
refused` in the same second; `brokers are down` 433 times, `Connection refused` 84, and from
eighteen seconds in `Failed to resolve 'kafka:9092': Name or service not known`, 130 times, to the
last minute. The broker was not answering, and at moments its name did not even resolve.

**Fraud-detection, because it alerted last.** The other reader of the same topic wrote no line of
any kind from the onset to the fix - not the `Consumed record` line it writes for every order, not a
broker complaint - and the trace store held no trace of it that began in the fault. Its alerts came
from its metrics alone: one span, failing and at the ceiling, over a rate that had drained to
nothing. A consumer that goes silent everywhere says only that it is not consuming. Accounting said
why.

**Kafka's log, because everything pointed at it.** At rest it writes thirty to forty-five lines a
minute, all INFO, segment rolls and snapshots on its metadata log, every one naming
`dir=/tmp/kafka-logs`. Two seconds after onset it failed to write a metadata snapshot, `Caused by:
java.io.IOException: No space left on device`. At 4.7 seconds it wrote `ERROR Error while writing
to checkpoint file /tmp/kafka-logs/replication-offset-checkpoint`, `No space left on device` again
with its stack, `Stopping serving replicas in dir /tmp/kafka-logs ... because the log directory has
failed`, and then `ERROR Shutdown broker because all log dirs in /tmp/kafka-logs have failed`. The
broker had stopped itself, on purpose, and said why and where.

**Kafka's restarts.** Half a second after the shutdown, its container started again: seven lines
of start-up script - `===> User`, `===> Configuring ...`, `Running in KRaft mode...`, `===>
Launching ...`, `===> Using provided cluster id` - and under two seconds later one line of 494
characters. It begins with the JVM's warning and the tracing agent's version, and it ends:
`Formatting metadata directory /tmp/kafka-logs with metadata.version 3.9-IV0. Error while writing
meta.properties file /tmp/kafka-logs: java.nio.file.AccessDeniedException:
/tmp/kafka-logs/bootstrap.checkpoint.tmp`. Then nothing, until the next start. **Eighteen starts
before the fix** - at 5, 7, 9, 12, 15, 20, 28, 43 and 70 seconds and then every minute - each
ending on that same line, and no line of the broker's own after the shutdown. The restarts were not
failing on a full disk. They were failing to write to the directory at all: each start found it
there and could not create a file in it.

**Kafka's runtime reports.** Its 52 JVM series stopped with the halt - the last report is from the
minute before it, held for the store's lookback and gone from queries at about T+4:15. Behind them
were **nineteen instance ids that each reported seven series once and never again**: one for each
failed start, from the start-up step's short-lived JVM - the one whose line carries the agent's
banner and the format error - and a nineteenth fifteen seconds after the fix. A stopped service
has no runtime reports; this one had a fresh identity every minute.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on kafka, on
checkout, on either consumer or on anything else. The change history for the window is empty. A
disk filling is not a change anything records.

## Root cause

Kafka's only log directory filled to capacity. A broker whose every log directory has failed halts
itself within seconds - this one did at 4.7, naming the file it could not write and the directory
that had failed. Its supervisor then restarted it in place, and on this world that cannot work: the
restarted container's log directory is not writable by the broker's user, so every start failed on
its first step, formatting the directory, with access denied, and the broker stayed down until the
container was recreated. Checkout publishes every order to that broker as the last step of placing
it, after the card is charged and the confirmation sent, with no fallback: the publish waited on a
client with no broker to talk to, then on an open circuit breaker, and failed after more than a
minute - and checkout treats a failed publish as something to record, not as a failed order, so
the order was returned as placed and the customer-facing failures were the checkouts the proxy cut
at fifteen seconds. The two consumers of the topic had nothing to read: accounting said so in its
log and produced no spans, fraud-detection said nothing anywhere. Nothing was deployed, configured
or flagged; the broker's address, image and configuration were right all along. Its disk was full,
and a halted broker here does not come back without being recreated.

## Resolution

The fill could not be removed in place - the container was never up long enough for a command to
land - so the broker was recreated on an empty directory, and then accounting, fraud-detection and
checkout were restarted, because none of them reconnects to a broker that went away and came back.
Class of fix: **free_storage**, the disk-fill class's own; the restarts after it are the runbook's
second step, not a second fix. Restarting the broker as it stood would have changed nothing - its
supervisor had restarted it eighteen times - and there was no configuration to revert.

The recovery had one stumble and was otherwise clean. Checkout's restart dropped the calls the
frontend had been holding on it for up to ninety seconds - twelve `14 UNAVAILABLE: Connection
dropped` in the frontend's log 2.6 seconds after the fix. The new broker logged `Kafka Server
started` at 6.3 seconds. At 8.9 seconds checkout **panicked** on its first order - `invalid memory
address or nil pointer dereference` in `sendToPostProcessor` (`main.go:630`) under `PlaceOrder` -
having come up before the broker could answer and kept no producer; the frontend's one call in
flight dropped with it, and its container restarted it within a second, from when it served
normally. Accounting's first fetch, two seconds after the fix, got `Subscribed topic not available:
orders: Broker: Unknown topic or partition` - an empty broker has no topic until the first order
creates it - and its error ratio read 4.7% as it came back, on those fetches, then under 2%. Both
consumers were consuming again within two minutes, their rates climbing as their windows refilled;
no duplicate-key wave followed, because the recreated broker had no orders to redeliver. The alerts
cleared in the order they had come: fraud-detection's two by the fix, accounting's no-traffic 45
seconds after it, checkout's error rate at 1m45s and its latency at 3m45s as the held publishes
aged out of its window; all clear 4m02s after the fix. The frontend's error ratio read 1.5 to 2.4%
for four minutes after the fix, on the dropped calls, and its p95 14.7 seconds for one minute, under
its lines. No alert fired only in recovery; postgresql was untouched; the directory was at 1% after.

## Detection notes

- Onset to first page: **6m15s** - checkout's p95 at the ceiling for the latency rule's three
  minutes. The broker halted at T+4.7s; the world noticed six minutes later.
- Services on the page: **one**, the producer, not the culprit. By the fix: **five alerts across
  three services** - checkout twice, fraud-detection twice, accounting once - and the broker on
  none of them.
- Alerts that fired only during recovery: **none.**
- Did the loudest service turn out to be the culprit? **No.** Checkout paged first and longest; it
  was hanging on its last step. The broker, which was the fault, has no rule.
- Would the page alone have led you to the right service? **No, but one trace would.** The page
  said checkout was slow. Checkout's slow span was its publish, and the publish's error named
  `kafka`. The broker's own log named its disk in under five seconds.
- **A failing publish is not a failing order.** No order failed, every order was charged, and
  checkout's own server spans were clean while its producer spans were not. The customer-facing
  failures were the proxy's timeouts on orders that had already gone through. Read which spans
  carry the errors before concluding what the customer saw.
- **Two readers of one topic, two different silences.** Accounting said everything in its log and
  produced no spans; fraud-detection said nothing anywhere. Neither alone reads as a broker outage.
  Together they do: the only thing both depend on is the thing that is missing.
- **Read the restart's last line whole.** Each restart wrote seven short lines and then one long
  one whose beginning is a harmless JVM warning; the reason it failed is at its end, four hundred
  characters in. A log view that cuts lines short shows eighteen silent restarts. The whole line
  shows eighteen identical failures - and a different one from the halt: access denied, not no
  space.
- **A crashloop under an agent leaves a trail of identities.** The broker's 52 runtime series
  stopped at the halt, and one new instance id per start appeared behind them, seven series each,
  one report apiece. Count the instance ids.
- **The fix is neither a restart nor a revert.** The broker was restarted eighteen times by its
  supervisor and nothing was misconfigured. Free the directory - on this world, recreate the service
  on an empty one - and then restart what stopped consuming, because they will not come back on
  their own.
