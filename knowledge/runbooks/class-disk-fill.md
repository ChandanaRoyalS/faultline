---
id: class-disk-fill
title: Fault class - disk_fill
origin: authored
applies_to: [any]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [free_storage, restart_service]
---

The service's only writable data directory is full. Reads still work; every write fails with
*no space left on device*.

**Resolves by `free_storage`, and then by `restart` for whatever stopped consuming.** Free the
directory - remove what filled it, or recreate the service on an empty one - and the writer comes
back. Its consumers do not: in this world they do not reconnect to a broker that went away, so
they are restarted after it. `free_storage` names the first; `restart_service` on each consumer
is the second.

## What the target does, measured

**A broker halts, in seconds.** Two seconds after its directory filled, the message broker logged
that it was shutting down because all of its log directories had failed, and its supervisor
restarted it into the same full directory, over and over, for as long as the fault lasted. Its
own log is the evidence: dozens of lines of `No space left on device` and storage exceptions
naming the checkpoint file it could not write, then the shutdown line - all reachable in the
log store under the broker's name.

**The world notices six and a half minutes later.** The producer's writes hang to their delivery
timeout and then fail: `ServiceHighLatency` on it first, with a p95 off the top of the histogram,
then `ServiceHighErrorRate` half a minute after. The consumers starve - `ServiceNoTraffic` on
each, eight to eleven minutes in, one of them erroring for two minutes first as its fetches
failed loudly before its rate drained. The gap between the halt and the first alert is the rate
window plus the rule's hold, and it is the same floor every fault on this world has: a broker
outage is a six-minute-old fact by the time anything pages.

## What separates it from a misconfigured producer

A producer pointed at the wrong broker address logs connection failures while the broker's own
log is clean and its consumers are fed. A full disk shows the reverse: the broker's log is the
loudest thing in the world and the consumers are silent. Both stop orders; only one starves the
services that read them.

## What the change record holds

**Nothing.** No configuration, artifact or flag changed. Storage filled.

## Recovery

Freeing the directory on a running broker may be impossible - a broker restarting every few
seconds cannot be reached to delete a file - and recreating it on an empty directory is the
robust fix, at the cost of whatever it held. Then restart the consumers. Measured: every alert
clear four minutes after the recreate, with no second wave.

**One thing to expect after any consumer restart on a broker that kept its data**: the consumer
re-reads the last few messages it had not yet committed and re-inserts them, and each re-insert
fails on a duplicate key - about four minutes of `ServiceHighErrorRate` on the consumer, on a
world with nothing wrong. On a broker recreated empty, there is nothing to re-read and the alert
does not appear.
