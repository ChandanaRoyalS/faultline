"""T3.1 triage, against dev-split bundles and synthetic incidents only.

**Quarantine.** Every incident built here comes from a dev bundle's manifest or is synthetic.
The sync-join case is the one that would reach for `email-wrong-image`, which is **holdout** -
so it is pinned with a synthetic incident naming `checkoutservice` over the real graph instead.
Nothing about the edge under test needs the holdout bundle: the edge kind was measured once and
lives in `EDGE_KINDS`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from faultline.agents.triage import Direction, EntryReason, Triage, TriageResult
from faultline.context.catalog import GraphPresence, ServiceCatalog
from faultline.context.settings import ContextSettings
from faultline.orchestrator.models import Episode, Incident, Severity

DEV = Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "artifacts" / "dev"
START = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def triage(radius: int | None = None) -> Triage:
    settings = ContextSettings()
    return Triage(
        ServiceCatalog.from_snapshot(), radius if radius is not None else settings.hop_radius
    )


def incident_of(*services: tuple[str, int]) -> Incident:
    """A synthetic incident: (service, seconds after start) per alerting episode."""
    incident = Incident(opened_at=START, last_activity_at=START)
    for index, (service, offset) in enumerate(services):
        at = START + timedelta(seconds=offset)
        incident.episodes[f"episode-{index}"] = Episode(
            episode_key=f"episode-{index}",
            fingerprint=f"fp-{index}",
            service=service,
            severity=Severity.CRITICAL,
            alertname="ServiceHighErrorRate",
            starts_at=at,
            attached_at=at,
        )
    return incident


def incident_from_bundle(name: str) -> Incident:
    """The alert set a dev bundle actually recorded, as an incident.

    Built from `alerts_over_window`, skipping anything flagged `began_after_revert` - ADR-0009's
    rule that recovery-phase alerts are not blast radius, applied at the point the incident is
    constructed rather than left for the scorer.
    """
    manifest = json.loads((DEV / name / "manifest.json").read_text())
    entries = [a for a in manifest["alerts_over_window"] if not a.get("began_after_revert")]
    incident = Incident(opened_at=START, last_activity_at=START)
    for index, entry in enumerate(entries):
        at = datetime.fromisoformat(entry["first_seen"])
        key = f"{entry['service']}:{entry['alert']}"
        incident.episodes.setdefault(
            key,
            Episode(
                episode_key=key,
                fingerprint=f"fp-{index}",
                service=entry["service"],
                severity=Severity.CRITICAL,
                alertname=entry["alert"],
                starts_at=at,
                attached_at=at,
            ),
        )
    return incident


def by_service(result: TriageResult) -> dict[str, object]:
    return {member.service: member for member in result.blast_radius}


# --- the three pinned cases ----------------------------------------------------


def test_a_never_alerting_service_joins_through_a_measured_sync_edge() -> None:
    """`checkoutservice -> emailservice` is `sync`, measured: the callee died and the caller's
    error ratio went 0 -> 0.061 (`docs/evidence/t3.1-edge-kinds/`).

    So an incident that names only `checkoutservice` reaches `emailservice`, which is the
    `email-wrong-image` shape - checkout alerted and the broken service never did. **Pinned
    synthetically**: that bundle is holdout, and the edge kind is already measured.
    """
    result = triage().run(incident_of(("checkoutservice", 0)))
    members = by_service(result)

    assert "emailservice" in members
    email = members["emailservice"]
    assert email.reason is EntryReason.SYNC_EDGE
    assert email.direction is Direction.CANDIDATE_CAUSE, "checkout's callee, not its casualty"
    assert email.entered_at is None, "it never alerted, so no entry time was observed"
    assert email.hops == 1


def test_the_radius_does_not_spread_past_frauddetection_through_the_async_edge() -> None:
    """`frauddetection-memory-squeeze`, dev. The bundle's only alert is `ServiceNoTraffic` on
    `frauddetectionservice`, and `checkoutservice -> frauddetectionservice` is measured `async`:
    the callee sat at 0.014 req/s for 852 seconds and the caller's error ratio never left zero.

    Before the measurement, a graph-based triage would have concluded that
    `frauddetectionservice` failing endangers `checkoutservice` - which ADR-0020 §6 names as the
    exact thing this task was blocked on.
    """
    result = triage().run(incident_from_bundle("frauddetection-memory-squeeze"))

    assert result.services == {"frauddetectionservice"}
    assert "checkoutservice" not in result.services
    assert result.unmeasured_edges == [], "the only edge available was measured, and blocked"


def test_a_leaf_service_reaches_its_one_caller_and_nothing_else() -> None:
    """`adservice` is a leaf: its only edge is `frontend -> adservice`, measured `sync`.

    One leaf, one caller, nothing else. The 2-hop radius does not turn that into the frontend's
    other children - `cartservice` shares a caller with `adservice` and has nothing to do with
    it, and reaching it would mean reading a directed measurement as undirected.
    """
    result = triage().run(incident_of(("adservice", 0)))

    assert result.services == {"adservice", "frontend"}
    frontend = by_service(result)["frontend"]
    assert frontend.reason is EntryReason.SYNC_EDGE
    assert frontend.direction is Direction.ALSO_AFFECTED, "the caller is affected, not suspected"


def test_the_ad_bundles_recorded_alert_set_reproduces_that_leaf_shape() -> None:
    """The same bundle through its real alert set: frontend, loadgenerator and adservice all
    alerted, so `adservice` and its caller are both seeds and the leaf shape is inside the
    result rather than the whole of it."""
    result = triage().run(incident_from_bundle("ad-memory-squeeze"))
    members = by_service(result)

    assert {"adservice", "frontend", "loadgenerator"} <= result.services
    assert members["adservice"].direction is Direction.SEED
    assert members["frontend"].direction is Direction.SEED


# --- the semantics the contract requires ---------------------------------------


def test_an_unmeasured_edge_is_surfaced_with_the_edge_and_the_service_it_admitted() -> None:
    """Never silently either kind. The output says which edge was unmeasured and which service
    arrived through it, and the count travels with the result."""
    result = triage().run(incident_of(("checkoutservice", 0)))
    members = by_service(result)

    payment = members["paymentservice"]
    assert payment.reason is EntryReason.UNMEASURED_EDGE
    assert payment.via_edge == ("checkoutservice", "paymentservice")
    assert payment.reached_from == "checkoutservice"

    assert ("checkoutservice", "paymentservice") in result.unmeasured_edges
    assert "unmeasured edge(s) crossed" in result.summary()
    assert str(len(result.unmeasured_edges)) in result.summary(), "every output quotes its n"


def test_no_member_is_admitted_across_a_measured_async_edge() -> None:
    """The rule, stated over the whole result rather than one case."""
    result = triage().run(incident_of(("checkoutservice", 0)))

    assert "frauddetectionservice" not in result.services
    assert all(
        member.via_edge != ("checkoutservice", "frauddetectionservice")
        for member in result.blast_radius
    )


def test_a_service_absent_from_the_graph_stays_in_the_output_with_its_provenance() -> None:
    """`loadgenerator` alerts in almost every captured incident and has no graph presence - its
    only edge is the synthetic-client one, excluded at load (ADR-0017). Dropping it would report
    a service that alerted as one that was unaffected."""
    result = triage().run(incident_of(("loadgenerator", 0), ("frontend", 0)))
    members = by_service(result)

    assert "loadgenerator" in members
    assert members["loadgenerator"].presence is GraphPresence.ARTIFACT_ONLY
    assert members["loadgenerator"].reason is EntryReason.ALERTED


def test_start_from_skips_the_synthetic_client_even_when_it_alerted_first() -> None:
    """Three narratives open by setting `loadgenerator` aside - "its error rate restates what
    the storefront is doing and carries no information about cause". Starting there is the first
    wrong turn the corpus records, so the entry point is the earliest service the graph can
    actually reason about."""
    result = triage().run(incident_of(("loadgenerator", 0), ("frontend", 5), ("adservice", 20)))

    assert result.start_from == "frontend"


def test_triage_uses_the_correlation_radius_rather_than_one_of_its_own() -> None:
    """An incident and its blast radius disagreeing about how far apart two services are would
    make them describe different graphs (ADR-0017)."""
    settings = ContextSettings()

    assert settings.hop_radius == 2
    wide = triage(radius=1).run(incident_of(("adservice", 0)))
    assert wide.services == {"adservice", "frontend"}, "the leaf shape is radius-independent"


# --- the output shape ADR-0020 §6 requires -------------------------------------


def test_the_output_is_a_set_with_entry_times_and_names_no_culprit() -> None:
    """ADR-0009's scoring needs entry times; ADR-0020 §6 needs the set to be scoreable against
    the pre-revert alert set. Alerting members carry a time; graph-derived ones do not, and that
    absence is the honest value rather than an inherited guess."""
    result = triage().run(incident_of(("frontend", 0), ("checkoutservice", 30)))

    alerting = {member.service: member.entered_at for member in result.alerting}
    assert alerting == {
        "frontend": START,
        "checkoutservice": START + timedelta(seconds=30),
    }
    assert all(member.entered_at is None for member in result.blast_radius if member.hops > 0)
    assert not hasattr(result, "culprit")
    assert not hasattr(result, "ranking")


def test_severity_is_the_maximum_across_the_incidents_episodes() -> None:
    incident = incident_of(("frontend", 0))
    incident.episodes["episode-0"] = Episode(
        episode_key="episode-0",
        fingerprint="fp",
        service="frontend",
        severity=Severity.WARNING,
        alertname="ServiceHighLatency",
        starts_at=START,
        attached_at=START,
    )

    assert triage().run(incident).severity is Severity.WARNING
