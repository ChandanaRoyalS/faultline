---
id: world-change-records-have-no-prior-value
title: A change record here names the new value and not the old one
origin: authored
applies_to: [any]
signals: []
actions: [rollback_image, revert_config]
---

The injector is the only thing in this world that changes anything, so it is also the change log.
**What it writes is deliberately less than a real change-management system would write**, and the
difference matters to anything phrased in a CD system's vocabulary.

## What a record actually holds

A record carries a resource, a summary, a `before` and an `after`. For every change the injector
can make - an image reference, an environment variable, a memory limit, a CPU quota, a network
delay - **the `before` is `None`.** The record names what the value became and never what it was.

The reverting record is the mirror image: it carries the faulted value as its `before` and no
`after` at all. So the pair of records spans the change, and neither one on its own holds two
values.

## Why the prior value is missing, which is not an oversight

The description is keyed on the **parameters** of the change rather than on the fault class.
Keying it on the class would put the class one refactor away from the output surface, and **the
class is the answer to the question being asked.** An agent reading the change log would be
reading the answer key.

So what gets written is a record an operator would have written - the fields a change ticket
carries - rather than everything the injector knows.

## The consequence for two allowlist preconditions

`rollback_image` and `revert_config` both carry preconditions phrased as *a prior X for this
service is recorded in change history*. **Read literally, no executor could ever meet them**,
because no change record here holds a prior value. ADR-0032's addendum records this: those
sentences were written in a CD system's vocabulary for a world that has no CD system.

**They were reinterpreted rather than rewritten, and the difference is deliberate.** The
catalog's prose stays as the operator-facing description of *when an action is appropriate*. What
the executor evaluates is **drift**: the running container differs from what the declared
definition would produce, in the field the action would change. `catalog_version` stayed at 1
because the catalog's meaning did not change - only the thing that had never been executable
became executable.

## What "the declared definition" means

The three hashed compose files with no generated override, rendered by compose itself, compared
against one inspection of the running container. The fields compared differ by action: the image
alone for `rollback_image`; environment, memory and CPU quota for `revert_config`; nothing at all
for `restart_service`, which recreates the service under whatever it currently runs.

A service whose only drift is its image tag has had a deploy, and an executor that reverted it
under `revert_config` would be right for the wrong reason.

**Whether the service is running is itself a drift field**, added after a first version of the
table compared image, environment and limits and never asked whether the service was up. A
declared service that is not running is the most basic drift there is.

Environment is compared on the **declared keys only**: a declared key missing from the container
or holding another value is drift, and an extra key on the container is not.
