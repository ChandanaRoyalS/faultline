---
id: class-bad-config
title: Fault class - bad_config
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceNoTraffic]
actions: [revert_config]
---

An environment value, connection string, or feature flag was changed to something that does
not work. The service is running the right code against the wrong world.

**Resolves by `config_revert`.** Every `bad_config` scenario in the catalog is labelled that
way.

## Confirming it

The change record shows the variable and both values. A configuration pointing at an address
that no longer answers usually produces connection errors in the service's own logs with the
address quoted verbatim - the fastest confirmation available, because the wrong value appears
in the evidence rather than being inferred from it.

## Where it overlaps with bad_deploy

Both are change-induced and both are found in change history. The distinction is whether the
*image* moved or a *value* moved, and the remediation classes differ accordingly - rollback
versus config revert. Reporting the right root cause with the wrong remediation class still
scores as a miss on the remediation half.
