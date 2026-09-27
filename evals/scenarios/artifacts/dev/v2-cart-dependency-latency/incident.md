---
origin: scenario:v2-cart-dependency-latency
split: dev
fault_class: dependency_latency
recorded_from: 2026-09-27T08:42:06+00:00
capability: cap:d2b243e0
onset_to_page: 4m50s
page_to_fix: 5m00s
fix_to_all_clear: 5m02s
---

# Cart service network path acquires 300ms of delay

## What was observed

The page was four alerts in the same moment, `ServiceHighLatency` on **cart**, **frontend**,
**frontend-proxy** and **load-generator**, 4m50s after the trouble started. A minute later
`ServiceHighLatency` fired on **checkout**. Five alerts on five services by the fix, all of them
latency, and none after it. Nothing errored: every error ratio on the world stayed at zero for
the whole incident.

Cart's p95 had been 3ms. It was 8ms a minute in, 378ms at two, 863ms at three, and from four
minutes it held between 910 and 934ms. Its callers followed it up and past it. Checkout's p95 went
from about 35ms to about 1.3 seconds at three minutes and held at about 1.6 seconds; the
frontend's from about 41ms to about 1.8 seconds; frontend-proxy's and the load generator's to about
1.85 seconds. It was a step, not a ramp: the numbers climbed for three minutes only because the
windows they are measured over were filling with slow requests, and then they were flat.

Traffic thinned a little and did not stop. The load generator's rate fell from about 5.2 to about
4.6 spans a second and the frontend's from about 12.4 to about 11, because shoppers waiting on a
slow page make fewer requests. Cart kept serving, at about 3.4 to 3.9 spans a second against about
4.2, and payment, shipping, currency and the catalog kept their usual rates and their usual few
milliseconds. Orders were being placed, slowly.

## What was checked

**The traces, because four services slowed at once and the page did not say which one first.**
Every slow trace touched cart, and the time sat in the same places in all of them. At rest, cart
answered a `GetCart` in 0.4ms and its store answered an `HGET` in 0.3ms. Under the fault, in 80
traces drawn, every `HGET`, `HMSET` and `EXPIRE` beneath cart took **300 to 305ms**, not one of them
less, and cart's own flag read to flagd took the same. So a `GetCart`, one store command, took
301ms at cart; an `AddItem` or an `EmptyCart`, three commands each, took 903 to 905ms. And each
caller's span was **another 300ms longer** than cart's answer beneath it: checkout's `GetCart` call
602ms over cart's 301, the frontend's `AddItem` call 1205ms over cart's 903. A cart page, which
adds an item and then reads the cart back, cost the frontend 1.8 seconds, and so did an order,
whose cart read and cart emptying cost checkout 1.8 of its 1.85 seconds. Everything else in those
traces - the catalog, currency, shipping, payment, email - answered in its usual milliseconds.

**Where the 300ms was.** Not inside cart's handler and not inside the store. The store's own work
had not changed, and cart's had not either; what had changed was that every message *leaving* cart
took 300ms to arrive: its commands to the store, its flag read, and its answer to whoever had
called it. Messages arriving at cart were not delayed, which is why the caller's extra 300ms sits
after cart's span ends, not before it begins. Three round trips out of cart, three times 300ms.
That is a delay on cart's network interface, on egress, and nothing else produces that shape.

**The agent's trace tool, which names a degrading hop.** On cart's and the frontend's traces it
named the frontend's call into cart, `/api/cart` to `CartService/GetCart` or `AddItem`, in six of
ten and three of ten: the right edge, seen from the caller's side. On checkout's traces it named
the load generator's own session span instead, which is a dead end - that span holds the scripted
shopper's pauses between requests, several seconds of nothing, and is not a hop at all. The tool
points at the slow edge; it takes the trees to see that the edge's slowness is cart's egress.

