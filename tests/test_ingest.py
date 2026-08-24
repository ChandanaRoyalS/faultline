"""T2.1 against the deliveries Alertmanager actually made. No Redis, no network.

Every fixture here is a real captured payload from `docs/evidence/t2.1-webhook/`: eight
webhook deliveries taken live against a `cart-redis-misconfig` injection. Tests written
against a hand-written payload prove the receiver handles what we imagined Alertmanager
sends; these prove it handles what it sent.

The two seams - `EpisodeLog` and `EventStream` - are substituted, so the dedupe *rule* is
exercised while its durability is not. That is the deliberate split: the rule is logic and
belongs here, the durability is Redis's and is asserted in ADR-0015 rather than mocked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from faultline.ingest.dedupe import InMemoryEpisodeLog
from faultline.ingest.models import GO_ZERO_TIME, AlertStatus, WebhookPayload
from faultline.ingest.receiver import Receiver
from faultline.ingest.stream import RecordingEventStream

CAPTURE = Path(__file__).resolve().parents[1] / "docs" / "evidence" / "t2.1-webhook"
PAYLOADS = CAPTURE / "payloads.jsonl"

RECEIVED = datetime(2026, 8, 24, 10, 41, tzinfo=UTC)
"""A fixed receipt stamp. The capture's own `received_at` is per delivery; the receiver's
is per request, and pinning it keeps the events comparable."""


def deliveries() -> list[dict[str, Any]]:
    """The eight captured bodies, in the order they arrived."""
    lines = [json.loads(line) for line in PAYLOADS.read_text().splitlines() if line.strip()]
    return [entry["body"] for entry in lines]


def payloads() -> list[WebhookPayload]:
    return [WebhookPayload.model_validate(body) for body in deliveries()]


@pytest.fixture
def receiver() -> tuple[Receiver, RecordingEventStream]:
    stream = RecordingEventStream()
    return Receiver(episodes=InMemoryEpisodeLog(), stream=stream), stream


def test_the_capture_is_the_one_the_evidence_describes() -> None:
    """Guard the fixture. If the capture is replaced, these tests are about something else."""
    bodies = deliveries()
    assert len(bodies) == 8, "the evidence README documents eight deliveries"
    assert {b["version"] for b in bodies} == {"4"}, "Alertmanager v4 payload shape"
    assert all(len(b["alerts"]) == 1 for b in bodies), (
        "every captured delivery carried exactly one alert - see the README on group_by"
    )


def test_all_eight_deliveries_produce_eight_events(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """No false dedupe. Four alerts x two transitions each is eight distinct transitions.

    The trap this guards: keying dedupe on `fingerprint` alone would collapse each alert's
    firing and resolved into one, and the incident would never be seen to close. Keying on
    `(fingerprint, startsAt)` without `status` does the same.
    """
    ingest, stream = receiver

    results = [ingest.receive(p, received_at=RECEIVED) for p in payloads()]

    assert sum(r.published for r in results) == 8
    assert sum(r.duplicates for r in results) == 0
    assert len(stream.events) == 8
    assert len({e.episode_key + e.status.value for e in stream.events}) == 8
    assert len({e.fingerprint for e in stream.events}) == 4, "four alerts, two states each"


def test_replaying_a_delivery_publishes_nothing(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """A repeat notification or an Alertmanager retry is not a second transition.

    `repeat_interval: 1h` was never reached during the capture (README, "No duplicates, no
    retries"), so this is the case the evidence could not produce and the rule must still
    handle - replayed here from the real payload rather than invented.
    """
    ingest, stream = receiver
    captured = payloads()
    for payload in captured:
        ingest.receive(payload, received_at=RECEIVED)

    replay = ingest.receive(captured[0], received_at=datetime(2026, 8, 24, 11, 41, tzinfo=UTC))

    assert replay.received == 1
    assert replay.published == 0
    assert replay.duplicates == 1
    assert len(stream.events) == 8, "the replay must not reach the stream at all"


def test_replaying_the_whole_capture_publishes_nothing(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """The restart case, in the shape it would actually arrive: everything, again."""
    ingest, stream = receiver
    for payload in payloads():
        ingest.receive(payload, received_at=RECEIVED)

    second = [ingest.receive(p, received_at=RECEIVED) for p in payloads()]

    assert sum(r.published for r in second) == 0
    assert sum(r.duplicates for r in second) == 8
    assert len(stream.events) == 8


def test_the_post_revert_emailservice_firing_is_a_new_episode(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """Delivery #5: an alert that fired *after* the revert, 12ms before another resolved.

    The recovery artifact is indistinguishable from an opening alert at the transport layer
    (README). Ingest must not suppress it for arriving mid-resolution, and must not decide
    it belongs to the incident that is closing - that correlation is T2.2's (ADR-0015).
    """
    ingest, stream = receiver
    for payload in payloads():
        ingest.receive(payload, received_at=RECEIVED)

    email = [e for e in stream.events if e.service == "emailservice"]
    firing = [e for e in email if e.status is AlertStatus.FIRING]

    assert len(firing) == 1, "the post-revert firing came through"
    assert firing[0].fingerprint == "c1cf16569b44acd6"
    assert firing[0].starts_at == datetime(2026, 8, 24, 10, 39, 30, 583000, tzinfo=UTC)

    # It interleaves: a frontend resolution was published after this firing, and the
    # emailservice resolution came last of all. Ingest preserves that order rather than
    # sorting the incident into tidy phases.
    order = [(e.service, e.status.value) for e in stream.events]
    assert order.index(("emailservice", "firing")) < order.index(("frontend", "resolved"))
    assert order[-1] == ("emailservice", "resolved")


def test_a_resolved_delivery_closes_the_episode_it_names(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """Same fingerprint, same episode key, an `endsAt` that is a real date.

    checkoutservice is the clearest case in the capture: it resolved (#4) before two other
    services had even started resolving.
    """
    ingest, stream = receiver
    for payload in payloads():
        ingest.receive(payload, received_at=RECEIVED)

    checkout = [e for e in stream.events if e.service == "checkoutservice"]
    firing, resolved = checkout

    assert firing.status is AlertStatus.FIRING and resolved.status is AlertStatus.RESOLVED
    assert firing.episode_key == resolved.episode_key, "one episode, two transitions"
    assert firing.ends_at is None
    assert resolved.ends_at == datetime(2026, 8, 24, 10, 39, 0, 583000, tzinfo=UTC)


def test_the_fingerprint_survives_annotation_drift(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """Measured: frontend reported 29.25% firing and 10.08% resolved under one fingerprint.

    This is why the fingerprint is usable as identity and why we compute none of our own.
    If it ever stopped holding, dedupe would silently split every alert in two.
    """
    ingest, stream = receiver
    for payload in payloads():
        ingest.receive(payload, received_at=RECEIVED)

    frontend = [e for e in stream.events if e.service == "frontend"]
    descriptions = {e.alert["annotations"]["description"] for e in frontend}

    assert len({e.fingerprint for e in frontend}) == 1
    assert len(descriptions) == 2, "the rendered text differed between the two deliveries"


def test_go_zero_time_is_absent_rather_than_a_date(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """`0001-01-01T00:00:00Z` parses as a valid date and is not one.

    Left alone it reads as an alert that ended two thousand years ago, which any
    "is it over?" comparison answers wrongly and confidently.
    """
    ingest, stream = receiver
    for payload in payloads():
        ingest.receive(payload, received_at=RECEIVED)

    firing = [e for e in stream.events if e.status is AlertStatus.FIRING]

    assert firing, "the capture opens with firing deliveries"
    assert all(e.ends_at is None for e in firing)
    assert all(e.alert["endsAt"] is None for e in firing), "normalised on the way out too"
    assert GO_ZERO_TIME.year == 1, "the sentinel this guards against"


def test_the_event_carries_the_alert_whole(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """Faithful delivery: a consumer never has to go back to the webhook for a field."""
    ingest, stream = receiver
    ingest.receive(payloads()[0], received_at=RECEIVED)

    event = stream.events[0]

    assert set(event.alert) >= {
        "status",
        "labels",
        "annotations",
        "startsAt",
        "endsAt",
        "generatorURL",
        "fingerprint",
    }, "Alertmanager's own field names, as delivered"
    assert event.alert["labels"]["service_name"] == "frontend", "the raw label is kept"
    assert event.received_at == RECEIVED
    assert event.group_key.startswith('{}:{alertname="ServiceHighErrorRate"')


def test_the_service_field_is_normalised_across_the_two_naming_schemes(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """`service` is `service_name` through `canonical_service`, so T2.2 keys on one identity.

    Every service in the capture is already a compose name, so the capture alone cannot show
    this doing anything. The container-named case is constructed from a captured delivery by
    changing one label - the world names `cartservice` `cart-service` at the container.
    """
    ingest, stream = receiver
    body = deliveries()[0]
    body["alerts"][0]["labels"]["service_name"] = "cart-service"

    ingest.receive(WebhookPayload.model_validate(body), received_at=RECEIVED)

    event = stream.events[0]
    assert event.service == "cartservice", "normalised for the orchestrator"
    assert event.alert["labels"]["service_name"] == "cart-service", "raw label untouched"


def test_an_alert_without_a_service_label_still_publishes(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """Not every rule is per-service. `service` is absent rather than invented."""
    ingest, stream = receiver
    body = deliveries()[0]
    del body["alerts"][0]["labels"]["service_name"]

    result = ingest.receive(WebhookPayload.model_validate(body), received_at=RECEIVED)

    assert result.published == 1
    assert stream.events[0].service is None


def test_a_resolved_for_an_unseen_episode_is_still_published(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """Ingest was down when the alert fired, or restarted. The close is still a transition.

    Suppressing it would be ingest deciding the episode does not matter - a correlation
    call, and not its to make. Constructed by feeding only the resolved half of a captured
    pair.
    """
    ingest, stream = receiver
    resolved_only = payloads()[3]  # delivery #4: checkoutservice resolved

    result = ingest.receive(resolved_only, received_at=RECEIVED)

    assert result.published == 1
    assert stream.events[0].status is AlertStatus.RESOLVED


def test_a_grouped_delivery_publishes_every_alert_in_it(
    receiver: tuple[Receiver, RecordingEventStream],
) -> None:
    """The unit is the alert, not the POST.

    One alert per delivery is our `group_by` and not the protocol (README). Dropping
    `service_name` from the grouping would deliver all four services in one payload, so
    this is constructed from the capture: the four firing alerts in a single body.
    """
    ingest, stream = receiver
    bodies = deliveries()
    grouped = bodies[0]
    grouped["alerts"] = [b["alerts"][0] for b in bodies if b["status"] == "firing"]

    result = ingest.receive(WebhookPayload.model_validate(grouped), received_at=RECEIVED)

    assert result.received == 4
    assert result.published == 4
    assert len({e.fingerprint for e in stream.events}) == 4


# --- the HTTP surface ---------------------------------------------------------


def test_the_route_accepts_a_real_captured_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end over ASGI, in-process: no socket, no Redis, the actual JSON Alertmanager sent.

    Everything above tests the receiver directly. This tests the one thing that cannot:
    that FastAPI's validation accepts the real body at the real path, rather than a payload
    shaped to fit the model.
    """
    from fastapi.testclient import TestClient

    from faultline.ingest import app as app_module

    stream = RecordingEventStream()
    ingest = Receiver(episodes=InMemoryEpisodeLog(), stream=stream)
    monkeypatch.setattr(app_module, "receiver", lambda: ingest)

    with TestClient(app_module.app) as client:
        first = client.post("/api/v1/alerts", json=deliveries()[0])
        repeat = client.post("/api/v1/alerts", json=deliveries()[0])

    assert first.status_code == 200
    assert first.json() == {"received": 1, "published": 1, "duplicates": 0}
    assert repeat.json() == {"received": 1, "published": 0, "duplicates": 1}
    assert len(stream.events) == 1


def test_the_route_rejects_a_body_that_is_not_an_alertmanager_delivery() -> None:
    """Validation is the trust boundary's only current occupant - the port has no auth.

    A malformed body is refused; a *well-formed* one from anywhere at all is accepted, which
    is the gap docs/THREAT-MODEL.md records and T2.6/T6.8 closes.
    """
    from fastapi.testclient import TestClient

    from faultline.ingest import app as app_module

    with TestClient(app_module.app) as client:
        response = client.post("/api/v1/alerts", json={"nope": True})

    assert response.status_code == 422
