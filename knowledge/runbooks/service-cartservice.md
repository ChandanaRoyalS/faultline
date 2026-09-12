---
id: service-cartservice
title: Service - cartservice
origin: authored
applies_to: [cartservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The busiest leaf on the browse path and a synchronous dependency of the order path. It is also
the only application service whose datastore is a separate container, which is the fact most
worth carrying into an investigation of it.

## What calls it, and what it calls

Two inbound edges, both **sync**: `frontend -> cartservice` (1754 calls) and
`checkoutservice -> cartservice` (572). Between them they make it the second-most-called
service in the world.

**No outbound edge appears in the measured graph.** That absence is not the whole truth: it
reaches `redis-cart` through a Redis client, and the only trace of that is the client span
(`HGET`, `HMSET`) recorded *inside* cartservice's own trace. Redis emits no spans and carries
no `service.name`, so the dependency is real and the edge is invisible.

## The consequence, which is the point of this document

A latency increase inside cartservice and a latency increase on its path to its datastore look
the same from the outside: the caller waits longer, `ServiceHighLatency` fires on cartservice,
and nothing fires anywhere else.

Separating them is a trace question, not a metric one. **Look at the client span's self-time
against the span's total.** A cartservice handler doing its own work slowly has self-time to
show for it; a cartservice handler waiting on a datastore has a leaf span holding the time and
almost no self-time above it.

## What a recreate does and does not remove

`restart_service` recreates the container from the declared definition. That removes anything
attached to the container's own network namespace and anything in its process. It does not
touch `redis-cart`, which is a different container: an action on cartservice cannot fix a
condition that lives on the other side of the client span.

## Its silence

Both of its callers are instrumented and both page on their own behalf, so a cartservice
failure is visible from two directions. It is one of the better-observed services here, and an
absence of alerts on it means more than it would for a service with one caller.
