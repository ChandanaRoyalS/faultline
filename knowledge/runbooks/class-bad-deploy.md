---
id: class-bad-deploy
title: Fault class - bad_deploy
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceNoTraffic]
actions: [rollback_image]
---

A service is running an image it should not be. In this world the mechanism is a compose image
tag changed under the service, and the container recreated.

**Resolves by `rollback`.** Every scenario labelled `bad_deploy` in the catalog carries
`expected_remediation_class: rollback`, without exception.

## Confirming it

Change history is the first and usually the only query needed: an image reference that changed
inside the incident window, on the service the alert names or one hop upstream of it. Logs
confirm the shape of the failure; they rarely identify it faster than the change record.

## What makes this class easy to get wrong

A wrong image often produces *no* errors on the service itself - it fails to start, or starts
and refuses connections, so the errors surface on its callers. The service named by the loudest
alert is frequently not the service whose image changed.
