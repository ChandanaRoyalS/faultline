---
origin: scenario:v2-payment-memory-squeeze
split: dev
fault_class: resource_exhaustion
recorded_from: 2026-09-27T20:17:54+00:00
capability: cap:d2b243e0
onset_to_page: 9m46s
page_to_fix: 5m00s
fix_to_all_clear: 0s
---

# Payment service memory limit cut to what its runtime can barely run in

## What was observed

One alert. `ServiceHighLatency` on **payment**, 9m46s after the trouble started. It fired for
45 seconds and cleared on its own, four minutes before the fix, and nothing fired after it.

Payment's p95 had been 4ms. Within the first half-minute it read 18ms, then 26 to 28ms for the
next three and a half minutes, then 5ms for a minute and a half, then **430 to 450ms** for four
minutes straight, which is what paged. It dropped to 3ms at T+10:30, read 93ms a minute later, and
was back at 420 to 460ms from T+12:30 until the fix. Nothing else on the world moved. Checkout's
p95 stayed between 35 and 45ms, the storefront's at its usual 42 to 50ms, and every call rate held:
payment served 0.25 to 0.34 charges a second the whole time, checkout placed orders at its usual
rate, and 122 orders completed in the fourteen and three-quarter minutes of the incident.

There were a few errors. Checkout's error ratio read 0.4 to 0.5% in the first four minutes, zero
for the next seven, and 1.7 to 2.4% from T+11 to the fix - six failed orders in all - and the
frontend's, the proxy's and the load generator's never passed 0.8%. Payment's own error ratio was
zero throughout: it never returned an error, it was slow.

## What was checked

**Whether payment was slow or absent.** Slow, with interruptions. Its rate never dipped, its
server spans are present in every minute, and its 75 runtime series - event loop, V8 heap by
space, garbage collection - never stopped. That rules out a dead service; a dead service has no
spans and no series. But the series were not one process's: the garbage-collection and event-loop
counters reset again and again through the incident, which a single process never does.

**Payment's log, which says when.** It shows `payment gRPC server started on 0.0.0.0:50051`
thirteen times: 3 seconds after onset, then at T+1:04, then in pairs and bursts - two at T+6:05
and T+6:12, four between T+10:43 and T+11:10, five between T+14:03 and T+14:37. Between them,
ordinary charge records, 369 across the incident. Before every one of the thirteen, **nothing**:
no shutdown line, no error, no exception, no last request. A process that starts thirteen times
and never says why it stopped is being killed from outside, and the bursts - several starts a few
seconds apart - are a process being killed as fast as it can come back.

**What the slow stretches were.** The event loop's utilisation, 0.2 to 0.3% at rest, read 3 to
4.5% at four points through the incident - T+2, T+3, T+8 and T+13: a process working ten to
twenty times harder to do the same number of charges. Its old-space heap sat at 16.6 to 17.6MB
against 18 to 19 before. Nothing it was asked to do had changed - the same charges, at the same
rate, from the same caller.

**The six failed orders, which are the kills seen from checkout.** Every checkout error trace is
`PlaceOrder` failing at `oteldemo.PaymentService/Charge` with `connection refused` at payment's
address, with the cart read, the catalog lookups, the currency conversions and the shipping quote
before it all complete in milliseconds. Six refusals, all inside the restart bursts: an order that
reached payment in the seconds between a kill and the next start found nothing listening. The
slow orders are the rest: a charge of hundreds of milliseconds to over a second under an order
whose every other step took a few.

**What changed.** No deploy, no image change, no environment change, no flag. One record, at
onset, under payment's name: `memory limit lowered on payment`, to `memory=80m`, from 140M.
Payment had been using about 103MB. The record names a ceiling below the process's size, and the
log names the moment - 3 seconds later - the process was first killed and replaced.

**What it was not.** A slow dependency behind payment - payment has none; its charge is its own
work. A slow network to payment - that shows in checkout's p95 with payment's own unchanged, and
here it is the reverse. A flag failing charges - that shows errors, not latency, and leaves no
record. A bad deploy - that shows an image in the record, and the record shows the same
`2.2.0-payment` throughout.

## Root cause

The payment service container's memory limit was lowered from 140M to 80m, below the 103MB its
Node process was using. The kernel killed it at once. Every process that replaced it started inside
the new limit and ran at its ceiling, starved for memory, so it served slowly - charges taking
hundreds of milliseconds to seconds instead of a few milliseconds - and was killed and restarted
again and again, in bursts, whenever its footprint reached the limit. Orders still completed,
slowly, except the six in flight when a kill landed. Nothing about payment's image, code or
configuration changed; restoring the limit fixed it.

## Resolution

The memory limit was restored to 140M. The process running at that moment - started nine seconds
earlier, the last of the thirteen - kept running and was never restarted; with room to run in, its
p95 read 4ms within a minute of the fix and stayed there. The latency alert had already cleared at
T+10:30, when a burst of restarts happened to hand the window a fresh process, so the world was
all clear at the moment of the fix and nothing fired during recovery.

Class of fix: **config_revert**. The container's resource limit was wrong and it was set back.
Restarting payment was what the kernel had already been doing, thirteen times, and each restart
bought a minute or two before the next kill; rolling back its image would have changed nothing,
because the image was never the problem.

## Detection notes

- Onset to first page: **9m46s**, the third slow stretch finally holding for the rule's three
  minutes. Services on the page: **one**, payment, the culprit. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one.
- Would the page alone have led you to the right service? **Yes.** Nothing else was named, and
  nothing else was wrong.
- **A starved process that still fits is slow, not absent.** The page for this fault is latency
  on the target with every rate unchanged and its callers barely touched - not errors, not
  silence - and it is a quiet page: 430ms against a 250ms line, for a service whose callers
  spend one span in fourteen on it.
- **A start-up line with nothing before it, repeated, is a process being killed from outside.**
  Thirteen starts, no shutdown, no error. The log names the moments; the change record names
  the reason.
- **The alert flickers, because every restart resets the clock.** A killed process comes back fresh
  and fast; the latency rule needs three minutes of slow, and a burst of restarts inside those
  three minutes clears it. This page fired once, for 45 seconds, and the fault ran four more
  minutes unpaged.
- **Runtime series with no instance id hide restarts.** Payment's series never gapped; the
  thirteen restarts show only as counters resetting. Read restarts off the log.
- **After the fix, the five-minute window carries the last slow minutes forward.** p95 can read
  hundreds of milliseconds for minutes after a service is already fast; the raw charges, or a
  minute's patience, tell the difference.
