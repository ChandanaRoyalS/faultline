"""B0, the no-LLM baseline (T4.7) — and the two things it measures about the benchmark."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evalharness import baselines

ONSET = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def change(service: str, resource: str, minutes_before: float = 5) -> baselines.Change:
    return baselines.Change(
        service=service, at=ONSET - timedelta(minutes=minutes_before), resource=resource
    )


# --- the primary signal: the most recent change in the window ------------------------------


def test_the_most_recent_change_names_the_culprit_whatever_service_it_is_on() -> None:
    """**The v1 defect, pinned.**

    v1 chose a suspect from alerts first and then looked for changes *on that service*. The plan
    says *"most-recent deploy in window"*, not *on the suspect*. This is the case that broke it:
    `frontend` alerts first because it is the **propagator** (ADR-0020 §6), and the change that
    caused the incident is on `adservice`. v2 follows the change.
    """
    signals = baselines.Signals(
        alerting=["frontend", "adservice"],
        changes=[change("adservice", "resource_limits", 3)],
    )

    prediction = baselines.predict(signals, ONSET)

    assert prediction.service == "adservice"
    assert prediction.fault_class == "resource_exhaustion"
    assert prediction.fix_class == "config_revert"


def test_a_change_on_a_service_that_never_alerted_is_not_this_incident() -> None:
    """Alert-label attribution still scopes the search - it just no longer picks the suspect.
    A deploy elsewhere in the cluster during the window did not cause an incident that never
    reached it."""
    signals = baselines.Signals(
        alerting=["cartservice"],
        changes=[change("recommendationservice", "image", 1)],
    )

    assert baselines.latest_change(signals, ONSET) is None


def test_a_change_after_onset_cannot_explain_it() -> None:
    """A change made after the incident began did not cause it. The same causal tier T3.4's
    ranking applies, applied by a heuristic."""
    signals = baselines.Signals(
        alerting=["cartservice"], changes=[change("cartservice", "image", minutes_before=-5)]
    )

    assert baselines.latest_change(signals, ONSET) is None


def test_the_most_recent_of_two_pre_onset_changes_wins() -> None:
    signals = baselines.Signals(
        alerting=["cartservice", "frontend"],
        changes=[change("cartservice", "image", 60), change("frontend", "environment", 2)],
    )

    assert baselines.predict(signals, ONSET).fault_class == "bad_config"


def test_simultaneous_changes_break_on_the_larger_error_delta() -> None:
    """The only work signal 3 does when a change is present, and it has to do something: two
    changes landing in the same second is not hypothetical in a demo world deployed by one
    script."""
    signals = baselines.Signals(
        alerting=["cartservice", "frontend"],
        changes=[change("cartservice", "image", 5), change("frontend", "environment", 5)],
        error_deltas={"cartservice": 0.4, "frontend": 0.02},
    )

    assert baselines.predict(signals, ONSET).service == "cartservice"


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
        assert baselines.predict(signals, ONSET).fault_class == expected, resource


# --- the fallback, for when no change points anywhere --------------------------------------


def test_the_largest_error_delta_picks_the_suspect_when_nothing_changed() -> None:
    signals = baselines.Signals(
        alerting=["frontend", "cartservice"],
        error_deltas={"frontend": 0.03, "cartservice": 0.41},
    )

    service, why = baselines.fallback_culprit(signals)

    assert service == "cartservice"
    assert "largest error-rate delta" in why


def test_without_an_error_series_it_falls_back_to_the_earliest_alert() -> None:
    """**Common, and doing more work than it looks like it should.** `cartservice` publishes no
    `calls_total` series at all, so several real incidents reach this branch - which is exactly
    the kind of thing a baseline exists to expose."""
    signals = baselines.Signals(alerting=["frontend", "checkoutservice"], error_deltas={})

    service, why = baselines.fallback_culprit(signals)

    assert service == "frontend"
    assert "earliest alerting service" in why


def test_a_delta_for_a_service_that_did_not_alert_is_ignored() -> None:
    """Alert-label attribution scopes the fallback too: a service that never alerted is not a
    suspect, however far its error ratio moved."""
    signals = baselines.Signals(
        alerting=["frontend"], error_deltas={"frontend": 0.02, "adservice": 0.99}
    )

    assert baselines.fallback_culprit(signals)[0] == "frontend"


def test_no_change_before_onset_predicts_latency_and_that_is_a_fact_about_the_injector() -> None:
    """**The residual rule, and the reason B0 is more than a coin flip.**

    `dependency_latency` is the one class injected without touching configuration - pumba adds
    delay to an interface and leaves no change record. So "nothing changed" is a positive
    prediction here. A reader should notice this says something about the injector rather than
    about incidents.
    """
    signals = baselines.Signals(alerting=["cartservice"], changes=[])

    prediction = baselines.predict(signals, ONSET)

    assert prediction.fault_class == "dependency_latency"
    assert any("no change" in line for line in prediction.why)


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


# --- B0 as a run under the standard harness ---------------------------------------------


def test_b0_carries_its_own_runtime_and_never_the_agents_stamp() -> None:
    """**The separation that makes B0 a control.** `runtime_version` is a digest over role
    prompts and contract schemas; B0 uses none of them. Stamping it with the agent's digest would
    put a baseline run in the same comparability generation as the pipeline it controls for -
    which is exactly the comparison it exists to make possible."""
    from faultline.agents.stamp import runtime_version

    assert runtime_version() != baselines.BASELINE_RUNTIME
    assert "baseline" in baselines.BASELINE_RUNTIME


def test_the_version_is_in_the_runtime_so_v1_and_v2_can_never_be_pooled() -> None:
    """**A baseline that changes silently is not a baseline.**

    v1 answered `dependency_latency` on `ad-memory-squeeze` against a truth of
    `resource_exhaustion`, and that run is kept. Keeping it is only safe if nothing downstream can
    average it with a v2 run, and the thing that guarantees that is the version being *in the
    runtime string* the eval DB groups on - not a convention someone has to remember.
    """
    assert baselines.BASELINE_RUNTIME.endswith(f".{baselines.BASELINE_VERSION}")
    assert baselines.BASELINE_RUNTIME != "faultline/0.0.1+baseline:B0", "the v1 string"


# --- the two reader defects v1's single run could not have shown ---------------------------


def test_change_rows_are_dicts_and_carry_no_service_of_their_own() -> None:
    """**The defect that could only fire on the path v2 makes primary.**

    `ChangeRecord.as_row` emits `at`/`actor`/`resource`/`action`/`summary` and no `service` -
    the service belongs to the query, not the row. v1 read these as objects. It never raised
    because its one run asked `frontend`, which had no changes.
    """
    from faultline.tools.results import ChangeResult, Window

    result = ChangeResult(
        service="adservice",
        window=Window(start=ONSET - timedelta(minutes=30), end=ONSET),
        records=[
            {
                "at": (ONSET - timedelta(minutes=4)).isoformat(),
                "actor": "deployer",
                "resource": "resource_limits",
                "action": "update",
                "summary": "memory limit 300Mi -> 40Mi",
                "before": "300Mi",
                "after": "40Mi",
            }
        ],
    )

    changes = baselines.changes_in(result, "adservice")

    assert len(changes) == 1
    assert changes[0].service == "adservice", "taken from the result, since the row has none"
    assert changes[0].resource == "resource_limits"
    assert changes[0].at < ONSET


def test_a_naive_timestamp_is_read_as_utc_rather_than_guessed() -> None:
    """A guess at local time would shift a change across onset and silently change the verdict."""
    from faultline.tools.results import ChangeResult, Window

    result = ChangeResult(
        service="adservice",
        window=Window(start=ONSET - timedelta(minutes=30), end=ONSET),
        records=[{"at": "2026-09-03T11:56:00", "resource": "image"}],
    )

    assert baselines.changes_in(result, "adservice")[0].at == ONSET - timedelta(minutes=4)


def test_the_error_delta_comes_from_series_not_from_a_points_attribute() -> None:
    """**Why signal 3 never ran in v1.** `MetricResult` has `series`, each with `points`; v1 read
    `result.points`, which does not exist, so `error_deltas` was always empty and B0 always took
    the no-error-series fallback."""
    from faultline.tools.results import MetricResult, MetricSeries, Window

    result = MetricResult(
        query="error ratio",
        window=Window(start=ONSET - timedelta(minutes=30), end=ONSET),
        series=[
            MetricSeries(labels={"service_name": "cartservice"}, points=[(0.0, 0.01), (1.0, 0.42)])
        ],
    )

    delta = baselines.error_delta(result)

    assert delta is not None
    assert abs(delta - 0.41) < 1e-9


def test_a_series_with_no_points_yields_no_delta_rather_than_a_zero() -> None:
    """Zero would be a measurement. Absence is not one, and ADR-0019's distinction holds for a
    baseline as much as for the agent."""
    from faultline.tools.results import MetricResult, MetricSeries, Window

    window = Window(start=ONSET - timedelta(minutes=30), end=ONSET)

    assert baselines.error_delta(MetricResult(query="q", window=window, series=[])) is None
    assert (
        baselines.error_delta(
            MetricResult(query="q", window=window, series=[MetricSeries(labels={}, points=[])])
        )
        is None
    )


def test_the_artifact_has_every_field_the_scorer_reads() -> None:
    """B0 is scored by `evalharness.run.score`, not by a parallel scorer - a baseline scored
    differently is not a baseline. This asserts the artifact satisfies that reader."""
    prediction = baselines.predict(
        baselines.Signals(alerting=["cartservice"], changes=[change("cartservice", "image")]), ONSET
    )
    written = baselines.artifact(
        incident_id="i-1",
        trajectory_id="t-1",
        blast_radius=["cartservice", "frontend"],
        unmeasured_edges=2,
        exclude_origin="scenario:cart-bad-image-tag",
        prediction=prediction,
    )

    for field_name in (
        "trajectory_id",
        "blast_radius",
        "unmeasured_edges",
        "verdict",
        "flags",
        "failed_dispatches",
        "narrative_error",
    ):
        assert field_name in written, f"the scorer reads {field_name}"
    assert written["verdict"]["fault_class"] == "bad_deploy"
    assert written["verdict"]["remediation_class"] == "rollback"


def test_the_artifact_leaves_the_agents_fields_empty_rather_than_absent() -> None:
    """A reader diffing a B0 artifact against an agent's should see which parts of the pipeline
    B0 does not have, rather than which keys someone forgot."""
    written = baselines.artifact(
        "i", "t", [], 0, None, baselines.predict(baselines.Signals(), ONSET)
    )

    assert written["retrieved"] == []
    assert written["proposal"] is None
    assert written["disclosure"] == {}


def test_every_read_comes_back_as_a_tool_call_with_its_envelope() -> None:
    """**The panel defect, pinned.** v1 wrote `TOOL_CALL` steps carrying no `ToolCallRecord`, so
    nothing reached `trajectory_tool_calls` and the metric panel reported *0 tool calls* beside
    *2 steps* - two true statements that together read as a defect. B0 does make tool calls, and
    they belong in the table the panel reads, with the envelope the agent would have seen.
    """
    from faultline.tools.envelope import CLOSE_PREFIX
    from faultline.tools.results import ChangeResult, MetricResult, MetricSeries, Window

    window = Window(start=ONSET - timedelta(minutes=30), end=ONSET)

    class Layer:
        def change_history(self, service: str, start: datetime, end: datetime) -> ChangeResult:
            return ChangeResult(
                service=service,
                window=window,
                records=[
                    {
                        "at": (ONSET - timedelta(minutes=4)).isoformat(),
                        "actor": "deployer",
                        "resource": "image",
                        "action": "update",
                        "summary": "image tag v1 -> v2",
                        "before": "v1",
                        "after": "v2",
                    }
                ],
            )

        def promql_query(self, query: str, start: datetime, end: datetime) -> MetricResult:
            return MetricResult(
                query=query,
                window=window,
                series=[MetricSeries(labels={}, points=[(0.0, 0.01), (1.0, 0.30)])],
            )

    signals, calls = baselines.signals_from_tools(Layer(), ["cartservice"], ONSET, window)

    assert [call.tool for call in calls] == ["change_history", "promql_query"]
    for call in calls:
        assert call.result_id, "the id the envelope's closing delimiter carries"
        assert call.envelope.startswith("<tool_result "), "rendered by the one renderer"
        assert call.envelope.endswith(f"{CLOSE_PREFIX}:{call.result_id}>")
    assert signals.error_deltas, "signal 3 actually read something"
    assert baselines.predict(signals, ONSET).fault_class == "bad_deploy"


def test_a_baseline_run_cannot_share_a_config_fingerprint_with_an_agent_run() -> None:
    """T4.7 wants baselines as *"ordinary configs in the eval DB"* - which only means anything if
    they are **distinct** configs. `baseline` is a fingerprint input, so a B0 run and an agent
    run on the same world and models still hash differently."""
    from evalharness import evaldb

    common = {
        "scenario_id": "cart-redis-misconfig",
        "models": {"planner": "claude-opus-5"},
        "budget": {"max_tokens": 120000},
    }
    agent = evaldb.fingerprint(common)
    baseline = evaldb.fingerprint({**common, "baseline": "b0"})

    assert agent.fingerprint != baseline.fingerprint
    assert "baseline" in agent.missing, "an agent run simply does not carry the input"
