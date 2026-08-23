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
        if args == ("list",):
            return "currency-cpu-throttle\n"
        # Nothing injected: this test is about the alert gate, not the solo gate.
        return "no active injections\n"

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    monkeypatch.setattr(rehearse, "firing_alerts", lambda: ["ServiceHighErrorRate/frontend"])
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(
        rehearse, "container_memory_usage", lambda: [("kafka", 42.0, "500MiB / 1.172GiB")]
    )
    monkeypatch.setattr(rehearse, "orphaned_image_references", list)

    with pytest.raises(rehearse.RehearsalError, match="aborting before injection"):
        rehearse.rehearse(
            "currency-cpu-throttle", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert ("start", "currency-cpu-throttle") not in calls, (
        "a fault was injected despite a dirty baseline - the world is now broken and the "
        "recorder does not know it"
    )
    assert calls == [("list",), ("status",)], (
        f"expected only the catalog lookup and the solo-gate check, got {calls}"
    )
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


def test_alerts_that_started_after_the_revert_are_marked_as_recovery() -> None:
    """The recreate has its own failure modes; they are not the fault's blast radius.

    The real case: emailservice sat at 0% for the whole cart-redis-misconfig incident, then
    went to a 100% error ratio for ~75s starting 28 seconds after the revert.
    """
    from datetime import UTC, datetime

    from evalharness.prom import alert_intervals

    revert = datetime.fromtimestamp(2000, tz=UTC)
    payload = {
        "data": {
            "result": [
                {
                    "metric": {"alertname": "ServiceHighErrorRate", "service_name": "frontend"},
                    "values": [[1900.0, "1"], [1915.0, "1"]],
                },
                {
                    "metric": {"alertname": "ServiceHighErrorRate", "service_name": "emailservice"},
                    "values": [[2028.0, "1"], [2043.0, "1"]],
                },
            ]
        }
    }

    by_service = {e["service"]: e for e in alert_intervals(payload, step=15, revert=revert)}

    assert by_service["frontend"]["began_after_revert"] is False, "fired while the fault was live"
    assert by_service["emailservice"]["began_after_revert"] is True, "fired only during recovery"


def test_without_a_revert_the_recovery_flag_is_absent_rather_than_false() -> None:
    """A baseline capture has no revert; asserting False would claim what the data cannot."""
    from evalharness.prom import alert_intervals

    payload = alert_series("ServiceHighErrorRate", "frontend", [1000, 1015])

    assert "began_after_revert" not in alert_intervals(payload, step=15)[0]


# --- two recorders must not share a world ------------------------------------


def test_a_world_with_no_active_fault_passes_the_solo_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rehearse, "injector", lambda *a: "no active injections\n")

    assert rehearse.require_no_active_faults().startswith("no active injections")


def test_an_already_injected_fault_aborts_before_anything_is_injected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The measured failure: a rehearsal started 99s into another fault, before it alerted.

    The alert gate cannot catch this - detection lags injection by minutes - so the world
    looks quiet to the second recorder and its whole bundle times against the wrong
    incident.
    """
    calls: list[tuple[str, ...]] = []
    active = (
        "1 active injection(s)\n\ncart-redis-misconfig\n"
        "    class  : bad_config\n    target : cartservice\n"
    )

    def fake_injector(*args: str) -> str:
        calls.append(args)
        if args == ("list",):
            return "cart-dependency-latency\n"
        if args == ("status",):
            return active
        return ""

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    # Deliberately quiet: the other fault has not alerted yet, which is the whole point.
    monkeypatch.setattr(rehearse, "firing_alerts", list)
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(
        rehearse, "container_memory_usage", lambda: [("kafka", 42.0, "500MiB / 1.172GiB")]
    )
    monkeypatch.setattr(rehearse, "orphaned_image_references", list)

    with pytest.raises(rehearse.RehearsalError) as caught:
        rehearse.rehearse(
            "cart-dependency-latency", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert "cart-redis-misconfig" in str(caught.value), "name the fault that is blocking"
    assert ("start", "cart-dependency-latency") not in calls, (
        "a second fault was injected into a world that already had one"
    )
    assert not list(tmp_path.iterdir()), "an aborted rehearsal must leave no partial bundle"


def test_the_solo_gate_runs_before_the_alert_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Order matters: the injector's state file is true immediately, alerts lag by minutes."""
    order: list[str] = []

    def fake_injector(*args: str) -> str:
        if args == ("status",):
            order.append("solo-gate")
            return "1 active injection(s)\n\nsomething\n"
        return "cart-dependency-latency\n"

    def fake_alerts() -> list[str]:
        order.append("alert-gate")
        return []

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    monkeypatch.setattr(rehearse, "firing_alerts", fake_alerts)

    with pytest.raises(rehearse.RehearsalError):
        rehearse.rehearse(
            "cart-dependency-latency", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert order == ["solo-gate"], (
        f"the alert gate ran despite an active fault: {order}. Checking alerts first wastes "
        "up to --baseline-timeout waiting on a world that is disqualified already."
    )


# --- a rehearsal must not start in a world that is about to OOM ---------------


def test_a_world_with_memory_headroom_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        rehearse,
        "container_memory_usage",
        lambda: [("kafka", 42.0, "500MiB / 1.172GiB"), ("frontend", 11.5, "57MiB / 500MiB")],
    )

    assert rehearse.require_memory_headroom() == ["kafka: 42.0%", "frontend: 11.5%"]


