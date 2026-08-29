# T7.19 — what redis-cart's growth actually is

No agent, no injection. The world watched as it normally runs.

## The quantity T7.13 measured is not the one that binds

`redis-cart`'s cgroup, read directly:

| component | bytes | reclaimable before an OOM kill? |
|---|---|---|
| `anon` — the actual data | 7,438,336 | **no** |
| `file` — page cache | 9,887,744 (7,819,264 inactive) | **yes** |
| `slab` | 681,296 | mostly no |
| `memory.current` | 20,172,800 of 20,971,520 = **96.2%** | — |

96.2% looks like a container about to die. It is not: the kernel reclaims page cache before it
OOM-kills, so what binds is `anon + slab` ≈ **8.1 MiB of 20 MiB, 38.7%**.

**`redis-cart` runs RDB persistence** — `save 3600 1 300 100 60 10000`, `appendonly no`. Every
bgsave writes a multi-megabyte `dump.rdb` into page cache, and under load the `60 10000` rule fires
constantly. That is where T7.13's rise came from.

## The slopes

Three windows, at rest:

| window | length | `used_memory` | `keys` | `anon` |
|---|---|---:|---:|---:|
| T7.13 | 90 s | +39 B/s | +0.256 /s | not measured |
| **T7.19 fresh** | **11 min** | **+43.7 B/s** | **+0.31 /s** | **+129.9 B/s** |
| **T7.19 lifetime** | **27.6 h** (container uptime, 0 restarts) | — | **+0.192 /s** | **+64.8 B/s** |

**Growth is linear.** Not decelerating and not bounded: `expires=0`, every sampled TTL is `-1`,
`maxmemory` is `0` and the policy is `noeviction`. 204 bytes per key. The three key-rate figures
agree across windows spanning 90 seconds to 27.6 hours.

The `anon` figures differ by 2x between the 11-minute and 27.6-hour windows because jemalloc grows
arenas in steps; the 27.6-hour number is the one to quote.

## And `memory.current` is currently going *down*

Over the same 11 minutes: `file` **−2710 B/s**, `memory.current` **−2060 B/s**. Page cache is
draining faster than the data grows. `docker stats` reported 42.95% and then 53.36% ten minutes
later, on a container whose real occupancy moved by about 0.09 MB.

**This falsifies T7.13's own claim** that the surge left redis "permanently 11 points higher" and
that it "did not come back down when load did." It did come back down. T7.13 looked once.

## What that makes the onset

| regime | basis | time to the 20 MiB ceiling |
|---|---|---|
| at rest | measured, 27.6 h window | **≈ 55 hours** |
| at rest | measured, 11 min window | ≈ 27 hours |
| under sustained 50x load | **extrapolation**, labelled as one | ≈ 4 hours |

The load figure scales the key rate by the world's measured throughput ceiling — T7.13 found
throughput plateaus at 102 req/s, about 12x baseline, *not* 50x — and it is an extrapolation from
an at-rest slope, not an observation.

**T7.13's "roughly 90 minutes" is retired.** It extrapolated `docker stats`, which counts
reclaimable RDB page cache, toward a ceiling page cache never reaches.

## The consequence that is not hypothetical

`evalharness.rehearse.MEMORY_HEADROOM_PERCENT = 90.0` refuses a rehearsal when any container is
above 90% of its limit. At the measured rates `redis-cart` reaches that in **23–46 hours**, and the
20 MiB ceiling in 27–55 hours. Whoever hits it will see every rehearsal refused, citing a container
that no scenario touches.
