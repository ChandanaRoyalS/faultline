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

**Resolves by `config_revert`.** The wrong thing is a value the service was given, so the fix is
to restore the previous value and recreate the container - which is what `revert_config` does.
This mechanism does not touch the image.

## What the change record holds

The variable and both values, with a timestamp.

**What the logs hold is not uniform, and this document had it wrong.** An earlier version said a
service pointed at an address that no longer answers logs connection errors quoting the address
verbatim, and called that the fastest confirmation available. That is true of some
configurations in this world and false of others: one recorded capture was corrected precisely
because the misconfigured service's logs showed normal operation throughout - its logs were
exculpatory rather than diagnostic. Expect the change record to name the value. Do not rely on
the logs to.

## Its relationship to bad_deploy

Both mechanisms are changes and both are recorded in change history. They are different changes
- one moves an image reference, the other moves an environment value - and the actions that undo
them differ accordingly, `rollback_image` against `revert_config`.
