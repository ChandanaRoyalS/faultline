# ADR-0005: Running the OTel demo on Apple Silicon — emulation, and dropping the feature-flag service

- **Status:** accepted
- **Date:** 2026-08-22
- **Task:** T1.1 (bring up the world)

## Context
The target environment is the OpenTelemetry Demo, pinned at v1.2.1 (ADR-0004 confirmed
this is the latest release). The development machine is Apple Silicon (arm64). Roughly
twenty of the demo's images are published for linux/amd64 only and run under Rosetta
emulation.

Two problems surfaced on first bring-up.

**Memory.** The demo sets per-container limits tuned for native x86 (frontend 200M,
adservice 300M, checkoutservice 20M). Measured usage under emulation sat *at* those
ceilings. An OOM-killed container is an incident Faultline did not inject; it would
pollute the baseline that every eval number depends on.

**The feature-flag service segfaults.** It is an Elixir/Erlang service, and the BEAM VM
does not survive x86 emulation — it crash-loops with `Segmentation fault` under both
Rosetta and QEMU. Building it natively for arm64 was attempted and failed for an unrelated
reason: the demo's 2022-era Dockerfile downloads the latest rebar3, which is now compiled
for a newer Erlang than the image's pinned OTP 25. That build would fail identically on an
Intel machine. Patching a third party's Erlang build is out of scope.

## Decision
1. **Raise memory limits** for emulated services via a version-controlled compose override
   (`compose/world-arm64.override.yml`). Limits are raised, not removed, so genuine runaway
   memory is still caught.
2. **Do not run the feature-flag service.** It is set `restart: "no"` and stopped. The
   demo's remaining nineteen services run correctly; the storefront returns HTTP 200 and
   the load generator drives normal traffic.
3. **Filter its residual error noise** (implemented in T1.2), matched narrowly to that one
   dependency's connection errors. **Superseded — see "The filter is gone" below.** The
   filter landed in promtail rather than the collector, and it was never narrow.

## Consequences
We lose the demo's built-in fault injection, which is driven by feature flags. This costs
nothing: T1.4 builds a purpose-built injector precisely because the catalog commits to
eight fault classes rather than whatever the demo happens to expose.

Measured cost of the missing service before filtering: **390 of 2317 log lines over 90
seconds (17%)**, all one repeated connection-error pattern, constant in normal operation
and therefore not a source of false alerts. After filtering, the baseline is clean.

Risk accepted: a collector-level filter can mask real signal. It is scoped to the exact
error string from the exact dead dependency, and recorded here so it is visible rather
than mysterious.

> **The two paragraphs above are the 2026-08-22 record and are no longer accurate.** The
> filter shipped in promtail, not the collector, and it was a bare term match rather than
> the scoped one described here. It has since been removed. The section below is what is
> true now; this is left in place because the gap between what an ADR claims and what the
> code does is the point of the story.

## The filter is gone (2026-08-23, T1.5)

### What it was for
The real Erlang flag service was permanently down, and its callers logged a connection
failure on every request: **390 of 2317 lines over 90 seconds, 17% of all log volume**,
one repeated pattern, constant in normal operation. Filtering it was right at the time.

### Why it no longer applies
ADR-0006 replaced that service with a native-arm64 stub that answers. The dependency the
filter was written against does not exist any more, so there is no noise left to remove.

### What was actually shipped, versus what this ADR promised
This ADR said the filter was "scoped to the exact error string from the exact dead
dependency." The implementation in `compose/promtail-config.yml` was:

```yaml
expression: ".*(featureflag|feature-flag|feature_flag).*"
```

Any line, from any container, containing the term — including a line reporting that the
flag service is healthy. The code never matched its own stated contract, and nothing
tested that it did.

### Measured before removing it
Over 30 minutes across all 20 logging containers:

| | lines |
|---|---|
| emitted | 16,510 |
| matched the drop expression | **24 (0.15%)** |

All 24 came from Loki's own container, logging the `{service="feature-flag-service"}`
queries run during this investigation. Not one line of demo traffic was being dropped.

