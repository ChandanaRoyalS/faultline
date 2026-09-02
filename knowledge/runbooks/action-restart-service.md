---
id: action-restart-service
title: Action - restart_service
origin: authored
applies_to: [any]
signals: [ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service]
---

Recreate a service's container without changing its image or configuration. The allowlist
entry is `restart_service`, remediation class `restart`.

## What it actually fixes here

`dependency_latency`. The injected delay lives in the container's network namespace, so
recreating the container removes it. That is the whole mechanism, and it is why this class
resolves by restart rather than by touching configuration.

## What it does not fix

`resource_exhaustion`. The squeeze is a limit applied to the container, so a restart brings
the container back under the same limit and the fault returns. Proposing a restart for a memory
squeeze looks reasonable and is wrong.

## Blast radius, and the one irreversible property

One service, for the duration of the recreate. **This action is not reversible** - it discards
in-process state, which for this world's services is cache only. Say so in the proposal rather
than leaving the approver to know it.
