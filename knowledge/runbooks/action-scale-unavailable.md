---
id: action-scale-unavailable
title: Action - scale_service is unperformable in this world
origin: authored
applies_to: [any]
signals: []
actions: [scale_service]
---

**Do not propose scaling.** The allowlist lists `scale_service` and marks it
`status: unperformable`.

## Why, measured

ADR-0029 measured it: Docker Compose refuses to scale a service that declares
`container_name`, and 25 of this world's services declare one. The action cannot run - not "is
discouraged", cannot run.

## Why it is listed at all rather than omitted

Two reasons, and both matter to a proposer. Omitting the class would make its absence look like
an oversight in the catalog. Listing it without the status would let something propose an
action the world cannot perform, and a proposal that cannot be executed is worse than no
proposal, because it consumes an approval decision and returns nothing.

## The consequence for the benchmark

There is no `scale` scenario in the catalog and there cannot be one until this world can both
cause and perform scaling. If an investigation concludes that scaling is the fix, the
conclusion is either wrong or describes a fault this world cannot express.
