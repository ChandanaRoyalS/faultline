# The recycle that does not recycle — 2026-09-22

**\$0, no model call.** The pre-flight gate, newly able to see the v2 world, refused a sweep with
`kafka` at **92.08%** of its 620 MB limit and printed v1's documented remedy. The remedy was
followed. **It bought three percentage points.**

| | total | anon | non-heap (anon − 400 MiB committed heap) |
|---|---:|---:|---:|
| before restart, ~5 h old | 570.9 MiB — **92.08%** | 564.5 MiB | **164 MiB** |
| 30 s after restart | 550.6 MiB — **88.81%** | 482.1 MiB | **82 MiB** |

v1's measurement for the same operation, T7.30: **99.87% → 26.27%.**

## Why it is not the same phenomenon

**v2 ships `-Xms400m` equal to `-Xmx400m`.** The JVM commits its entire heap at startup, so a
restart re-commits 400 MiB immediately. The arithmetic checks out at both ends: 30 seconds after a
restart, `anon` is 482.1 MiB — 400 MiB of committed heap plus 82 MiB of JVM overhead.

v1's growth was Rosetta translation cache: accumulated, unbounded, and **genuinely freed by a
restart**. That is why ADR-0005's addendum says raising the limit is not the remedy and cycling is.
**This world is native arm64** — measured at the first bring-up, 28 of 28 containers, nothing
emulated — so there is no Rosetta here and nothing for a restart to reclaim.

**The consequence is a sizing fact, not a leak.** A freshly restarted kafka sits at **88.8%** of
620M and the gate's guard is **90%**. The container is not near its limit because it grew; **it
starts there.** No recycle cadence fixes that, and the gate would have refused nearly every sweep
on this world however often it was recycled.

## Three places were telling the operator to do it anyway

| where | what it did |
|---|---|
| `gate.py` refusal | printed v1's container names, v1's remedy, and Rosetta as the cause |
| `rehearse.py` abort | printed v1's consumer names |
| `sweep.py` `_recycle_world()` | **ran it**, with `check=False` |

**The third is the one that mattered.** `_recycle_world` executes
`docker restart accounting-service frauddetection-service checkout-service`. On v2 those containers
are `accounting`, `fraud-detection`, `checkout`, so the command fails — and `check=False` **swallowed
the error**. Nothing printed, nothing raised. The sweep would restart kafka, silently fail to
restart its consumers, wait out the settle, re-read the gate, be refused again at ~89%, and recycle
again: **a loop that burns five minutes a turn and cannot converge**, while leaving the consumers in
exactly the disconnected state T7.27 measured as quietly breaking the world.

All three now take the world. `kafka_consumers(world)` names the containers, `recycle_effect(world)`
carries what a recycle actually achieves, and `_recycle_world` **reads the exit status and says so**
rather than swallowing it.

## The fix, and why the number is what it is

**`kafka`: 620M → 1024M** in `world-v2.override.yml`.

400 MiB of committed heap is an irreducible floor. Non-heap measured 82 MiB fresh and 164 MiB at
five hours. 1024M puts a fresh container at 54% and a five-hour-old one at about 58%, leaving
~330 MiB under the gate's 90% guard — roughly twenty hours at the observed growth, which covers any
sweep — while still catching genuine runaway. It matches opensearch's existing ceiling and costs
~400 MiB on a machine measured with 11 GB free.

**`world-v2.override.yml` nominated this exact trigger in advance**, when it declined to raise
kafka on one idle reading: *"if either trips the gate under load, that is a measurement and it gets
its own row."* It has, and this is the row. `opensearch` has not and stays out.

## Raised now because it is free now and will not be later

**`rehearse` says in as many words that raising a limit is the remedy that must not be taken**, and
the reason is exact: the file holding those limits feeds `world.compose_digest` (ADR-0014), so
editing it invalidates every bundle already recorded.

That argument is right for v1 and **does not yet bind here**, for two independent reasons:

- **No v2 bundle exists.** There is nothing to invalidate.
- **`InjectorSettings.compose_files` still names v1's three files**, so nothing currently digests
  `world-v2.override.yml` at all.

**The second of those is a gap, not a licence.** A v2 bundle recorded today would carry the *v1*
world's `compose_digest` — a digest of files that are not in the world it ran on, and which
therefore cannot distinguish two different v2 worlds or tell a v2 world from a v1 one. That belongs
with the injector migration and is recorded in
[the v1-isms inventory](2026-09-22-the-harness-still-speaks-v1.md) rather than fixed here.

**The window closes when the injector is migrated.** After that, raising this limit costs the
corpus, exactly as it does on v1 today.

## Provisional, and what would revise it

**A ceiling only helps if the growth plateaus.** Non-heap went 82 → 164 MiB in five hours — a
doubling. If that is asymptotic, 1024M is generous and the container never approaches it. **If it
is linear, no limit is sufficient** and the answer is a cap on whatever is growing — direct byte
buffers or metaspace — rather than more room to grow into.

Two loosely-timed readings cannot tell those apart, which is why a sampler is now recording `anon`
and `memory.current` every five minutes. **Q88** carries the open question and names the curve as
what settles it. This figure moves if the curve says so.
