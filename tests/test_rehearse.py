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
    monkeypatch.setattr(rehearse, "container_uptimes", lambda: [("kafka", 9999)])

    with pytest.raises(rehearse.RehearsalError, match="still firing"):
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
    monkeypatch.setattr(rehearse, "container_uptimes", lambda: [("kafka", 9999)])

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
    monkeypatch.setattr(rehearse, "container_uptimes", lambda: [("kafka", 9999)])

    with pytest.raises(rehearse.RehearsalError, match="memory limit"):
        rehearse.rehearse(
            "currency-cpu-throttle", dwell=1, alert_timeout=1, force=True, baseline_timeout=1
        )

    assert ("start", "currency-cpu-throttle") not in calls
    assert not list(tmp_path.iterdir()), "an aborted rehearsal must leave no partial bundle"


# --- a container running a reclaimed image kills pumba silently ---------------


def test_a_coherent_world_passes_the_image_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rehearse, "orphaned_image_references", list)
    monkeypatch.setattr(rehearse, "container_uptimes", lambda: [("kafka", 9999)])

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


# --- the YAML may not disagree with the fault that will actually run ----------


def test_a_scenario_matching_its_catalog_entry_passes() -> None:
    rehearse.require_scenario_matches_catalog(
        rehearse.find_scenario("recommendation-memory-squeeze")
    )  # does not raise


