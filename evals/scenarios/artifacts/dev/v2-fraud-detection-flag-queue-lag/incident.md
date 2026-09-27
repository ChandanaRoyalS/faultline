---
origin: scenario:v2-fraud-detection-flag-queue-lag
split: dev
fault_class: feature_flag
recorded_from: 2026-09-27T05:17:32+00:00
capability: cap:d2b243e0
onset_to_page: 4m15s
page_to_fix: 5m00s
fix_to_all_clear: 1m01s
---

# A feature flag floods the orders queue, slows its consumer and breaks accounting

## What was observed

The page was one alert, `ServiceHighLatency` on **fraud-detection**, 4m15s after the trouble
started. Nothing else fired, then or later, and nothing fired after the fix.

Fraud-detection's p95 had been about 90ms. From the first minute it was about 1,370ms, then
1,380ms, flat, until the fix. Its error ratio stayed under 1%, well below the line. Its rate of
work changed shape too: it had been reading a few records a minute, as fast as orders came in;
from the first minute it read **exactly one a second**, sixty a minute, and did not move from that.

Nothing on the storefront or the order path changed. Checkout placed orders at its usual rate with
no errors and no added latency, and payment and email were normal. The one other service that
moved was **accounting**, the other consumer of the same Kafka topic: its span rate went from
about 0.4 a second to between 16 and 25, with no errors, and its latency fell, from about 90ms to
about 2ms.

## What was checked

**Fraud-detection's traces, to see what the time was spent on.** Its work is two kinds of span:
`orders receive`, when it polls Kafka for a batch of records, and `orders process`, one for each
record it handles. The receive spans were fast. Every `orders process` span lasted about a second,
and a single poll's trace held about a hundred of them, one after another. The p95 of about
1,380ms is near the top of the latency histogram's bucket that a one-second span falls in. Nothing
inside the process span called anything: the second was spent in fraud-detection itself.

**Its log, which said why in its own words.** Before every record it logged `FeatureFlag
'kafkaQueueProblems' is enabled, sleeping 1 second`, and after it `Consumed record with orderId:
...`, up to sixty a minute, 551 sleeps in all and none before onset. The order ids repeated: the
first order after onset was consumed 101 times in a row, one a second, its running count climbing
by one each time, and the next one at least 99 times after it. Orders were arriving
many times over.

**Whether Kafka or the producer was failing.** Neither was. Checkout's orders completed normally.
Accounting, reading the same topic without the sleep, was reading records far faster than orders
were being placed, which is how fast the topic was being filled: each placed order was on it a
hundred and one times. The topic was healthy and far busier than the orders being placed.

**Accounting's log, because its traffic had jumped.** For the records it read it logged `Order
details: {...}` and then `fail: ... Order parsing failed:`, 302 to 1,010 times a minute and 6,566
times in all, where it had logged none in the five minutes before onset. For the duplicates the
exception was `The instance of entity type 'OrderEntity' cannot be tracked because another
instance with the same key value for {'Id'} is already being tracked`: accounting was refusing to
save an order it already held. But 66 of the failures, 2 to 10 a minute, about the rate orders
were being placed, were `Unexpected entry.EntityState: Detached` from inside the save: new orders
were being refused as well as copies. Its spans showed no error and made no database call, which
is why its latency fell and why nothing about it paged. The failure was in its log and nowhere
else.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart. The log names a feature flag on one side of the topic. The duplicates on the other side
started at the same moment.

## Root cause

The `kafkaQueueProblems` feature flag was turned on in the flag service, and it acts on both sides
of the orders topic. Fraud-detection sleeps a second before each record, so it consumes one a
second, and checkout publishes every order a hundred extra times, so the consumer falls further
behind every second. Accounting, the topic's other consumer, received every duplicate. The
duplicates left its long-lived database session in a state where saves fail, so it refused new
orders as well as the copies, silently. Kafka was healthy, and nothing was deployed or
reconfigured. The fault was the flag's value, and it left damage that outlasts it.

## Resolution

The flag was turned back off. Checkout stopped duplicating orders, and fraud-detection worked
through its backlog at once: about 6,500 records in the minute after the fix, then back to its
usual rate of about ten a minute, and its latency fell to about 2ms. Its latency alert cleared
1m01s after the fix.

**Accounting did not recover.** After the fix it logged six more `Order parsing failed`, each a new
order refused with `Unexpected entry.EntityState: Detached`. There were no copies left to refuse;
it was refusing real orders. Nothing alerted. Accounting was restarted about a minute after the
fix. The orders it refused while broken were read and committed, so they are not read again: they
are lost from accounting's records.

Class of fix: **config_revert**, for the flag, and **a restart of accounting**, which the page does
not ask for.

## Detection notes

- Onset to first page: **4m15s**. Services on the page: **one**, fraud-detection. By the fix:
  **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Partly.** Fraud-detection paged, and it is
  where the flag slows the work. The same flag was flooding the topic from checkout, and it broke
  accounting, which never paged.
- Would the page alone have led you to the right service? **To one of them.** The page and the log
  name the flag. Nothing on the page points at accounting, and accounting's damage is the part that
  outlasts the fix.
- **A consumer pinned at exactly one record a second is being paced, not overloaded.** A struggling
  consumer slows unevenly. A round number means something is deciding the pace.
- **The same order id consumed again and again means the topic is flooded, not that the consumer is
  retrying.** Here every placed order was on the topic a hundred and one times.
- **A service can fail the records it handles and show no error at all.** Accounting's failures
  were caught in its own code and never reached a span. Its latency fell and its traffic rose, and
  its log was the only place the failure appeared.
- **A cleared page is not a clean world.** After the fix, check every service the flag touched, not
  only the one that paged. Accounting was still refusing new orders after the flag was off, needed
  a restart that nothing asked for, and every order it refused in the meantime was lost.
