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
3. **Filter its residual error noise at the OTel collector** (implemented in T1.2), matched
   narrowly to that one dependency's connection errors.

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

Revisit if: the project moves to x86 hardware (all of this disappears), or a later demo
release publishes arm64 images for the affected services.
