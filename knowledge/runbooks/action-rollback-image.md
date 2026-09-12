---
id: action-rollback-image
title: Action - rollback_image
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceNoTraffic]
actions: [rollback_image]
---

Redeploy a service at the image tag it ran before the most recent change, and recreate its
container. The allowlist entry is `rollback_image`, remediation class `rollback`.

## Before proposing it

The allowlist's preconditions are the operator-facing description of when this action is
appropriate: *a prior image tag for this service is recorded in change history*, and the
incident's evidence naming a deploy or image change inside its window.

**What the executor actually evaluates is drift**, and the difference is on the record rather
than an inconsistency. No change record in this world carries a prior value, so the first
precondition is unmeetable read literally; the executor compares the running container's **image
and whether it is running at all** against the declared definition instead. The second field was
added after a stopped container wearing its declared image read as *no drift* and the action was
refused. `world-change-records-have-no-prior-value` sets out why,
and which fields each action compares.

## Blast radius

One service. Callers see connection resets while the container recreates; the dependency
graph's inbound edges name exactly who. Say which callers in the proposal - "one service" is
true and unhelpful to whoever approves it.

## Approval

Required, always. Nothing in this system executes an action; the proposer cites the entry and
a human approves it.
