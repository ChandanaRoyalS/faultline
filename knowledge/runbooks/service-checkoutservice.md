---
id: service-checkoutservice
title: Service - checkoutservice
origin: authored
applies_to: [checkoutservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The order path's fan-out point. It has more measured outbound edges than any other service in
this world, which makes it the service most often *affected* and one of the least often at
fault.

## What calls it, and what it calls

One inbound edge: `frontend -> checkoutservice`, 330 calls in the capture window, and the edge
is `unmeasured` - the traffic was seen but the measurement does not license a directional
claim from it.

Seven outbound, and the kinds matter more than the counts:

- `cartservice` (572, **sync**), `shippingservice` (572, **sync**), `productcatalogservice`
  (451, sync), `emailservice` (286, sync)
- `currencyservice` (698), `paymentservice` (286), `accountingservice` (286) - all
  **unmeasured**
- `frauddetectionservice` (286, **async**)

## Why an alert here usually names somebody else

`ServiceHighLatency` on checkoutservice is a claim about the slowest thing it waited for. Four
of its callees are reached synchronously, so their latency is its latency, and the span tree
separates them in one read: the hop holding the added time is the one to look at.

**The async edge is the exception and it is a strong one.** `frauddetectionservice` is reached
through a broker, so checkout does not wait on it. Blast-radius traversal crosses no `async`
edge in either direction for exactly this reason: frauddetection can be dead while checkout
completes orders normally, and each tells you nothing about the other.

## What its silence means

`ServiceNoTraffic` needs prior traffic to fire - the rule compares a three-minute window
against a thirty-minute one offset by ten. A checkoutservice that has been quiet since before
the comparison window opened does not page. Read the catalog's presence field before
concluding anything from an absent signal.

## Reading an incident that names it

Most incidents in this world name checkoutservice somewhere, because most of the order path
passes through it. That frequency is a property of its position, not evidence about it: a
service reached by four synchronous callees will appear in the blast radius of any of them.
Treat its presence in an alert set as the starting point of a walk, not as a conclusion.
