---
scenario_id: cart-redis-misconfig
origin: scenario:cart-redis-misconfig
split: dev
incident_id: b0cfda91-17ee-4704-b8ac-2a0fe62fded4
recorded_from: 2026-09-09T15:49:24.900601+00:00
---

# cartservice crashloop on a non-default Redis port; checkoutservice was the noticer

## What the investigation concluded

An automation cycle edited cartservice's REDIS_ADDR to point at the redis-cart host on 6380 rather than the default 6379 about two and a half minutes before onset, and — unlike every prior turn of that same cycle in the preceding day — that edit was still in force at onset. Each cartservice process start attempted the connection, threw an unhandled exception out of store initialization on the entry-point path, and died, re-looping every 20–40s without ever reaching a serving state. With no listener, checkoutservice's client call to CartService/GetCart errored at the connection boundary and that status rode up through PlaceOrder to the frontend root. The fault is a wrong configured value, not a slow or saturated dependency: the address names a port nothing answers on.

## What ruled the alternatives out

Three discriminators did the work. (1) Span shape: the deepest and first span carrying an error in every sampled failing trace was the caller's client span, sub-millisecond, with no server-side child and no fan-out past it — fast rejection at connect, which eliminates a slow-dependency story and any saturation story, both of which produce waits and partial downstream work. (2) Artifact vs. value: the hotfix image reference from the same automation cycle had already been undone ~30m before onset and a delay-adding sidecar detached ~10m before, so the running image at onset was baseline; the failure frames sat in configuration-driven connection setup, not in an unstartable binary. That eliminates the bad-artifact hypothesis. (3) Direction: checkoutservice had no change in the queried window and was alive and accepting work throughout, so it is downstream of the fault, not the source. The dead-Redis hypothesis survives only weakly: the target recorded on every attempt is the non-default port introduced by the timed edit, which a spontaneously unavailable Redis would not explain — but redis-cart was never touched directly.

## What the proposal rested on

Preconditions: none were recorded, which is itself notable — the whole chain assumes 6379 is serving and 6380 is closed, inferred from the change record plus connect failures, never from the Redis side. Blast radius as mechanism: one service's processes replaced, cart traffic shifted from the non-default port back to the default, callers seeing connection resets where they already see errors, and — because the environment is restored wholesale rather than one key — every other value that same automation cycle set is also displaced, with unmeasured effect. Falsifiers: cartservice keeps dying with the connect target now reading the default port (the port inference is wrong); cartservice reaches serving state but checkoutservice's error ratio stays near 0.109 (a second fault among the unexamined dependencies); or the non-default port reappears within minutes (the automation definition itself changed, and no manual correction holds). Confirmation window was 180s.

## What happened at the approval boundary

The record does not state what became of the proposal. It was neither noted as accepted nor as refused, and nothing here should be read as either.

## What was never measured

Nothing was ever queried against redis-cart, so neither port's actual listening state was confirmed. cartservice emitted no calls_total under the queried service_name label in either window, so the crashloop timeline rests on logs alone with no metric-side corroboration. The caller's own logs describe a silent stall after the onset minute with no completion and no error lines, while traces show 1–3ms rejections; those two signatures are unreconciled, and trace sampling covered only about a minute starting a minute after onset, so the onset minute itself may have looked different (connect timeouts before the process fully died). The caller's error-ratio metric has an earlier change point ~39m before onset at the same peak and a nonzero baseline, so errors of this shape pre-date the environment edit and were never explained. The change query for checkoutservice started at the incident timestamp rather than before it, so a change there in the preceding minutes was never covered. Four graph edges triage crossed were never examined — redis-cart, frontend, and nine remaining checkout dependencies — so a concurrent second fault cannot be excluded. Finally, why the automation cycle left this turn standing (failed cleanup job vs. changed definition) is unknown, and that determines whether any correction would hold.
