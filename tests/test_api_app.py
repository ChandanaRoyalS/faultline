"""The test that was missing, and the reason the gap survived twelve passing ones.

`tests/test_incident_routes` builds its own `FastAPI()`, mounts `incidents.build(...)` on it, and
asserts the routes behave. Every assertion in it is true and none of them is about the application
this project actually serves - so `build()` and `page_router()` could be, and were, called from
nowhere in `src/` while the suite stayed green.

**Everything here asserts against the app `faultline-ingest` starts.** Not a stand-in for it.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

from faultline.api import auth
from faultline.api.app import assemble
from faultline.ingest import app as ingest_module

USER = "faultline"
PASSWORD = "not-the-real-one"


def serves(client: TestClient, path: str, headers: dict[str, str] | None = None) -> bool:
    """Whether the app routes this path at all.

    **A probe, not an enumeration of `app.routes`.** FastAPI 0.141 resolves `include_router`
    lazily: an included router sits in `app.routes` as an opaque marker and the routes never
    flatten, so a test that enumerated them would report every composed route missing and, worse,
    would report an empty app as matching an empty expectation. 404 means not routed; anything
    else - 200, 401, 422 - means something is there.
    """
    return client.get(path, headers=headers or {}).status_code != 404


# --- the receiver half is unchanged -------------------------------------------------------------


def test_the_receiver_alone_is_what_you_get_without_a_dsn() -> None:
    """T2.1's contract, and the proof that the read half is opt-in rather than default-on.

    A deployment that only receives alerts must not acquire a Postgres dependency because T5.1
    needed one.
    """
    client = TestClient(assemble())

    assert serves(client, "/healthz")
    assert not serves(client, "/api/v1/incidents")
    assert not serves(client, "/ui/incidents/inc-1")


def test_the_module_level_app_still_serves_the_write_path() -> None:
    """`from faultline.ingest.app import app` is imported by four T2.1 tests, and composing a new
    app out of its router must not have taken the routes off it."""
    client = TestClient(ingest_module.app)

    assert client.get("/healthz").json() == {"status": "ok"}
    assert serves(client, "/api/v1/alerts")


def test_healthz_answers_on_the_assembled_app() -> None:
    assert TestClient(assemble()).get("/healthz").json() == {"status": "ok"}


# --- the read half is mounted, which is the whole point of the module ----------------------------


class FakeIncidents:
    def recent(self, _limit: int) -> list[object]:
        return []

    def get(self, _incident_id: str) -> None:
        return None


class FakeTrajectories:
    def latest_for_incident(self, _incident_id: str) -> None:
        return None


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The assembled app with the read half mounted, and **no database**.

    `read_surface` is the seam: it is the only part that knows about psycopg, so substituting it
    tests the assembly and the credential without asking CI for Postgres. What it must not do is
    substitute `incidents.build` - that would test a mount of something other than the real router.
    """
    from faultline.api import app as app_module
    from faultline.api import incidents

    monkeypatch.setenv(auth.USER_VAR, USER)
    monkeypatch.setenv(auth.PASSWORD_VAR, PASSWORD)

    def without_postgres(app: object, _dsn: str) -> object:
        credential = auth.guard()
        app.include_router(  # type: ignore[attr-defined]
            incidents.build(FakeIncidents(), FakeTrajectories()), dependencies=[credential]
        )
        app.include_router(incidents.page_router(), dependencies=[credential])  # type: ignore[attr-defined]
        return app

    monkeypatch.setattr(app_module, "read_surface", without_postgres)
    return TestClient(app_module.assemble(postgres_dsn="postgresql://unused"))


def header(user: str = USER, password: str = PASSWORD) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_the_screen_the_slack_link_points_at_is_served(served: TestClient) -> None:
    """`notify.messages.UI_PATH` is `/ui/incidents/`. Until this mount existed the notification
    T5.2 sends linked to a 404 on every deployment, including a correct one."""
    response = served.get("/ui/incidents/inc-1", headers=header())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_the_api_the_page_polls_is_served(served: TestClient) -> None:
    """`static/incident.html` fetches `/api/v1/incidents/{id}` every 3000ms. A page served by an
    app that does not serve that route is a spinner."""
    assert served.get("/api/v1/incidents", headers=header()).status_code == 200
    assert served.get("/api/v1/incidents/nope", headers=header()).status_code == 404


def test_both_halves_share_one_port(served: TestClient) -> None:
    """The receiver and the read surface are one process. If they were not, the deploy would need
    two containers and `FAULTLINE_NOTIFY_PUBLIC_BASE_URL` could not name both."""
    assert serves(served, "/healthz")
    assert serves(served, "/api/v1/alerts")
    assert serves(served, "/api/v1/incidents", header())
    assert serves(served, "/ui/incidents/inc-1", header())


# --- the credential ------------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/incidents", "/ui/incidents/inc-1"])
def test_the_read_surface_refuses_an_anonymous_reader(served: TestClient, path: str) -> None:
    """Incident data carries the monitored world's telemetry - every log line the agent quoted
    and every query it ran. A wider exposure than the write path's, and why this is not optional."""
    response = served.get(path)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


def test_a_wrong_password_is_refused(served: TestClient) -> None:
    assert served.get("/api/v1/incidents", headers=header(password="wrong")).status_code == 401


def test_the_write_path_stays_open(served: TestClient) -> None:
    """**Deliberate.** Alertmanager sends no credential of any kind - measured over the eight
    deliveries in docs/evidence/t2.1-webhook/. Basic auth here would not authenticate anyone, it
    would stop the alerts arriving. That defence is T2.6/T6.8's."""
    response = served.post("/api/v1/alerts", json={"alerts": []})

    assert response.status_code != 401


def test_assembling_the_read_half_without_a_password_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At startup, not per request. A process that starts and *then* 401s everything has told the
    operator it is running, which is the one thing they should not conclude."""
    monkeypatch.delenv(auth.PASSWORD_VAR, raising=False)

    with pytest.raises(auth.Unconfigured):
        assemble(postgres_dsn="postgresql://unused")


def test_the_refusal_does_not_echo_the_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(auth.PASSWORD_VAR, PASSWORD)
    monkeypatch.setenv(auth.USER_VAR, USER)

    guarded = auth.credentials()

    assert guarded == (USER, PASSWORD)
    assert PASSWORD not in auth.NO_PASSWORD
