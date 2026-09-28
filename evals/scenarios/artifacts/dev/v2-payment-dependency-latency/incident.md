---
origin: scenario:v2-payment-dependency-latency
split: dev
fault_class: dependency_latency
recorded_from: 2026-09-27T10:27:19+00:00
capability: cap:91279a09
onset_to_page: 5m35s
page_to_fix: 5m00s
fix_to_all_clear: 4m02s
---

# Payment's replies are late, and only checkout can tell

## What was observed

The page was one alert, `ServiceHighLatency` on **checkout**, 5m35s after the trouble started.
Nothing else fired, then or later, and nothing fired after the fix. Nothing errored: every error
ratio on the world stayed at zero for the whole incident.

Checkout's p95 had been 35 to 39ms. It was 45ms at two minutes, 270 at three, 306 at four, and
from five minutes it held at 335 to 338ms for as long as the trouble lasted. Nothing around it
moved. **Payment**'s p95 stayed between 2 and 10ms throughout, as it had been. The frontend's p95
sat at 43 to 48ms through the fault, frontend-proxy's at 45 to 50 and the load generator's at 47
to 54; in the last two minutes before the fix the proxy's and the load generator's brushed 200
and came back, under the line. Cart, shipping, email, currency and the catalog kept their usual
milliseconds. Checkout's request rate dipped from about 1.9 spans a second to 1.3 to 1.45 in the
middle of the fault and came back before the fix; payment's dipped with it. Orders were being
placed, each about 300ms later than before.

That is the page: one service slow, by a fixed amount, and everything it depends on reporting
itself fast.

## What was checked

**Checkout's traces, the service on the page.** Every order was slow in one place. In 76 traces
drawn under the fault, `PlaceOrder` took 329 to 373ms where it had taken 27 to 79. Beneath it the
cart read, the product lookups, the currency conversions, the shipping quote, the shipment, the
emptying of the cart and the confirmation email all took what they always take, a few
milliseconds each. And checkout's `Charge` call to payment took **303ms**, 311 at the p95, where
it had taken 2 to 10. One call, 300ms longer, in every order.

**Payment's side of the same call.** Beneath every one of those 303ms client spans sat payment's
own `Charge` server span, at **0.8ms**, 5.6 at the p95, exactly what it had been at rest, with its
`charge` step inside it at half a millisecond. Payment received the request, did its work in under
a millisecond, and answered. The 300ms was not in payment's work. It sat between the end of
payment's span and the end of checkout's: after payment had answered and before checkout heard
it. That is the shape of a reply that leaves late, not of a service that works slowly.

**Whether payment was unwell.** It was not, by anything it reported. Its 75 Node runtime series
reported every fifteen seconds without a gap: its event-loop delay was flat, its event-loop
utilisation a fifth of a percent, its heap steady, its garbage collector on its usual cadence.
Its log went on as before - `Charge request received.` and the card, the amount and the loyalty
level for each, 84 charges over the fault, 3 to 13 a minute with the traffic, and not one error
or warning. Its own p95 never left single digits. A service whose replies are late but whose
process is idle and whose spans are fast is a service whose replies are being held on their way
out.

**Why only checkout paged.** Payment calls nothing, so it has no downstream call for the delay to
sit inside, and its own spans close before its replies leave: the delay never enters payment's
metrics at all. Checkout is the only service that calls payment, so checkout is the only service
whose spans grew. Each order is about one span in twelve of checkout's, and two of them grew - the
charge and the order that contains it - which was enough to move checkout's p95 past the line. The
storefront's order spans are a smaller share of its own, under one in twenty, so the frontend's
p95 barely moved and the proxy's and the load generator's only brushed the line late. A fault on a
leaf shows up one hop above it, on the caller, and nowhere else.

**The agent's trace tool, which names a degrading hop.** On payment's and checkout's traces it
named `PlaceOrder` to `Charge` in every one: checkout's call into payment, the right edge, seen
from the caller's side. On the frontend's newest traces, which mostly do not carry an order, it
named product browsing and cart pages, dead ends.

**The flag readers' sliver.** A dead end. Fraud-detection's error ratio showed 1.4 to 2.1% and
flagd's under 1% for a few minutes around three and again around twelve minutes in, and had
shown the same five minutes before the trouble began: the flag service's routine ten-minute
stream reconnect. It came nowhere near a line and involved no order.

**What changed.** On checkout, nothing: no deploy, no image change, no environment change, no
limit change. On payment, no deploy, no image, no environment, no limit either - and one record,
at the start, that is none of those: a **container created**, described as a traffic-shaping
container attached to payment's network namespace, carrying `eth0 delay=300ms jitter=0ms`. The
four familiar questions came back empty on both services and the fifth was the incident, under
the name of the service that never paged.

## Root cause

A traffic-shaping rule attached to the payment service's network namespace added 300ms of delay
to every packet leaving the container. Payment's code, image, configuration and process were
untouched, and it answered every charge in under a millisecond; its answers arrived 300ms late.
Payment calls nothing, so the delay never entered its own spans or metrics; checkout, which waits
on every charge, carried it alone. Every order took about 300ms longer and nothing failed.

## Resolution

The shaping container was removed and the rule went with it: the rule lives in payment's network
namespace and does not outlive what holds it, so recreating payment would have cleared it as well.
Checkout's p95 drained with its five-minute window - 304ms two and a half minutes after the fix, 266
a minute later, 60 the minute after that - and its alert cleared three and a half minutes after the
fix. Everything was quiet 4m02s after the fix, and nothing fired during recovery.

Class of fix: **restart**. The rule is bound to the container's network namespace; recreating the
container is the operator's remedy, and removing the shaping container is the same fix from the
other end. Nothing about payment's image or configuration, and nothing about checkout, needed to
change.

## Detection notes

- Onset to first page: **5m35s**. Services on the page: **one**, checkout, which was not at
  fault. By the fix: **one**. The culprit never alerted and never could have.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** Checkout was the only service that
  was loud at all; payment's own numbers were perfect throughout.
- Would the page alone have led you to the right service? **To its caller.** Every order has one
  slow span, and it is the call to payment; payment's own span beneath it is fast.
- **A leaf with a delayed egress cannot see its own delay.** A service that calls nothing closes
  its spans before its replies leave, so its p95 stays at rest while every caller waits. Look at
  the callee's span beneath the slow client span: fast beneath slow is a late reply.
- **The gap after the callee's span is the delay's address.** Time inside the callee's span is
  the callee's work; time between the callee's end and the caller's end is the reply in flight.
  Here the whole 300ms was in flight.
- **A fixed step on one call in every request is a delay, not a load.** Every charge took 300ms
  and a few, at three orders a minute and at thirteen. A struggling service is uneven and gets
  worse with traffic.
- **A fault one hop below the page is invisible above it.** Checkout's p95 crossed the line
  because orders are a large enough share of its spans; the storefront's did not, because they
  are not. How far a latency fault propagates is arithmetic about shares, not about severity.
- **"Nothing changed" on the paging service is the wrong service to ask.** Checkout's change
  history was empty and so were payment's deploys, image, environment and limits; the record was
  a container under payment's name.
