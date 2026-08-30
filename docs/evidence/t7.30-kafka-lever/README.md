# T7.30 — the lever that engaged and did not hold

Measurement only. No scenario, no agent. NMT was enabled through a temporary override outside the
repository, the container was restored to its committed definition afterwards, and
`compose_digest f5bd108f…` / `observability_digest 857d95b4…` are verified unmoved.

## The corrected diagnosis, in one line

**kafka runs an x86-64 image under Rosetta emulation, and the memory that grows is the emulator's
JIT translation cache — not glibc arenas.** T7.27 measured a real effect, but a secondary one.

## The finding that reframes everything: this container is emulated

| check | result |
|---|---|
| image | `ghcr.io/open-telemetry/demo:v1.2.1-kafka`, **`arch: amd64`** |
| host | **`arm64`** |
| `uname -m` inside the container | **`x86_64`** |
| mapped into PID 1 | **`/run/rosetta/rosetta`** |
| distro | RHEL 8.6, glibc 2.28 — the container T7.27 described |

**This was already in the repository.** ADR-0005 records that ~20 demo images are amd64-only and run
under Rosetta, and that *"the demo sets per-container limits tuned for native x86… Measured usage
under emulation sat at those ceilings."* Memory inflation under emulation is a documented, accepted
property of this world. T7.27 diagnosed an emulated container's memory without reading it against
that ADR, and reached for glibc instead.

## Where the memory actually is

Captured at **14.12 h uptime with the lever live**, immediately before the restart that this task's
NMT run required — the grown state is destroyed by that restart, so it was recorded first.

| | value |
|---|---:|
| container | **1.997 GiB / 2 GiB — 99.87%** |
| cgroup `anon` | 2,123,079,680 (2,024 MB) |
| cgroup `anon_thp` | **1,962,934,272 (1,872 MB — 93% of anon)** |
| cgroup `file` | 253,952 — page cache squeezed to nothing |
| `memory.current` vs `memory.max` | 2,147,405,824 / 2,147,483,648 — **78 KB from the limit** |

Anonymous mappings, by permission:

| permission | count | total |
|---|---:|---:|
| **`rwxp` — executable** | 1,165 | **1,429 MB** |
| `rw-p` | 932 | 1,129 MB |
| `---p` — reserved, not resident | 310 | 1,254 MB |
| **64 MB glibc arena regions** | **0** | **0 MB** |

**Ten regions hold 1,408 MB of it** — one of 256 MB and nine of 128 MB. `smaps` says they are real:

```
Size:  131072 kB   Rss:  131060 kB   Private_Dirty:  131060 kB   AnonHugePages:  129024 kB
```

Fully resident, fully dirty, 98% THP-backed. Not reserved address space — committed memory.

## The ceiling argument: the JVM cannot own this

The same style of argument T7.27 used, applied to the category that matters:

> **`Code (reserved=248994KB, committed=20918KB)`** — 243 MB is the most the JVM's code cache can
> *ever* be, because that is its reservation.

Observed executable anonymous memory: **1,429 MB**. **At least 1,186 MB of executable memory cannot
be JVM code**, and glibc arenas were at **zero** the whole time. The regions also sit at `0xefff…`,
nowhere near the JVM heap at `0xe7000000`, while Rosetta itself is mapped at `0x800000000000`.

Executable memory is written by something that generates machine code. With the JVM's own generator
bounded at 243 MB and arenas gone, the emulator is what remains.

## NMT re-run, same method, directly comparable

| | T7.27 (lever off) | **T7.30 (lever on)** |
|---|---:|---:|
| Total committed | 584,958 KB | **586,971 KB** |
| Java Heap | 409,600 KB | **409,600 KB** |
| Class | 54,350 KB | 55,987 KB |
| Thread | 9,344 KB | 9,481 KB |
| Code | 17,369 KB | 20,296 KB |
| GC | 68,571 KB | 68,674 KB |

**The JVM's own footprint is unchanged by the lever.** Whatever the setting did, it did not do it
inside the JVM.

## The decisive comparison: the gap opens identically with arenas at zero

T7.27 sampled the anon-versus-NMT gap at 5 and 30 minutes. This run sampled on the same cadence.

| | T7.27 — **68 arenas** | **T7.30 — 0 arenas** |
|---|---:|---:|
| anon at ~25–30 min | 616,168 KB | **617,388 KB** |
| gap at ~25–30 min | **+23 MB** | **+23 MB** |

**Same anon, same gap, same trajectory, opposite arena counts.** Arena retention cannot be
producing a gap that opens identically in a process with no arenas. This is the falsification.

## Separating load from time — and it separates cleanly

Full series in [`nmt-samples-at-rest.csv`](nmt-samples-at-rest.csv) and
[`load-probe.txt`](load-probe.txt).

| window | duration | anon rate | `rwxp` change |
|---|---:|---:|---:|
| **at rest, post-warm-up** | 1.42 h | **+6.2 MB/h** | **+0 MB** |
| **under load** (client churn, same process) | 0.22 h | **+221 MB/h** | **+128 MB** |
| T7.29 sweep (8 injections) | 2.78 h | +151 MB/h | — |

