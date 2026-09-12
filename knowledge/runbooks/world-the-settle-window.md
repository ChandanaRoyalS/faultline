---
id: world-the-settle-window
title: The settle window, and why a resolved incident reopens rather than a new one opening
origin: authored
applies_to: [any]
signals: []
actions: []
---

`FAULTLINE_ORCH_SETTLE_WINDOW_SECONDS`, default **300**. It has exactly one job and it is easy to
mistake for a different one.

## The correlation rule, in order

1. If an incident is **open** and the event correlates into it - join it.
2. If no incident is open but one **closed within the settle window** - join that one,
   **reopening it**.
3. Otherwise - open a new incident.

## What closes an incident is not this window

An incident closes when **every episode in it is resolved**. That turns on an observable event and
needs no timer. An earlier reading had the window governing closure; the correction is recorded in
ADR-0016, and after it **the settle window's only job is step 2.**

## Reopening puts an incident back, it does not restart it

A `RESOLVED` incident carries the state it was in when it closed, so a reopen returns it to that
state - or to `OPEN` if it never started - and clears its resolution. Re-admission to the work
queue happens only if it goes back to `OPEN`.

The announcement fires only on a genuine open. **A reopen inside the window is the same incident,
and a channel that announced it twice would be reporting one fault as two.** Each join records
which rule admitted it, so a settle-window join is distinguishable afterwards from an overlap
join.

## Why 300 seconds, and why it is flagged rather than asserted

The floor is arithmetic from the rule file: a recovery-caused alert cannot appear sooner than its
`for:` clause after the remediation - 2m, 3m, and about 6m respectively (`world-alert-timing`).
**5 minutes catches the first two and lets a recovery-caused `ServiceNoTraffic` open a second
incident; 7 minutes catches all three and puts every closure seven minutes behind the world.**

ADR-0016 names it a placeholder and flags the trade-off rather than asserting it, because the
evidence base on the 5-minute side is thin.

## The consequence for anything driving this world

**A resolved incident is not a finished incident until its settle window has elapsed.** A firing
episode arriving inside the window reopens the old incident rather than opening a new one, which
is correct behaviour and is exactly how one run's alerts get attributed to a previous run's
incident. Anything that injects a fault and then waits for "an incident" has to wait out the
window first, or it will find the wrong one.

The scoring gate reads the window from the orchestrator's own settings on every call, so a
deployment that changes it moves the gate with it.

## Three different settles, same word

- **The orchestrator's settle window**, 300s, this document.
- **A post-recycle wait**, also 300s, which exists because containers need to warm up before a
  recording can start - a different quantity that happens to share a value.
- **An investigation settle**, 90s, pinned to the figure the harness waits after an alert.

They are unrelated. Reading a sentence about one as though it were about another is a mistake the
shared word invites.
