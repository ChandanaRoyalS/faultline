---
id: world-saturation-is-invisible
title: This world has no saturation signal
origin: authored
applies_to: [any]
signals: []
actions: []
---

**There is no saturation alert rule.** Three rules exist - error rate, latency, no traffic -
and none of them observes queue depth, connection-pool occupancy, or any plateau.

## What that costs, measured

ADR-0024 ran 50x normal load for twenty minutes with all three rules blind throughout.
Saturation queues rather than erroring, and the span metrics do not widen enough to trip the
250 ms latency threshold, so a saturated service looks healthy on every signal this world
collects.

## What it means for an investigation

Absence of evidence is not evidence of absence for this one property. A report that concludes
"no saturation" has concluded nothing - the instrument that would show it does not exist. The
honest statement is that saturation was not observable, not that it was ruled out.

Adding the rule is queued as **Q13**: `alert-rules.yml` is the first file in the observability
digest, so the change re-founds comparability for every recorded figure and waits for a batch
that is already re-recording.
