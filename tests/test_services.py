"""The service catalog (T2.4): grounded where it claims to be, and unable to drift.

Every field here is checked against the thing it came from. The SLO numbers are checked
against the alert rules that actually page; the dependencies are checked against the measured
graph; the service list is checked against the world the injector describes. A catalog whose
fields nobody checks is a document that was true the day it was written, which is the defect
this project has spent its audits finding.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from faultline.context.runbooks import load_runbooks
from faultline.context.services import catalog_path, load_services
from injector.world import SERVICE_CONTAINERS, canonical_service

ALERT_RULES = Path("compose/prometheus/alert-rules.yml")
SNAPSHOT = Path("docs/evidence/t2.4-dependency-graph/dependencies.json")
MODULE = Path("src/faultline/context/services.py")


def alert_thresholds() -> dict[str, float]:
    """The numbers the rules compare against, read out of the rules themselves."""
    rules: Any = yaml.safe_load(ALERT_RULES.read_text())
    found: dict[str, float] = {}
    for group in rules["groups"]:
        for rule in group.get("rules", []):
            match = re.search(r">\s*([0-9.]+)", rule.get("expr", ""))
            if match:
                found[rule["alert"]] = float(match.group(1))
    return found


def measured_edges() -> set[tuple[str, str]]:
    data: Any = json.loads(SNAPSHOT.read_text())["data"]
    return {(canonical_service(e["parent"]), canonical_service(e["child"])) for e in data}


def test_every_service_the_world_has_is_in_the_catalog_exactly_once() -> None:
    names = [s.name for s in load_services().services]
    assert sorted(names) == sorted(SERVICE_CONTAINERS)
    assert len(names) == len(set(names))


def test_every_container_name_matches_the_world() -> None:
    """The two naming schemes are the reason `canonical_service` exists; a catalog that got
    one wrong would send a proposed action at a container that is not there."""
    for service in load_services().services:
        assert SERVICE_CONTAINERS[service.name] == service.container


def test_no_dependency_names_a_service_that_does_not_exist() -> None:
    known = set(SERVICE_CONTAINERS)
    for service in load_services().services:
        for child in service.depends_on:
            assert child in known, f"{service.name} depends on {child!r}, which is not a service"


def test_no_declared_dependency_was_never_observed() -> None:
    """Declared edges are a subset of measured ones, never a superset.

    The graph is span-derived, so it is a **lower bound**: an absent edge means "not seen in
    the capture window", not "not there". Declaring an edge the world never showed would be
    inventing architecture, which is the one thing this catalog must not do - so the check
    runs in that direction only, and the incompleteness is recorded in ADR-0035 instead.
    """
    measured = measured_edges()
    for service in load_services().services:
        for child in service.depends_on:
            assert (service.name, child) in measured, (
                f"{service.name} -> {child} is declared and was never measured"
            )


def test_the_slo_numbers_are_the_thresholds_that_actually_page() -> None:
    """The whole reason these numbers are defensible.

    They are not a target someone chose; they are the thresholds in
    `compose/prometheus/alert-rules.yml`, which ADR-0012 set against a measured quiet
    baseline. If either moves without the other, this fails.
    """
    thresholds = alert_thresholds()

    for service in load_services().applications:
        assert service.slo is not None, f"{service.name} is an application with no SLO"
        assert service.slo.error_ratio == thresholds["ServiceHighErrorRate"]
        assert service.slo.p95_latency_ms == thresholds["ServiceHighLatency"]
        assert service.slo.source == "compose/prometheus/alert-rules.yml"


def test_only_application_services_carry_an_slo() -> None:
    """Prometheus does not page on Prometheus, and an SLO on a telemetry backend would be a
    target nothing measures."""
    for service in load_services().services:
        if service.kind != "application":
            assert service.slo is None, f"{service.name} is {service.kind} and carries an SLO"


def test_every_owner_is_marked_synthetic() -> None:
    """**The one field with nothing behind it.**

    This world has no owners: it is a demo application, and the teams do not exist. The
    `demo/` prefix is on every value so the file says so on its face rather than in a
    docstring somebody has to find. See ADR-0035.
    """
    for service in load_services().services:
        assert service.owner.startswith("demo/"), (
            f"{service.name} has owner {service.owner!r}, which reads as a real team"
        )


def test_every_runbook_link_resolves_to_a_runbook_that_exists() -> None:
    """A link to a document that does not exist is worse than no link.

    The proposer would cite it and the citation would resolve to nothing - which is
    indistinguishable, to a reader, from evidence that was recorded and then lost.
    """
    known = {runbook.id for runbook in load_runbooks()}
    for service in load_services().services:
        for link in service.runbooks:
            assert link in known, f"{service.name} links {link!r}, which is not a runbook"


def test_the_services_with_a_measured_quirk_carry_its_runbook() -> None:
    """Only two services here have a documented property that changes how they are read.

    `featureflagservice` emits no span metrics and cannot page on its own behalf (ADR-0006);
    `frontendproxy`'s only measured edge is the tracing UI routing itself (ADR-0017). Both
    facts live in the catalog already; the link is how an investigation finds the explanation.
    """
    directory = load_services()
    assert directory.get("featureflagservice").runbooks == ["world-uninstrumented-services"]
    assert directory.get("frontendproxy").runbooks == ["world-tracing-artifact-edges"]


def test_only_the_loader_names_the_catalog_file() -> None:
    offenders = [
        str(path)
        for path in Path("src").rglob("*.py")
        if path != MODULE and "services.yaml" in path.read_text()
    ]
    assert not offenders, f"these modules name the catalog file directly: {offenders}"


def test_the_catalog_is_repository_data() -> None:
    assert catalog_path().parent.name == "knowledge"
