---
id: service-redis-cart
title: Service - redis-cart
origin: authored
applies_to: [redis-cart]
signals: []
actions: [restart_service, revert_config]
---

The cart's datastore, and the clearest example in this world of a service that can be a cause
without ever being a signal.

## It emits nothing

Redis produces no spans and carries no `service.name`. `count by (service_name) (calls_total)`
does not return it. **All three alert rules are evaluated per `service_name`, so none of them
can fire for redis-cart** - not "did not fire", cannot. The catalog classifies it
`infrastructure` and `usable_for_graph_reasoning: false` for this reason.

It is in the catalog anyway, deliberately. ADR-0017 records the decision and its addendum 3
records what settled it: a service that cannot be named is a service that cannot be blamed, and
the culprit-service axis needed to be able to name this one.

## How it appears at all

Through `cartservice`. The Redis client inside cartservice emits a span per operation - `HGET`,
`HMSET` - and that span is the only evidence in the whole telemetry stack that redis-cart
exists. A condition here surfaces as latency or errors *on cartservice*, one hop up, and on
cartservice's two callers after that.

## What follows for an investigation

**An incident whose alerts all name instrumented services can still originate here.** The
blast radius will not contain redis-cart, because the graph is span-derived and there is no
span to derive an edge from; the catalog is where the possibility has to come from instead.

The question that distinguishes it: does the cartservice span tree show its own handler slow,
or a Redis client leaf holding the time? The second points here, and no metric on cartservice
can tell you which it was.

## Acting on it

`restart_service` and `revert_config` both operate on the container and are performable. What
they cannot do is be verified the usual way - there is no alert on redis-cart to clear, so
recovery is observed on cartservice and on cartservice's callers. Plan the confirmation
window around the service that pages, not around the one that changed.
