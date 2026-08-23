"""The recorder's preconditions, over fakes. No world, no daemon, no network.

Only the parts that can invalidate a bundle are tested here. The bundle's *format* is
tests/test_artifact_bundle.py's job; this file is about the recorder refusing to produce
one that would look fine and be wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evalharness import rehearse


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Poll instantly. These tests exercise the loop, not the clock."""
    monkeypatch.setattr(rehearse, "POLL_SECONDS", 0)


def test_a_clean_baseline_proceeds_immediately() -> None:
    moment = rehearse.wait_for_clean_baseline(300, poll=list)

    assert moment is not None, "a quiet world is the normal case and must not block"


def test_a_dirty_baseline_that_clears_waits_and_then_proceeds() -> None:
    polls = iter([["ServiceHighErrorRate/frontend"], ["ServiceHighErrorRate/frontend"], []])

    moment = rehearse.wait_for_clean_baseline(300, poll=lambda: next(polls))

    assert moment is not None
    assert next(polls, "exhausted") == "exhausted", "should stop polling once clear"


def test_a_dirty_baseline_that_never_clears_names_what_is_blocking() -> None:
    stuck = ["ServiceHighErrorRate/checkoutservice", "ServiceNoTraffic/cartservice"]

    with pytest.raises(rehearse.RehearsalError) as caught:
        rehearse.wait_for_clean_baseline(1, poll=lambda: stuck)

    message = str(caught.value)
    for alert in stuck:
        assert alert in message, "the operator has to know which alert to wait on"
    assert "aborting before injection" in message


def test_a_dirty_baseline_aborts_before_anything_is_injected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The whole point: no fault reaches the world, so nothing needs reverting afterwards."""
    calls: list[tuple[str, ...]] = []

    def fake_injector(*args: str) -> str:
        calls.append(args)
        return "currency-cpu-throttle\n" if args == ("list",) else ""

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    monkeypatch.setattr(rehearse, "firing_alerts", lambda: ["ServiceHighErrorRate/frontend"])
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)

    with pytest.raises(rehearse.RehearsalError, match="aborting before injection"):
        rehearse.rehearse(
            "currency-cpu-throttle", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert ("start", "currency-cpu-throttle") not in calls, (
        "a fault was injected despite a dirty baseline - the world is now broken and the "
        "recorder does not know it"
    )
    assert calls == [("list",)], f"expected only the catalog lookup, got {calls}"
    assert not list(tmp_path.iterdir()), "an aborted rehearsal must leave no partial bundle"


def test_alert_evolution_marks_what_paged_and_what_came_later() -> None:
    """The narrative has to show growth; a flat list understates the blast radius."""
    facts = {
        "alerts_at_fire": ["ServiceHighErrorRate/frontend"],
        "alerts_over_window": [
            {
                "alert": "ServiceHighErrorRate",
                "service": "frontend",
                "first_seen": "2026-08-23T06:06:37+00:00",
                "last_seen": "2026-08-23T06:15:21+00:00",
            },
            {
                "alert": "ServiceNoTraffic",
                "service": "cartservice",
                "first_seen": "2026-08-23T06:10:06+00:00",
                "last_seen": "2026-08-23T06:11:51+00:00",
            },
        ],
    }

    rendered = rehearse.alert_evolution(facts)

    frontend, cart = [line for line in rendered.splitlines() if "Service" in line][-2:]
    assert "**on the page**" in frontend, "the alert that paged must be marked as such"
    assert "later" in cart and "**on the page**" not in cart
    assert "1 more than the responder saw" in rendered


def test_alert_evolution_survives_an_incident_that_never_alerted() -> None:
    rendered = rehearse.alert_evolution({"alerts_at_fire": [], "alerts_over_window": []})

    assert "No alerts recorded" in rendered, "a fault that fired nothing still needs a bundle"


# --- alert_intervals: the two ways a derived blast radius goes wrong ----------


def alert_series(alertname: str, service: str, seconds: list[int]) -> dict[str, object]:
    """An ALERTS query_range payload with samples at the given epoch seconds."""
    return {
        "data": {
            "result": [
                {
                    "metric": {"alertname": alertname, "service_name": service},
                    "values": [[float(s), "1"] for s in seconds],
                }
            ]
        }
    }


def test_alerts_before_the_injection_are_not_this_incidents_blast_radius() -> None:
    """The window opens early to show the healthy baseline; a previous run may still clear."""
    from datetime import UTC, datetime

    from evalharness.prom import alert_intervals

    inject = datetime.fromtimestamp(1_000_000, tz=UTC)
    payload = alert_series("ServiceHighErrorRate", "checkoutservice", [999_700, 999_800])

    assert alert_intervals(payload, step=15, since=inject) == [], (
        "alerts that cleared before this fault was injected belong to the previous incident"
    )
    assert alert_intervals(payload, step=15), "without `since` the same samples are reported"


def test_a_flapping_alert_is_reported_as_separate_episodes() -> None:
    """Collapsing to min/max would hide the signature a crash-loop scenario is made of."""
    from evalharness.prom import alert_intervals

    payload = alert_series(
        "ServiceHighErrorRate",
        "featureflagservice",
        [1000, 1015, 1030, 1400, 1415],  # a >60s gap splits the two bursts
    )

    episodes = alert_intervals(payload, step=15)

    assert len(episodes) == 2, f"expected two firing episodes, got {episodes}"
    assert episodes[0]["minutes_firing"] == 0.8
    assert episodes[0]["last_seen"] != episodes[1]["first_seen"]


# --- --force replaces a bundle, it does not merge into one -------------------


def test_clearing_a_bundle_removes_stale_artifacts_but_keeps_the_narrative(
    tmp_path: Path,
) -> None:
    """A file the recorder no longer produces must not survive a re-record.

    The real case: a log capture taken under the old, wrong Loki selector sat next to the
    correct one, both plausible, nothing saying which was current.
    """
    bundle = tmp_path / "cart-redis-misconfig"
    (bundle / "logs").mkdir(parents=True)
    (bundle / "metrics").mkdir()
    (bundle / "incident.md").write_text("the narrative a person wrote")
    (bundle / "manifest.json").write_text("{}")
    (bundle / "logs" / "cartservice.txt").write_text("# stale, wrong selector")
    (bundle / "metrics" / "error-ratio.json").write_text("{}")

    removed = rehearse.clear_bundle(bundle)

    assert (bundle / "incident.md").read_text() == "the narrative a person wrote", (
        "the hand-written narrative is the one file a re-record must never destroy"
    )
    assert not (bundle / "logs").exists(), "the stale log capture must be gone"
    assert not (bundle / "manifest.json").exists()
    assert sorted(removed) == ["logs", "manifest.json", "metrics"]


def test_clearing_a_bundle_that_has_no_narrative_yet_is_fine(tmp_path: Path) -> None:
    bundle = tmp_path / "never-written-up"
    bundle.mkdir()
    (bundle / "manifest.json").write_text("{}")

    assert rehearse.clear_bundle(bundle) == ["manifest.json"]
    assert bundle.exists() and not list(bundle.iterdir())