def test_a_scenario_whose_yaml_drifted_from_the_catalog_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Measured: a memory limit edited in the YAML while the injector kept its own value.

    `make check` compares the two, but only at check time - edit and rehearse immediately
    and nothing intervenes, because the injector never reads the scenario file.
    """
    scenario = rehearse.find_scenario("recommendation-memory-squeeze")
    drifted = scenario.model_copy(
        update={"injection": scenario.injection.model_copy(update={"params": {"memory": "64m"}})}
    )

    with pytest.raises(rehearse.RehearsalError) as caught:
        rehearse.require_scenario_matches_catalog(drifted)

    message = str(caught.value)
    assert "64m" in message and "32m" in message, "show both values"
    assert "injector.catalog is authoritative" in message, "say which side wins"
    assert "aborting before injection" in message


def test_the_scenario_gate_runs_before_anything_touches_docker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """It needs no subprocess at all, so a disagreeing scenario must cost nothing to reject."""
    touched: list[str] = []

    def fake_injector(*args: str) -> str:
        touched.append("injector")
        return "recommendation-memory-squeeze\n" if args == ("list",) else "no active injections\n"

    monkeypatch.setattr(rehearse, "injector", fake_injector)
    monkeypatch.setattr(
        rehearse, "orphaned_image_references", lambda: touched.append("images") or []
    )
    monkeypatch.setattr(rehearse, "container_memory_usage", lambda: touched.append("memory") or [])
    monkeypatch.setattr(rehearse, "firing_alerts", list)
    monkeypatch.setattr(rehearse, "ARTIFACT_ROOT", tmp_path)

    real = rehearse.find_scenario
    monkeypatch.setattr(
        rehearse,
        "find_scenario",
        lambda sid: real(sid).model_copy(
            update={
                "injection": real(sid).injection.model_copy(update={"params": {"memory": "1m"}})
            }
        ),
    )

    with pytest.raises(rehearse.RehearsalError, match="disagrees with the fault it cites"):
        rehearse.rehearse(
            "recommendation-memory-squeeze",
            dwell=1,
            alert_timeout=1,
            force=True,
            baseline_timeout=1,
        )

    assert touched == ["injector"], (
        f"only the catalog lookup should have run before the scenario gate: {touched}"
    )


# --- the archive keeps metrics too, compressed --------------------------------


def test_archiving_keeps_the_manifest_and_compressed_metrics(tmp_path: Path) -> None:
    """Manifest-only archiving lost the metric window an argument later needed."""
    import gzip
    import json

    bundle = tmp_path / "some-scenario"
    (bundle / "metrics").mkdir(parents=True)
    (bundle / "logs").mkdir()
    (bundle / "manifest.json").write_text(json.dumps({"t_inject": "2026-08-23T07:52:24+00:00"}))
    (bundle / "metrics" / "latency-p95.json").write_text('{"data": {"result": [1, 2, 3]}}')
    (bundle / "metrics" / "call-rate.json").write_text('{"data": {"result": []}}')
    (bundle / "logs" / "svc.txt").write_text("a log nobody has ever cited")

    name = rehearse.archive_recording(bundle)

    archive = bundle / rehearse.SUPERSEDED / str(name)
    assert name == "20260823T075224Z", "named for the run it preserves"
    assert json.loads((archive / "manifest.json").read_text())["t_inject"].startswith("2026-08-23")
    assert sorted(p.name for p in (archive / "metrics").iterdir()) == [
        "call-rate.json.gz",
        "latency-p95.json.gz",
    ]
    restored = gzip.decompress((archive / "metrics" / "latency-p95.json.gz").read_bytes())
    assert json.loads(restored)["data"]["result"] == [1, 2, 3], "must round-trip exactly"
    assert not (archive / "logs").exists(), "logs are deliberately not archived"


def test_clearing_a_bundle_preserves_the_archive(tmp_path: Path) -> None:
    """A re-record must not wipe the archive it just contributed to."""
    bundle = tmp_path / "some-scenario"
    (bundle / rehearse.SUPERSEDED / "20260823T075224Z").mkdir(parents=True)
    (bundle / "manifest.json").write_text("{}")

    rehearse.clear_bundle(bundle)

    assert (bundle / rehearse.SUPERSEDED / "20260823T075224Z").is_dir()
    assert not (bundle / "manifest.json").exists()


# --- the fifth capture --------------------------------------------------------


def test_the_runtime_capture_names_the_compose_service_not_the_container() -> None:
    """`exported_job` holds the compose service name, and half the targets are containers.

    `ad-memory-squeeze` targets the container `ad-service`; the series are published under
    `adservice`. Passing the target through unchanged returns a well-formed query that
    matches nothing, and an empty capture is the one failure mode this evidence cannot
    survive - its whole meaning is that absence is informative.
    """
    query = rehearse.runtime_query(rehearse.canonical_service("ad-service"))

    assert 'exported_job="adservice"' in query
    assert "ad-service" not in query


def test_the_runtime_capture_covers_every_runtime_the_demo_uses() -> None:
    """JVM, CPython, Go and .NET services all have to land in the same file.

    Prometheus anchors regexes, so `runtime_.*` does not also match `process_runtime_*`.
    Dropping one pattern silently narrows the capture to whichever runtimes happen to be
    targeted next.
    """
    query = rehearse.runtime_query("cartservice")

    for family in ("process_runtime_", "runtime_", "system_memory_"):
        assert family in query, f"{family}* would not be captured"


def test_the_recorder_says_so_when_the_narrative_predates_the_capability_set(
    tmp_path: Path,
) -> None:
    """A capture-set change must not land with narratives silently stale (T7.8).

    It warns rather than refuses: refusing would block a recording over prose, and the standing
    rule is that a re-record never rewrites a narrative - a person does, afterwards. `make check`
    is what stops it landing; this is what tells whoever is standing at the recorder that they
    now owe a review.
    """
    from evalharness.capability import capability_version
    from evalharness.rehearse import warn_if_narrative_is_stale

    bundle = tmp_path / "a-bundle"
    bundle.mkdir()

    (bundle / "incident.md").write_text("---\ncapability: cap:0000dead\n---\n\n# old\n")
    assert warn_if_narrative_is_stale(bundle) is True, "an older stamp is a debt"

    (bundle / "incident.md").write_text("---\nrecorded_from: x\n---\n\n# unstamped\n")
    assert warn_if_narrative_is_stale(bundle) is True, "no stamp is also a debt"

    (bundle / "incident.md").write_text(f"---\ncapability: {capability_version()}\n---\n\n# ok\n")
    assert warn_if_narrative_is_stale(bundle) is False, "reviewed at the current set is quiet"

    (bundle / "incident.md").unlink()
    assert warn_if_narrative_is_stale(bundle) is False, "no narrative is not a stale narrative"
