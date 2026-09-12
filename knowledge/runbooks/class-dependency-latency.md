---
id: class-dependency-latency
title: Fault class - dependency_latency
origin: authored
applies_to: [any]
signals: [ServiceHighLatency]
actions: [restart_service]
---

Network delay injected into a container's namespace, so calls across that boundary take longer
while both processes remain healthy.

**Resolves by `restart`.** The delay lives in the container's network namespace, so recreating
the container removes it - measured, and durable: after a recreate the shaper does not
re-attach, because it binds to the container that existed when it started.

**"There is no configuration to revert" was the old reason given here, and it is false.** The
qdisc is a thing on an interface and deleting it is an operation an operator can perform;
ADR-0027 measured that too, on one target, and `action-revert-config` carries what was and was
not established. The class resolves by `restart`; it does not resolve by `restart` because the
alternative is imaginary.

## What the mechanism does, measured

**The delay is paid per packet crossing the shaped interface.** What that does to the shaped
service's own metrics **depends on the service, not on the mechanism**, and this world has the
measurement that proves it: a service whose handler makes downstream calls has its own span
extended by their delayed egress and its p95 moves; **a leaf's delayed egress lands after its
server span has already closed, so its own span metrics never move at all** - measured, over a
full alert budget, with no rule firing. T7.22 recorded that a mechanism's observability is a
property of the target.

Where it does move, it moves by **a multiple set by the operation's round-trip count over that
interface, not by a fixed factor**: an operation making two round trips pays the delay twice. An
observed figure that is not the injected one is not evidence against the mechanism.

**Nothing fails.** A delayed call still succeeds, so the error ratio stays at 0.0 throughout and
`ServiceHighErrorRate` has nothing to fire on. That is a property of delay as a mechanism, not
an observation about any particular incident.

**The onset is immediate** - the qdisc attaches at once - while the *visible* onset lags it by
the 2-minute rate window filling plus the rule's 3-minute `for:` clause.

## The magnitude has a ceiling, and past it the class changes

ADR-0013: push a latency fault past the point where requests still complete and **the signal
inverts from latency to absence** - the service goes flat and healthy, then absent, and what the
world is producing is a different class under the same label. The bound is a property of the
injection, not of the investigation.
