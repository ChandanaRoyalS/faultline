---
id: class-dependency-latency
title: Fault class - dependency_latency
origin: authored
applies_to: [any]
signals: [ServiceHighLatency]
actions: [restart_service]
---

Network delay injected into a container's namespace, so calls across that boundary take longer
while both processes remain healthy.

**Resolves by `restart`.** Every `dependency_latency` scenario in the catalog carries
`expected_remediation_class: restart`, because the delay lives in the container's network
namespace and recreating the container removes it. Reverting configuration changes nothing -
no configuration was changed.

## The signature

The caller's p95 rises; the callee's own p95 does not. Nothing errors, so
`ServiceHighErrorRate` stays quiet and only `ServiceHighLatency` fires. **A latency alert with
no error alert beside it is this class more often than anything else.**

Traces separate cause from effect faster than metrics here: the span tree shows which hop holds
the added time, and that hop is the injected boundary.
