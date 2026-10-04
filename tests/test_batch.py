"""The batch runner (`PREREGISTRATION-headline-v2.md`, Addendum 1, item 9; T7.3's randomized queue).

The queue's shape as the two registrations fix it, every arm's switches as part C built them, the
tally by the registered rule, and the runner's order: check, launch, tally, stop.
"""

from __future__ import annotations

import json
import tomllib
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from evalharness import batch
from evalharness.batch import Queue, Slot, Tally, WorldCheck

REPO = Path(__file__).resolve().parents[1]
DEV = [f"v2-d{i:02d}" for i in range(29)]
HOLD = [f"v2-h{i}" for i in range(10)]


# --- the queues -------------------------------------------------------------------------------


def test_the_headline_queue_is_dev_then_holdout_each_scenario_s_four_arms_together() -> None:
    slots = batch.headline_queue(DEV, HOLD, seed=7)

    assert len(slots) == 156
    assert [s.slot for s in slots] == list(range(1, 157))
    assert {s.pass_name for s in slots[:116]} == {"dev"}
    assert {s.pass_name for s in slots[116:]} == {"holdout"}
    groups = [slots[i : i + 4] for i in range(0, 156, 4)]
    assert all(len({s.scenario for s in g}) == 1 for g in groups)
    assert all(sorted(s.arm for s in g) == sorted(batch.HEADLINE_ARMS) for g in groups)
    firsts = Counter(g[0].arm for g in groups[:28])
    assert set(firsts.values()) == {7}, "the arm order rotates"
    assert [g[0].scenario for g in groups[:29]] != sorted(DEV), "the scenario order is shuffled"


def test_a_queue_is_fixed_by_its_seed() -> None:
    assert batch.headline_queue(DEV, HOLD, 3) == batch.headline_queue(DEV, HOLD, 3)
    assert batch.headline_queue(DEV, HOLD, 3) != batch.headline_queue(DEV, HOLD, 4)
    twelve = DEV[:12]
    assert batch.t73_queue(twelve, 5) == batch.t73_queue(list(reversed(twelve)), 5)


def test_t73_s_queue_is_every_configuration_on_every_scenario_once() -> None:
    scenarios = batch.t73_scenarios()
    slots = batch.t73_queue(scenarios, seed=11)

    assert len(scenarios) == 12
    assert len(slots) == 120
    assert Counter((s.scenario, s.arm) for s in slots) == Counter(
        {(sc, c): 1 for sc in scenarios for c in batch.T73_CONFIGS}
    )
    assert {s.pass_name for s in slots} == {"t73"}
    assert [s.arm for s in slots[:10]] != list(batch.T73_CONFIGS)


def test_a_queue_round_trips_and_refuses_what_it_cannot_run() -> None:
    queue = Queue("t73", 11, batch.t73_queue(DEV[:12], 11), "abc123")
    assert batch.read_queue(batch.render_queue(queue)) == queue

    with pytest.raises(ValueError, match="E7 runs pinned"):
        batch.read_queue(batch.render_queue(Queue("t73", 11, queue.slots, None)))
    bad = Queue("t73", 1, [Slot(1, "t73", "x", "E10")])
    with pytest.raises(ValueError, match="unknown arm"):
        batch.read_queue(batch.render_queue(bad))
    gap = Queue("t73", 1, [Slot(2, "t73", "x", "F")])
    with pytest.raises(ValueError, match="numbered"):
        batch.read_queue(batch.render_queue(gap))


# --- the arms ---------------------------------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in batch.SWITCH_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("name", ["E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9"])
def test_each_switch_arm_is_recorded_as_an_ablation_and_f_as_none(
    clean_env: pytest.MonkeyPatch, name: str
) -> None:
    """Part C's record, reached through the arm table: one link, so the two cannot disagree."""
    from evalharness.run import ablation_config

    arm = batch.arms("abc123")[name]
    assert set(arm.env) <= set(batch.SWITCH_ENV)
    for key, value in arm.env.items():
        clean_env.setenv(key, value)
    assert ablation_config(), name


