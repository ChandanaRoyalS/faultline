---
id: service-checkoutservice
title: Service - checkoutservice
origin: authored
applies_to: [checkoutservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The order path's fan-out point. `kind: application`, `tier: core`, owner `demo/checkout`,
container `checkout-service`. It has more measured outbound edges than any other service here,
and the catalog's `depends_on` lists the same eight.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `frontend -> checkoutservice` | 330 | unmeasured |
| outbound | `checkoutservice -> currencyservice` | 698 | unmeasured |
| outbound | `checkoutservice -> cartservice` | 572 | sync |
| outbound | `checkoutservice -> shippingservice` | 572 | sync |
| outbound | `checkoutservice -> productcatalogservice` | 451 | sync |
| outbound | `checkoutservice -> accountingservice` | 286 | unmeasured |
| outbound | `checkoutservice -> emailservice` | 286 | sync |
| outbound | `checkoutservice -> frauddetectionservice` | 286 | async |
| outbound | `checkoutservice -> paymentservice` | 286 | unmeasured |

**Eight outbound: four `sync`, three `unmeasured`, one `async`.** The kinds are measured from
recorded bundles rather than read off `span.kind`, which the bundles do not carry at all.

## What the three kinds mean

- **`sync`** - a callee's failure was observed to reach this caller. Measured propagation, not a
  claim about the RPC mechanism.
- **`async`** - a callee's failure was observed **not** to reach it. `frauddetectionservice` is
  reached through kafka. Blast-radius traversal crosses no `async` edge in either direction.
- **`unmeasured`** - nothing recorded says which of those two it is. It is **not** a synonym for
  `sync`, and not a statement that the direction is unknown: the direction and the call count
  are measured. Traversal **does** cross an unmeasured edge, and every crossing is counted and
  reported alongside the radius.

Five of the world's fifteen edges are `unmeasured`, and four of those five are incident to
checkoutservice: the three outbound ones above and its one inbound edge.

## The at-rest latency tail

**Measured over twelve hours at 15s resolution on a world at rest** (ADR-0025): checkoutservice's
median p95 is 37.8ms - its committed baseline - while **295 of 2398 samples were above the 250ms
threshold**, 264 of them above 1000ms, sustained past the rule's three-minute `for:` clause. It
is the largest tail of the three services that have one; every other service in the world
recorded zero samples over threshold.

**What is established** (ADR-0025 addendum, T7.23): it is accumulated in-process state, not
anything downstream. The handler finishes in ~20-25ms while its span reports 15-30 seconds, no
goroutine is executing it during the stall, and the two services that wait on checkout -
`frontend` and `loadgenerator` - report the same number because they are waiting, which is why
the affected set is exactly those three. Restarting the one container returned all three. **The
mechanism inside the process is not established**, and the ADR fences off the leading account as
a hypothesis rather than a measurement.

The rule was deliberately not changed, because it reports a true condition and because
de-sensitising it would falsify recorded bundles. The scoring gate absorbs it instead:
`KNOWN_TAIL_SERVICES` names checkoutservice, frontend and loadgenerator, and the gate **refuses**
to inject during an excursion rather than exempting them.

**The consequence for a recorded incident is the one that matters.** Because the gate will not
start a recording while an excursion is firing, a `ServiceHighLatency` on checkoutservice inside
an incident's window is not this.

One more distinction the table above depends on: `frontend -> checkoutservice` is `unmeasured`
because `EDGE_KINDS` records *failure* propagation and nobody has broken checkoutservice in a
bundle. ADR-0025 measured separately that frontend and loadgenerator wait on it for *latency*.
Unmeasured for one is not unmeasured for the other.

## What can page for it

All three rules, evaluated per `service_name`. SLO: p95 250ms, error ratio 0.05, from
`compose/prometheus/alert-rules.yml`. `alert-high-latency` and `alert-no-traffic` carry the
rules' mechanics; `ServiceNoTraffic` in particular needs prior traffic, so read the catalog's
presence field before drawing anything from an absent signal.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. The recreate is not invisible across edges: the
allowlist records that **callers see the connection reset while the container recreates**, and
checkoutservice's inbound edge names who - `frontend`. A proposal is expected to say so.
