---
id: world-tracing-artifact-edges
title: Some dependency edges are artifacts of how the world is run
origin: authored
applies_to: [frontendproxy]
signals: []
actions: []
---

The dependency graph is built from spans, which means it records what the world *did* during
the capture window - including things the application does not actually depend on.

## frontendproxy

Its only measured edge is `frontendproxy -> jaeger-all-in-one`: the tracing UI routing itself.
That is infrastructure observing infrastructure, not an application dependency, and ADR-0017
classifies the service `artifact_only` for exactly this reason.

Scoping an investigation through that edge walks from the shop into the tracing stack and
returns services that cannot be involved in a shop incident.

## The general rule

An edge in a span-derived graph is evidence that two things talked, not that one depends on
the other. Before using an edge to widen a blast radius, ask whether the traffic it represents
is the application working or the platform observing itself.

## And the other direction

An absent edge means "not seen in the capture window", never "not there". The service catalog
declares only observed dependencies and a test enforces that direction, so the declared graph
is a floor - treat a missing edge as unknown rather than as ruled out.
