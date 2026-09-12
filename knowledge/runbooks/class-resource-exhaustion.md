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

**Resolves by `config_revert`, not by restart, and this is the counter-intuitive one.** The
squeeze *is* a configuration change - a memory limit applied to the container - so restoring
that configuration is what removes it. A restart recreates the container under the same limit
and the fault comes back with it.

## The mechanism has a narrow usable band, measured

T7.20 probed it from both sides. **Too gentle and the container restarts faster than detection**,
with nothing alerting at all. **Too harsh and it never starts**, alerts far more widely than the
fault, and stops exporting the runtime evidence that would describe it. CPU was retired as a
mechanism entirely (ADR-0013), so memory is the only one this world has.

Container logs carry allocation failures or the runtime's own out-of-memory signature. Which of
the three rules trips depends on how the runtime behaves under the limit, and the mechanism does
not settle that in advance.

## What you will not see

Saturation itself is invisible here - see `world-saturation-is-invisible`. A service being
starved is detected by what starvation does to it, never by a saturation signal.
