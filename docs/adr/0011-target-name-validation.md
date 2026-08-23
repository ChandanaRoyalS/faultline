# ADR-0011: Fault targets are validated against the world's naming at catalog load

- **Status:** accepted
- **Date:** 2026-08-22
- **Task:** T1.5 (scenario coverage)

## Context
`FaultDefinition.target` means two different things depending on the mechanism behind the
fault. `docker update` and `tc netem` reach a container and need a *container* name; a
generated compose override reaches a service and needs a *compose service* name. The OTel
demo gives almost every service an explicit `container_name` that differs from it -
`cartservice` runs in `cart-service`, `productcatalogservice` in `product-catalog-service`.

ADR-0007 documented this in a comment at the top of the catalog and left it there. That was
survivable with four definitions. It is not survivable at twelve. Both failure modes are
loud, and both are loud about the wrong thing:

- Get it wrong on a docker-CLI mechanism and `docker inspect` says "no such container".
- Get it wrong on a compose mechanism and the override *declares* a service that does not
  exist in the base files. Measured on a scratch pair of files: compose rejects the whole
  project with `service "cart-service" has neither an image nor a build context specified:
  invalid compose project`. The real target is untouched, and nothing in the message
  mentions the fault, the override, or the fact that two naming schemes exist.

Neither is discovered at the moment the mistake is made. Both are discovered mid-rehearsal
against a running world, which is the expensive place to discover a typo.

## Decision

### The check runs at import, not at inject

`injector.catalog` validates every definition as the module loads, and raises `CatalogError`
if any target uses the wrong convention. Importing the injector at all - CLI, engine, or a
test - is enough to trip it. A definition with the wrong target cannot reach a rehearsal,
because it cannot reach a running process.

`check_target` is also exported for definitions that are not in the shipped catalog, so
T7.0 and the scenario authoring path get the same check without duplicating it.

### The naming map is checked in, not read from the world

`injector.world.SERVICE_CONTAINERS` is a hand-maintained copy of the service-to-container
mapping across the three compose files the injector loads. Reading it from `./world` at
import time was rejected: that clone does not exist until `make world-up`, `make check`
must pass without it, and a check that silently no-ops when the world is absent would be
worse than no check - it would pass in CI and fail on the machine running the demo.

The cost is a copy that can drift. `tests/test_injector_world.py` parses the real compose
files and asserts the map matches, skipping when the clone is absent. **CI never clones the
world, so CI cannot catch this drift** - only a developer with `./world` checked out will,
which is also the only person who can act on it. Accepted, with the skip made explicit in
the test rather than silent.

Services behind a compose profile - the demo's `frontendTests` and `integrationTests` - are
excluded from the map, since `make world-up` never starts them and nothing may target them.

### One predicate decides the mechanism, so the check and the injection cannot disagree

`resource_exhaustion` is the only class whose target convention depends on the definition:
`memory` goes at a container, `cpus` goes through compose. Both the mechanism dispatch in
`ResourceExhaustionFault.inject` and the answer `target_kind` gives the catalog now read the
same `_is_cpu_quota` predicate. Two copies would drift, and the drift would be the worst
possible kind - a definition validated against one mechanism and injected by the other.

Each handler class declares its own answer through `Fault.target_kind`, which is abstract,
so a new fault class cannot be added without stating which naming it addresses.

## Consequences

The error names the fix rather than the problem:

```
cart-redis-misconfig: bad_config addresses a compose service name,
but 'cart-service' is the world's other name for the same thing - use 'cartservice'
```

A target belonging to neither scheme - a typo - says so instead of guessing at a correction.

**What this buys is timing and phrasing, not detection.** Both wrong-convention mistakes
already failed loudly; they failed at inject time, in compose's or docker's vocabulary
rather than the injector's. Moving the failure to import time and rewriting it in terms of
the definition is the whole of the improvement. That is worth a module and a test, and it
is not worth more than that.

**Names that are their own opposite are accepted by both mechanisms.** `kafka`, `frontend`,
`quoteservice`, `redis-cart`, and the telemetry containers use one string for service and
container alike, so neither reading can be wrong and the check has nothing to say. That is
correct, but it means the check is weakest exactly where the naming is least confusing.

**The check proves the convention, not the existence.** A definition targeting
`emailservice` passes whether or not that service is running, and `world.py` describes the
world as pinned at v1.2.1 - if ADR-0005's pin ever moves, the map moves with it and every
target is revalidated against the new world. That is a feature: the drift test will fail
before any scenario is scored against naming that has changed underneath it.

Revisit if: scenario files (T1.5) start carrying their own injection targets rather than
citing a catalog id, in which case this check has to run at scenario load too.