**The risk was latent and never realised.** It is tempting to write this up as "an
over-broad filter blinded three of ten scenarios" — that is what it looked like from a
line count alone, and it is false. `feature-flag-service` sits at ~1 line/hour because the
stub prints one startup banner and nothing per request; the filter passed that line
through untouched. The honest cost of this defect was 0.15% of self-referential noise. The
honest danger was that the next flag-service scenario to log the word would have vanished
from its bundle with nothing to say why.

### Decision: deleted, not narrowed
A narrowed version was written and measured first, requiring both a reference to the flag
service *and* a connection failure. It was then removed rather than kept, because against
a dependency that no longer exists it can only ever drop zero — and a no-op filter is a
rot risk that also advertises that noise is being handled when nothing is. The history
lives here instead. `compose/promtail-config.yml` now has no `pipeline_stages` at all.

Baseline after removal, lines/hour by service, on an idle world with the load generator
running — this is the reference for judging whether a future filter is warranted:

| Service | lines/h | | Service | lines/h |
|---|---:|---|---|---:|
| `cart-service` | 5,424 | | `accounting-service` | 564 |
| `kafka` | 5,250 | | `frauddetection-service` | 564 |
| `otel-col` | 4,524 | | `quoteservice` | 564 |
| `checkout-service` | 2,256 | | `redis-cart` | 72 |
| `shipping-service` | 2,256 | | `frontend` | **0** |
| `recommendation-service` | 1,680 | | `product-catalog-service` | **0** |
| `currency-service` | 1,668 | | `feature-flag-service` | **0** |
| `email-service` | 1,128 | | `frontend-proxy` | 0 |
| `payment-service` | 1,128 | | `load-generator` | 0 |
| `loki` | 1,044 | | `alertmanager`, `grafana`, `jaeger` | 0 |
| `ad-service` | 852 | | `postgres`, `prometheus`, `promtail` | 0 |

**Total: ~29,000 lines/h**, 10-minute window, healthy world with the load generator running
and no fault injected.

Two things this baseline says that matter more than the total.

**Several services log only when something is wrong.** `frontend` measured 6,355 lines in
30 minutes earlier the same hour and **0** here. The difference is that the earlier window
overlapped an injected `cart-redis-misconfig`, and every failed request produced a gRPC
stack trace. One minute after the revert, frontend went silent and stayed silent. So the
two measurements in this ADR are *not* like-for-like: the 16,510-line figure above includes
fault traffic, the table here does not. The filter figure (24 dropped) is unaffected either
way, because all 24 were Loki's own query logs.

That is useful rather than annoying: **log volume is itself a signal.** A service going
from 0 to thousands of lines/hour is evidence, and a scenario may legitimately cite it.

**Three services are silent even under load**, and a scenario targeting them cannot expect
log evidence at all:

- `product-catalog-service` — one startup banner in 4.75 hours. Scraped, stream known to
  Loki, simply never logs per request. Two scenarios target it.
- `feature-flag-service` — the ffs-stub prints one line per start and nothing per request.
  It does log on restart, which is what `flag-service-crashloop` depends on.
- `load-generator`, `frontend-proxy` — quiet by design.

`evals/scenarios/ARTIFACTS.md` turns this into a step: check every `expected_evidence` item
against the recorded bundle before marking a scenario rehearsed. One item has already been
corrected this way.

### Standing rule
**Anything that removes telemetry is an evidence gap by construction, and ships with a
measurement of what it removes.** Drop stages, collector filters, sampling, log-level
changes, metric relabelling that discards series — all of it. This project's entire claim
is that agents can reach a correct conclusion from available evidence, so quietly
narrowing what is available invalidates the measurement rather than tuning it.

If noise returns, the fix is a scoped filter **plus a test proving what it drops**: a
fixture of lines it must remove and lines it must keep. Not a term match. Not an
unmeasured one. A filter nobody can state the cost of is not narrow, whatever its regex
looks like.

Revisit if: the project moves to x86 hardware (all of this disappears), or a later demo
release publishes arm64 images for the affected services.

## Addendum (2026-08-30, T7.30): emulation is also where kafka's unbounded memory comes from

**This ADR's "Memory" paragraph was more load-bearing than it looked.** It recorded that emulated
containers sit at ceilings tuned for native x86 and that limits were raised in response. What it did
not say — because it was not yet known — is that **emulation introduces a source of memory growth
that no container limit bounds.**