def test_f_and_the_baselines_set_no_switch_and_e4_tiers_only_the_specialists(
    clean_env: pytest.MonkeyPatch,
) -> None:
    from evalharness.run import ablation_config

    table = batch.arms()
    for name in ("F", "B0", "B1", "B2", "E1"):
        assert not table[name].env
    assert ablation_config() == {}
    assert table["E1"].flags == table["B1"].flags == ("--baseline", "b1")
    tiers = json.loads(table["E4"].env["FAULTLINE_AGENT_ROLE_MODELS"])
    assert tiers == {s: "claude-sonnet-4-6" for s in ("changes", "logs", "metrics", "traces")}


def test_a_switch_in_the_operator_s_shell_never_reaches_another_arm() -> None:
    leaked = {
        "FAULTLINE_AGENT_BRIEFING_MODE": "push",
        "PATH": "/bin",
        "FAULTLINE_TOOLS_WORLD": "v2",
    }

    f_env = batch.slot_env(leaked, batch.arms()["F"])
    e3_env = batch.slot_env(leaked, batch.arms()["E3"])

    assert "FAULTLINE_AGENT_BRIEFING_MODE" not in f_env
    assert f_env["FAULTLINE_TOOLS_WORLD"] == "v2"
    assert e3_env["FAULTLINE_AGENT_EVIDENCE_MODE"] == "raw"
    assert "FAULTLINE_AGENT_BRIEFING_MODE" not in e3_env


def test_a_holdout_slot_carries_holdout_and_the_batch_s_label() -> None:
    argv = batch.slot_argv(Slot(120, "holdout", "v2-h1", "B2"), batch.arms()["B2"], "hl", 9, 156)

    assert argv[:4] == ["faultline-eval", "v2-h1", "--runs-remaining", "9"]
    assert "--holdout" in argv and argv[argv.index("--baseline") + 1] == "b2"
    assert argv[argv.index("--sweep") + 1] == "hl"
    assert argv[argv.index("--sweep-slot") + 1] == "120"
    dev = batch.slot_argv(Slot(1, "dev", "v2-d1", "F"), batch.arms()["F"], "hl", 9, 156)
    assert "--holdout" not in dev and "--baseline" not in dev


# --- the tally --------------------------------------------------------------------------------


def test_tokens_are_priced_per_role_at_the_model_that_ran_it_times_1_26() -> None:
    manifest = {
        "models": {"planner": "claude-opus-5"},
        "ablation_config": {"role_models": {"logs": "claude-sonnet-4-6"}},
        "judge": {"judge_model": "claude-haiku-4-5", "tokens_in": 1_000_000, "tokens_out": 0},
    }
    steps = {"planner": (1_000_000, 0), "logs": (1_000_000, 0), "triage": (0, 1_000_000)}

    usd = batch.run_usd(manifest, steps, "claude-opus-5")

    agent = 5.0 + 3.0 + 25.0
    assert usd == pytest.approx(agent * 1.26 + 1.0)


def test_an_unpriced_model_is_refused_not_guessed() -> None:
    with pytest.raises(ValueError, match="no published price"):
        batch.price("claude-mystery", 1, 1)


def test_the_tally_sums_every_label_inside_the_cap_and_the_probes(tmp_path: Path) -> None:
    for name, label, incident in (("a", "trial", "i1"), ("b", "hl", "i2"), ("c", "other", "i3")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "manifest.json").write_text(
            json.dumps({"run_id": name, "incident_id": incident, "sweep": {"id": label}})
        )
    steps = {"i1": {"planner": (1_000_000, 0)}, "i2": {"planner": (2_000_000, 0)}}

    total = batch.tally(["hl", "trial"], 2, "claude-opus-5", lambda i: steps[i], root=tmp_path)

    assert total.runs == 2
    probe = 2 * batch.price("claude-opus-5", batch.PROBE_INPUT_TOKENS, 1)
    assert total.usd == pytest.approx(15.0 * 1.26 + probe)


