# The exact text added to `SYNTHESIZER_SYSTEM` (T4.5)

Inserted between the past-incidents paragraph and `{UNTRUSTED_RULE}`. Nothing else in any
prompt changed.

```
CHOOSING `fault_class`. The class names **what went wrong in the world** - the failing
mechanism - not **which act caused it**. Those are different questions and a change record
answers the second one.

- `resource_exhaustion`: the service ran out of something it needed - memory, CPU, file
  descriptors, connections, threads - and failed because it ran out.
- `dependency_latency`: something the service depends on became slow, and the service failed
  because it waited.
- `bad_deploy`: the running artifact is not the one that should be running - a wrong image,
  a wrong version, a build that cannot start.
- `bad_config`: a configuration value is itself wrong - it names the wrong address, port,
  credential, limit or flag - **and the wrongness of that value is the failure**.

A change record is **evidence for** a class, never the class itself. Almost every failure has
some act upstream of it, and classifying by that act collapses this taxonomy into two values.
Ask what the service is doing wrong now, then ask what would make it stop.

`bad_config` is right when **the misconfiguration is the mechanism** - the value is wrong and
the wrong value is what breaks the request. It is not right merely because a configuration edit
appears upstream. A limit lowered until a process is killed for exceeding it is
`resource_exhaustion`: the edit is how it started, exhaustion is what is happening. A setting
that inserts delay into a call path is `dependency_latency`: the wait is the failure. An image
reference pointed at the wrong artifact is `bad_deploy`, even though an image reference is
configuration.

The same discipline applies to `remediation_class`: name the fix that would actually resolve
this, which is not always the inverse of the last change.
```
