# The v2 world, brought up and injected — 2026-09-22

**Development machine (Apple Silicon), \$0, no model call.** OpenTelemetry Demo **2.2.0** at
`b74a7bc7`, brought up in a scratch directory outside the repository under compose project
`otelv2`, with the local v1 world stopped so nothing collided and the memory reading was clean.

**This is the attempt CLAUDE.md rule 7 asks for**, run instead of a fourth desk assessment. The
last three T7.1 documents were all reasoning; this one has measurements, and two of them contradict
what the reasoning would have predicted.

## 1. It came up 28 of 28, native, on the first attempt

| | |
|---|---|
| containers running | **28 of 28** |
| architecture | **`arm64/linux`** — native, no emulation |
| total memory | **3,327 MiB** |
| images pulled | 27, 40–90 s each |
| images built locally | **1** (`opensearch`, 28.2 s) |

**ADR-0005's problem does not exist in v2.** That ADR dropped the demo's Elixir feature-flag
service because it *"segfaults under x86 emulation on Apple Silicon"*, and
[ADR-0006](../../adr/0006-feature-flag-service-stub.md) built `ffs-stub` to stand in for it. **v2
has no Elixir service**: flags are served by `flagd`, a Go binary that pulled and ran natively with
no override. **Both ADRs' workaround is a candidate for deletion rather than porting**, which is the
opposite of what a major-version migration usually costs.

**And `world-arm64.override.yml` loses its stated reason.** Its header says the demo's limits are
*"tuned for native x86"* and that *"under emulation on Apple Silicon the same workloads use more
memory and sit at their ceilings."* Nothing is emulated here. **The file does not simply
disappear** — see §4 — but the emulation argument for it is gone.

## 2. Two traps, both found by running rather than reading

**The committed `.env` pulls an unpinned world.** At tag 2.2.0 it sets `DEMO_VERSION=latest`, and
`docker-compose.yml` uses `${DEMO_VERSION}` for every service image; `IMAGE_VERSION=2.2.0` is only
a build-cache tag. **A plain `docker compose up` at the 2.2.0 tag pulls `:latest`.** That is exactly
the unpinned world [ADR-0026](../../adr/0026-the-world-is-somebody-elses-repository.md) exists to
prevent, and the migration must set `DEMO_VERSION` explicitly. Caught before the first bring-up,
not after.

**One service has no published image.** `opensearch` carries a `build:` section — its Dockerfile
strips 22 plugins off the stock image — and `otel-collector` declares
`depends_on: opensearch: condition: service_healthy`, with no profile to exclude it. So a
`--no-build` bring-up fails at container creation and nothing starts. It builds in 28 seconds.
**It probably does not survive into Faultline's world at all**: opensearch is v2's log store where
Faultline uses Loki, and Faultline overlays its own `telemetry.yml` exactly as it does on v1.

## 3. The injection mechanism, proven end to end

`flagd` bind-mounts `./src/flagd` from the host and watches the file
(`--uri file:./etc/flagd/demo.flagd.json`). **Injection is a file edit. flagd hot-reloads it. No
container is recreated.**

**Three attempts, and the third is decisive.**

| # | flag | result |
|---|---|---|
| 1 | `adFailure` | flagd logged the reload (`filepath event: … WRITE`); **no failure seen in 2 ad requests** |
| 2 | `failedReadinessProbe` | **no effect, and could not have had one** |
| 3 | **`productCatalogFailure`** | **200 → 500 → 200, control product 200 throughout** |

**Attempt 1 was underpowered, not failed, and the distinction is the finding.** `AdService.java`
throws *"1/10 of the time"* — `random.nextInt(10) == 0` — and the service took two requests after
the flip. At p = 0.1 that shows no failure **81%** of the time. The test was designed wrong; the
mechanism was never tested.

**Attempt 2 is a real negative and it belongs to the world, not the flag.** `docker inspect cart`
returns an empty health status because **v2's compose defines exactly two healthchecks** (kafka and
opensearch), and the chart's `livenessProbe` is commented out. **`failedReadinessProbe` flips a
health endpoint that nothing polls**, under either deployment shape. It is inert, and a scenario
authored against it would inject nothing.

**Attempt 3 is the proof:**

```
baseline   GET /api/products/OLJCESPC7Z   HTTP 200
inject     flag -> on                     HTTP 500
control    GET /api/products/66VCHSJNUP   HTTP 200
revert     flag -> off                    HTTP 200
```

`checkProductFailure` returns early unless the id is `OLJCESPC7Z`, so the fault is **deterministic
and scoped to one product**. The control was run in the same breath as the injection precisely so
that *the world broke* and *the world broke where it was aimed* are two separate observations.
**Inject, scope, revert — the T1.4 bar, met by a mechanism that needs no container recreation.**

## 4. What this costs, stated with the wins

**Five of the fifteen flags are probabilistic or rate-based**, where every v1 fault is
deterministic — a wrong image takes the container down, full stop. `adFailure` is 1/10,
`paymentFailure` reads a rate, `recommendationCacheFailure` is ~50%, `llmRateLimitError` is random,
`emailMemoryLeak` is a multiplier. **Partial stochastic degradation is more realistic than total
failure and it is harder to author against**: the scenario needs enough traffic for the fault to
manifest, and the alert threshold has to be reachable at a 10% error rate. That is a scenario-design
constraint, and it is registered here rather than discovered during a sweep.

**Two containers sit at their memory ceilings while idle**: `llm` at **49.68 / 50 MiB (99.4%)** and
`flagd-ui` at **187.1 / 200 MiB (93.5%)**, with kafka at 78% and opensearch at 77%. This is the
condition Faultline's pre-flight gate refuses — *"a dozen memory limits were raised because
containers sat at 95%+ idle and tripped the baseline gate"*. **So an override file is still needed**,
for different services and for a different reason than emulation.

## 5. What it settles beyond T7.1

**The VM can host this.** 3,327 MiB against the deployment's **11 GB available**
(2026-09-21's [reboot drill](../deploy-drills/2026-09-21-the-reboot-drill.md)), where the v1 world
consumes 3.75 GiB. v2 is **not meaningfully heavier than what already runs there**, which was not
obvious in advance and which the earlier estimate got wrong in the other direction.

## 6. What is still unknown

**Whether the other twelve flags produce anything observable**, and which of them reach metrics,
logs and traces rather than only an HTTP status. Attempt 2 shows that *implemented* and
*observable* are different properties in this world.

**Whether the flags individuate as classes.** [ADR-0043](../../adr/0043-what-individuates-a-fault-class.md)
makes mechanism the criterion and [ADR-0029](../../adr/0029-four-fault-classes-and-why-there-is-no-fifth.md)
§4's topology finding the acceptance test: alert shapes must be distinct, or classes merge. Nothing
here measures an alert — v2's own Prometheus was running, Faultline's rules were not.

**And nothing here is a scenario.** One product returning 500 is an injection, not a labelled,
rehearsed catalog entry with a ground truth and a recorded page.
