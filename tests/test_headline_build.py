"""The headline run's build, part A (`PREREGISTRATION-headline-v2.md`, Addendum 1, items 1-5).

Each test holds one item: the v2 catalog the sweep lists, the freeze's v2 container, the v2 world's
pinned digests, a gated run scored as a miss, and the world check's two new lines. v1's behaviour
is pinned beside each, because the build must leave it exactly as it was.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[1]


# --- item 2: the sweep lists the v2 catalog ---------------------------------------------------


def test_the_v2_catalog_is_twenty_nine_dev_and_ten_holdout() -> None:
    from evalharness import sweep

    dev = sweep.runnable(world="v2")
    both = sweep.runnable(world="v2", holdout=True)

    assert len(dev) == 29
    assert len(both) == 39
    assert all(i.startswith("v2-") for i in both)
    assert not set(dev) & set(sweep.runnable())


def test_the_default_world_reads_exactly_what_it_always_read() -> None:
    from evalharness import sweep
    from evalharness.scenario import Scenario

    expected = sorted(
        s.id
        for s in (Scenario.from_yaml(p) for p in sorted(sweep.SCENARIO_ROOT.glob("*.yaml")))
        if not s.blocked
        and s.split != "holdout"
        and not any(
            (sweep.SCENARIO_ROOT / "artifacts" / split / s.id / "INVALID.md").is_file()
            for split in ("dev", "holdout")
        )
    )
    assert sweep.runnable() == expected
    assert sweep.runnable(world="v1") == expected


def test_an_unknown_world_is_refused() -> None:
    from evalharness import sweep

    with pytest.raises(ValueError, match="unknown world"):
        sweep.runnable(world="v3")


def test_the_sweep_accepts_world_v2_and_lists_it() -> None:
    from evalharness import sweep

    args = sweep.parser().parse_args(["--world", "v2", "--list"])
    assert args.world == "v2"
    assert sweep.parser().parse_args(["--list"]).world == "v1"


def test_the_same_class_exclusion_reads_a_v2_scenario_from_its_own_catalog() -> None:
    from evalharness.run import scenario_world
    from evalharness.sweep import same_class_origins

    assert scenario_world("v2-cart-freeze") == "v2"
    assert scenario_world("cart-bad-image-tag") == "v1"
    origins = same_class_origins("v2-cart-freeze", world="v2")
    assert "scenario:v2-cart-freeze" in origins
    assert all(o.startswith("scenario:v2-") for o in origins)


# --- item 3: the freeze's reference container -------------------------------------------------


def test_the_freeze_reads_each_world_from_its_own_reference_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from evalharness import freeze, provenance

    asked: list[str] = []
    monkeypatch.setattr(provenance, "image_content_digest", lambda c: asked.append(c) or "sha")
    monkeypatch.setenv("FAULTLINE_TOOLS_WORLD", "v2")
    freeze.world_state()
    monkeypatch.setenv("FAULTLINE_TOOLS_WORLD", "v1")
    freeze.world_state()

    assert asked == ["cart", "cart-service"]
    assert freeze.reference_container_for("v1") == "cart-service"


def test_the_recorder_and_the_freeze_name_the_same_containers() -> None:
    from evalharness import freeze, rehearse

    assert rehearse.REFERENCE_CONTAINER_BY_WORLD is freeze.REFERENCE_CONTAINER_BY_WORLD


# --- item 4: the v2 world's pinned digests ----------------------------------------------------


def test_every_valid_v2_bundle_is_on_the_pinned_v2_world() -> None:
    from evalharness import generations, sweep

    for scenario_id in sweep.runnable(world="v2", holdout=True):
        manifest = next(
            json.loads(p.read_text())
            for p in REPO.glob(f"evals/scenarios/artifacts/*/{scenario_id}/manifest.json")
        )
        world = manifest["world"]
        assert world["compose_digest"][:12] == generations.WORLD_V2, scenario_id
        assert world["observability_digest"] == generations.CURRENT_OBSERVABILITY_V2, scenario_id


def test_every_run_records_the_world_it_was_taken_in() -> None:
    """Q86: a provenance field beside `runtime_version`, not a capability-stamp move."""
    import inspect

    from evalharness import run

    assert 'run.manifest["world"] = tools_world()' in inspect.getsource(run.main)


# --- item 5: a gated run is a miss ------------------------------------------------------------


def test_the_harness_mirrors_the_product_s_gated_exit() -> None:
    from evalharness.run import INVESTIGATE_GATED
    from faultline.agents.runner import Exit

    assert int(Exit.GATED) == INVESTIGATE_GATED


TRANSCRIPT = """incident aa34  state triaging  anchor 08:00:37
triage: 1 services, severity warning, start from nowhere the graph knows, 0 unmeasured edge(s)

