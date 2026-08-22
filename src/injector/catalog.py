"""The fault definitions the injector ships with (T1.4).

Defaults are chosen to produce failures this world has been observed to
produce, against thresholds T1.3 measured on a healthy baseline - a fault that
trips no alert teaches the investigator nothing, and one that flattens the
world teaches it nothing either.

Note which name each fault targets. Faults that reach containers directly
(docker update, tc netem) target the *container* name; faults that go through
compose target the *service* name. The demo names them differently on purpose
(service `cartservice`, container `cart-service`), so they are not
interchangeable.
"""

from __future__ import annotations

from evalharness.scenario import FaultClass
from injector.models import FaultDefinition

CATALOG: tuple[FaultDefinition, ...] = (
    FaultDefinition(
        id="recommendation-memory-squeeze",
        fault_class=FaultClass.RESOURCE_EXHAUSTION,
        target="recommendation-service",
        description=(
            "Shrink the recommendation service's memory limit far below its working set. "
            "The kernel OOM-kills it, compose restarts it, and the frontend sees the gap."
        ),
        params={"memory": "64m"},
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
        id="cart-redis-misconfig",
        fault_class=FaultClass.BAD_CONFIG,
        target="cartservice",
        description=(
            "Point the cart service at the wrong Redis port. The dependency is up, the "
            "config is wrong, and only cart operations fail - a config-revert, not a rollback."
        ),
        params={"env_var": "REDIS_ADDR", "value": "redis-cart:6380"},
    ),
)


def by_id(fault_id: str) -> FaultDefinition | None:
    return next((f for f in CATALOG if f.id == fault_id), None)
