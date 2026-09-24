---
id: class-network-partition
title: Fault class - network_partition
origin: authored
applies_to: [any]
signals: [ServiceHighLatency, ServiceNoTraffic, ServiceHighErrorRate]
actions: [reconnect_service]
---

The service's container is cut from the network it shares with its callers and its
dependencies. Its process keeps running; it can reach nothing and nothing can reach it.

**Resolves by `reconnect`.** The container needs re-attaching to the network, not recreating:
the process is healthy and nothing about it changed. `reconnect_service` is that action; the
catalog lists it and the executor does not yet perform it, so a proposal may name it and must
not expect it to run.

## Why a cut-off service hangs rather than refuses, measured

Removing a container from its network removes its interface, and packets on the connections its
callers already hold are **dropped, not reset**: nothing sends a reset or an unreachable, so the
caller waits out its deadline. New connections fare no better - the name is gone from the
network's own resolver and the client keeps retrying the connection it has. From the caller's
side this is indistinguishable from a frozen process: **0.0% errors and a p95 off the top of the
histogram** at the direct caller, throughput collapsed, errors surfacing one hop up at the proxy,
and everything behind the caller silent for want of calls. Measured: the same thirteen alerts on
the same ten services as a freeze, to within noise.

**The target pages by absence** - `ServiceNoTraffic` about eight to ten minutes in, once the
rate window drains - and it is not the first alert.

## What the target shows, and it is the whole distinction

**One repeating log line.** The cut-off service keeps running and keeps trying to export its
telemetry, and once a minute it writes that it could not: an upload failure naming a deadline
exceeded, for the whole duration of the fault. Its spans are absent - it cannot deliver them -
but its log reaches the log store, because the log collector reads container output through the
container runtime and not through the network the container lost.

That line is the evidence that separates this class from a freeze. It is reachable only after
the culprit has been found - the page lands on the caller, and the caller's own log says nothing
about why its dependency stopped answering.

## Recovery

Reconnect, and every request that hung wakes at once: a **second wave** of error-rate alerts on
the target and its callers two minutes after the reconnect, self-resolving within three. About
six minutes from reconnect to quiet, measured. The wave is the recovery, not a second fault.
