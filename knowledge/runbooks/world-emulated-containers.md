---
id: world-emulated-containers
title: Most of this world runs under emulation, and it changes what memory means
origin: authored
applies_to: [any]
signals: []
actions: [restart_service]
---

The reference host is Apple Silicon. **Roughly twenty of the demo's images are published for
linux/amd64 only and run under Rosetta emulation**, and that is not a deployment detail - it
changes the memory behaviour of the containers and it is the first thing to check about any
memory finding here.

## The standing rule

**A memory finding in an emulated container names the emulation before it names the allocator.**
Any of the emulated services can grow this way. The check is two commands: compare the image's
architecture to the host's, and look for executable anonymous regions that the runtime's own code
reservation cannot account for.

That rule was written after a diagnosis went the other way. The emulation fact was already in the
repository when an investigation of an emulated container's memory reached for glibc instead of
reading the container's own architecture - and reached a wrong answer that took two further
measurements to unwind. `service-kafka` records that sequence in full and is the worked instance
of everything below.

## What emulation does to memory

Emulated execution builds a **JIT translation cache**, which grows as new code paths execute.
That means **growth tracks work rather than uptime**: measured inside one process, about +6 MB an
hour at rest against **+221 MB an hour under load**, a 36× difference with everything else held
constant. It also means **no container limit bounds it** - a ceiling buys time proportional to
its size and nothing more. Any ceiling is a delay when growth is work-driven.

So **recycling an emulated long-running runtime is an operational precondition here, not a
workaround.**

## The limits were raised, and that is why they exist

The demo ships per-container limits tuned for native x86 - some as low as 20M - and measured
usage under emulation sat *at* those ceilings. An OOM-killed container is an incident nobody
injected, and it would pollute the baseline every figure depends on. `compose/world-arm64.override.yml`
raises them, and **raises rather than removes them, so genuine runaway memory is still caught.**

## Telling unbounded growth from a container that was simply too small

Two containers raised the same morning **settled below their old ceilings** once given room -
which is what an undersized container does when it stops being undersized. A container that
climbs back to whatever new limit it is given is doing something else. A single settled reading
looks identical either way; it is the trajectory after the raise that separates them.

## The collector does the same thing, and the consequence is worse

`otelcol` was measured at 291.7MiB of a 300M limit after about a day up - 97.2%, **the same
unbounded shape**. Its limit was raised to 600M on the same reasoning, and the raise was taken
knowing it buys time rather than fixing the growth, because the collector is the path every
metric and trace takes: **a broker running out of memory writes a spurious incident into a
recording; a collector running out of memory writes a hole.**

It surfaces as a blocked rehearsal rather than as anything that looks like a memory problem,
because the recorder refuses to start against a container above 90% of its limit. That
consequence is reasoned rather than measured - the guard has never let it happen, which is the
guard working.

## Two exceptions worth knowing

**The feature-flag service is not emulated.** The real service segfaults under emulation and its
native build is blocked upstream - its 2022-era Dockerfile downloads a toolchain now compiled for
a newer runtime than the image pins, and that build would fail identically on an Intel machine.
It runs as a native-arm64 stub instead, which is why it emits no span metrics
(`world-uninstrumented-services`).

**The same three compose files describe a different world on different hardware.** Emulation
inflates runtime footprints measurably, so a memory ceiling that squeezes a service here need not
squeeze the same service on native x86, where it can rest at half the size. The compose files are
identical and the world is not.
