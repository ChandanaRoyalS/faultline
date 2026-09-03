"""B0, the no-LLM baseline (T4.7) — and the two things it measures about the benchmark."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evalharness import baselines

ONSET = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def change(service: str, resource: str, minutes_before: float = 5) -> baselines.Change:
    return baselines.Change(
        service=service, at=ONSET - timedelta(minutes=minutes_before), resource=resource
    )


# --- the three signals -------------------------------------------------------------------


def test_the_largest_error_delta_picks_the_culprit() -> None:
    signals = baselines.Signals(
        alerting=["frontend", "cartservice"],
        error_deltas={"frontend": 0.03, "cartservice": 0.41},
    )

    service, why = baselines.culprit(signals)

    assert service == "cartservice"
    assert "largest error-rate delta" in why


def test_without_an_error_series_it_falls_back_to_the_earliest_alert() -> None:
    """**Common, and doing more work than it looks like it should.** `cartservice` publishes no
    `calls_total` series at all, so several real incidents reach this branch - which is exactly
    the kind of thing a baseline exists to expose."""
    signals = baselines.Signals(alerting=["frontend", "checkoutservice"], error_deltas={})

    service, why = baselines.culprit(signals)

    assert service == "frontend"
    assert "earliest alerting service" in why


def test_a_delta_for_a_service_that_did_not_alert_is_ignored() -> None:
    """Alert-label attribution comes first: a service that never alerted is not a suspect,
    however far its error ratio moved."""
    signals = baselines.Signals(
        alerting=["frontend"], error_deltas={"frontend": 0.02, "adservice": 0.99}
    )

    assert baselines.culprit(signals)[0] == "frontend"


# --- the class table ----------------------------------------------------------------------


def test_each_changed_resource_maps_to_its_fault_class() -> None:
    for resource, expected in (
        ("image", "bad_deploy"),
        ("resource_limits", "resource_exhaustion"),
        ("environment", "bad_config"),
        ("config", "bad_config"),
    ):
        signals = baselines.Signals(
            alerting=["cartservice"], changes=[change("cartservice", resource)]
        )
        assert baselines.classify(signals, "cartservice", ONSET)[0] == expected, resource


def test_no_change_before_onset_predicts_latency_and_that_is_a_fact_about_the_injector() -> None:
    """**The residual rule, and the reason B0 is more than a coin flip.**

    `dependency_latency` is the one class injected without touching configuration - pumba adds
    delay to an interface and leaves no change record. So "nothing changed" is a positive
    prediction here. A reader should notice this says something about the injector rather than
    about incidents.
    """
    signals = baselines.Signals(alerting=["cartservice"], changes=[])

    predicted, why = baselines.classify(signals, "cartservice", ONSET)

    assert predicted == "dependency_latency"
    assert "no change" in why


def test_a_change_after_onset_cannot_explain_it() -> None:
    """A change made after the incident began did not cause it. The same causal tier T3.4's
    ranking applies, applied by a heuristic."""
    signals = baselines.Signals(
        alerting=["cartservice"], changes=[change("cartservice", "image", minutes_before=-5)]
    )

    assert baselines.classify(signals, "cartservice", ONSET)[0] == "dependency_latency"


def test_the_most_recent_pre_onset_change_wins() -> None:
    signals = baselines.Signals(
        alerting=["cartservice"],
        changes=[change("cartservice", "image", 60), change("cartservice", "environment", 2)],
    )

    assert baselines.classify(signals, "cartservice", ONSET)[0] == "bad_config"


# --- what B0 measures about the benchmark ---------------------------------------------------


def test_remediation_is_a_table_lookup_because_the_catalog_makes_it_one() -> None:
    """**The finding B0 exists to surface.** Across all eighteen scenarios the fault class
    determines the remediation class exactly, so the two scored axes are not two measurements.
    A headline reporting both as if they were is double-counting one result - and B0 demonstrates
    it with a `dict`.
    """
    from pathlib import Path

    import yaml

    mapping: dict[str, set[str]] = {}
    for path in Path("evals/scenarios").glob("*.yaml"):
        loaded = yaml.safe_load(path.read_text())
        fault = loaded.get("fault_class")
        remediation = (loaded.get("ground_truth") or {}).get(
            "expected_remediation_class"
        ) or loaded.get("expected_remediation_class")
        if fault and remediation:
            mapping.setdefault(fault, set()).add(remediation)

    for fault, remediations in mapping.items():
        assert len(remediations) == 1, (
            f"{fault} maps to {remediations}, so the axes are independent"
        )
        assert baselines.CLASS_TO_REMEDIATION[fault] == next(iter(remediations)), fault


def test_a_prediction_records_which_signal_produced_each_half() -> None:
    """B0 has to be auditable for the same reason the agent does: a baseline nobody can check is
    a baseline nobody should believe."""
    signals = baselines.Signals(
        alerting=["cartservice"],
        changes=[change("cartservice", "image")],
        error_deltas={"cartservice": 0.5},
    )

    prediction = baselines.predict(signals, ONSET)

    assert prediction.fault_class == "bad_deploy"
    assert prediction.fix_class == "rollback"
    assert len(prediction.why) == 3
    assert all(line.strip() for line in prediction.why)


def test_nothing_alerting_produces_no_prediction_rather_than_a_guess() -> None:
    prediction = baselines.predict(baselines.Signals(), ONSET)

    assert prediction.service is None
    assert prediction.fault_class is None
    assert prediction.fix_class is None
