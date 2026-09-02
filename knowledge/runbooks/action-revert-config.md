---
id: action-revert-config
title: Action - revert_config
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [revert_config]
---

Restore a service's previous environment and configuration, and recreate it. The allowlist
entry is `revert_config`, remediation class `config_revert`.

## It covers two fault classes, which is unusual

`bad_config` obviously. **And `resource_exhaustion`**, because a memory squeeze is applied as a
limit on the container - configuration, not state. Two of the four fault classes in this world
resolve through this one action, which makes it the most-proposed entry in the catalog and the
one worth being most precise about.

## Before proposing it

A prior configuration for this service must exist in change history, and the incident's
evidence must name a configuration or flag change inside its window.

## Blast radius

One service - with one exception worth naming explicitly. Where the reverted value is a
dependency address, the services it was pointing at see traffic move. That is a second-order
effect on a service nobody alerted on, and it belongs in the proposal.
