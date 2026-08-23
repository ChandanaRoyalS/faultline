"""The fault definitions the injector ships with (T1.4).

Defaults are chosen to produce failures this world has been observed to
produce, against thresholds T1.3 measured on a healthy baseline - a fault that
trips no alert teaches the investigator nothing, and one that flattens the
world teaches it nothing either.

Note which name each fault targets. Faults that reach containers directly
(docker update, tc netem) target the *container* name; faults that go through
compose target the *service* name. The demo names them differently on purpose
(service `cartservice`, container `cart-service`), so they are not
interchangeable. That is checked here rather than left to the reader: importing
this module validates every definition against the world's naming, so a fault
using the wrong convention fails loudly at import instead of at 2am (ADR-0011).
"""

from __future__ import annotations

from evalharness.scenario import FaultClass
from injector.faults import target_kind
from injector.models import FaultDefinition, TargetKind
from injector.world import CONTAINER_SERVICES, SERVICE_CONTAINERS


class CatalogError(RuntimeError):
    """A shipped fault definition cannot be right, so the injector refuses to load."""


def check_target(definition: FaultDefinition) -> None:
    """Raise unless `target` uses the naming convention this definition's mechanism needs."""
    kind = target_kind(definition)
    wanted, other = (
        (SERVICE_CONTAINERS, CONTAINER_SERVICES)
        if kind is TargetKind.SERVICE
        else (CONTAINER_SERVICES, SERVICE_CONTAINERS)
    )
    if definition.target in wanted:
        return

    expected = "a compose service name" if kind is TargetKind.SERVICE else "a container name"
    # The common mistake is reaching for the world's *other* name for the same
    # thing, so when that is what happened, say which one to use instead of
    # leaving the reader to work out that the two naming schemes exist.
    correction = other.get(definition.target)
    detail = (
        f"is the world's other name for the same thing - use {correction!r}"
        if correction is not None
        else "is not a name in the world injector.world describes"
    )
    raise CatalogError(
        f"{definition.id}: {definition.fault_class} addresses {expected}, "
        f"but {definition.target!r} {detail}"
    )


def _validated(definitions: tuple[FaultDefinition, ...]) -> tuple[FaultDefinition, ...]:
    for definition in definitions:
        check_target(definition)
    return definitions


