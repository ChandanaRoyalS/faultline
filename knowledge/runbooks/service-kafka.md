---
id: service-kafka
title: Service - kafka
origin: authored
applies_to: [kafka]
signals: []
actions: [restart_service, revert_config]
---

The broker. `kind: infrastructure`, `tier: infrastructure`, owner `demo/platform`, `slo: null` -
no SLO row, because no rule can evaluate one for it. Its compose service name and container name
are both `kafka`.

## Its measured edges

No measured edges: this service appears in no trace and has no node in the graph.

## Why no rule can fire for it

**Its producer and consumer spans belong to the services on either side; the broker has none.**
So it has no series under either metric family the rules read - `calls_total` for
`ServiceHighErrorRate` and `ServiceNoTraffic`, `latency_bucket` for `ServiceHighLatency` - and
**none of the three can fire for it.** Not "did not fire": cannot. Its `signals` list above is
empty for that reason.

The catalog carries it anyway, as `infrastructure`: a broker the services depend on, which can be
a culprit and never a node in a span-derived graph. It is absent from the graph *and not because
the world was quiet*, which is a different fact from being absent.

It is nonetheless one of the two most talkative log producers here, at about **5,250 lines an
hour** at rest.

## Two of checkoutservice's edges pass through it

To `accountingservice` and to `frauddetectionservice`. **Trace context propagates through the
broker**, so each producer span and consumer span join into one trace and the dependency job
renders the pair as a direct edge - which is why the graph cannot see the difference between a
broker hop and an RPC, and why one of those two edges is `async` by measurement while the other
is `unmeasured`.

## Its memory is the most-watched number in this world

The container runs an **amd64 image on an arm64 host, under Rosetta**. At 14 hours of uptime it
was measured at **1.997 GiB of a 2 GiB limit - 99.87%, seventy-eight kilobytes from the ceiling**,
with the page cache squeezed to almost nothing.

**What grows is the emulator's JIT translation cache.** 1,429 MB of the container's memory was
executable anonymous mapping across 1,165 regions, with ten regions holding 1,408 MB of it -
fully resident, fully dirty, and mostly huge-page backed. **243 MB is the most the JVM's code cache
can ever be, because that is its reservation**, so at least 1,186 MB of that executable memory
cannot be JVM code - and the regions sit nowhere near the JVM heap. The JVM's footprint is unchanged
throughout: the heap sits exactly
at its 400m cap.

**Growth tracks work, not uptime.** Measured inside a single process: +6.2 MB/h at rest against
**+221 MB/h under load**, a 36× difference with container age and configuration held constant.
The mechanism was caught in the act - the executable total held flat across three cycles while
its region count crept up, then a single new 128 MB block appeared on the fourth.

## Why raising the limit is not the remedy

The limit was raised from 1200M to 2g, and it was back to **90.2% of the new limit in about nine
hours**. Contrast two containers raised the same morning, each of which settled *below* its old
ceiling. **This is unbounded growth, not undersizing** - 2 GB against roughly 600 MB of genuine
JVM footprint is nearly 3× headroom. Any ceiling is a delay when growth is work-driven.

Of the three available responses, only one removes the mechanism: recycling before recording
clears the translation cache completely and returns the container from ~99% to ~26%; raising the
limit is honest but temporary; running the broker natively on arm64 is the fix.

**Recycling an emulated long-running JVM is an operational precondition here, not a workaround**
- and the restart has a second step, because it strands the consumer that does not self-heal.

## What the gate does about it

The recorder refuses to start against any container above 90% of its limit. Kafka additionally
gets a **forward projection**: a measured growth rate of 151 MB/h is multiplied by the run's
expected hours, the result is subtracted from the 90% guard, and the run is refused if the
container is already above what is left. The limit is read from the container rather than
assumed, so raising it moves the threshold on its own, and the threshold is computed rather than
chosen.

A faster rate measured over a thirteen-minute burst was deliberately **not** used: a rate has to
be estimated over a window comparable to the horizon it predicts. The refusal is a pause rather
than a discard - nothing was injected and the scenario has not been attempted.

## Three wrong diagnoses, in order, and what each one cost

This is the most-corrected item in the repository and the sequence is the lesson.

1. **Undersizing.** A single settled reading looks identical whether a container was too small or
   simply grows to fill what it is given. Raising the limit and watching it refill settled it.
2. **The JVM heap.** Capping the heap was predicted to stop the growth. It was **half right: the
   heap stopped growing and the process did not** - 585 → 1866 MiB in about 14.5 hours against a
   fixed 400m cap. The cause proposed alongside that correction, page cache counting against the
   cgroup, was superseded too: the page cache was measured at a quarter of a megabyte.
3. **glibc arenas.** 68 anonymous regions of 63.9 MB each and 7,413 MB of mapped address space
   looked decisive, and pinning arenas to two took them to zero and the mapped space to 2,456 MB.
   **The falsification was that the growth curve did not change**: same anon, same gap, same
   trajectory, opposite arena counts. Arena retention cannot produce a gap that opens identically
   in a process with no arenas.

The rate that supported the third diagnosis had been measured over a 5-to-30-minute window, which
is the JIT warm-up phase. **The arithmetic matched and the reasoning did not** - at the true idle
rate the observed figure would have taken twelve days, and it arrived in 1.5 because the world was
working.

**The arena setting is kept, and it is kept for a different reason than it was added**: it does
not bound the growth, it has no measured downside, and removing it would cost a second digest
move. Keeping it must not be recorded as evidence that it helped.

The general form: **a memory finding in an emulated container names the emulation before it names
the allocator.** Around twenty services here run under Rosetta and any of them can grow this way.
The check is two commands - compare the image's architecture to the host's, and look for
executable anonymous regions the runtime's own code reservation cannot account for.

**What is still not established**: nothing has instrumented the emulator itself. The attribution
rests on a ceiling argument, the executable permission bit, the address ranges, and a 128 MB block
appearing under load.

## Acting on it

`restart_service` and `revert_config` operate on the container and are performable. A restart is
the documented remedy for the growth above, and it must be followed by restarting the consumer
that does not reconnect on its own. There is no alert on kafka to clear afterwards, because there
is no alert on kafka at all, so recovery is confirmed on the services either side of it.
