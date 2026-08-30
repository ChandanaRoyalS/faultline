# kafka under `MALLOC_ARENA_MAX=2` — the lever engages and does not bound growth

Passive observation alongside dev sweep 7. **No injection**, no separate task. This is the
re-measure T7.27 queued.

## The premise did not hold, and that changes what can be claimed

T7.27 said confirming the bound needs ~24h of uptime *under the setting*. The container had been up
**4h53m** when the sweep started:

```
kafka started   2026-08-29T22:12:26Z
sweep start     2026-08-30T03:05Z
sweep end       2026-08-30T05:52Z
```

Arena state is a property of process lifetime and a restart clears all of it (T7.27 measured
exactly that: 1.949 GiB → 570 MiB across a restart). So this is a **~5h → ~8h observation, not a
24h one**, and it was registered that way before the sweep ran.

## Readings

| | start 03:05Z | **end 05:52Z** | delta |
|---|---:|---:|---|
| uptime | 4h53m | **7h40m** | +2h47m |
| container | 1.399 GiB / 2 GiB — **69.95%** | 1.814 GiB / 2 GiB — **90.69%** | **+20.7 points** |
| cgroup `anon` | 1,462,681,600 | **1,903,943,680** | **+441,262,080 (+421 MB)** |
| cgroup `file` | 28,344,320 | 29,143,040 | +0.8 MB |
| cgroup `slab` | 6,836,840 | 8,066,328 | +1.2 MB |
| **64 MB arena regions** | **0** | **0** | **unchanged** |
| total mapped anon | 3,134 MB | **3,553 MB** | +419 MB |
| `MALLOC_ARENA_MAX` | `2` | `2` | in effect throughout |

## What this establishes

**The lever engaged once and stayed engaged.** T7.27 measured 68 → 0 arena regions at the moment of
restart; this shows **0 regions at both ends of a further three hours**, so the glibc per-thread
arena signature does not creep back with uptime. That part of T7.27's finding holds.

**It does not bound long-run growth.** Anonymous memory grew **421 MB in 2h47m** with the arenas
pinned at zero, and the container reached **90.69%** — past the recorder's 90% headroom guard. The
growth mechanism T7.27 identified is *reduced* in address-space terms (7,413 MB → 2,462 MB at
restart, 3,553 MB now) but the resident growth continues.

**So the queued question is answered in the direction T7.27 could not reach**: the setting is not a
fix for the growth, only for the arena signature.

## What this does not establish

**No rate comparison to T7.27's ~55 MB/h.** That figure was the anon-versus-NMT gap on a
near-idle world; this window ran **eight fault injections** including two memory squeezes. Load is
not controlled between the two measurements, so the ≈151 MB/h here is **not** evidence that the
setting made growth faster. It is evidence that growth continued to a threshold, under load.

**Nothing at 24h.** The original question — what happens over a full day under the setting — is
still unmeasured, and this observation does not substitute for it. What it does show is that the
question is no longer the interesting one: the guard is reached in under eight hours of uptime.

## Operational consequence

**Recycling kafka is now a precondition of recording, not an occasional fix.** The next rehearsal
against this container will refuse at the headroom guard unless kafka is restarted first. T7.27
already recorded that restarting kafka strands `accountingservice` and that it must be restarted
after — so the precondition is a two-step one.