**Whether cart was unwell.** It was not. Its 35 .NET runtime series reported every fifteen seconds
without a gap. Its CPU time did not move, its working set sat at 115 to 117MB throughout, its thread
count went from 38 to 39, its thread pool queued nothing, and it collected garbage three times in
the ten minutes, about as it does at rest. Its log went on as before: `GetCartAsync called`,
`AddItemAsync called`, 52 to 109 lines a minute against about 100 at rest, and not one error,
warning or timeout in it. A service that is short of anything shows it in one of those. This one was
idle and slow.

**Whether the store was slow.** The store has no spans of its own, but cart's client spans to it
say it was not: every command took 300ms and a fraction, whether a read or a write, with nothing
of the variation a struggling store shows. A store answering in 300ms is a store whose answers
are waiting somewhere; a delay of exactly the same size on the flag read, to a different service
over a different protocol, says the wait was at cart, not at either of them.

**Flagd's sliver.** A dead end. Flagd's error ratio showed 0.3 to 1.4% for a few minutes around
onset and again around eight to twelve minutes in, and had shown the same before the trouble: the
flag service's routine ten-minute stream reconnect. It came nowhere near a line.

**What changed.** No deploy, no image change, no environment change, no limit change, on cart or
anywhere else. And one record, under cart's name, at the start, that is none of those: a
**container created**, described as a traffic-shaping container attached to cart's network
namespace, carrying `eth0 delay=300ms jitter=0ms`. The four familiar questions came back empty and
the fifth was the incident. The change was made below the level a service's own definition
describes, and it is recorded under the service's name rather than anywhere in the service's
configuration.

## Root cause

A traffic-shaping rule attached to the cart service's network namespace added 300ms of delay to
every packet leaving the container. Cart's code, image, configuration and store were untouched
and its process was unstrained. Every cart operation paid the delay once on its answer and once on
each round trip to its store or to the flag service, so a cart read cost its caller 600ms and an
add or an empty 1.2 seconds, and every page and order that touched a cart waited on it. Nothing
failed.

## Resolution

The shaping container was removed and the rule went with it: the rule lives in cart's network
namespace and does not outlive what holds it, so recreating cart would have cleared it as well. The
p95s drained with their five-minute windows: checkout's, the frontend's, frontend-proxy's and the
load generator's alerts cleared three and a half minutes after the fix, and cart's, the last, at
four and a half, its p95 at 329ms a minute before it read 3ms again. Everything was quiet 5m02s
after the fix, and nothing fired during recovery.

Class of fix: **restart**. The rule is bound to the container's network namespace; recreating the
container is the operator's remedy, and removing the shaping container is the same fix from the
other end. Nothing about cart's image or configuration needed to change.

## Detection notes

- Onset to first page: **4m50s**. Services on the page: **four**, cart among them, with three of
  its callers. By the fix: **five**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Not by the numbers.** The callers' p95s
  were twice cart's, because a caller pays cart's time and then its own 300ms on the answer.
  The service with the highest latency was three hops from the fault.
- Would the page alone have led you to the right service? **Nearly.** Cart was on it, with three
  services that call it and nothing that it calls. The leaf of the slow chain is where the time
  is being spent.
- **Latency without errors is a delay, not a failure.** Not one span errored and not one request
  was dropped. Everything worked, slowly, which rules out anything that refuses, crashes or
  times out.
- **A constant added per hop is a network delay; a constant added per operation is a slow
  service.** Every store command paid 300ms, and so did the flag read to a different service, and
  so did every answer to every caller. A slow store slows only store commands; a slow cart slows
  its handler. Only cart's interface touches all three.
- **The caller's extra time sits after the callee's span, not before it.** Egress delay shows up
  as a gap between the callee finishing and the caller hearing about it. Ingress delay would sit
  before the callee's span begins.
- **A step is a change; a ramp is a load.** The p95s climbed for three minutes and then went flat,
  because the windows were filling. The underlying delay was constant from the first request.
- **"Nothing changed" is a conclusion about four queries, not about a service.** The deploy, image,
  environment and limit questions all came back empty; the change record still held the answer,
  under cart's name, as a container that was not cart.
