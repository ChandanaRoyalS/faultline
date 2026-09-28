---
origin: scenario:v2-valkey-cart-dependency-latency
split: dev
fault_class: dependency_latency
recorded_from: 2026-09-27T09:16:49+00:00
capability: cap:91279a09
onset_to_page: 4m04s
page_to_fix: 5m00s
fix_to_all_clear: 5m02s
---

# Cart is slow because its store is, and the store has no spans

## What was observed

The page was one alert, `ServiceHighLatency` on **cart**, 4m04s after the trouble started. A
minute later `ServiceHighLatency` fired on all four of cart's callers at once: **checkout**,
**frontend**, **frontend-proxy** and **load-generator**. Five alerts on five services by the fix,
all of them latency, and none after it. Nothing errored: every error ratio on the world stayed at
zero for the whole incident.

Cart's p95 had been 3ms. It was 318ms a minute in, 837ms at three, and from four minutes it held
at about 900ms. Its callers followed it up and a little past it. Checkout's p95 went from about
34ms to 446ms at two minutes and held at about 870ms from four; the frontend's from about 43ms to
about 1.15 seconds; frontend-proxy's and the load generator's to about 1.25 seconds. It was a step,
not a ramp: the numbers climbed for three minutes only because the windows they are measured over
were filling with slow requests, and then they were flat.

Traffic thinned and did not stop. The load generator's rate fell from about 5.3 to about 4.5 to
4.8 spans a second and the frontend's from about 12.7 to about 10.4 to 11.5, because shoppers
waiting on a slow page make fewer requests; checkout's fell further, from about 2.3 to between 1.0
and 1.75, and cart's from about 4.6 to between 2.75 and 3.6. Cart kept serving. Payment, the
catalog, currency and shipping kept their usual few milliseconds. Orders were being placed, slowly.

## What was checked

**The traces, because cart paged first and its callers followed.** Every slow trace touched cart,
and inside cart the time was in one place. At rest, cart answered a `GetCart` in 0.3ms and its
store answered an `HGET` in 0.2ms. Under the fault, in 80 traces drawn, every `HGET`, `HMSET` and
`EXPIRE` beneath cart took **300 to 305ms**, not one of them less. So a `GetCart`, one store
command, took 301ms at cart; an `EmptyCart`, two commands, 603ms; an `AddItem`, three, 903ms. And
that was the whole of it. Checkout's `GetCart` call took 303ms over cart's 301, the frontend's
`AddItem` 904ms over cart's 903: the callers' spans ended within a millisecond or two of cart's.
A cart page, which adds an item and reads the cart back, cost the frontend 1.2 seconds, and an
order, whose cart read and cart emptying come to three store commands, cost checkout about 930ms.
Everything else in those traces - the catalog, currency, shipping, payment, email - answered in
its usual milliseconds.

**The one dependency call of cart's that was not slow.** Beneath the same `EmptyCart` spans, beside
an `HMSET` and an `EXPIRE` at 300ms each, sat cart's flag read to the flag service,
`flagd.evaluation.v1.Service/ResolveBoolean`, at **1.1 to 2.3ms**, exactly what it had been at
rest. Cart was making two kinds of call out of the same process over the same interface, and only
the calls to its store were slow. That rules out cart's own network path, which would have slowed
both, and it rules out cart's handler, whose own time between the commands was under a
millisecond. The delay sat between cart and its store, and on the store's side of it.

**Where the 300ms was, exactly.** A store that is itself slow - short of memory, blocked on a save,
swapping - answers some commands slowly and others fast, reads differently from writes, and worse
under load than at rest. This store answered every command, read or write, in 300ms and a fraction,
with a few milliseconds of spread across 200 of them, and the same when traffic thinned as when it
did not. That is not a store working slowly. It is a store whose answers are all held for the same
time on their way out, which is a delay on its network interface.

**The store itself, which is where the trouble was and where the tools run out.** The store has no
spans: cart's `HGET` is a client span, and nothing answers it from the other side. It has no
metrics of any kind, under any name. What it has is a log, and its log said nothing was wrong: its
five-minute save ran on schedule at 5m01s intervals through the whole incident - `100 changes in
300 seconds. Saving...`, four lines of a background save completing in a hundred milliseconds -
before, during and after, and nothing else. A process that is starved or blocked does not keep
that schedule. The store was well. Its answers were late.

