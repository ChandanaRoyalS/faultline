# ADR-0007: How the chaos injector breaks the world - and how it puts it back

- **Status:** accepted
- **Date:** 2026-08-22
- **Task:** T1.4 (chaos injector CLI)

## Context
Every number this project reports comes from injecting a fault with a known label and
scoring what the agents concluded. That makes the injector a measurement instrument, not a
utility script, and it inherits three requirements the rest of the system does not.

**Reversibility is the product.** A scenario is run many times. If the world does not
return to the baseline T1.3 measured, every subsequent run is scored against a different
environment and the comparison is meaningless.

**Faults must fire deterministically.** A fault that manifests only under a load spike
produces scenarios that fail intermittently for reasons unrelated to the agent under test.

**The world is pinned and unowned.** `./world` is a clean clone at v1.2.1 (ADR-0005).
Nothing in it may be edited, so every fault must be applied from the outside.

## Decision

### One mechanism per fault class, chosen for reversibility

| Class | Mechanism | Restore |
|---|---|---|
| `resource_exhaustion` | `docker update --memory` on a container | write back the inspected pre-fault limit |
| `bad_deploy` | build `faultline/ffs-stub:broken`, recreate the service on it | recreate from the world's own compose files |
| `dependency_latency` | pumba sidecar driving `tc netem` | SIGTERM the sidecar; pumba reverts its own rule |
| `bad_config` | generated compose override with one wrong env var | recreate without the override, delete the file |

The two compose-driven faults share one implementation: writing an override file and
recreating a single service (`--no-deps`, so a fault touches one service and does not
inject a second unlabelled incident; `--no-build`, because the demo's build definitions
must stay inert). The override is a real file on disk, so the change is inspectable while
the incident is live and its removal is a complete rollback.

`bad_deploy` builds its faulty image from the *same* Dockerfile as the healthy stub via a
build arg. A second image definition could drift, and then the scenario would be blaming a
deploy for an incidental difference between two images.

### Restore data is captured at inject time and persisted

`start` and `stop` are separate processes, and the pre-fault state is gone from the world
the moment we overwrite it. Each injection therefore writes a typed restore record - a
discriminated union, so mypy checks every restore path - into `.faultline/injections.json`.

Three behaviours follow from treating that file as the source of truth:

- Stopping an inactive fault exits 0. Resetting the world must be safe to repeat, and a
  demo script cannot branch on whether the previous run cleaned up.
- Re-injecting an active fault is refused, because the second inject would capture
  post-fault values as the restore record and strand the world broken permanently.
- A failed restore keeps its state entry and exits non-zero, so a retry still has the data.

### Defaults are grounded in measurements of this world, not round numbers

The memory squeeze first defaulted to 64m. Measured, the recommendation service's
steady-state RSS is ~55MiB against an 800M ceiling, so 64m removed headroom without ever
forcing a kill. At 48m the container is OOM-killed and restarted repeatedly and sits pinned
at its ceiling - the fault fires every time. Likewise the cart delay is 300ms because T1.3
set the p95 latency alert at 250ms on a baseline of 1.9-9.6ms.

## Consequences

Verified against the live world, each fault injected, observed, and reverted:

- **resource_exhaustion**: limit 800M -> 48m, container OOM-killed twice within 2 minutes,
  memory pinned at 47.6/48MiB; restored to exactly 838860800/1677721600 bytes.
- **bad_deploy**: `recommendation-service` logged `StatusCode.UNAVAILABLE: flag store
  unreachable`, errors reached the frontend - the cascade ADR-0006 measured - and the
  service came back on `faultline/ffs-stub:1` with the storefront at HTTP 200.
- **dependency_latency**: `qdisc netem ... delay 300.0ms` present on `cart-service` eth0
  during the fault, back to `noqueue` after `stop`.
- **bad_config**: `REDIS_ADDR=redis-cart:6380` in the running container and in its logs,
  back to `:6379` after `stop`.

What this costs:

**The compose file list is duplicated** between the Makefile's `COMPOSE_WORLD` and
`InjectorSettings.compose_files`. They must agree or the injector addresses a different
compose project than `make world-up` created. Overriding one from the other means making
the Makefile depend on the Python package, and a shell-level import of make variables is
worse than the duplication.

**Latency injection runs an emulated tc image.** `gaiadocker/iproute2` is amd64-only and
publishes no version tags, so on Apple Silicon it runs under emulation, pinned only to
`latest`. Pumba itself is pinned at 0.10.1 and does publish arm64. Measured: the netem rule
applies and reverts correctly. Accepted, because the alternative is maintaining our own
arm64 tc image for one short-lived privileged command.

**Pumba enumerates every container** to find its target, and dies if any of them references
an image that no longer exists locally. This surfaced on a world where an earlier stub
build had been retagged and pruned; recreating that service fixed it. Faults injected
through pumba therefore have a dependency on the whole world being coherent, not just on
their target.

**A pumba fault goes silently inert if its target container is recreated** (measured
2026-08-23, T1.5). Pumba binds to the container that existed when the sidecar started. Once
that container is replaced, netem is not re-applied to its successor, and the sidecar keeps
running with nothing to shape.

Measured on `cart-dependency-latency`: cartservice p95 ran 1.9ms at baseline and ~650ms
under the fault. After `docker restart cart-service`, p95 decayed 668 -> 600 -> 495 -> 390
-> 3.7 -> 1.9ms over roughly two minutes - that is the 2m rate window emptying, not a slow
recovery - and stayed there. The delay did not return, with the sidecar still running.

This is the useful half: it is what makes `restart` the correct
`expected_remediation_class` for both `dependency_latency` scenarios, rather than the
least-bad of four options (ADR-0008).

The dangerous half is that **`faultline-inject status` still reports the fault active**.
The state file records what was injected, and the sidecar is genuinely still up, so nothing
in the injector's model is wrong by its own lights - but the world no longer has the fault
in it. State and world have diverged, and there is no signal anywhere that they have.

Not reachable during a rehearsal: `evalharness.rehearse` never restarts a container, and it
injects, dwells and reverts without touching the target. It is reachable by a person
debugging by hand, which is exactly when someone restarts a container to see what happens -
and they will then be looking at a world they believe is faulted and is not. The failure
mode is a wrong conclusion, not a broken run.

Not fixed here, deliberately: detecting it means the injector polling container identity
for the lifetime of every pumba fault, which is a background process this codebase does not
otherwise have. `stop` remains correct either way - it removes the sidecar, and removing a
sidecar that is shaping nothing is a no-op that succeeds. Revisit if a scenario ever needs
a container restart while a latency fault is live.

**Superseded in part by ADR-0010**, which adds a second mechanism to two of these classes
(CPU quota under `resource_exhaustion`, an unresolvable image tag under `bad_deploy`) and
seven more definitions. The table above is no longer the whole list.

Revisit if: T7.0's four additional fault classes need a mechanism this structure cannot
express, or a scenario needs two faults active on one target at once - the state file
allows it, but nothing has been measured about how their restores interact.