**A 36× difference between rest and load, measured within a single process** — so container age,
uptime and configuration are all held constant and only the work varies.

**The load probe caught the mechanism in the act.** Four cycles of Kafka client churn
(`checkout-service` + `accounting-service` restarts, replicating what T7.29's sweep did eight
times). For three cycles `rwxp` total held at 142 MB while its *region count* crept 959 → 1037 —
small translations accumulating. On the fourth cycle **a single new 128 MB block appeared**, exactly
the unit that dominates the grown state:

```
t=10min  anon=628MB  rwxp=142MB (1037 regions)
t=13min  anon=671MB  rwxp=270MB (1053 regions)   <-- one 128 MB translation block
```

**Growth tracks work, not uptime**, which is what a translation cache does: it fills when new code
paths execute, and a fault injection is precisely an instruction to run error paths that normal
traffic never reaches.

## What this does to T7.27's ~55 MB/h

**T7.27's rate was measured over its 5 → 30 minute window, which is the JIT warm-up phase.** This
run's warm-up-inclusive rate is **+38 MB/h** — the same regime. Its post-warm-up rate is
**+6.2 MB/h**.

T7.27 extrapolated the warm-up rate to *~1.3 GB/day* and observed that this "matches the 1.86 GiB
reached in 1.5 days." **The arithmetic matched and the reasoning did not.** At the true idle rate,
1.86 GiB would take about twelve days. It arrived in 1.5 days because the world was *working* —
which is why the extrapolation appeared to confirm a mechanism that is not there.

## So which of the three was it

The question was whether T7.27 measured a real but secondary effect, whether the arena signature was
a symptom of the same allocation, or whether this is a different mechanism that only shows under
load. **It is the first and the third, and not the second.**

- **Real.** 68 regions of 63.9 MB existed and `MALLOC_ARENA_MAX=2` collapsed them to 0. The lever
  did exactly what T7.27 said it would.
- **Secondary.** Arenas held *address space* — 7,413 → 2,456 MB mapped. The resident growth was
  never in them, which is why removing them changed the address-space figure and nothing else.
- **A different mechanism, and load-driven.** The translation cache is a distinct allocation by a
  distinct allocator (Rosetta, not glibc), and at rest it does not grow at all.

**Not a symptom of the same allocation.** Two different allocators holding two different kinds of
memory; T7.27 found one and attributed the other's growth to it.

## What should happen to `MALLOC_ARENA_MAX=2`

**It is in the world, it moved a `compose_digest`, and it forced T7.28's full re-record of eleven
bundles — for a benefit that has not been demonstrated in resident memory.** Stating that plainly is
the point of this section.

**Recommendation: keep it, and record that it is kept for a different reason than it was added.**

- **Removing it costs another digest move**, another full catalog re-record, and it would invalidate
  dev sweep 7 — the only current-world benchmark, measured three days ago. That is a large, certain
  cost against no measured benefit either way.
- **It has no measured downside.** The JVM footprint is identical with and without it, and arena
  address space is genuinely lower.
- **It is not the fix, and must not be recorded as one.**

**What would justify keeping it on its own merits:** evidence that reduced address-space
fragmentation matters here — for instance a measurement showing allocation failures or THP behaviour
that improves with fewer arenas. None has been taken.

**What would justify removing it:** the next time the world moves for an independent reason. At that
moment the digest is moving anyway and the re-record is already being paid for, so dropping a
setting that does nothing measurable becomes free. **Removing it on its own is not worth a re-record.**

**The actual fixes, none of which is a malloc tunable:**

1. **Recycle kafka before recording.** T7.29 established this and this task confirms the mechanism —
   a restart clears the translation cache completely (99.87% → 26.27%). Cheap, and already required.
2. **Raise the limit.** Honest but temporary: T7.1 measured that 1200M → 2g bought about nine hours,
   and growth is work-driven rather than bounded, so any ceiling is a delay.
3. **Run kafka natively on arm64.** ADR-0005 already names this exit — *"revisit if… a later demo
   release publishes arm64 images."* This finding is a second, independent reason to want it, and
   the only one of the three that removes the mechanism rather than managing it.

## What this does not establish

**No measurement of Rosetta's internals.** The attribution rests on a ceiling argument, the
executable permission bit, the address ranges, and a 128 MB block appearing under load — not on
instrumenting the emulator, which is closed.

**The load proxy is not the sweep.** The probe used client churn; T7.29's window ran eight fault
injections. Both produce rates far above rest (221 and 151 MB/h against 6.2), and the probe caught a
translation block being allocated, but **the probe does not reproduce the sweep and no equivalence
between the two is claimed.**

**The missing cell is lever-off-under-load.** Getting it means putting the old configuration back,
which moves the digest and invalidates the catalog. So the lever's effect is isolated **at rest
only**, where it is nil.

## World state

Left healthy: **15 services reporting**, only `frontend-proxy` silent (its documented clean state),
**no alerts firing**, kafka fresh at **26.27%**, `accounting-service` restarted after the kafka
cycle per T7.27's operational rule. The temporary NMT override was deleted and both digests verified
unmoved.