def test_probes_from_an_earlier_night_are_read_off_its_log(tmp_path: Path) -> None:
    log = tmp_path / "BATCH-hl.tsv"
    log.write_text(
        "slot\tpass\tscenario\tarm\toutcome\tattempts\trerun\ttally_usd\n"
        "1\tdev\tx\tF\tscored\t2\t0\t0.5\n"
        "2\tdev\tx\tB0\tscored\t1\t0\t0.5\n"
    )
    assert batch.logged_probes(log) == 2
    assert batch.logged_probes(tmp_path / "none.tsv") == 0


# --- the checks -------------------------------------------------------------------------------


def test_the_registered_stamps_are_today_s() -> None:
    ok, detail = batch.stamps()
    assert ok, detail


def test_the_corpus_must_be_at_both_pins_with_no_holdout_chunk() -> None:
    from evalharness.generations import CURRENT_CORPUS_BODY, CURRENT_CORPUS_SHAPE

    good = {"rows": 9, "sha256": CURRENT_CORPUS_SHAPE, "body_sha256": CURRENT_CORPUS_BODY}
    assert batch.corpus_frozen({**good, "holdout_chunks": 0})[0]
    assert not batch.corpus_frozen({**good, "holdout_chunks": 1})[0]
    ok, detail = batch.corpus_frozen({**good, "sha256": "0" * 64, "holdout_chunks": 0})
    assert not ok and "shape" in detail


def test_a_quote_clock_failure_restarts_quote_and_rechecks() -> None:
    fail = WorldCheck(False, "PASS  loki /ready\nFAIL  quote's clock within 1 s (Q121)  9 s")
    answers = [fail, fail, WorldCheck(True, "ALL PASS")]
    restarted: list[bool] = []

    ok, detail = batch.world_ready(lambda: answers.pop(0), lambda: restarted.append(True), _no)

    assert ok and restarted == [True] and "recheck 2" in detail


def test_a_world_that_will_not_settle_stops_the_batch_without_restarting_quote() -> None:
    restarted: list[bool] = []
    firing = WorldCheck(False, "FAIL  nothing firing  ServiceHighLatency/cart")

    ok, detail = batch.world_ready(lambda: firing, lambda: restarted.append(True), _no)

    assert not ok and not restarted and "nothing firing" in detail


# --- the runner -------------------------------------------------------------------------------


def _no(_: float) -> None:
    return None


class _Harness:
    """A world where each launch costs a dollar and `codes` says what each launch returns."""

    def __init__(self, codes: dict[tuple[str, str], list[int]] | None = None) -> None:
        self.codes = codes or {}
        self.launched: list[list[str]] = []
        self.envs: list[dict[str, str]] = []
        self.judged: list[str] = []
        self.spent = 0.0

    def launch(self, argv: list[str], env: dict[str, str]) -> int:
        self.launched.append(argv)
        self.envs.append(env)
        self.spent += 1.0
        arm = next((a for a in batch.arms() if batch.arms()[a].flags == _flags(argv)), "F")
        planned = self.codes.get((argv[1], arm))
        return planned.pop(0) if planned else 0

    def run(self, queue: Queue, **kw: Any) -> batch.BatchResult:
        defaults: dict[str, Any] = {
            "label": "hl",
            "stop_usd": 57.0,
            "settle": 0,
            "retries": 2,
            "launch": self.launch,
            "judge": self.judged.append,
            "find_run": lambda label, slot: f"run-{slot}",
            "read_tally": lambda labels, probes: Tally(self.spent, len(self.launched), probes),
            "world": lambda: (True, "ok"),
            "corpus": lambda: (True, "ok"),
            "check_stamps": lambda: (True, "ok"),
            "wait": _no,
            "base_env": {},
        }
        return batch.run_batch(queue, **{**defaults, **kw})


def _flags(argv: list[str]) -> tuple[str, ...]:
    return ("--baseline", argv[argv.index("--baseline") + 1]) if "--baseline" in argv else ()


def _queue(kind: str = "headline", n_dev: int = 2, n_hold: int = 1) -> Queue:
    return Queue(kind, 1, batch.headline_queue(DEV[:n_dev], HOLD[:n_hold], 1))


