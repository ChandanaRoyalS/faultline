---
id: class-resource-exhaustion
title: Fault class - resource_exhaustion
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [revert_config]
---

A service is denied the resources it needs - in this world, by squeezing its memory limit
until the runtime cannot allocate.

**Resolves by `config_revert`, not by restart.** This is the counter-intuitive one, and the
catalog is unambiguous: every `resource_exhaustion` scenario carries
`expected_remediation_class: config_revert`. The squeeze *is* a configuration change - a limit
applied to the container - so reverting that configuration is the fix. A restart recreates the
container under the same limit and the fault returns.

## Confirming it

Container logs carry allocation failures or the runtime's own out-of-memory signature. The
symptom mix varies with how the service dies: it may error, may slow, or may go silent
entirely, so the class is confirmed from logs rather than from which alert fired.

## What you will not see

Saturation itself is invisible here - see `world-saturation-is-invisible`. A service being
starved is detected by what starvation does to it, never by a saturation signal.
