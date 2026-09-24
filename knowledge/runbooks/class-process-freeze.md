---
id: class-process-freeze
title: Fault class - process_freeze
origin: authored
applies_to: [any]
signals: [ServiceHighLatency, ServiceNoTraffic, ServiceHighErrorRate]
actions: [restart_service]
---

The service's process is stopped - every thread frozen - while its container, its network and
its listening socket all remain. Connections are accepted into the kernel's backlog and never
answered.

**Resolves by `restart`.** A frozen process resumes when it is unfrozen; where an operator cannot
do that directly, recreating the container replaces the frozen process with a live one, which is
what `restart_service` does. Nothing was changed, so nothing is reverted.

## What the callers show, measured

**They hang.** A frozen service does not refuse a connection, so a caller does not fail fast: it
waits out its deadline. Measured on the frozen catalog service's direct caller: **0.0% errors and
a p95 off the top of the histogram**, with throughput down by 80% because every hanging request
held capacity. The errors surface one hop further up, where a proxy times the caller out.

**Everything behind the caller goes silent.** Seven services fired `ServiceNoTraffic` with
nothing wrong with them, because the caller that would have called them was stuck. Freezing one
leaf produced **thirteen alerts on ten services**. The alert shape is *hang and cascade*, and it
is the topology's, not the mechanism's: any accept-and-never-answer fault on a hub dependency
looks like this.

**The target itself pages by absence.** Its rate reads zero once the rate window drains, and
`ServiceNoTraffic` fires on it about eight minutes after the freeze - the five-minute window plus
the rule's three-minute hold. It is rarely the first alert.

## What the target shows

**Nothing.** A frozen process cannot log, cannot export, cannot answer. Its log has no new line,
its spans are absent, and its change history is empty. Every one of those is consistent with a
process that is simply not running, and the difference from a crashloop is that a crashloop
*refuses* - fast errors at the caller and a startup banner in the log every restart - where a
freeze accepts and hangs.

## Recovery is not clean, and that is expected

When the process resumes, every request that was hanging wakes at once, many past their
deadlines, and fails together: a **second wave of error-rate alerts** - on the target and its
callers - about two minutes after the resume, lasting two or three. Measured at nearly six
minutes from resume to quiet. An error-rate alert on the target *after* it was resumed is the
thundering herd, not a second fault.

## Its relationship to network_partition

From a caller's side the two are the same fault: a peer that accepts and never answers, the same
thirteen alerts, the same numbers within noise. What separates them is the target's own log - a
frozen process writes nothing; a cut-off one keeps running and complains that it cannot reach
anything. The distinction is thin and it is the one a human operator uses.