CATALOG: tuple[FaultDefinition, ...] = _validated(
    (
        FaultDefinition(
            id="recommendation-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="recommendation-service",
            description=(
                "Shrink the recommendation service's memory limit below its working set. "
                "The kernel OOM-kills it, compose restarts it, and the frontend sees the gap."
            ),
            # 48m against a measured steady-state RSS of ~55MiB (800M ceiling). Chosen
            # below the working set on purpose: a limit that merely removes headroom
            # produces an OOM kill only when load happens to spike, and a fault that
            # fires sometimes is worse than no fault at all for an eval scenario.
            params={"memory": "48m"},
        ),
        FaultDefinition(
            id="flag-service-bad-deploy",
            fault_class=FaultClass.BAD_DEPLOY,
            target="featureflagservice",
            description=(
                "Deploy a build of the flag service whose GetFlag returns UNAVAILABLE. It starts "
                "and serves, then fails on the hot path - the cascade to recommendationservice "
                "and the frontend that ADR-0006 measured."
            ),
            params={"image": "faultline/ffs-stub:broken", "server": "server_broken.py"},
        ),
        FaultDefinition(
            id="flag-service-crashloop",
            fault_class=FaultClass.BAD_DEPLOY,
            target="featureflagservice",
            description=(
                "Deploy a build of the flag service that serves correctly and then exits. The "
                "world restarts it, so it flaps rather than failing or staying down - callers "
                "see bursts of UNAVAILABLE between healthy stretches, and the restart count is "
                "the only signal that names the cause."
            ),
            # The third shape of a bad deploy, and the point of having three: this is
            # neither flag-service-bad-deploy (starts, then fails every call) nor
            # cart-bad-image-tag (never starts). An agent that has learned "bad_deploy
            # means steady 5xx" should get this one wrong.
            params={"image": "faultline/ffs-stub:crashloop", "server": "server_crash.py"},
        ),
        FaultDefinition(
            id="cart-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="cart-service",
            description=(
                "Add 300ms of network delay to the cart service, well past the 250ms p95 alert "
                "threshold, so checkout slows without anything erroring outright."
            ),
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="currency-cpu-throttle",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="currencyservice",
            description=(
                "Cut the currency service's CPU quota to a sliver. Every price on every page "
                "goes through it, so conversions queue behind the CFS period and latency climbs "
                "across the storefront while nothing errors outright."
            ),
            # 0.05 CPU = 5ms of runtime per 100ms period. The currency service is a
            # small C++ gRPC server whose per-call work is short, so a quota set
            # *above* its average demand would never throttle; one set far below it
            # would queue without bound until callers time out and the fault becomes
            # an error-rate incident instead of a latency one. 0.05 sits close to the
            # measured demand on purpose, so the container exhausts its slice inside
            # most periods and stalls to the next one - tens of ms at a time, which is
            # what pushes p95 past the 250ms alert without breaking anything.
            # NOT YET REHEARSED: see ADR-0010. If p95 stays under 250ms, halve it; if
            # ServiceHighErrorRate fires instead, raise it.
            params={"cpus": "0.05"},
        ),
        FaultDefinition(
            id="ad-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="ad-service",
            description=(
                "Shrink the ad service's memory limit below its JVM working set. The heap was "
                "sized for the old ceiling, so the kernel OOM-kills it and the frontend loses "
                "its ad panel while everything else keeps serving."
            ),
            # 256m against the 700M ceiling world-arm64.override.yml gives it. That
            # ceiling was itself raised from the demo's native-x86 300M because the
            # JVM sits at its limit under emulation, so the working set is known to be
            # north of 300M and 256m cannot hold it. `docker update` moves the cgroup
            # limit under a JVM that already sized its heap for 700M, which is what
            # makes the kill prompt rather than eventual.
            params={"memory": "256m"},
        ),
        FaultDefinition(
            id="cart-bad-image-tag",
            fault_class=FaultClass.BAD_DEPLOY,
            target="cartservice",
            description=(
                "Deploy the cart service on an image tag that was never pushed. The container "
                "never starts, so cart goes dark rather than erroring: ServiceNoTraffic is the "
                "alert that names the culprit, and the callers' errors are downstream noise."
            ),
            # A plausible hotfix tag against the world's real image name, so the
            # investigator has to notice the tag is wrong rather than that the image
            # is obviously foreign. No `server` param, so nothing is built: the point
            # is that this tag resolves nowhere.
            params={"image": "ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2"},
        ),
        FaultDefinition(
            id="productcatalog-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="product-catalog-service",
            description=(
                "Add 300ms of network delay to the product catalog service. It sits on the "
                "product listing and the checkout path both, so the slowdown shows up in two "
                "places at once and the shared dependency is the thing to find."
            ),
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="cart-redis-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="cartservice",
            description=(
                "Point the cart service at the wrong Redis port. The dependency is up, the "
                "config is wrong, and only cart operations fail - a config-revert, not a rollback."
            ),
            params={"env_var": "REDIS_ADDR", "value": "redis-cart:6380"},
        ),
        FaultDefinition(
            id="checkout-currency-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="checkoutservice",
            description=(
                "Point the checkout service at a currency host that does not exist. Currency "
                "itself is healthy and serving everyone else, so only checkout fails - the "
                "evidence is in the caller's config, not in the dependency."
            ),
            # A hostname in the shape the world's own addresses take, resolving nowhere
            # on the compose network. The port stays 7001 so the wrong thing is the
            # host, and only the host.
            #
            # No scenario cites this fault at n=10. It is a near-duplicate of
            # cart-redis-misconfig - a service pointed at an address that does not
            # answer - and bad_config has two slots for three faults (ADR-0008).
            # Kept as the T7.1 spare: do not delete it to tidy the gap.
            params={"env_var": "CURRENCY_SERVICE_ADDR", "value": "currencyservice-canary:7001"},
        ),
        FaultDefinition(
            id="product-catalog-flag-failure",
            fault_class=FaultClass.BAD_CONFIG,
            target="featureflagservice",
            description=(
                "Turn on the demo's own productCatalogFailure flag at the flag service. "
                "GetProduct starts failing for one product id, so the product catalog errors "
                "on part of its traffic and the cause is a flag, not the service's own code."
            ),
            # The stub answers every flag "disabled" unless FAULTLINE_ENABLED_FLAGS
            # names it (ADR-0006, ADR-0010). productCatalogFailure is read by
            # productcatalogservice itself - see world/src/productcatalogservice/main.go -
            # so this is the demo's designed failure mode, driven from config rather
            # than from a rebuilt image.
            params={"env_var": "FAULTLINE_ENABLED_FLAGS", "value": "productCatalogFailure"},
        ),
    )
)


def by_id(fault_id: str) -> FaultDefinition | None:
    return next((f for f in CATALOG if f.id == fault_id), None)
