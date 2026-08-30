# T7.27 — where the kafka memory lives

Measurement only. No scenario, no agent, no recording, and `compose_digest` is verified unmoved.
NMT was enabled through a temporary override file outside the repository, and the container was
restored to its committed definition afterwards.

## The restart, which is itself the first result

| | before | after |
|---|---|---|
| container | **1.949 GiB / 2 GiB — 97.44%** | **570.1 MiB — 27.84%** |
| cgroup `anon` | 1,997,643,776 | 590,905,344 |
| uptime | ~1.5 days | 0 |

**The growth is real, accumulates with uptime, and a restart clears all of it.** It had reached
97.44% — the recorder's pre-flight guard refuses at 90%, so it was already past the point of
blocking a rehearsal.

## NMT breakdown at baseline

`Total: reserved=1950374KB, committed=584958KB` against cgroup `anon` of 590,905,344 bytes — at
start **NMT accounts for ~97% of resident anonymous memory.**

| category | committed | reserved |
|---|---:|---:|
| **Java Heap** | **409,600 KB** | 409,600 KB — hard cap, `-Xmx400m` |
| Class (metaspace) | 54,350 KB | 1,097,634 KB |
| GC | 68,571 KB | 68,571 KB |
| Code | 17,369 KB | 248,733 KB |
| Thread | 9,344 KB | 100,112 KB (stacks 99,652) |
| Symbol | 11,215 KB | — |
| Other | 5,370 KB | — |
| Arena Chunk | 5,348 KB | — |
| Internal | 924 KB | — |
| Compiler | 337 KB | — |
| **Native Memory Tracking itself** | **2,166 KB** | — |

**NMT's own overhead is ~2 MB and must not be read as a finding.** It grew to 2,361 KB over the
observation window; that is the tool, not the subject.

## Which category holds the bulk — none of them

**The JVM's own accounting cannot reach the observed number.** Filling *every* NMT category to its
reserved ceiling gives at most **0.87 GiB**, and the heap — the largest — is hard-capped at 400 MB
and was measured sitting exactly at its cap. Observed on the 1.5-day-old container: **1.86 GiB**.
**At least 0.99 GiB is outside every NMT category.**

That is the answer to "which category holds the bulk": no category does.

## Watched in the act

Sampling every 5 minutes (`nmt-samples.csv`), the gap between cgroup `anon` and NMT-committed:

| elapsed | cgroup anon | NMT committed | gap |
|---|---:|---:|---:|
| 5 min | 580,148 KB | 582,361 KB | **−2 MB** |
| 30 min | 616,168 KB | 592,780 KB | **+23 MB** |

**≈55 MB/hour accumulating outside NMT**, which extrapolates to ~1.3 GB/day and matches the
1.86 GiB reached in 1.5 days.

The `summary.diff` over that window names what moved *inside* the JVM — 13.4 MB of it, against
~37 MB of anon growth:

| candidate | NMT delta | ruled |
|---|---:|---|
| direct / mapped `ByteBuffer` (`Other`) | **+4 KB** | **out** |
| thread stacks (`Thread`) | +56 KB, count flat at 97 | **out** |
| GC structures | +229 KB | **out** |
| metaspace (`Class`) | +2,513 KB | real, tiny |
| code cache | +10,047 KB | JIT warmup after restart, bounded by 249 MB reserved — not the gigabyte |
| **Java Heap** | **0 KB** | capped and behaving |