**The agent's trace tool, which names a degrading hop.** On cart's traces it named cart's own
store commands, `AddItem` to `EXPIRE` or to `HGET`, in five of seven: the right edge, and the
deepest span there is, because the store has none beneath it. On checkout's traces it named the
load generator's session span, a dead end - that span holds the scripted shopper's pauses between
requests. On the frontend's newest traces it named product browsing and a product-reviews call,
because most of the frontend's traffic does not touch a cart at all; a dead end too. The tool
points at the deepest slow span it can see; here the culprit is one span deeper than that.

**Whether cart was unwell.** Not by anything the traces show. Its own time in every span was a
millisecond or less once its store commands are taken out, its flag reads were as fast as ever,
and it raised no error. Its log went on as before: `GetCartAsync called`, `AddItemAsync called`,
52 to 75 lines a minute, thinning with the traffic, and not one error, warning or timeout in it.

**Flagd's sliver.** A dead end. Flagd's error ratio showed 0.3 to 1.6% for a few minutes around
two and again around twelve minutes in, and had shown the same before the trouble: the flag
service's routine ten-minute stream reconnect. It came nowhere near a line, and flagd's own p95 sat
at 2ms throughout, which is also the reason cart's flag reads were a clean control.

**What changed.** On cart, nothing: no deploy, no image change, no environment change, no limit
change, and no record of any kind under its name. On its store, one record, at the start: a
**container created**, described as a traffic-shaping container attached to valkey-cart's
network namespace, carrying `eth0 delay=300ms jitter=0ms`. The name in that record appears in no
service's metrics and no span; it appears in cart's environment, as the address cart's store
commands go to, and in change history. Every question asked about the services on the page came
back empty. The change was on the one thing in the chain that is not a service.

## Root cause

A traffic-shaping rule attached to valkey-cart's network namespace added 300ms of delay to every
packet leaving the store, so every one of cart's store commands waited 300ms for its reply. Cart's
code, image, configuration, process and network path were untouched, and so was the store's own
work: its replies were held on their way out. A cart read cost 300ms, an add 900ms, and every page
and order that touched a cart waited on it. Nothing failed. The slow component has no spans and no
metrics, and is named only in the change record and in cart's configuration.

## Resolution

The shaping container was removed and the rule went with it: the rule lives in the store's network
namespace and does not outlive what holds it, so recreating the store would have cleared it as
well. The p95s drained with their five-minute windows: the four callers' alerts cleared three and
a half minutes after the fix, and cart's, the last, at four and a half, its p95 at 294ms a minute
before it read 3ms again. Everything was quiet 5m02s after the fix, and nothing fired during
recovery.

Class of fix: **restart**. The rule is bound to the store container's network namespace;
recreating that container is the operator's remedy, and removing the shaping container is the
same fix from the other end. Nothing about cart, and nothing about the store's own configuration
or data, needed to change.

## Detection notes

- Onset to first page: **4m04s**. Services on the page: **one**, cart, which was not at fault. By
  the fix: **five**, none of them the store, which has nothing to alert on.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The callers' p95s were highest, cart
  paged first, and the culprit has no p95.
- Would the page alone have led you to the right service? **To the service in front of it.** Cart
  was alone on the page, and cart's traces put every millisecond on its store commands. The last
  step is inferring a component the traces cannot show.
- **When two kinds of call leave one process and only one kind is slow, the process and its
  network are cleared.** Cart's store commands took 300ms and its flag reads took one. A slow
  interface slows everything that crosses it.
- **A caller's span that ends with the callee's says the callee's answers are not delayed.** In
  the cart-interface incident the callers paid 300ms after cart's span; here they paid nothing.
  Where the extra time sits, before, inside or after the callee's span, says which side of which
  hop the delay is on.
- **Uniform is not the same as slow.** Every command at 300ms and a fraction, reads and writes
  alike, under load and not, is a fixed delay in the path, not a store working hard. A struggling
  store is uneven.
- **The deepest span is not always the culprit.** The trace tool named cart's store commands,
  which is as deep as the traces go. The store beneath them has no span, and its health had to be
  read from its own log and its change record.
- **The store's log answered "is it alive" and nothing else.** A save every five minutes, on time,
  says the process was fine. It says nothing about the network in front of it.
