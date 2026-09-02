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

- A prior image tag for this service must exist in change history. Without one there is
  nothing to roll back *to*, and the proposal is unactionable.
- The incident's evidence must name a deploy or image change inside its window. An image that
  has not changed is not the cause, however plausible the service looks.

## Blast radius

One service. Callers see connection resets while the container recreates; the dependency
graph's inbound edges name exactly who. Say which callers in the proposal - "one service" is
true and unhelpful to whoever approves it.

## Approval

Required, always. Nothing in this system executes an action; the proposer cites the entry and
a human approves it.
