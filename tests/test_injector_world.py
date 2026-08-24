"""The world's two names for everything, and the catalog check that keeps them straight.

`injector.world` is a hand-maintained copy of naming that lives in `./world`, a
pinned clone this repo does not own. The copy exists because `make check` must
pass on a machine that has never run `make world-up`. The first test here closes
that loop whenever the clone *is* present.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evalharness.scenario import FaultClass
from injector.catalog import CATALOG, CatalogError, check_target
from injector.models import FaultDefinition
from injector.settings import InjectorSettings
from injector.world import CONTAINER_SERVICES, SERVICE_CONTAINERS


def compose_files() -> list[Path]:
    settings = InjectorSettings()
    return [(settings.world_dir / name).resolve() for name in settings.compose_files]


def test_the_naming_map_matches_the_compose_files_it_copies() -> None:
    """Drift guard. Skips in CI, which never clones the world - see ADR-0011."""
    paths = compose_files()
    missing = [p for p in paths if not p.is_file()]
    if missing:
        pytest.skip(f"world not cloned; run `make world-up` to check this: {missing[0]}")

    declared: dict[str, str] = {}
    profiled: set[str] = set()
    for path in paths:
        services = yaml.safe_load(path.read_text()).get("services") or {}
        for name, body in services.items():
            body = body or {}
            if body.get("profiles"):
                # Behind a compose profile, so `make world-up` never starts it.
                profiled.add(name)
            if body.get("container_name"):
                declared[name] = body["container_name"]
    for name in profiled:
        declared.pop(name, None)

    assert declared == SERVICE_CONTAINERS, (
        "the world's naming has moved under injector.world; every fault definition's "
        "target was validated against the stale copy"
    )


def test_every_service_and_container_name_is_reachable_from_either_side() -> None:
    assert len(CONTAINER_SERVICES) == len(SERVICE_CONTAINERS), (
        "two services sharing a container name would make the reverse lookup lie"
    )


# --- the catalog-load check -------------------------------------------------


def probe(fault_class: FaultClass, target: str, **params: str) -> FaultDefinition:
    return FaultDefinition(
        id="probe", fault_class=fault_class, target=target, description="a probe", params=params
    )


def test_the_shipped_catalog_names_every_target_correctly() -> None:
    for definition in CATALOG:
        check_target(definition)


@pytest.mark.parametrize(
    ("definition", "expected"),
    [
        (probe(FaultClass.BAD_CONFIG, "cart-service"), "use 'cartservice'"),
        (probe(FaultClass.BAD_DEPLOY, "feature-flag-service"), "use 'featureflagservice'"),
        (
            probe(FaultClass.DEPENDENCY_LATENCY, "productcatalogservice"),
            "use 'product-catalog-service'",
        ),
        (probe(FaultClass.RESOURCE_EXHAUSTION, "adservice", memory="256m"), "use 'ad-service'"),
        (
            probe(FaultClass.RESOURCE_EXHAUSTION, "currency-service", cpus="0.05"),
            "use 'currencyservice'",
        ),
    ],
    ids=["bad_config", "bad_deploy", "dependency_latency", "memory", "cpu_quota"],
)
def test_the_wrong_convention_is_refused_by_name(
    definition: FaultDefinition, expected: str
) -> None:
    with pytest.raises(CatalogError, match=expected):
        check_target(definition)


def test_resource_exhaustion_wants_a_different_name_for_each_resource() -> None:
    """The one class whose answer depends on params - and the reason for one predicate."""
    check_target(probe(FaultClass.RESOURCE_EXHAUSTION, "ad-service", memory="256m"))
    check_target(probe(FaultClass.RESOURCE_EXHAUSTION, "currencyservice", cpus="0.05"))


def test_a_name_from_neither_scheme_says_so_rather_than_guessing() -> None:
    with pytest.raises(CatalogError, match="not a name in the world"):
        check_target(probe(FaultClass.BAD_CONFIG, "carrtservice"))


def test_a_name_that_is_its_own_container_name_satisfies_both_mechanisms() -> None:
    # `kafka` is service and container alike, so neither reading can be wrong.
    check_target(probe(FaultClass.BAD_CONFIG, "kafka"))
    check_target(probe(FaultClass.DEPENDENCY_LATENCY, "kafka"))


def test_a_fault_target_resolves_to_the_container_that_carries_its_logs() -> None:
    """The rehearsal recorder translates targets before querying Loki (evalharness.rehearse).

    Both directions matter: compose-driven faults name a service and must be translated,
    docker-driven ones already name the container and must pass through untouched.
    """
    from evalharness.rehearse import container_for

    assert container_for("cartservice") == "cart-service"
    assert container_for("featureflagservice") == "feature-flag-service"
    assert container_for("cart-service") == "cart-service", "already a container name"
    assert container_for("kafka") == "kafka", "its own opposite"
