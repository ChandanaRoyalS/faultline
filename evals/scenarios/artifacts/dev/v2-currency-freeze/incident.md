---
origin: scenario:v2-currency-freeze
split: dev
fault_class: process_freeze
recorded_from: 2026-09-27T22:11:13+00:00
capability: cap:91279a09
onset_to_page: 5m30s
page_to_fix: 5m00s
fix_to_all_clear: 1m01s
---

# The currency process is frozen - its socket accepts and nothing answers

## What was observed

The page came 5m30s after orders started hanging, and it named the wrong service:
`ServiceHighErrorRate` on **fraud-detection**, a consumer at the far end of the order path that
nothing calls. Its latency alert followed a minute later. Then, two minutes after the page,
`ServiceNoTraffic` fired at once on **six services**: currency, payment, shipping, quote, email
and accounting; fraud-detection joined them three minutes after that. Nine alerts on seven
services by the fix, and nothing after it: the world was all clear 1m01s after the resume.

Almost nothing else moved. The frontend recorded no errors and no change in latency, a p95 of
41 to 44ms throughout; its request rate eased from about 11.7 a second to 9. The proxy's error
ratio climbed to 2.9% and the load generator's to 3%, both under their lines, and their p95s
touched the histogram's ceiling for two minutes, T+5 and T+6, and fell back before any rule could
hold them. Product pages, ads, recommendations, adding to carts and viewing them all worked as
before. Cart served at two thirds of its usual rate with its usual 3ms.

What stopped was orders. Currency's rate went from 0.36 a second to nothing by T+4 with no error
of its own; checkout's fell from 1.7 to about 0.2 and stayed there, its p95 dropping from 38ms to
4; and payment, shipping, quote, email and accounting went to zero with currency. From T+4 none of
them had an error ratio or a latency value.

## What was checked

**fraud-detection, because it was on the page.** A dead end, and a short one. Its error ratio
read 100% from T+4 on a rate of 0.004 a second: one span in five minutes, its routine
flag-stream reconnect to flagd, closed at the histogram's ceiling, which is also its latency
alert. With no orders on the topic it had nothing else to report, so the one long stream span
was all of it. flagd's p95 sat at the ceiling on the same spans. Nothing was wrong with either.
The page was an artefact of everything else going quiet.

**The proxy's errors, because they were the only errors.** 70 traces in ten minutes, and every
one a checkout - `user_checkout_single` 35, `user_checkout_multi` 35 - cut at the proxy's
fifteen-second route timeout. Not one product page, cart view or add-to-cart among them. The
proxy's ratio never reached its line because checkouts are one request in twenty; the ratio said
"something small is hanging", and the traces said what.

**Checkout, from the traces.** Under every timed-out proxy span the frontend's `POST /api/checkout`
was still open, for 600, 602 and 615 seconds in the three drawn, on a `PlaceOrder` open just as
long; and inside checkout's `prepareOrderItemsAndShippingQuoteFromCart` the cart read had
completed in under a millisecond, the catalog lookup in one, and then
`oteldemo.CurrencyService/Convert` was open for **599,887ms**, **601,703ms**, **615,073ms** - the
whole length of the freeze - with everything after it (the shipping quote, the second
conversion, the charge, the emptying of the cart, the email, the order record) done in
milliseconds once it finally returned. Every order in the window put all of its time in one
call, and the call was to currency.

**Why checkout did not go quiet.** Its rate held at about 0.2 a second through the fault: the
cart read and the catalog lookup that come before the conversion completed and were exported,
so checkout kept a pulse of two spans an order while its orders hung. That is why no-traffic
never fired on checkout, and why its p95 *fell* - to 4ms, the two fast spans being all it had to
report. A service can be stuck and look quick.

**The six silent services, as a group.** Payment, shipping, quote, email, accounting and
fraud-detection are only called once an order has got past its conversion. Nothing was getting
past it, so their silence was a consequence. Currency was on the list too, and on the alert list
it looked like just another starved service. It was the one everything else was waiting on.

**Currency's own view of itself.** It has none. Currency exports no runtime series on this world
and writes no log a reader can reach, before, during or after; the log capture for the window is
empty because there is nothing to capture. So its silence is not evidence of anything, and it
cannot be told idle from absent by anything it reports. Everything known about it comes from its
callers: a rate that went to zero, no spans at all while orders hung on it, and one `Convert`
call per order open for ten minutes that returned in two milliseconds the moment it resumed.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

## Root cause

The currency process was suspended. The container existed and kept its port; the kernel went on
accepting connections into its backlog; but nothing in the process ran, so no request was read or
answered. Only checkout calls currency, twice an order, after the cart read and the catalog
lookup, so every order hung at its first conversion with no deadline of its own, and nothing
after it ran: no shipping quote, no charge, no confirmation, no order record. The storefront
browsed, added to carts and viewed them as before, and the proxy timed the hung checkouts out at
fifteen seconds without ever reaching its error line. Currency neither errored nor logged,
because it was not running, and it reports nothing of its own in any case. Nothing about it had
been changed.

## Resolution

The currency process was resumed. Every held order woke together: 110 orders completed in the
minutes after the resume, each one's conversion having waited up to ten minutes and then taken
two milliseconds, and not one failed - checkout, the frontend and currency have no error traces
from the resume onward. Where an operator cannot resume a suspended process, restarting the
container does the same job. Class of fix: **restart**. Nothing was deployed or misconfigured, so
there was nothing to roll back or revert.

The six no-traffic alerts cleared 45 seconds after the resume as their windows refilled, and the
world was all clear 1m01s after it. The wave that followed is in the numbers but not in the
alerts on record: checkout's and the frontend's p95 read at the ceiling from T+11 as the held
spans closed at their ten-minute lengths, the proxy's and the load generator's went back to it,
the order path ran at two to three times its usual rate as the backlog cleared, and currency's
own p95 read 359ms on the burst. Whether the latency rules fired on that wave is not recorded;
the recording's window closed two minutes after the all-clear, a minute before those rules could
have held their three.

## Detection notes

- Onset to first page: **5m30s**. The page named fraud-detection, a service two hops past the
  problem with nothing wrong.
- Services on the page: **one**, not the culprit, not even on the path to it. By the fix: **nine
  alerts across seven services**, seven of them silence.
- Alerts that fired only during recovery: **none on record** - see the resolution.
- Did the loudest service turn out to be the culprit? **No.** The loudest was a consumer that
  starved into a 100% error ratio on one span.
- Would the page alone have led you to the right service? **No.** The page pointed away from it.
  The proxy's error traces pointed at checkouts; checkout's traces put every second in one call.
- **A small hang pages by silence, and the silence pages the wrong name first.** One request in
  twenty hung, too few for any caller's error or latency rule; what fired was a starved consumer's
  thin error ratio, then the no-traffic wave. The culprit was one name among seven.
- **A stuck service can look quick.** Checkout kept exporting the two fast spans that come before
  its hung call, so it never went quiet and its p95 fell. The open span is in the traces, not in
  the metrics.
- **A target with nothing of its own is read entirely off its callers.** Currency has no runtime
  series and no log; its rate, its missing spans and the open `Convert` under every order are the
  whole case, and they are enough.
- **The proxy's ratio measures the share of requests that hang, not the size of the fault.** 5%
  of requests, 3% of the proxy's spans; the catalog's freeze at the same rule paged in four
  minutes, the cart's in five, this one never on that rule.
- **The all-clear can come before the recovery's own wave has had time to page.** Ten-minute
  spans closing at once put three services at the ceiling for the store's window; the rule
  needs three minutes, and the record ends before that.
