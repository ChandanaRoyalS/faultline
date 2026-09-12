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

**Resolves by `rollback`.** The wrong thing is the image the container is running, so the fix is
to run the previous one again - which is what `rollback_image` does. The service's configuration
is untouched by this mechanism, so reverting configuration restores nothing.

## What the change record holds

An image reference that changed, with a timestamp - and **the new value only**. No change record
in this world carries a prior value; `world-change-records-have-no-prior-value` is why. The swap
is recorded as a change when it is made, so evidence for this class exists as a recorded fact
rather than only as an inference from symptoms.

## What the mechanism does to the container

**Two shapes, and the injector produces both**: a container that never starts, and one that
starts and fails on the hot path. Both are the same image swap. A record elsewhere in this
repository said three for a long time and was corrected at T7.39 - the injector never said so.

A container that is not running emits no spans, so while it is down no `calls_total`,
`latency_bucket` or error-ratio series exists for it at all. That is the same mechanical
consequence `world-uninstrumented-services` describes arriving by a different route.
