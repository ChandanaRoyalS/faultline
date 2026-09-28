---
origin: scenario:v2-fraud-detection-partition
split: dev
fault_class: network_partition
recorded_from: 2026-09-28T09:56:37+00:00
capability: cap:91279a09
onset_to_page: 7m46s
page_to_fix: 5m00s
fix_to_all_clear: 1m00s
---

# Fraud detection is cut from the network - its process runs and reaches nothing

## What was observed

The page came 7m46s after onset and it was one line: `ServiceNoTraffic` on **fraud-detection**.
Nothing before it, nothing beside it, nothing after it. One alert on one service by the fix, and
the world all clear 1m00s after the fix.

Nothing else in the world had moved. The storefront served at its usual speed: the frontend's
error ratio zero and its p95 41 to 45ms, the proxy's and the load generator's the same; checkout
ran at 2.0 to 2.5 requests a second and 119 orders completed while the fault held; cart, the
catalog, recommendation, currency, shipping, payment, email all within their usual range.
Accounting - which reads the same orders topic fraud-detection reads - kept consuming at its
usual rate, its error ratio zero. Not one request anywhere hung or failed.

What had changed was fraud-detection alone. Its span rate went from about 0.3 a second to nothing
by T+4, and from then until the fix it had no error ratio and no latency value at all: no samples,
not zero errors. A consumer had stopped consuming, and that was the whole of what the alerts and
the dashboards could say.

## What was checked

**The alert, and what it does not say.** A service with no traffic is one of two things: a
service that has stopped, or a service that nothing is feeding. Fraud-detection has no callers -
it is not a service anyone requests from; it reads orders off a Kafka topic - so there was no
hung call in any trace to point at it and no caller whose latency or errors could implicate it.
Orders were still being placed, so the topic was still being fed. That leaves stopped.

**Its own view of itself.** Its 52 runtime series - JVM threads, classes, memory pools, garbage
collection - had stopped at the onset: the last report is the one before it, they held for the
store's lookback and dropped out of queries at T+4, and nothing replaced them until 29 seconds
after the fix. A consumer that is merely idle keeps sending its runtime reports on a timer. This
one had stopped reporting on itself as well as on its orders.

**Its log.** At rest fraud-detection writes one line per order it consumes, about ten a minute:
`Consumed record with orderId ..., and updated total count to ...`. The last of those came nine
seconds before the onset, and then no more. What replaced them was the agent that ships its
telemetry, writing at ERROR to the same console: `Failed to export metrics. The request could not
be executed` twelve seconds in, on a request that timed out; then the same failure once a minute,
at 46 seconds past every minute, for as long as the fault held, and the cause had changed:
`UnknownHostException: otel-collector`. The process could no longer even resolve the name of the
collector it had been sending to a minute earlier. Two more failures, on spans, at T+1 and T+11,
as spans closed with nowhere to go. Fifteen failures, thirty-two lines of the agent's own, every
one of them the fault's; none in the five minutes before it. It was running. It was trying to
send. Nothing it sent had anywhere to go - and nothing, orders included, was reaching it.

**Kafka and the rest.** Kafka had not restarted; accounting was reading the topic without
trouble. Flagd, which fraud-detection asks for a flag on every order, was serving everyone else.
Nothing upstream of fraud-detection was wrong; it was fraud-detection that could not reach
anything.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

## Root cause

The fraud-detection container was disconnected from the demo network. The process kept running,
on an address nothing could reach, and nothing it tried to reach answered. Nothing calls
fraud-detection - it consumes orders from Kafka - so no request anywhere hung or failed: the
storefront served, every order completed, accounting read the same topic as before, and the
only visible change in the world was that one consumer stopped consuming and stopped reporting.
Fraud-detection itself was alive the whole time and said so in the only place it could still
write, its own log: its order lines stopped and its export failures began at the same moment.
Nothing about it had been changed.

## Resolution

The container was put back on its network under its original names. Where an operator cannot
reconnect a container with its aliases, recreating or restarting it does the same job. Class of
fix: **restart**. Nothing was deployed or misconfigured, so there was nothing to roll back or
revert.

The recovery had a wave of its own, on fraud-detection alone. It was reading its topic again 2.6
seconds after the fix, and the orders it had missed came back as a single batch under one
receive span of nineteen seconds. Inside that batch, the first sixty-odd orders each took 500
milliseconds and ended in error: their flag lookup into flagd failed at its deadline, though
flagd itself answered in under a millisecond, because the provider's connection to flagd had
gone stale during the cut and took that long to notice and recover. The remaining orders in the
batch processed in a fraction of a millisecond each. So fraud-detection's error ratio read 33%
and its p95 780ms from T+13 to the end of the record, on a trace that was itself the recovery.
The no-traffic alert cleared 29 seconds after the fix and the world was all clear at 1m00s; whether an
error-ratio or latency rule then held on the recovery's numbers is not recorded, because the
record ends two minutes after the all-clear. The broker did not restart; nothing
else in the world noticed the fix any more than it had noticed the fault.

## Detection notes

- Onset to first page: **7m46s**, the no-traffic window draining. Nothing faster was available:
  no caller, so no latency and no error rate to cross a line.
- Services on the page: **one, the culprit.** By the fix: **one alert on one service.**
- Alerts that fired only during recovery: **none on record** - see the resolution.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one that made
  a sound: one no-traffic alert.
- Would the page alone have led you to the right service? **To the right service, not to the
  right fault.** The page named fraud-detection; it could not say whether fraud-detection had
  stopped, been starved, or been cut off. The runtime reports settled the first; the log settled
  the rest.
- **A consumer's silence has no cascade.** Nothing waits on a Kafka consumer, so a cut-off one
  takes nothing down with it: no timeouts, no error ratios, no latency anywhere. The only signals
  are its own - its span rate, its runtime reports, its log. Read them, because there is nothing
  else to read.
- **Silence alone is also what "nothing to consume" looks like.** Confirm the topic is still
  being fed (here: orders completing, accounting consuming) before concluding the consumer has
  stopped.
- **The runtime reports separate stopped from idle. The log separates stopped from cut off.** A
  frozen process writes nothing; a crashed one writes a start-up; a cut-off one keeps writing that
  it cannot reach anything, on its export schedule, with a name that stopped resolving.
- **The recovery's errors are the recovery's.** A backlog consumed in one batch, with a stale
  connection to a dependency failing until it recovers, puts an error ratio and a latency on the
  culprit in the minutes after the fix that it never had during the fault. Errors that begin at
  the fix are not a second fault.