def test_every_slot_runs_in_order_and_only_the_headline_s_f_is_judged() -> None:
    harness = _Harness()
    result = harness.run(_queue())

    assert [r.slot for r in result.rows] == list(range(1, 13))
    assert harness.judged == [f"run-{r.slot}" for r in result.rows if r.arm == "F"]
    assert [int(a[3]) for a in harness.launched] == list(range(12, 0, -1))
    other = _Harness()
    t73 = other.run(Queue("t73", 1, [Slot(1, "t73", "x", "F")]))
    assert t73.rows and not other.judged


def test_a_discard_is_re_run_once_at_the_end_of_its_pass_and_a_second_removes_it() -> None:
    queue = _queue(n_dev=2, n_hold=1)
    once, twice = queue.slots[1], queue.slots[9]
    harness = _Harness(
        {
            (once.scenario, once.arm): [4],
            (twice.scenario, twice.arm): [4, 4],
        }
    )
    result = harness.run(queue)

    order = [(r.slot, r.rerun) for r in result.rows]
    assert order.index((once.slot, True)) == 8, "after the dev pass's eight slots"
    assert order[-1] == (twice.slot, True)
    assert result.removed == [twice.scenario]
    assert result.stopped is None


def test_a_refusal_is_retried_and_never_injected() -> None:
    queue = _queue(n_dev=1, n_hold=0)
    first = queue.slots[0]
    harness = _Harness({(first.scenario, first.arm): [3, 0]})
    result = harness.run(queue)

    assert result.rows[0].attempts == 2 and result.rows[0].outcome == "scored"


def test_the_batch_stops_when_the_tally_passes_the_line_and_names_what_is_left() -> None:
    result = _Harness().run(_queue(), stop_usd=4.5)

    assert len(result.rows) == 5
    assert result.stopped and "passed the registered stop" in result.stopped
    assert [s.slot for s in result.unfinished] == list(range(6, 13))


def test_a_failed_check_stops_before_the_slot_and_the_slot_is_unfinished() -> None:
    calls = iter([(True, "ok"), (False, "FAIL  kafka running (Q114)")])
    result = _Harness().run(_queue(n_dev=1, n_hold=0), world=lambda: next(calls))

    assert len(result.rows) == 1
    assert result.stopped and "world check failed before slot 2" in result.stopped
    assert result.unfinished[0].slot == 2


def test_a_moved_stamp_stops_everything() -> None:
    result = _Harness().run(_queue(), check_stamps=lambda: (False, "prompts:000"))

    assert not result.rows and result.stopped and "stamps" in result.stopped


def test_a_block_runs_only_its_slots_and_counts_down_over_itself() -> None:
    harness = _Harness()
    result = harness.run(_queue(), from_slot=5, to_slot=8)

    assert [r.slot for r in result.rows] == [5, 6, 7, 8]
    assert [int(a[3]) for a in harness.launched] == [4, 3, 2, 1]


def test_the_switch_reaches_only_its_own_slot() -> None:
    harness = _Harness()
    queue = Queue("t73", 1, [Slot(1, "t73", "x", "E9"), Slot(2, "t73", "x", "F")], None)
    harness.run(queue, base_env={"FAULTLINE_AGENT_EVIDENCE_MODE": "raw"})

    assert harness.envs[0] == {"FAULTLINE_AGENT_BRIEFING_MODE": "push"}
    assert harness.envs[1] == {}


def test_faultline_batch_is_a_console_script() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert project["project"]["scripts"]["faultline-batch"] == "evalharness.batch:run_cli"
    args = batch.parser().parse_args(["run", "q.tsv", "--label", "hl", "--stop-usd", "57"])
    assert args.stop_usd == 57.0 and args.also_count == []


# --- the trial (`PREREGISTRATION-trial-v2.md`) -------------------------------------------------


def test_the_trial_is_the_registered_draw_and_the_switch_scenario_is_outside_the_twelve() -> None:
    from evalharness import sweep

    dev = sweep.runnable(world="v2")
    drawn = batch.trial_scenarios(dev)
    assert drawn == ["v2-cart-bad-image-tag", "v2-ad-bad-image-tag", "v2-product-catalog-freeze"]
    chosen = batch.switch_scenario(drawn, batch.t73_scenarios())
    assert chosen == "v2-ad-bad-image-tag"

    slots = batch.trial_headline_queue(dev)
    assert len(slots) == 12 and {s.pass_name for s in slots} == {"dev"}
    assert Counter(s.scenario for s in slots) == Counter({d: 4 for d in drawn})