> **Corrected 2026-08-30 (T7.30). The section below is falsified in its conclusion, and left in
> place because a hypothesis that was tested and failed is worth more in the record than one quietly
> removed.**
>
> **What survives:** 68 anonymous regions of 63.9 MB existed, they are the glibc arena signature, and
> `MALLOC_ARENA_MAX=2` collapsed them to zero. Every observation here was reproduced.
>
> **What is wrong:** the attribution. **kafka runs an x86-64 image under Rosetta emulation** — image
> `arch: amd64`, host `arm64`, `uname -m` returning `x86_64`, and `/run/rosetta/rosetta` mapped into
> PID 1. The memory that grows is **the emulator's JIT translation cache**: at 14 h uptime, 1,429 MB
> of *executable* (`rwxp`) anonymous memory, 1,408 MB of it in ten fully-resident, fully-dirty
> blocks — **with arena regions at zero throughout.**
>
> **The decisive measurement:** with the lever live and arenas at 0, the anon-versus-NMT gap opens
> to **+23 MB by 25 minutes** — against the **+23 MB at 30 minutes** recorded below with 68 arenas.
> Same trajectory, opposite arena counts. Arena retention cannot produce a gap that opens identically
> in a process with no arenas.
>
> **And the ~55 MB/h below is a warm-up rate.** It was sampled across 5 → 30 minutes, the JIT
> warm-up phase. Measured past warm-up, the idle rate is **6.2 MB/h**; under load it is
> **221 MB/h**. The growth tracks work, not uptime — so extrapolating the warm-up rate to ~1.3 GB/day
> "matching" 1.86 GiB in 1.5 days was arithmetic that happened to land, not a confirmed mechanism.
>
> See [`../t7.30-kafka-lever/README.md`](../t7.30-kafka-lever/README.md). ADR-0005 already recorded
> that ~20 demo images run under Rosetta and that measured usage under emulation sat at its ceilings;
> this investigation did not read its own container against that ADR.

### The original reasoning, now falsified

## What it is: the allocator, not the JVM

The container is **RHEL 8.6 on glibc 2.28** with **97 threads**. Its memory map carries **68
anonymous regions of exactly 63.9 MB** — the glibc per-thread arena signature — for **7,413 MB of
mapped anonymous address space**. glibc's default `M_ARENA_MAX` is 8 × cores, which is 80 here.

Arenas retain freed pages rather than returning them to the OS, so a long-running multi-threaded
process grows resident memory without the JVM allocating anything more. **The JVM is not leaking.
glibc is holding freed pages.**

## The lever, and what it was and was not shown to do

Restarted with `MALLOC_ARENA_MAX=2`:

| | default | `MALLOC_ARENA_MAX=2` |
|---|---:|---:|
| 64 MB arena regions | **68** | **0** |
| mapped anonymous address space | 7,413 MB | **2,456 MB** |

**Shown: the lever engages.** The arenas disappear and address space falls by two thirds.

**Not shown: that it bounds the long-run growth.** Confirming that needs ~1.5 days of uptime under
the setting, and this task did not run that. The mechanism and the lever are established; the
outcome is an expectation, and it should be re-measured at 24 hours after it lands.

## Is it digest-locked

**Yes.** `MALLOC_ARENA_MAX` is a container environment variable and belongs in
`compose/world-arm64.override.yml`, which is a `compose_digest` input. It cannot land without the
re-record T7.26 specifies.

**A smaller consequence worth naming:** kafka's growth is characterised in prose *inside that same
file*, in the T7.1 comment. **Even correcting that comment moves the digest**, so this addendum
lives in PLAN.md instead — the explanation cannot be filed next to the thing it explains.

> **Corrected 2026-08-30 (T7.30).** The conclusion below — *"a bounded-allocator problem, not a
> limit problem"* — is wrong on the first half. It is an **emulation** problem: the growth is
> Rosetta's translation cache, and no malloc tunable reaches it. The second half stands and is
> strengthened: a further raise still buys time and nothing else, because the growth is driven by
> work rather than bounded by a ceiling.

## Is the container simply sized wrong

**No, and this is worth stating because it changes the fix.** A 2 GB limit against ~600 MB of
genuine JVM footprint is not undersizing — it is nearly 3× headroom. The growth is unbounded in
uptime and would consume any ceiling; T7.1 already recorded that raising 1200M → 2g bought about
nine hours. **This is a bounded-allocator problem, not a limit problem**, and the same evidence
says a further raise would buy time and nothing else.

## Two operational findings

**Restarting kafka strands `accountingservice`, and it does not self-heal.**
`frauddetectionservice` reconnected on its own within three minutes; `accountingservice` sat at
0.000 req/s until restarted. Anyone cycling kafka must restart `accounting-service` after it.

**Checkout's stall returned on schedule.** It was restarted at 19:34 the previous day and was back
at 15000ms p95 roughly a day later — consistent with T7.23's estimate, and cleared again by the
restart that ADR-0025's addendum prescribes.

## World state

Left healthy: **no alerts firing**, `accountingservice` 0.183 req/s and `frauddetectionservice`
0.174 req/s both serving, kafka fresh at 26.85% with no `KAFKA_OPTS` and no `MALLOC_ARENA_MAX`,
`compose_digest 299d791c5e0da43e` unmoved. The temporary override file was deleted.
