"""The read routes T5.1's UI calls (T5.1).

`faultline.api.view` assembled the payload and **nothing served it**. A view nobody can fetch is a
view nobody has — the same shape as the A/A check that was library-only until its CLI landed.
Twice in one day is enough to treat "and the caller" as part of the deliverable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from faultline.agents.trajectory import InMemoryTrajectoryStore, Trajectory
from faultline.api.incidents import LIST_LIMIT, build
from faultline.orchestrator.models import Episode, Incident, Severity
from faultline.orchestrator.store import InMemoryIncidentStore

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def incident(identifier: str, service: str = "cartservice", minutes: int = 0) -> Incident:
    opened = NOW - timedelta(minutes=minutes)
    made = Incident(opened_at=opened, last_activity_at=opened)
    made.id = identifier
    made.episodes[f"{identifier}-e0"] = Episode(
        episode_key=f"{identifier}-e0",
        fingerprint="f",
        service=service,
        severity=Severity.CRITICAL,
        alertname="ServiceHighErrorRate",
        starts_at=opened,
        attached_at=opened,
    )
    return made


def client(incidents: list[Incident], trajectories: list[Trajectory] | None = None) -> TestClient:
    store = InMemoryIncidentStore()
    for made in incidents:
        store.save(made)
    trajectory_store = InMemoryTrajectoryStore()
    for trajectory in trajectories or []:
        trajectory_store.save(trajectory)
    app = FastAPI()
    app.include_router(build(store, trajectory_store))
    return TestClient(app)


# --- the routes exist and serve the view -------------------------------------------------------


def test_the_list_returns_incidents_newest_first() -> None:
    body = (
        client([incident("old", minutes=60), incident("new", minutes=1)])
        .get("/api/v1/incidents")
        .json()
    )

    assert [row["incident_id"] for row in body["incidents"]] == ["new", "old"]
    assert body["incidents"][0]["services"] == ["cartservice"]


def test_a_missing_incident_is_a_404_not_an_empty_view() -> None:
    """An incident that does not exist and one that has not been investigated are different
    states, and only the first is an error."""
    assert client([]).get("/api/v1/incidents/nope").status_code == 404


def test_an_uninvestigated_incident_is_a_200_with_no_report() -> None:
    """The state a live-updating view spends its first seconds in. It must not be an error."""
    response = client([incident("inc-1")]).get("/api/v1/incidents/inc-1")

    assert response.status_code == 200
    body = response.json()
    assert body["report"] is None
    assert body["trajectory_id"] is None


def test_the_view_finds_the_trajectory_through_the_store_not_a_field_on_the_incident() -> None:
    """**`incident.trajectory_id` does not exist**, and adding one would duplicate an edge
    `trajectories.incident_id` already carries and let the two copies disagree. The link was in
    the data and not in the protocol; T5.1's view is the first reader that needed to traverse it.
    """
    trajectory = Trajectory(incident_id="inc-1", model="m", effort="medium", started_at=NOW)

    body = client([incident("inc-1")], [trajectory]).get("/api/v1/incidents/inc-1").json()

    assert body["trajectory_id"] == trajectory.id


def test_the_newest_trajectory_wins_when_an_incident_was_investigated_twice() -> None:
    """A re-run after a transient failure leaves two, and a view showing an arbitrary one would
    show a different answer on each refresh. The newest is the one a responder means."""
    older = Trajectory(incident_id="inc-1", model="m", effort="medium", started_at=NOW)
    newer = Trajectory(
        incident_id="inc-1", model="m", effort="medium", started_at=NOW + timedelta(minutes=5)
    )

    body = client([incident("inc-1")], [older, newer]).get("/api/v1/incidents/inc-1").json()

    assert body["trajectory_id"] == newer.id


def test_a_trajectory_for_another_incident_is_not_shown() -> None:
    other = Trajectory(incident_id="inc-2", model="m", effort="medium", started_at=NOW)

    body = client([incident("inc-1")], [other]).get("/api/v1/incidents/inc-1").json()

    assert body["trajectory_id"] is None


# --- the list is capped ------------------------------------------------------------------------


def test_the_list_is_capped_and_says_when_it_truncated() -> None:
    """An uncapped read of every incident ever is a query whose cost grows with the record it is
    meant to make legible — and a truncated list that does not say so is a list that lies."""
    many = [incident(f"i{n}", minutes=n) for n in range(LIST_LIMIT + 5)]

    body = client(many).get("/api/v1/incidents").json()

    assert len(body["incidents"]) == LIST_LIMIT
    assert body["truncated"] is True


def test_a_short_list_is_not_marked_truncated() -> None:
    assert client([incident("i1")]).get("/api/v1/incidents").json()["truncated"] is False


# --- read-only, structurally --------------------------------------------------------------------


def test_the_router_exposes_no_write_method() -> None:
    """**T5.1 is a view.** A read surface that could mutate would be an action plane nobody
    designed, and THREAT-MODEL thesis 2 is about exactly that boundary. Asserted over the routes
    rather than trusted: the router never imports a writer and offers no verb but GET."""
    routes = build(InMemoryIncidentStore(), InMemoryTrajectoryStore()).routes

    methods = {method for route in routes for method in getattr(route, "methods", set())}

    assert methods <= {"GET", "HEAD"}, f"a read surface offered {methods - {'GET', 'HEAD'}}"
