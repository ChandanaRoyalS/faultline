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
limit on the container - configuration, not state. Two of this world's four fault mechanisms are
undone by this action as the thing that removes them, which is a fact about the mechanisms and
not about how often anything proposes it.

**A third has been measured to work on one target, and the scope is the point.** ADR-0027 tested
deleting a netem qdisc from one service's `eth0`: the delay cleared durably, 3 of 3, container
never restarted and the traffic shaper still running, because that shaper applies its rule once
and does not reconcile. ADR-0027's own consequences record the one other scenario it gave
that field to as **inference, not measurement**, and the repository has refused the
same generalisation twice more since. A remediation is a claim that it was tested on the thing
it is being claimed for.

## Before proposing it

The allowlist's preconditions are the operator-facing description of when this action is
appropriate: *a prior configuration for this service is recorded in change history*, and the
incident's evidence naming a configuration or flag change inside its window.

**What the executor evaluates is drift.** No change record in this world carries a prior value,
so that first precondition is unmeetable read literally; the executor compares the running
container's environment, memory limit, CPU quota and running state against the declared
definition. `world-change-records-have-no-prior-value` sets out why the catalog's prose was
reinterpreted rather than rewritten.

## Blast radius

One service - with one exception worth naming explicitly. Where the reverted value is a
dependency address, the services it was pointing at see traffic move. That is a second-order
effect on a service nobody alerted on, and it belongs in the proposal.
