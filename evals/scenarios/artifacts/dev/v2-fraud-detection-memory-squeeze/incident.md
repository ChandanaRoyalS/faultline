---
origin: scenario:v2-fraud-detection-memory-squeeze
split: dev
fault_class: resource_exhaustion
recorded_from: 2026-09-27T13:32:34+00:00
capability: cap:d2b243e0
onset_to_page: 7m15s
page_to_fix: 5m00s
fix_to_all_clear: 1m01s
---

# Fraud detection memory limit cut below what its JVM needs to run

## What was observed

One alert. `ServiceNoTraffic` on **fraud-detection**, 7m15s after the trouble started. Nothing
else fired for the entire incident, and nothing fired after the fix.

The store was perfect throughout. The frontend, frontend-proxy and the load generator recorded no
errors and no change in latency; checkout placed orders at its usual rate, payment charged them,
accounting recorded them at its usual 0.3 to 0.5 spans a second with its usual 90ms. Not one error
ratio on the world moved, apart from the flag readers' routine sliver. Orders were being placed,
charged, shipped, confirmed and booked the whole time.

What was missing was one consumer. Fraud-detection's span rate had been about 0.25 a second. It
was 0.14 a minute in, 0.06 at three, and nothing from four; from then on its error ratio and its
latency had no value at all. It had recorded nothing unusual before its numbers ran out: no error
of its own, no rise in latency.

This is the slowest page on this world and the smallest.

## What was checked

**Whether anyone was missing it.** No one. Nothing calls fraud-detection: it reads orders off the
same Kafka topic accounting reads, and checkout publishes an order and moves on. So checkout had
no failed call to show, accounting kept consuming - 115 orders logged over the fault, 2 to 15 a
minute, exactly the orders checkout published - and the only trace of anything wrong was the
absence of fraud-detection's own consumer spans: not one `orders receive` or `orders process` in
the fault, against 108 orders published.

**Fraud-detection's log, which is where it breaks open.** Its last ordinary line came 23 seconds
before the trouble began - `Consumed record with orderId ...` - and eight seconds after it began,
the JVM was starting: `Picked up JAVA_TOOL_OPTIONS`, the OpenJDK class-sharing warning, the
OpenTelemetry agent announcing its version. Then, three seconds later, the same three lines again.
**Nineteen times** in twelve minutes: seven starts in the first 50 seconds, then the gaps growing
- 15, 29, 54 seconds - to once a minute. Not one reached the application's own start-up, and not
one consumed a record. No line explains a failure: no exception, no stack trace, no out-of-memory
message from the JVM, no shutdown. A process that keeps starting and never says why it stopped is
a process being killed from outside, and a runtime backing off between attempts is what the gaps
are.

**Whether it was idle or absent.** Its 51 JVM runtime series - heap by pool, threads, garbage
collection, CPU - held their last values for four minutes, the store's lookback, and then vanished,
and no new instance's series appeared before the fix. A process that is merely idle keeps exporting
them; these stopped when the log says the first kill came, and read on for four minutes only
because the store serves a last value forward. The series answer *whether*, the log answers *when*.

**Why it never came back.** At rest fraud-detection was a JVM holding about 256MB in a 500M
container: a heap capped at 122MB by its own settings, 100MB of non-heap - the agent's
instrumentation, the code cache - and about 90MB the container held outside the JVM altogether.
Nineteen restarts in a row, each dying within seconds of loading the agent, is a JVM that cannot
fit its own start-up into what it is now allowed. Nothing about how much it needed had changed.
What it was allowed had.

**What changed.** No deploy, no image change - the same `2.2.0-fraud-detection` before and after -
no environment change, no flag. And one record, at the start, under fraud-detection's name:
`memory limit lowered on fraud-detection`, to `memory=160m`, from 500M. The record names the
cause, and it is the only kind of change on this world that leaves a process's image and
configuration exactly as they were and kills it anyway.

**The flag readers' sliver.** A dead end. Fraud-detection's own error ratio had read 1.4 to 2.0% in
the four minutes before the trouble, and flagd's under 1% then and again six to ten minutes in: the
flag service's routine ten-minute stream reconnect, which every flag reader shows and none of them
pages on. The only error traces in the fault were three of those stream closes, on ad,
recommendation and product-reviews. Nothing near a line, and nothing to do with orders.

## Root cause

The fraud detection container's memory limit was lowered from 500M to 160m, below the 256MB
working set of its JVM and below what a fresh JVM needs to load its instrumentation agent and
start at all. The kernel killed the running JVM within seconds, the restart policy brought it
back, and every new JVM was killed again before it could consume - nineteen times, with the
runtime backing off to once a minute - so orders went unchecked for fraud for the whole fault.
Nothing calls fraud-detection, so nothing else noticed: the storefront, checkout and accounting
were untouched, and the orders it missed waited for it in Kafka.

## Resolution

The memory limit was restored to 500M. The next JVM start, 25 seconds after the fix, was the first
in twelve minutes to run, and three seconds after that it began working through the backlog: dozens
of `Consumed record` lines in a single second, 157 in the five minutes after the fix against 46 in a
normal five, its span rate at 0.5 to 0.7 a second against its usual 0.25, until it had caught up on
every order published while it was gone. Its no-traffic alert cleared within a minute of the fix,
and everything was quiet 1m01s after it. Nothing fired during recovery.

Class of fix: **config_revert**. The container's resource limit was wrong and it was set back.
Restarting fraud-detection was what the runtime had already been doing, nineteen times; rolling
back its image would have changed nothing, because the image was never the problem.

## Detection notes

- Onset to first page: **7m15s**, the no-traffic window draining. Services on the page: **one**,
  fraud-detection, the culprit. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one, and it was
  not loud: its only alert was silence.
- Would the page alone have led you to the right service? **Yes.** Nothing else was named, and
  nothing else was wrong.
- **A consumer that nobody calls dies silently.** No caller errors, no latency anywhere, no queue
  visible to the tools: the only sign is the consumer's own traffic going to nothing. The page for
  this fault is the absence of a service, and it arrives only when a window has drained.
- **A truncated, repeating start-up is a process being killed from outside.** Nineteen JVM
  banners with nothing after them, at growing intervals, and no error anywhere: nothing inside the
  process decided to stop.
- **A killed process has no last words, so the cause is in what changed, not in what it said.** The
  change record names a memory limit; the log names nothing. The two together are the whole story.
- **Runtime series that stop do not stop at once.** They held their last values for four minutes
  before vanishing; the log dates the first kill to the eighth second. Read the stop time off the
  log, not off the series.
- **A consumer's missed work is not lost work.** The orders it missed were still on the topic, and
  it consumed them all in the first seconds back. Its rate after the fix was twice its usual: the
  size of the backlog, not a second fault.