### What was found

T7.27 investigated kafka reaching 97.44% of a 2 GB limit and diagnosed **glibc arena
fragmentation**: 68 anonymous regions of exactly 63.9 MB, the per-thread arena signature. It shipped
`MALLOC_ARENA_MAX=2` in `compose/world-arm64.override.yml`, which moved `compose_digest` and forced
T7.28 to re-record all eleven runnable bundles.

**T7.29 then measured, with the lever live and arena regions at zero throughout, 421 MB of anon
growth in 2h47m — crossing the recorder's 90% guard.** T7.30 established why:

**kafka runs an `amd64` image on an `arm64` host under Rosetta** — `uname -m` returns `x86_64` and
`/run/rosetta/rosetta` is mapped into PID 1. The memory that grows is **the emulator's JIT
translation cache**. At 14 h uptime: **1,429 MB of executable (`rwxp`) anonymous memory**, 1,408 MB
of it in ten fully-resident, fully-dirty, THP-backed blocks of 128–256 MB, with **0 arena regions**.

The JVM cannot own it: NMT reports `Code (reserved=248994KB)`, so **243 MB is the most the JVM's code
cache can ever be**, leaving at least 1,186 MB of executable memory outside it.

### Why the original diagnosis looked right

The arena observation was real and reproducible, and the lever genuinely collapsed mapped anonymous
address space from 7,413 MB to 2,456 MB. **What was wrong was the attribution:** arenas held
*address space*, not the growing *resident* memory. Two allocators, two kinds of memory, and the
growth of one was attributed to the other.

The decisive comparison, same method and cadence on both sides:

| | T7.27, **68 arenas** | T7.30, **0 arenas** |
|---|---:|---:|
| anon at ~25–30 min | 616,168 KB | **617,388 KB** |
| anon-vs-NMT gap | **+23 MB** | **+23 MB** |

### It is driven by work, not uptime

Measured within a single process, so age and configuration are constant:

| window | anon rate | translation cache |
|---|---:|---:|
| at rest, post-warm-up (1.42 h) | **+6.2 MB/h** | **+0 MB** |
| under load, client churn (0.22 h) | **+221 MB/h** | **+128 MB — one new block** |

A **36× difference**. This is what a translation cache does: it fills when new code paths execute,
and a fault injection is an instruction to run error paths normal traffic never reaches. It also
explains why the growth never saturates in this project's use — every scenario exercises new code.

### Consequences for this ADR's decisions

1. **Raising memory limits does not solve emulated-service memory growth, only delays it.** T7.1
   measured 1200M → 2g buying about nine hours. Any ceiling is a delay when growth is work-driven.
   The original decision to raise limits remains correct for its actual purpose — keeping tuned-for-x86
   ceilings from OOM-killing services and polluting the baseline — but it is not a fix for this.
2. **Recycling an emulated long-running JVM is an operational precondition, not a workaround.** A
   restart clears the translation cache completely (99.87% → 26.27%). For kafka this is now required
   before recording, and T7.27's rule still applies: restarting kafka strands `accountingservice`,
   which must be restarted after it.
3. **The "revisit if" clause at the bottom of this ADR gains a second, independent reason.** Native
   arm64 images would remove this mechanism outright rather than managing it. Moving to x86 hardware
   would do the same.

### On `MALLOC_ARENA_MAX=2`, which is now in the world

**It is kept, and it is kept for a different reason than it was added.** It does not bound the
growth; it has no measured downside; and removing it would cost a second digest move, a second full
re-record, and would invalidate dev sweep 7 — the only current-world benchmark. **The honest position
is that it stays because removal is expensive and its effect is nil, not because it works.**

**It should be dropped the next time the world moves for an independent reason**, when the re-record
is already being paid for. Keeping it must not be recorded as evidence that it helped.

### Standing rule this produces

**A memory finding in an emulated container names the emulation before it names the allocator.**
Roughly twenty services here run under Rosetta, and any of them can grow this way. The check is two
commands — compare the image's `Architecture` to the host's, and look for `rwxp` anonymous regions
that the JVM's `Code` reservation cannot account for.