states: triaging -> resolved
trajectory: none persisted
triage judged: noise (medium confidence, suspects unknown)
  A lone warning-severity alert on a single service describes a system still serving traffic.

GATED BEFORE FAN-OUT: no specialist ran and nothing was spent on this incident
"""


def test_triage_s_judgement_is_read_off_the_transcript() -> None:
    from evalharness.run import gated_judgement

    judged = gated_judgement(TRANSCRIPT)

    assert judged["disposition"] == "noise"
    assert judged["confidence"] == "medium"
    assert judged["suspects"] == "unknown"
    assert judged["reasoning"].startswith("A lone warning-severity alert")
    assert gated_judgement("no such line")["disposition"] is None


def test_a_gated_run_is_wrong_on_every_axis_and_never_an_abstention() -> None:
    from evalharness.run import bundle_for, gated_artifact, score

    scenario = "v2-cart-freeze"
    scored = score("r1", scenario, bundle_for(scenario), gated_artifact("inc"), {"steps": 0}, {})

    for label in (scored.fault_class, scored.fix_class, scored.service):
        assert label is not None
        assert not label.abstained
        assert not label.correct
    assert not scored.ranked_class.top_3


class _FakeRun:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.run_id = "20261004T000000Z-v2-cart-freeze"
        self.manifest: dict[str, Any] = {"models": {}, "budget": {"max_tool_calls": 4}}
        self.saved = False

    def save_manifest(self) -> None:
        self.saved = True

    def write(self, name: str, text: str) -> None:
        (self.path / name).write_text(text)


def test_a_gated_run_is_scored_and_recorded_not_discarded(tmp_path: Path) -> None:
    from evalharness.run import _score_gated, bundle_for

    (tmp_path / "investigate.txt").write_text(TRANSCRIPT)
    run = _FakeRun(tmp_path)

    class Args:
        scenario_id = "v2-cart-freeze"

    code = _score_gated(run, Args(), bundle_for("v2-cart-freeze"), "inc", False)

    assert code == 0
    assert run.saved
    assert run.manifest["gated"]["disposition"] == "noise"
    assert run.manifest["score"]["fault_class"]["correct"] is False
    assert run.manifest["score"]["fault_class"]["abstained"] is False
    assert "GATED by triage" in (tmp_path / "report.txt").read_text()
    assert not (tmp_path / "DISCARDED.md").exists()


# --- item 1: the world check ------------------------------------------------------------------


def _world_check() -> Any:
    spec = importlib.util.spec_from_file_location("world_check", REPO / "scripts/world_check.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quote_s_offset_is_read_against_its_caller() -> None:
    wc = _world_check()
    spans = [
        {"service": "shipping", "id": "a", "parent": "", "start": 1000.0},
        {"service": "quote", "id": "b", "parent": "a", "start": 1000.004},
        {"service": "quote", "id": "c", "parent": "b", "start": 1000.005},
        {"service": "checkout", "id": "d", "parent": "", "start": 999.0},
        {"service": "shipping", "id": "e", "parent": "d", "start": 999.1},
        {"service": "quote", "id": "f", "parent": "e", "start": 999.1 - 36 * 3600},
    ]

    offsets = wc.quote_offsets(spans)

    assert len(offsets) == 2, "a quote span called by quote is not a cross-clock reading"
    assert min(offsets) < 0.01
    assert max(offsets) > wc.QUOTE_MAX_OFFSET_SECONDS


def test_the_world_check_fails_without_alertmanager_and_exits_non_zero() -> None:
    import inspect

    wc = _world_check()
    source = inspect.getsource(wc.main)

    assert "alertmanager running and ready (Q124)" in source
    assert "alertmanager's receiver answering (Q124)" in source
    assert wc.RECEIVER == "http://localhost:8000"
    assert "check_quote_clock()" in source
    assert "return 0 if not failed else 1" in source


# --- item 6: the baselines at nine classes, with the culprit ----------------------------------

NINE = (
    "resource_exhaustion",
    "dependency_latency",
    "bad_deploy",
    "bad_config",
    "feature_flag",
    "process_freeze",
    "network_partition",
    "datastore_corruption",
    "disk_fill",
)


def test_b1_and_b2_are_shown_and_may_answer_all_nine_classes() -> None:
    from evalharness import baseline_agent, baseline_prior

    for prompt in (baseline_agent.system_prompt(), baseline_prior.B2_SYSTEM):
        for fault_class in NINE:
            assert f"`{fault_class}`" in prompt, fault_class
    assert baseline_agent.NINE_CLASSES.split("|") == list(NINE)
    for fault_class in NINE:
        assert fault_class in baseline_prior.B2_SYSTEM.split("Reply with JSON only")[1]


def test_b1_and_b2_carry_the_culprit_and_the_runners_up_into_the_scored_verdict() -> None:
    from evalharness import baseline_agent, baseline_prior
    from faultline.agents.contracts import Verdict

    verdict = Verdict.model_validate(
        {
            "root_cause": "cart is frozen",
            "service": "cart",
            "fault_class": "process_freeze",
            "remediation_class": "restart",
            "confidence": "medium",
            "evidence": [],
            "reasoning": "silent",
            "open_questions": [],
            "alternatives": [
                {
                    "root_cause": "partition",
                    "service": "cart",
                    "fault_class": "network_partition",
                    "why_not": "no log",
                }
            ],
        }
    )
    for module, run in (
        (baseline_agent, baseline_agent.B1Run(verdict=verdict)),
        (baseline_prior, baseline_prior.B2Run(verdict=verdict)),
    ):
        scored = module.artifact("inc", "traj", [], 0, [], run)["verdict"]
        assert scored["service"] == "cart"
        assert scored["alternatives"][0]["fault_class"] == "network_partition"


def test_b0_s_fix_table_matches_every_v2_scenario_s_label() -> None:
    import yaml

    from evalharness import baselines

    for path in sorted((REPO / "evals/scenarios/v2").glob("*.yaml")):
        scenario = yaml.safe_load(path.read_text())
        if scenario.get("blocked"):
            continue
        assert (
            baselines.CLASS_TO_REMEDIATION[scenario["fault_class"]]
            == scenario["expected_remediation_class"]
        ), path.name
    assert set(baselines.CLASS_TO_REMEDIATION) == set(NINE)
    assert baselines.BASELINE_RUNTIME.endswith("B0.4")


def test_b0_carries_its_culprit_and_cannot_name_the_five_classes_with_no_change_record() -> None:
    """The plan's three signals: on a T7.0 class there is no change record, so B0's no-change rule
    answers `dependency_latency`. Stated, not repaired."""
    from datetime import UTC, datetime

    from evalharness import baselines

    onset = datetime(2026, 10, 4, tzinfo=UTC)
    prediction = baselines.predict(baselines.Signals(alerting=["cart", "checkout"]), onset)
    row = baselines.artifact("inc", "traj", [], 0, [], prediction)["verdict"]

    assert row["service"] == "cart"
    assert row["fault_class"] == "dependency_latency"
