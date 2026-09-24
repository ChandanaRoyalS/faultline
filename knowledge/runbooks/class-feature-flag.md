---
id: class-feature-flag
title: Fault class - feature_flag
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceHighLatency]
actions: [revert_config]
---

A runtime flag was flipped in the flag store and the code path behind it is what fails. No
artifact changed and no configuration file was edited: the flag daemon re-read its own file, and
the services read the new value on their next evaluation.

**Resolves by `config_revert`.** The wrong thing is a value the service was handed at runtime,
and the fix is to hand it the previous value - which for a flag is the flag daemon's file, not the
service's environment. `revert_config` is the nearest action the catalog has; the container does
not need recreating for the flag to take effect, and recreating it changes nothing about the flag.

## What the change record holds

**Nothing.** This is the property that separates the class from `bad_config`, and it was
measured: the only change on the world is the flag daemon reloading a bind-mounted file, and no
compose change exists to record. *No change recorded but the world broke* is itself the signal.
An investigation that reads an empty change log and concludes "no change, so not a change-shaped
fault" has misread it; a flag flip is exactly the change-shaped fault that leaves no record here.

## What the target shows

**Errors, fast.** A flag that fails a code path fails it quickly - the failing service answered in
single-digit milliseconds - so `ServiceHighErrorRate` is the rule that fires and
`ServiceHighLatency` stays quiet. The span carries the reason: the failing service sets its span
status to an error message naming the flag, and that message is the evidence a trace read returns.

**The page lands on the caller, not the culprit.** Measured: a flag failing one product in the
catalog took the catalog service's own error ratio to under the 5% line - one failing product
diluted across everything else it serves - while the frontend, where one failed product fails the
page, went to 8% and paged. Expect the alerting service to be a caller of the flagged one, and
expect the flagged service's own ratio to sit under the rule.

**The target may log nothing.** The catalog service wrote no log line at all through thirteen
minutes of fault; it reports failure through span status, not its log. A log specialist that
returns nothing from the culprit has not found exculpatory evidence.

## Its relationship to bad_config

Both change a value the service reads. A `bad_config` value lives in the service's environment,
is recorded when it changes, and takes effect on a recreate. A flag lives in the flag store, is
recorded nowhere, and takes effect at once. The action that undoes each differs in where it is
applied, not in what it does.
