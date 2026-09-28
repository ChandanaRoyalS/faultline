---
origin: scenario:v2-payment-freeze
split: holdout
fault_class: process_freeze
recorded_from: 2026-09-27T23:17:20+00:00
capability: cap:91279a09
onset_to_page: 7m16s
page_to_fix: 5m00s
fix_to_all_clear: 1m00s
---

# The payment process is frozen - its socket accepts and nothing answers

## What was observed

The page came 7m16s after orders started hanging, and it was silence: `ServiceNoTraffic` on
**payment**, **email** and **accounting** at once. A minute later `ServiceHighLatency` fired on
**frontend-proxy**; a minute after that, error rate on **fraud-detection** and latency on the
**load generator**; a minute after that, latency on fraud-detection. Seven alerts on six
services by the fix, nothing after it, and the world all clear 1m00s after the resume.

The storefront barely noticed. The frontend recorded no errors and no change in latency, a p95
of 41 to 45ms throughout, its request rate easing from 12.4 a second to about 9.6. Product
pages, ads, recommendations, adding to carts and viewing them all worked as before. The proxy's
error ratio climbed to 3.1% and the load generator's to 3.4%, both under their lines, but their
p95s went to the histogram's ceiling, **15000ms**, from T+5 and T+6 and stayed there, which is
what paged them on latency.

What stopped was the end of every order. Payment's rate went from 0.3 a second to nothing by T+4
with no error of its own, and email's and accounting's went with it; from T+4 none of the three
had an error ratio or a latency value. Checkout, though, kept going at about half its rate, its
p95 *falling* from 39ms to 7; shipping ran at about half; currency and quote did not move at all.

## What was checked

**The proxy and the load generator, because they paged on latency.** Their error traces - 93 in
twelve minutes - were all the same thing: a checkout, `user_checkout_multi` 48 and
`user_checkout_single` 45, cut at the proxy's fifteen-second route timeout. Not one product
page, cart view or add-to-cart among them. Checkouts are one request in sixteen here, too few
to move the error ratio past its line, but every one of them held a proxy span at fifteen
seconds, and that was enough to put the proxy's 95th percentile at the ceiling.

**Checkout, from the traces.** Under every timed-out proxy span the frontend's `POST /api/checkout`
was still open, for 266, 469 and 729 seconds in the three drawn, on a `PlaceOrder` open just as
long. Inside checkout, `prepareOrderItemsAndShippingQuoteFromCart` had **completed** - the cart
read, the catalog lookups, both currency conversions and the shipping quote, all of it in 8 to
13 milliseconds - and then `oteldemo.PaymentService/Charge` was open for **265,782ms**,
**469,026ms**, **729,167ms**: the whole length of the freeze. When it finally returned, the
shipment, the emptying of the cart, the confirmation email and the order record took
milliseconds. Every order in the window put all of its time in one call, and the call was to
payment.

