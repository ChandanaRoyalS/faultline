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
}
"""Compose service name -> container name, across all three files the injector loads."""

CONTAINER_SERVICES: dict[str, str] = {
    container: service for service, container in SERVICE_CONTAINERS.items()
}
"""The reverse. Some names are their own opposite (`kafka`, `frontend`) - that is fine:
those services can be addressed by either mechanism without ambiguity."""


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
    """
    return CONTAINER_SERVICES.get(name, name)


def same_service(left: str, right: str) -> bool:
    """Whether two target names address the same service, whichever scheme each uses."""
    return canonical_service(left) == canonical_service(right)
