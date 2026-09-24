"""What the pinned world calls its services, and what docker calls their containers (T1.5).

The OTel demo gives almost every service an explicit `container_name` that is not
its compose service name - service `cartservice` runs in container `cart-service`.
The injector needs both, because its mechanisms are split down that line: `docker
update` and `tc netem` address a container, while a compose override addresses a
service. A definition that uses the wrong one either fails with an opaque "no such
container" or, worse, silently addresses nothing.

This map is what makes that checkable at catalog-load time (ADR-0011). It is a
hand-maintained copy of naming that lives in `./world`, which is a pinned clone
this repo does not own and cannot import from - the clone does not exist until
`make world-up`, and `make check` must pass without it. `tests/test_injector_world
.py` reads the real compose files and fails on any drift, whenever they are present.

Comparison is the map's other job. Two targets that look nothing alike can be the
same service, so anything asking *which* service a scenario touches goes through
`canonical_service` rather than `==` - see its docstring for what raw comparison
gets wrong.

Services behind a compose profile (the demo's test runners) are left out: they are
not part of the world `make world-up` starts, so nothing may target them.

**Two worlds, two maps** (T7.0 #6, 2026-09-24). v2 names every container after its service, so
its map is the identity over 28 services plus this repository's four telemetry containers - and
it is still a map rather than an assumption, because `canonical_service` on v1 turns
`load-generator` into `loadgenerator`, which on v2 is a service that does not exist. Which map is
live follows `ToolSettings.world`, the one setting that names the world for the whole run; the
module-level `SERVICE_CONTAINERS` stays v1's for the callers that read it as a constant, and
`service_containers()` is what reads the current world's.
"""

from __future__ import annotations

SERVICE_CONTAINERS: dict[str, str] = {
    "accountingservice": "accounting-service",
    "adservice": "ad-service",
    "alertmanager": "alertmanager",
    "cartservice": "cart-service",
    "checkoutservice": "checkout-service",
    "currencyservice": "currency-service",
    "emailservice": "email-service",
    "featureflagservice": "feature-flag-service",
    "ffs_postgres": "postgres",
    "frauddetectionservice": "frauddetection-service",
    "frontend": "frontend",
    "frontendproxy": "frontend-proxy",
    "grafana": "grafana",
    "jaeger": "jaeger",
    "kafka": "kafka",
    "loadgenerator": "load-generator",
    "loki": "loki",
    "otelcol": "otel-col",
    "paymentservice": "payment-service",
    "productcatalogservice": "product-catalog-service",
    "prometheus": "prometheus",
    "promtail": "promtail",
    "quoteservice": "quoteservice",
    "recommendationservice": "recommendation-service",
    "redis-cart": "redis-cart",
    "shippingservice": "shipping-service",
    "tempo": "tempo",
}
"""Compose service name -> container name, across all three files the injector loads.
`tempo` is this repository's (compose/telemetry.yml, T6.1), not the demo's, and is here because
the drift test reads every file the injector loads and the deploy overlay puts it on the network."""

CONTAINER_SERVICES: dict[str, str] = {
    container: service for service, container in SERVICE_CONTAINERS.items()
}
"""The reverse. Some names are their own opposite (`kafka`, `frontend`) - that is fine:
those services can be addressed by either mechanism without ambiguity."""

SERVICE_CONTAINERS_V2: dict[str, str] = {
    name: name
    for name in (
        "accounting",
        "ad",
        "alertmanager",
        "cart",
        "checkout",
        "currency",
        "email",
        "flagd",
        "flagd-ui",
        "fraud-detection",
        "frontend",
        "frontend-proxy",
        "grafana",
        "image-provider",
        "jaeger",
        "kafka",
        "llm",
        "load-generator",
        "loki",
        "opensearch",
        "otel-collector",
        "payment",
        "postgresql",
        "product-catalog",
        "product-reviews",
        "prometheus",
        "promtail",
        "quote",
        "recommendation",
        "shipping",
        "tempo",
        "valkey-cart",
    )
}
"""v2 at tag 2.2.0: every `container_name` equals its service name, across the demo's compose
file and `compose/telemetry-v2.yml`. Read off the files on 2026-09-24; the drift test in
`tests/test_injector_world.py` compares against the clone whenever it is present."""

SERVICE_CONTAINERS_BY_WORLD: dict[str, dict[str, str]] = {
    "v1": SERVICE_CONTAINERS,
    "v2": SERVICE_CONTAINERS_V2,
}


def _world() -> str:
    # Lazy for the same reason `injector.settings` is: `faultline.tools` imports this module.
    from faultline.tools.settings import ToolSettings

    return ToolSettings().world


def service_containers(world: str | None = None) -> dict[str, str]:
    """Compose service name -> container name, for `world` (default: the tools' world)."""
    return SERVICE_CONTAINERS_BY_WORLD[world or _world()]


def container_services(world: str | None = None) -> dict[str, str]:
    """The reverse of `service_containers`, for `world`."""
    return {container: service for service, container in service_containers(world).items()}


def canonical_service(name: str) -> str:
    """The single identity behind either of the world's two names for a service.

    Comparing `target` strings directly is unsafe. Which scheme a target uses is decided
    by the fault's mechanism, not by the service: `cart-dependency-latency` reaches the
    container and targets `cart-service`, `cart-redis-misconfig` goes through compose and
    targets `cartservice`, and those are the same service. `"cart-service" ==
    "cartservice"` is `False`, so a check asking "do these two scenarios touch the same
    service" by comparing raw targets answers *no* for every pair that crosses the naming
    schemes - silently, and in the direction that reports a contamination check as clean.

    The compose service name is the canonical form: it is the name the world's own
    `docker-compose.yml` keys on, and it is the one every service has, whereas
    `container_name` is only usually declared.

    An unknown name is returned unchanged. This is an identity function, not a validator -
    `injector.catalog.check_target` is the validator, and it runs at import.

    **World-aware since T7.0 #6**: on v2 the map is the identity, and reading v1's here would
    turn v2's `load-generator` into a service v2 does not have.
    """
    return container_services().get(name, name)


def same_service(left: str, right: str) -> bool:
    """Whether two target names address the same service, whichever scheme each uses."""
    return canonical_service(left) == canonical_service(right)
