# A9 — records that are not orders on the `orders` topic — RESULT

**Run 2026-09-30 03:05:19 → 03:26:52 UTC, \$0.** One run, `transcript.txt`, registered in
`evals/runs/PREREGISTRATION-T7.1-A9.md` before it was run. The verdicts are the pre-registered
definitions applied to the transcript and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **no - the fault paged nothing; the one page was the attempt's own tool** | Two alerts fired, both on `kafka`: `ServiceHighLatency/kafka` from 03:10:49 (+5:30) to 03:22:22, and `ServiceNoTraffic/kafka` from 03:25:52. The broker emits no spans at rest. In the shape at +11, `kafka` shows **0.100 requests a second - one every ten seconds, the writer's cadence** - at a 1380 ms p95. Every Kafka command run inside the broker's container starts a JVM with the tracing agent attached (the `otel.javaagent ... version: 2.23.0` line printed each time the transcript ran one: the writer, and each consumer-groups read), so the console producer that wrote the bad records reported its own sends as service `kafka`, and the no-traffic alert fired when they stopped. Neither alert is the fault's. **fraud-detection**, the consumer that died on the bad records, sat at **0.00 %** errors and a 92 ms p95, its rate down to 0.050 a second from about 0.28, and fired nothing; **accounting** fired nothing, as predicted; nothing else moved. |
| **DISTINCT** | **yes on (c), unused** | accounting's log carries `Order parsing failed:` and `Google.Protobuf.InvalidProtocolBufferException: Protocol message contained a tag with an invalid wire type.` with its stack into `Accounting.Consumer.ProcessMessage` (`Consumer.cs:line 90`), ten blocks in the transcript's read, while its `Order details` lines go on; fraud-detection's last lines are an uncaught stack through `AbstractParser.parseFrom` into `oteldemo.Demo$OrderResult.parseFrom` and `frauddetection.MainKt.main(main.kt:64)`, and its container restarted **14 times**. Both name a parse failure on the topic's contents - the class's shape - but no rule reads them. The transcript's whole-log read of fraud-detection returned nothing; why is not established, and nothing here rests on it. |
| **REVERTS** | **yes** | The writer ended on its own at 03:17:20. At that moment accounting was at lag 0 and fraud-detection's group had no active member (it was restarting) and lag 3; after `watch.py 10` both groups were at lag 0 at offset 2464, fraud-detection running since 03:18:59. The 72 records stay on the topic until retention or the broker's next recreate, read past by both groups. |
| **ADMISSIBLE** | **no** | It does not page on the world's own services. |

**Prediction scorecard.** PAGES on fraud-detection within eight minutes: **wrong** - it crashed and
restarted, and its spans neither failed nor stopped for long enough to meet a rule. Nothing on
accounting: right. DISTINCT on (c): right, as far as it goes. REVERTS: right; fraud-detection's
close did commit past the bad record, as read at source and left unverified before the run.

## Why fraud-detection died fourteen times and never paged

**72 bad records, 14 deaths.** The reading the transcript supports: fraud-detection dies on the
first bad record in a poll, its close commits the poll's position (both groups reached lag 0), and
a restart - a JVM start, an agent, a group join - takes long enough that several records, good and
bad, have accumulated by the next poll; it dies on the first bad one again, having skipped the
rest. Between deaths it consumes, so its rate fell without reaching zero, and none of its spans
ended in error (0.00 %) - the exception leaves `main`, and whatever span it interrupts is not
recorded as failed. No error ratio rose and no service went silent: the one consumer that fails
loudly in its log fails quietly in its metrics.

## What the page that did fire shows

**The attempt's own tool reports as the target.** The broker's container runs every JVM with the
tracing agent, and Kafka's command-line tools are JVMs: the console producer's sends and the
consumer-groups reads became `kafka` spans, enough to fire a latency alert and then a no-traffic
alert. An injector tool built on those commands would page on itself and name the broker - the
attacker's instrument in the telemetry, a leak no scenario may carry. Recorded as **Q118**: any
Kafka command run inside that container must run without the agent, or not there at all, and the
world was left with `ServiceNoTraffic/kafka` firing at the end of the transcript, from the attempt's
own reads.

## What A9 decides

By the pre-registered rule - *if it does not page, the finding is recorded and row 2 is blocked* -
**`v2-kafka-orders-corruption` is blocked**, and `datastore_corruption` row 2 stays empty with it.
The record is this attempt; no scenario file exists to mark. A second attempt with a changed
parameter, as A4b followed A4 (bad records at a cadence that keeps fraud-detection down, written
without the agent), would be a new registration and a decision for the row, not a re-run of this one.