**Why checkout, shipping and currency did not go quiet.** Everything an order does before its
charge still ran and still exported: checkout kept the six spans of its preparation, shipping
kept its quotes and lost only its shipments, currency kept both conversions. That is why
checkout's rate halved rather than vanished and its p95 fell - the fast half was all it had to
report - and why shipping, quote and currency were not on the no-traffic list. Only what comes
*after* the charge went silent: the shipment (inside shipping's rate), the email, the order
record accounting and fraud-detection consume. The shape of the silence is the shape of the
order after the charge.

**The three silent services, as a group.** Email and accounting are only called once an order
has been charged. Nothing was getting charged, so their silence was a consequence. Payment was
on the list too, and on the alert list it looked like just another starved service. It was the
one the other two were waiting on.

**Payment's own view of itself.** Its 75 runtime series - event loop, V8 heap by space, garbage
collection - stopped at the freeze: the last samples are from the minutes before onset, they
held for the store's four-minute lookback and then dropped out of queries, and nothing replaced
them until fourteen seconds after the fix. A service that is merely uncalled keeps sending its
runtime reports on a timer. This one had stopped reporting on itself altogether.

**Payment's log.** It logs every charge as a record of a few dozen lines, hundreds of lines a
minute at rest. Three charge records in the seconds before the freeze, the last eight seconds
before onset, and then **nothing** for twelve minutes: not an error, not a shutdown line, not a
start-up line, not a line. A payment cut off from the network would keep running and keep
logging; a payment that had crashed would show its runtime starting again; a payment that was
merely uncalled would at least be reporting on itself. This one wrote nothing because nothing in
it was running. And then, in the minute after the fix, a hundred charge records at once: the
backlog, answered together.

**Its traces.** Payment had no spans of its own while orders hung on it. Its only spans in the
window are charges it answered *after* the fix, in under a millisecond, under calls that had
been open for minutes.

**fraud-detection, because it was on the page.** A dead end. Its error ratio read 100% from T+7
on a rate of 0.004 a second - one span in five minutes, its routine flag-stream reconnect,
closed at the histogram's ceiling, which is also its latency alert. With no orders on the topic
it had nothing else to report. Nothing was wrong with it.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

## Root cause

The payment process was suspended. The container existed and kept its port; the kernel went on
accepting connections into its backlog; but nothing in the process ran, so no request was read
or answered. Only checkout calls payment, once an order, after the cart read, the catalog
lookups, the conversions and the shipping quote, so every order hung at its charge with no
deadline of its own, five steps done and none of the rest: no shipment, no confirmation email,
no order record. The storefront browsed, added to carts and viewed them as before, and the proxy
timed the hung checkouts out at fifteen seconds. Payment neither errored nor logged, because it
was not running. Nothing about it had been changed.

## Resolution

The payment process was resumed. Its first charge landed two seconds later and its runtime
reports were back within fifteen; every held order woke together, and all 114 of them completed
- charged in under a millisecond after waiting up to twelve minutes, then shipped, confirmed and
recorded - with not one failure: checkout, the frontend and payment have no error traces from
the resume onward. Where an operator cannot resume a suspended process, restarting the container
does the same job. Class of fix: **restart**. Nothing was deployed or misconfigured, so there was
nothing to roll back or revert.

The no-traffic and latency alerts cleared within a minute as their windows refilled and the
proxy's fifteen-second spans aged out, and the world was all clear 1m00s after the resume. The
wave that followed is in the numbers but not in the alerts on record: checkout's and the
frontend's p95 read at the ceiling from T+13 as the held spans closed at their minutes-long
lengths, the order path ran at two to three times its usual rate as the backlog cleared, and
cart's p95 rose to about 40ms on the burst of cart emptyings. Whether a latency rule fired on
that wave is not recorded: the recording's window closed two minutes after the all-clear, before
the rule could have held its three.

## Detection notes

- Onset to first page: **7m16s**, the no-traffic windows draining. Latency on the proxy a minute
  later, once a sixteenth of its requests at fifteen seconds had held its 95th percentile for
  three minutes.
- Services on the page: **three**, the culprit among them and indistinguishable from the other
  two. By the fix: **seven alerts across six services**.
- Alerts that fired only during recovery: **none on record** - see the resolution.
- Did the loudest service turn out to be the culprit? **No.** The culprit was one of three names
  in the first alert, and the proxy and a starved consumer were louder after it.
- Would the page alone have led you to the right service? **Not on its own.** The page named three
  services that had all gone quiet; which one the others were waiting on is in checkout's traces,
  and in which of the three had also stopped reporting on itself.
- **The silence has the shape of the order after the hung step.** Everything before the charge
  ran and exported; everything after it did not. Read the no-traffic list against the order's
  sequence and the hung step is the first name on it.
- **A stuck service can look quick.** Checkout kept exporting the six fast spans before its hung
  call, so it never went quiet and its p95 fell to 7ms. The open span is in the traces, not in
  the metrics.
- **A sixteenth of requests hanging is under the error line and over the latency line.** The
  proxy's ratio never reached 5%; its 95th percentile did reach fifteen seconds, because the
  hung share sat just above the fifth percentile. The same share on a slightly busier storefront
  would page on nothing but silence.
- **A frozen process leaves no line and no series.** The log simply stops mid-stream and resumes
  with a burst; the runtime reports stop and resume with the fix. A partition would have kept
  logging; a crash would have logged a start; an idle service would have kept reporting.
- **The all-clear can come before the recovery's own wave has had time to page.** Minutes-long
  spans closing at once put checkout and the frontend at the ceiling for the store's window; the
  rule needs three minutes, and the record ends before that.
