---
id: world-what-a-recreate-removes
title: What recreating a container removes, and what survives it
origin: authored
applies_to: [any]
signals: []
actions: [restart_service, revert_config, rollback_image]
---

All three performable actions recreate the container. They differ in what they recreate it *from*,
and none of them touches anything outside it.

## Two places a change can live, and only one of them is in the container

**A memory limit is a live property of a running container** and `docker update` changes it in
place. **An environment variable, an image reference or a CPU quota is not**: compose reads those
only when it creates the container, so changing one means a generated override file and a
recreate. `docker update` carries resource limits and nothing else.

That is why a configuration or image change in this world always comes with a container recreate,
and a memory squeeze does not have to.

## What a recreate-from-declared makes moot

Recreating a service from the base compose files alone brings it back as the world defines it,
whatever an override was saying. Three kinds of restore become unnecessary in that moment:

- an override file setting an environment variable,
- an override file setting an image reference or a CPU quota,
- a live memory limit set by `docker update`, which the recreate resets to the declared value.

**A traffic-shaping sidecar is not among them.** It is a separate container attached to the
target's network namespace, the recreate did not touch it, and it stays exactly where it was. The
injector and the executor both track that distinction, so that a revert does not claim to have
undone something it never reached.

## `restart_service` is the one that reverts nothing

It compares nothing and recreates the service **under whatever it currently runs, override
included**. A restart that also reverted would be two actions under one name. It is the only one
of the three marked irreversible, because it discards in-process state - which for this world's
services is cache.

## What a shaper does when its target is recreated

The shaper applies its rule once and waits out its duration rather than reconciling, so **nothing
reapplies it** - and because it binds to the container that existed when it started, a recreated
container is simply not re-shaped. Both halves matter: the delay does not come back, and the
sidecar is still running.

Two related properties of the same tool: it reverts its own rules when it is asked to stop, so a
sidecar that is gone took its rule with it; and it returns from `docker run --detach` as soon as
the container is *created*, not when the rule is *applied*. A fault once ran for thirteen minutes
with no rule in place, and the recording wrote a bundle of a perfectly healthy world.

## What a recreate does to the services around it

Callers see the connection reset while the container comes back, and the dependency graph's
inbound edges name exactly which callers those are. Where a reverted value is a dependency
address, the services it was pointing at see traffic move - a second-order effect on a service
nobody alerted on.

**A recreate can also produce a second wave of errors on its own**: a service that crash-loops
while a dependency comes back keeps its callers erroring, which refills the rate window and
delays the all-clear. The recovery is not instantaneous and the alerting does not say it is.

## And the container is not a baseline afterwards

`world-warm-up-latency` covers the four-minute decay. The recorder enforces the same thing from
the other side: it will not start a recording against a container that has been up for less than
300 seconds.