def test_a_container_near_its_memory_limit_aborts_and_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Measured before this check existed: kafka at 99.3%, payment-service at 95.7%."""
    monkeypatch.setattr(
        rehearse,
        "container_memory_usage",
        lambda: [
            ("kafka", 99.3, "1.164GiB / 1.172GiB"),
            ("payment-service", 95.7, "191.3MiB / 200MiB"),
            ("frontend", 11.5, "57MiB / 500MiB"),
        ],
    )

    with pytest.raises(rehearse.RehearsalError) as caught:
        rehearse.require_memory_headroom()

    message = str(caught.value)
    assert "kafka" in message and "1.164GiB / 1.172GiB" in message, "name it and show the usage"
    assert "payment-service" in message, "every offender, not just the worst"
    assert "frontend" not in message, "a healthy container is not an offender"
    assert "aborting before injection" in message


def test_the_memory_gate_stops_a_rehearsal_before_anything_is_injected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_injector(*args: str) -> str:
        calls.append(args)
        return "currency-cpu-throttle\n" if args == ("list",) else "no active injections\n"

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    monkeypatch.setattr(rehearse, "firing_alerts", list)
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(
        rehearse, "container_memory_usage", lambda: [("kafka", 99.3, "1.164GiB / 1.172GiB")]
    )
    monkeypatch.setattr(rehearse, "orphaned_image_references", list)

    with pytest.raises(rehearse.RehearsalError, match="memory limit"):
        rehearse.rehearse(
            "currency-cpu-throttle", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert ("start", "currency-cpu-throttle") not in calls
    assert not list(tmp_path.iterdir()), "an aborted rehearsal must leave no partial bundle"


# --- a container running a reclaimed image kills pumba silently ---------------


def test_a_coherent_world_passes_the_image_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rehearse, "orphaned_image_references", list)

    rehearse.require_coherent_images()  # does not raise


def test_an_orphaned_image_reference_aborts_and_names_the_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The measured case: three rebuilds of the stub tag left the flag service orphaned."""
    monkeypatch.setattr(
        rehearse,
        "orphaned_image_references",
        lambda: [("feature-flag-service", "sha256:2764ea72cffb58aa6f89db16db4d180ee786530e")],
    )

    with pytest.raises(rehearse.RehearsalError) as caught:
        rehearse.require_coherent_images()

    message = str(caught.value)
    assert "feature-flag-service" in message, "name the container"
    assert "sha256:2764ea72" in message, "name the orphaned image id"
    assert "aborting before injection" in message

    # The hint must name the compose SERVICE, not the container it reported, and give the
    # command that actually works. An earlier version said "make world-up will do it",
    # which sent a reader into a loop: compose compares the configured image name against
    # the container's, not the resolved id, so a container on an orphaned sha under a
    # still-valid tag looks up to date and is never recreated.
    assert "featureflagservice" in message, "name the compose service, not just the container"
    assert "--force-recreate --no-deps" in message, "give the command that actually recreates"
    assert "make world-up` will NOT fix this" in message, "say why the obvious move fails"


def test_the_image_gate_stops_a_rehearsal_before_anything_is_injected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_injector(*args: str) -> str:
        calls.append(args)
        return "cart-dependency-latency\n" if args == ("list",) else "no active injections\n"

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    monkeypatch.setattr(rehearse, "firing_alerts", list)
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(
        rehearse, "orphaned_image_references", lambda: [("feature-flag-service", "sha256:dead")]
    )
    # Would pass; the image gate must fire first and never reach it.
    monkeypatch.setattr(rehearse, "container_memory_usage", lambda: [("kafka", 5.0, "ok")])

    with pytest.raises(rehearse.RehearsalError, match="no longer exists"):
        rehearse.rehearse(
            "cart-dependency-latency", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert ("start", "cart-dependency-latency") not in calls
    assert not list(tmp_path.iterdir())


def test_the_image_gate_runs_before_the_slower_memory_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`docker stats` samples for seconds; image coherence is three fast queries."""
    order: list[str] = []

    def images() -> list[tuple[str, str]]:
        order.append("image-gate")
        return [("feature-flag-service", "sha256:dead")]

    def memory() -> list[tuple[str, float, str]]:
        order.append("memory-gate")
        return []

    monkeypatch.setattr(
        rehearse,
        "injector",
        lambda *a: "cart-dependency-latency\n" if a == ("list",) else "no active injections\n",
    )
    monkeypatch.setattr(rehearse, "firing_alerts", list)
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(rehearse, "orphaned_image_references", images)
    monkeypatch.setattr(rehearse, "container_memory_usage", memory)

    with pytest.raises(rehearse.RehearsalError):
        rehearse.rehearse(
            "cart-dependency-latency", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert order == ["image-gate"], f"the slower gate ran despite a disqualifying world: {order}"
