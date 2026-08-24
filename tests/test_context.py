"""T2.4 against the graph the world actually produced. No Jaeger, no network.

The fixture and the runtime input are the same file - `docs/evidence/t2.4-dependency-graph/`
is both the committed snapshot the policy loads and the evidence it is documented by, so
there is no second copy to drift.

Every hop count asserted below was measured from that capture, not chosen. Where a number
here disagrees with the snapshot, the snapshot is right and the test is stale.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

import pytest

from faultline.context.catalog import GraphPresence, ServiceCatalog
from faultline.context.graph import ARTIFACT_EDGES, SNAPSHOT, ServiceGraph
from faultline.context.policy import DecisionLog, DependencyPolicy, JoinRule
from faultline.context.settings import ContextSettings
from faultline.ingest.models import AlertEvent, AlertStatus
from faultline.orchestrator.cap import InvestigationCap
from faultline.orchestrator.core import Orchestrator
from faultline.orchestrator.correlation import TimeOverlapPolicy
from faultline.orchestrator.store import InMemoryIncidentStore
from injector.world import SERVICE_CONTAINERS

SETTLE = timedelta(minutes=5)
EDGES_TABLE = SNAPSHOT.parent / "edges.txt"


def graph() -> ServiceGraph:
    return ServiceGraph.from_snapshot()


def catalog() -> ServiceCatalog:
    return ServiceCatalog.from_snapshot()


def event(service: str, at: datetime, *, status: AlertStatus = AlertStatus.FIRING) -> AlertEvent:
    """One alert-episode transition. Synthetic, because these services have no capture."""
    return AlertEvent(
        received_at=at,
        fingerprint=f"fp-{service}",
        episode_key=f"fp-{service}@{at.isoformat()}",
        status=status,
        service=service,
        starts_at=at - timedelta(seconds=10),
        ends_at=None,
        alert={
            "labels": {
                "alertname": "ServiceHighErrorRate",
                "service_name": service,
                "severity": "critical",
            }
        },
        group_key=f'{{}}:{{service_name="{service}"}}',
    )


def orchestrator(
    policy: object, max_concurrent: int = 3
) -> tuple[Orchestrator, InMemoryIncidentStore]:
    store = InMemoryIncidentStore()
    return (
        Orchestrator(
            store=store,
            policy=policy,  # type: ignore[arg-type]
            cap=InvestigationCap(max_concurrent),
            settle_window=SETTLE,
        ),
        store,
    )


def dependency_policy(radius: int | None = None) -> DependencyPolicy:
    return DependencyPolicy(
        catalog=catalog(),
        fallback=TimeOverlapPolicy(SETTLE),
        radius=ContextSettings().hop_radius if radius is None else radius,
        log=DecisionLog(),
    )


# --- the snapshot --------------------------------------------------------------


def test_the_snapshot_is_the_capture_the_evidence_describes() -> None:
    """Guard the fixture. If the capture is replaced, every hop count below is about
    something else."""
    payload = json.loads(SNAPSHOT.read_text())

    assert len(payload["data"]) == 17, "17 edges captured over the 24h lookback"
    assert len(graph().edges) == 15, "15 after the two artifacts"
    assert len(graph().nodes) == 13


def test_the_artifact_edges_are_gone_and_take_their_node_with_them() -> None:
    """`loadgenerator -> frontend` is the synthetic client and the largest edge in the
    capture by a factor of three; `frontendproxy -> jaeger-all-in-one` is the tracing UI
    being traced. Excluding them is the one judgement call in loading the graph."""
    edges = graph().edge_set

    assert not (edges & ARTIFACT_EDGES)
    assert "jaeger-all-in-one" not in graph().nodes, "the span store is not a service"
    assert not graph().has("loadgenerator"), "its only edge was the excluded one"


def test_every_node_is_a_service_the_world_map_knows() -> None:
    """The graph names services as OTel `service.name`; the world names them as compose
    services. They agree in 12 of 13 cases, and `frontend-proxy` is the 13th - which is why
    identity goes through `canonical_service` before anything compares it."""
    unknown = {node for node in graph().nodes if node not in SERVICE_CONTAINERS}

    assert not unknown, f"graph nodes not in injector.world: {sorted(unknown)}"


def test_the_snapshot_and_the_rendered_table_agree() -> None:
    """Two committed artifacts describing one capture. The realistic drift is that somebody
    edits one of them."""
    # Table rows are right-aligned, so they start with whitespace; the summary lines below
    # the table start at column 0 and would otherwise parse as edges.
    rendered = {
        (parts[1], parts[2])
        for line in EDGES_TABLE.read_text().splitlines()
        if line.startswith(" ") and (parts := line.split()) and parts[0].isdigit()
    }
    captured = {
        (entry["parent"], entry["child"]) for entry in json.loads(SNAPSHOT.read_text())["data"]
    }

    assert rendered == captured


def test_the_drift_guard_compares_edge_sets_and_never_call_counts() -> None:
    """`callCount` changes on every capture with no change to the world.

    A guard comparing it would fire constantly and never truthfully - the `ffs_stub_image_id`
    mistake ADR-0014 names, where a field that produces false positives and cannot produce
    true ones is worse than absent. So `edge_set` carries endpoints only.
    """
    edge_set = graph().edge_set

    assert all(isinstance(edge, tuple) and len(edge) == 2 for edge in edge_set)
    assert {e.call_count for e in graph().edges}, "counts are kept on the edges themselves"


@pytest.mark.skipif(
    not os.environ.get("FAULTLINE_GRAPH_DRIFT_URL"),
    reason="live drift check: set FAULTLINE_GRAPH_DRIFT_URL to the dependencies endpoint",
)
def test_the_snapshot_still_matches_the_running_world() -> None:  # pragma: no cover - opt-in
    """Re-query Jaeger and compare edge sets. **Opt-in by environment variable.**

    `injector.world`'s drift guard skips when the world is not cloned, which it can tell from
    the filesystem. Whether the world is *running* cannot be answered without touching it,
    and a test that probes a local port would make the suite's result depend on what happens
    to be up - the exact trap `tests/conftest.py` exists to close. So this is explicit rather
    than automatic, which is weaker: it runs when someone remembers.
    """
    import urllib.request

    url = os.environ["FAULTLINE_GRAPH_DRIFT_URL"]
    with urllib.request.urlopen(url, timeout=20) as response:
        live = json.loads(response.read().decode())

    from injector.world import canonical_service

    live_edges = {
        (canonical_service(e["parent"]), canonical_service(e["child"])) for e in live["data"]
    } - set(ARTIFACT_EDGES)

    assert live_edges == graph().edge_set, (
        "the world's dependency graph has moved under the committed snapshot. Re-capture it "
        "and update docs/evidence/t2.4-dependency-graph/ - do not edit the snapshot by hand."
    )


# --- the catalog ---------------------------------------------------------------


def test_the_uninstrumented_service_is_an_entry_rather_than_an_absence() -> None:
    """Not connected and not visible are different facts, and a bare node set cannot tell
    them apart. ADR-0017 requires the flag service be carried explicitly for exactly this."""
    entry = catalog().get("featureflagservice")

    assert entry is not None
    assert entry.presence is GraphPresence.UNINSTRUMENTED
    assert not entry.usable_for_graph_reasoning
    assert entry.reason and "ADR-0006" in entry.reason


def test_a_service_present_only_through_an_artifact_edge_says_so() -> None:
    """Excluding `loadgenerator -> frontend` removes the node, so the service that alerts in
    almost every captured incident has no graph presence. Recorded rather than left absent -
    the same argument the flag service gets."""
    entry = catalog().get("loadgenerator")

    assert entry is not None
    assert entry.presence is GraphPresence.ARTIFACT_ONLY
    assert not entry.usable_for_graph_reasoning


def test_the_catalog_canonicalises_and_admits_what_it_does_not_know() -> None:
    assert catalog().usable("cart-service"), "the container name resolves to cartservice"
    assert catalog().get("nosuchservice") is None
    assert catalog().get(None) is None


# --- the measured hop counts ---------------------------------------------------


def test_the_hop_counts_this_policy_rests_on() -> None:
    """ADR-0016 predicted the emailservice distance before the graph existed. It holds."""
    g = graph()

    assert g.hops("emailservice", "cartservice") == 2, "ADR-0016's prediction, measured"
    assert g.hops("frauddetectionservice", "cartservice") == 2, "the async edge, same shape"
    assert g.hops("adservice", "quoteservice") == 4, "two leaves, opposite ends"
    assert g.hops("cartservice", "cartservice") == 0
    assert g.hops("cartservice", "featureflagservice") is None, "no node, no distance"


# --- the policy ----------------------------------------------------------------


def test_emailservice_joins_a_checkout_adjacent_incident_at_two_hops() -> None:
    """ADR-0016's prediction, now against the real graph rather than against a guess.

    The recovery alert that ADR-0016's whole correlation section is built around is joined by
    the dependency rule as well as by the time rule that shipped.
    """
    policy = dependency_policy()
    ingest, store = orchestrator(policy)
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    ingest.apply(event("cartservice", start))

    result = ingest.apply(event("emailservice", start + timedelta(minutes=3)))

    assert result.joined and not result.opened
    assert len(store.incidents) == 1
    decision = policy.log.decisions[-1]
    assert decision.rule is JoinRule.GRAPH
    assert decision.hops == 2


def test_frauddetectionservice_joins_too_because_correlation_is_call_causality() -> None:
    """The async edge, joined on purpose.

    ADR-0017, edge semantics: the trace graph records that A's work reaches B, never that A
    waits for B, so a synchronous RPC and a Kafka topic are the same edge here - measured, as
    four `checkoutservice` edges at 286 calls each, two of each kind, identical in every
    field the API returns. The distinction is declared **out of scope for correlation**,
    which asks whether two services are related at all and for which both kinds are
    relations, and in scope for blast radius at T3.1.

    So this joins exactly as `emailservice` does, even though the bundles measure their
    failure semantics as opposite - `email-wrong-image` took checkout down and
    `frauddetection-memory-squeeze` had no downstream impact at all.
    """
    policy = dependency_policy()
    ingest, store = orchestrator(policy)
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    ingest.apply(event("cartservice", start))

    result = ingest.apply(event("frauddetectionservice", start + timedelta(minutes=3)))

    assert result.joined
    assert len(store.incidents) == 1
    assert policy.log.decisions[-1].hops == 2


def test_two_services_further_apart_than_the_radius_decline() -> None:
    """`adservice` and `quoteservice` are 4 hops apart - both leaves, opposite ends of the
    graph. This is the case `TimeOverlapPolicy` cannot express at all."""
    policy = dependency_policy()
    ingest, store = orchestrator(policy)
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)
    ingest.apply(event("adservice", start))

    result = ingest.apply(event("quoteservice", start + timedelta(minutes=1)))

    assert result.opened and not result.joined
    assert len(store.incidents) == 2, "unrelated services, unrelated incidents"
    decision = policy.log.decisions[-1]
    assert decision.rule is JoinRule.GRAPH, "the graph answered - a decline is an answer"
    assert decision.joined is None


def test_only_two_hops_is_a_usable_radius() -> None:
    """The percentages in `ContextSettings.hop_radius`, as behaviour rather than a docstring.

    1 hop fails the measured `emailservice` case the policy exists for; 3 hops joins 97% of
    pairs and cannot decline even for two leaves at opposite ends.
    """
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)

    tight = dependency_policy(radius=1)
    ingest, _ = orchestrator(tight)
    ingest.apply(event("cartservice", start))
    assert ingest.apply(event("emailservice", start + timedelta(minutes=1))).opened, (
        "radius 1 splits the incident ADR-0016 measured as one"
    )

    # `accountingservice` and `adservice` are 3 hops apart, which is where the shipped
    # radius and the next one up disagree.
    shipped = dependency_policy(radius=2)
    ingest, _ = orchestrator(shipped)
    ingest.apply(event("accountingservice", start))
    assert ingest.apply(event("adservice", start + timedelta(minutes=1))).opened, (
        "radius 2 declines a 3-hop pair, which is what makes it a filter at all"
    )

    loose = dependency_policy(radius=3)
    ingest, _ = orchestrator(loose)
    ingest.apply(event("accountingservice", start))
    assert ingest.apply(event("adservice", start + timedelta(minutes=1))).joined, (
        "radius 3 joins it, and joins 97% of all pairs - a rule that barely declines"
    )
    assert ContextSettings().hop_radius == 2


# --- the flag-service case -----------------------------------------------------


def test_the_alert_stream_from_an_uninstrumented_cause_needs_no_special_case() -> None:
    """`product-catalog-flag-failure` injects on `featureflagservice`, which has no node.

    Its alerts land elsewhere. From the bundle's manifest, `alerts_over_window` names
    `loadgenerator`, `frontend` and `productcatalogservice` - all instrumented, two of them
    in the graph. So correlation works on the services that actually alerted, and **the
    blindness is about cause attribution, not about correlation**: the graph cannot explain
    *why* product catalog is failing, because the service responsible is not in it.

    The events are synthetic; that scenario predates the webhook capture. The service set and
    its order are the bundle's.
    """
    policy = dependency_policy()
    ingest, store = orchestrator(policy)
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)

    for offset, service in enumerate(["loadgenerator", "frontend", "productcatalogservice"]):
        ingest.apply(event(service, start + timedelta(seconds=15 * offset)))

    assert len(store.incidents) == 1, "one fault, one incident, no special case anywhere"
    incident = next(iter(store.incidents.values()))
    assert len(incident.episodes) == 3

    # All three rules fire in one real alert stream, which is why the provenance is worth
    # recording: two of these three joins did not come from the graph, and the incident they
    # produced looks identical either way.
    assert [d.rule for d in policy.log.decisions] == [
        # loadgenerator has no graph presence at all - its only edge was the artifact one.
        JoinRule.NO_GRAPH_PRESENCE,
        # frontend IS in the graph, but the only open incident holds loadgenerator, so there
        # was nothing to measure against and time overlap decided.
        JoinRule.NO_JUDGEABLE_CANDIDATE,
        # By now the incident holds frontend, and productcatalogservice is one hop from it.
        JoinRule.GRAPH,
    ]
    assert policy.log.decisions[-1].hops == 1
    assert policy.log.rule_counts() == {
        "no_graph_presence": 1,
        "no_judgeable_candidate": 1,
        "graph": 1,
    }


def test_a_fallback_join_is_distinguishable_from_a_graph_join() -> None:
    """The failure this provenance exists to catch is silent: falling back to time overlap
    reproduces the behaviour the graph was meant to improve on *and produces the same
    answer*, so nothing looks wrong (ADR-0017, ADR-0008)."""
    policy = dependency_policy()
    ingest, _ = orchestrator(policy)
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)

    ingest.apply(event("loadgenerator", start))
    ingest.apply(event("loadgenerator", start + timedelta(minutes=1)))

    assert all(d.rule is not JoinRule.GRAPH for d in policy.log.decisions)
    assert any("artifact_only" in (d.detail or "") for d in policy.log.decisions)


# --- the cap test ADR-0016 could not write -------------------------------------


def test_two_unrelated_incidents_are_live_at_once_and_the_cap_can_count_to_two() -> None:
    """ADR-0016 recorded that the cap is unreachable **by construction**, not merely untested:
    `TimeOverlapPolicy` joins any firing to any live incident, so at most one incident is ever
    non-terminal and nothing can count to two.

    A policy that can decline is what changes that, and this is the first test that could be
    written. `adservice` and `quoteservice` are 4 hops apart, so both incidents stay open.
    """
    policy = dependency_policy()
    ingest, store = orchestrator(policy, max_concurrent=1)
    start = datetime(2026, 8, 24, 12, tzinfo=UTC)

    ingest.apply(event("adservice", start))
    ingest.apply(event("quoteservice", start + timedelta(minutes=1)))

    live = [i for i in store.incidents.values() if not i.is_terminal]
    assert len(live) == 2, "two concurrent incidents - impossible under TimeOverlapPolicy"
    assert sorted(i.state.value for i in live) == ["queued", "triaging"]
    assert store.active_count() == 1, "the cap held, for the first time"
