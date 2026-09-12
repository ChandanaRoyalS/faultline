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

## The consequence

**This world can neither cause the fault nor perform the remedy**, and both halves are measured.
ADR-0024 measured the first: saturation is invisible here - 50x load for twenty minutes with all
three alert rules blind - so nothing pages when a service is starved of capacity.
ADR-0029 measured the second, above. A conclusion that scaling is the fix describes something
this world cannot express.
