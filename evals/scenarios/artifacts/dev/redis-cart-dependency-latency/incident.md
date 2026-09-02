---
origin: scenario:redis-cart-dependency-latency
split: dev
fault_class: dependency_latency
recorded_from: 2026-08-31T03:49:32+00:00
capability: cap:c4d52d00
onset_to_page: 3m50s
page_to_fix: 5m00s
fix_to_all_clear: 2m31s
---

# Cart is slow because its datastore is, and the datastore has no spans

<!-- NO ABSOLUTE TIMESTAMPS IN THE PROSE. Write "T+3m" or "about four minutes after
     the page", never "08:02:41". This file is read months later as a past incident,
     where the hour it happened means nothing - and a re-record would orphan every
     timestamp written here.

     `recorded_from` in the front matter above is the deliberate exception. It is
     absolute precisely so that it breaks when the recording changes: it pins this
     narrative to one recording, and a guard fails if they drift apart. Front matter
     is written to fail on a re-record; prose is written to survive one. Do not
     "fix" the inconsistency - see ARTIFACTS.md. -->

## What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

**On the page:** ServiceHighLatency/cartservice

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+3m50s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighLatency | cartservice | T-20s | 7.5m |
| later | ServiceHighLatency | checkoutservice | T-5s | 6.8m |
| later | ServiceHighLatency | frontend | T-5s | 6.8m |
| later | ServiceHighLatency | loadgenerator | T+10s | 6.8m |

The page named 1 service(s). By the time the fault was removed 4 alert(s) had fired - 3 more than the responder saw when they started.

## What was checked

**Whether anything was actually failing.** Nothing was. The error ratio was flat at zero on every
service for the whole window. Four services were slow together and none of them was returning
errors, which reads as queuing behind something rather than as a service falling over.

**Where in the chain the slowness started.** cartservice was the deepest service alerting and the
first to page, with checkout, the frontend and the load generator following it - the shape of
callers waiting on a callee rather than of a fault spreading outward. That put cartservice at the
bottom of the visible chain.

**Whether cartservice's own work had got slower.** This is where it stopped being obvious.
cartservice's p95 was ~655ms against a baseline of 1.9ms, but splitting its spans by kind showed
client-side p95 at ~390ms - a large part of its handler time was spent inside outbound calls, not
in its own code. Something cartservice talks to was answering late.

**Dead end: looking for what cartservice was waiting on, in the service metrics.** There is nothing
there to find. Cart's dependency is Redis, and Redis is not an instrumented service - it emits no
spans, exports no runtime metrics and has no service-level series of any kind. **No metric in the
system mentions it.** From the metrics alone, cart is a service that has become slow for no visible
reason.

**Dead end: cartservice's own recent history.** No deploy, no config change, no restart. Whatever
had changed, it had not changed on the service that looked broken.

**What named it:** the change history on `redis-cart`, which showed a network delay applied to the
container's interface. The one thing that had changed was the one thing with no telemetry.

## Root cause

Redis, the cart service's datastore, had a 300ms network delay applied to its interface, so every
response it sent back arrived late. Cart was not broken and was not doing anything differently - it
was blocking on a datastore that had become slow, and everything that calls cart inherited the wait.
The component at fault produces no telemetry of its own, so the only signal of it was the latency
appearing in its caller and a change recorded against its container.

## Resolution

The delay was removed from the Redis container's interface and latency returned to baseline as the
alert windows drained. **Class of fix: `restart`** - the intervention was on the container carrying
the fault, not a revert of any application configuration. Nothing about cartservice was changed at
any point, because nothing about cartservice was wrong.

## Detection notes

- Onset to first firing alert: 3m50s
- Services alerting on the page: 1
- Services alerting by the end of the fault: 4
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 2m31s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