def test_the_switch_trial_is_e2_to_e9_once_each_on_one_scenario() -> None:
    slots = batch.trial_t73_queue("v2-ad-bad-image-tag", 20261007)

    assert sorted(s.arm for s in slots) == list(batch.SWITCH_ARMS)
    assert {s.scenario for s in slots} == {"v2-ad-bad-image-tag"}
    assert [s.arm for s in slots] != list(batch.SWITCH_ARMS)
    queue = Queue("trial-t73", 20261007, slots, "abc123")
    assert batch.read_queue(batch.render_queue(queue)) == queue


def test_the_switch_scenario_pages_critical_so_the_noise_gate_cannot_take_it() -> None:
    manifest = next(REPO.glob("evals/scenarios/artifacts/dev/v2-ad-bad-image-tag/manifest.json"))
    page = json.loads(manifest.read_text())["alerts_at_fire"]
    assert page and all(a.startswith("ServiceHighErrorRate/") for a in page)


def test_the_headline_trial_judges_its_f_and_the_switch_trial_judges_nothing() -> None:
    assert batch.judged("trial-headline", "F")
    assert not batch.judged("trial-headline", "B1")
    assert not batch.judged("trial-t73", "E3")


def test_the_committed_trial_queues_are_what_their_seeds_print() -> None:
    """Committed before the trial, and nothing in them changes after a result."""
    from evalharness import sweep

    dev = sweep.runnable(world="v2")
    headline = Queue("trial-headline", 20261004, batch.trial_headline_queue(dev, 20261004))
    chosen = batch.switch_scenario(batch.trial_scenarios(dev), batch.t73_scenarios())
    switches = Queue(
        "trial-t73",
        20261007,
        batch.trial_t73_queue(chosen, 20261007),
        "233902d25c440f23af6f7d6e94d2946bac0bee0a",
    )
    for name, queue in (("trial-headline", headline), ("trial-t73", switches)):
        committed = (REPO / f"evals/runs/QUEUE-{name}-v2.tsv").read_text()
        assert committed == batch.render_queue(queue), name


# --- the trial's first attempt (2026-10-04): what it found ----------------------------------


def test_no_test_holds_the_real_world_lock() -> None:
    from injector.worldlock import LOCK_PATH, WorldLock

    assert WorldLock.__init__.__defaults__ is not None
    assert WorldLock.__init__.__defaults__[0] != LOCK_PATH


def test_the_key_file_reaches_every_slot_and_is_never_shown(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_text("sk-test-secret\n")

    env, state = batch.with_api_key({"PATH": "/bin"}, key)
    assert env["ANTHROPIC_API_KEY"] == "sk-test-secret"
    assert "sk-test" not in state

    kept, state = batch.with_api_key({"ANTHROPIC_API_KEY": "from-shell"}, key)
    assert kept["ANTHROPIC_API_KEY"] == "from-shell" and state == "present (environment)"
    _, state = batch.with_api_key({}, tmp_path / "absent")
    assert state == "MISSING"


def test_a_refusal_on_every_attempt_stops_the_batch_at_that_slot() -> None:
    queue = _queue(n_dev=2, n_hold=0)
    first = queue.slots[0]
    harness = _Harness({(first.scenario, first.arm): [3, 3]})
    result = harness.run(queue)

    assert len(harness.launched) == 2, "two attempts, then the stop, not seven more slots"
    assert result.stopped and "standing" in result.stopped
    assert result.unfinished[0].slot == 1


def test_a_held_world_lock_is_retried_and_never_counted_as_a_discard() -> None:
    queue = _queue(n_dev=1, n_hold=0)
    first = queue.slots[0]
    harness = _Harness({(first.scenario, first.arm): [2, 0]})
    result = harness.run(queue)

    assert result.rows[0].attempts == 2 and result.rows[0].outcome == "scored"
    assert not result.stopped
