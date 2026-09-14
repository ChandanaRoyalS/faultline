"""Q53's pilot driver, against fakes (`PREREGISTRATION-Q53.md`).

**Every defect T6.3 found was in its driver, not in what it drove**: a gate weaker than the
harness's, and a missing model client discovered *after* a fault had been injected. This pilot
spends money on a live world, so its logic is exercised here where neither is true.
"""

from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

import pytest

from evalharness import depthpilot
from evalharness.depthpilot import (
    BASELINE_ARM,
    CHANGE_ARM,
    Verdict,
    arm_order,
    env_for,
    run_pilot,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class _Steps:
    """A world that always admits, always alerts, and answers whatever it is told to."""

    def __init__(
        self,
        answers: dict[tuple[str, str], tuple[str, str] | None] | None = None,
        *,
        admits: bool = True,
        incident: bool = True,
        cost: float = 0.6,
        reject_raises: Exception | None = None,
        admits_after: int = 10**6,
        gate_wait: int = 0,
    ) -> None:
        self.answers = answers or {}
        self._admits = admits
        self._incident = incident
        self._cost = cost
        self._reject_raises = reject_raises
        self._admits_after = admits_after
        self._gate_wait = gate_wait
        self.gate_readings = 0
        self.injected: list[str] = []
        self.reverted: list[str] = []
        self.investigations: list[tuple[str, str]] = []
        self.rejections: list[tuple[str, str]] = []
        self.order: list[str] = []

    def gate_admits(self) -> depthpilot.GateCheck:
        self.gate_readings += 1
        admits = self._admits or self.gate_readings > self._admits_after
        return depthpilot.GateCheck(
            admits,
            () if admits else ("a leftover incident",),
            self._gate_wait,
        )

    def inject(self, scenario_id: str) -> str:
        self.injected.append(scenario_id)
        return "injected"

    def wait_for_incident(self, scenario_id: str, after: datetime) -> str | None:
        """A fresh incident per injection, because a re-attempt is a fresh injection: the old one
        is `failed`, which ADR-0016's table makes terminal."""
        if not self._incident:
            return None
        return f"inc-{scenario_id}-{self.injected.count(scenario_id)}"

    def investigate(self, incident_id: str, arm: str) -> Verdict | None:
        self.investigations.append((incident_id, arm))
        self.order.append(f"investigate:{arm}")
        scenario = incident_id.removeprefix("inc-").rsplit("-", 1)[0]
        answer = self.answers.get((scenario, arm), ("bad_deploy", "rollback"))
        if answer is None:
            return None
        return Verdict(arm, f"t-{scenario}-{arm}", answer[0], answer[1], self._cost)

    def reject(self, incident_id: str, reason: str) -> None:
        self.order.append("reject")
        if self._reject_raises is not None:
            raise self._reject_raises
        self.rejections.append((incident_id, reason))

    def spend_on(self, incident_id: str) -> float:
        """Priced per investigation started, verdict or not - which is the world's behaviour and
        the whole point of asking the world instead of summing the verdicts."""
        return self._cost * sum(1 for i, _ in self.investigations if i == incident_id)

    def revert(self, scenario_id: str) -> None:
        self.reverted.append(scenario_id)


def test_a_pair_is_one_injection_and_two_investigations() -> None:
    """**The design's whole point.** Both arms see one world state, one incident, one alert set and
    one change log, so the only difference between the verdicts is what retrieval handed the model.
    Two injections would reintroduce the world variance the pairing exists to remove."""
    steps = _Steps()

    result = run_pilot(steps, ("cart-bad-image-tag",))

    assert steps.injected == ["cart-bad-image-tag"]
    assert [arm for _, arm in steps.investigations] == [BASELINE_ARM, CHANGE_ARM]
    assert len({incident for incident, _ in steps.investigations}) == 1
    assert result.pairs[0].complete


def test_the_arm_order_alternates_across_pairs() -> None:
    """A second investigation runs against an incident that already carries the first's proposal.
    Alternating does not remove an order effect - it stops one being confounded with the arm."""
    assert arm_order(0) == (BASELINE_ARM, CHANGE_ARM)
    assert arm_order(1) == (CHANGE_ARM, BASELINE_ARM)

    steps = _Steps()
    run_pilot(steps, ("a", "b", "c", "d"))

    firsts = [steps.investigations[i][1] for i in range(0, 8, 2)]
    assert firsts == [BASELINE_ARM, CHANGE_ARM, BASELINE_ARM, CHANGE_ARM]


def test_identical_verdicts_do_not_count_as_a_difference() -> None:
    steps = _Steps()

    result = run_pilot(steps, ("a", "b"))

    assert result.complete_pairs and not result.differing
    assert "0 of 2 differ" in result.render()


def test_a_short_run_of_zero_differences_is_not_the_closure() -> None:
    """**The false claim the fifth dry run printed.**

    `0 of 1 differ ... this closes Q53 ... at 87% confidence`. The 87% is `1 - (1-0.186)**10` and
    belongs to ten pairs; one pair buys **18.6%**. The sentence fired on any run with no
    differences, so a ten-pair run that stopped at three would have closed Q53 on three pairs.
    """
    steps = _Steps()

    result = run_pilot(steps, ("a",))

    reading = result.closure_reading()
    assert "0 of 1 differ" in reading
    assert "19%" in reading or "18%" in reading, reading
    assert "NOT the closure" in reading
    assert "Q53 stays open" in reading
    assert "closes Q53" not in reading, "one pair must never claim the closure"


def test_the_closure_is_licensed_only_by_the_full_registered_set() -> None:
    """Ten complete pairs, and only then, is what §3.2 was written for."""
    steps = _Steps()

    result = run_pilot(steps, depthpilot.SCENARIOS)

    reading = result.closure_reading()
    assert len(result.complete_pairs) == 10
    assert "87%" in reading
    assert "closes Q53" in reading
    assert "NOT the closure" not in reading


def test_a_changed_fault_class_is_the_outcome() -> None:
    steps = _Steps(
        {
            ("b", CHANGE_ARM): ("resource_exhaustion", "config_revert"),
        }
    )

    result = run_pilot(steps, ("a", "b"))

    assert [p.scenario_id for p in result.differing] == ["b"]
    assert "DIFFERS" in result.render()


# --- Amendment 1: the rejection between the arms, and what it costs the outcome -----------------


def test_the_second_arm_is_reached_through_a_rejection_and_the_first_is_not() -> None:
    """**The defect the third dry run bought, for $0.79.**

    `ALLOWED` admits `PLANNING` from `TRIAGING` and from `REJECTED` and from nowhere else, which is
    why `INVESTIGABLE` has exactly those two members. An incident that has been investigated once is
    past `TRIAGING` permanently, so there is no door into a second investigation of one incident
    that does not pass through `REJECTED` - the registered design could not run without one.

    The rejection sits between the arms and nowhere else: the first arm is legal from `TRIAGING`,
    and an incident is not rejectable until something has proposed on it.
    """
    steps = _Steps()

    result = run_pilot(steps, ("cart-bad-image-tag",))

    assert steps.order == [
        f"investigate:{BASELINE_ARM}",
        "reject",
        f"investigate:{CHANGE_ARM}",
    ]
    assert len(steps.rejections) == 1
    assert result.pairs[0].rejected
    assert result.pairs[0].complete


def test_every_pair_is_rejected_with_the_same_registered_reason() -> None:
    """**Fixed before any run, identical across pairs, carrying no scenario-specific content.**

    A reason chosen after seeing a verdict would be prompt-fitting - the reject-loop driver's rule.
    A reason that varied by scenario would put scenario text in one arm's brief and not the other's,
    which is the confound the pairing exists to remove.
    """
    steps = _Steps()

    run_pilot(steps, ("a", "b", "c"))

    reasons = {reason for _, reason in steps.rejections}
    assert reasons == {depthpilot.REJECTION_REASON}
    for scenario_id in depthpilot.SCENARIOS:
        assert scenario_id not in depthpilot.REJECTION_REASON
        for word in scenario_id.split("-"):
            assert word not in depthpilot.REJECTION_REASON.split(), scenario_id


def test_a_moved_remediation_class_alone_is_not_the_outcome() -> None:
    """**Amendment 1's whole point.** The rejection reaches the proposer's brief and only the
    proposer's - `test_an_operator_rejection_reaches_the_proposer_in_the_user_message_only` pins
    that - and T6.3 measured a rejection's effect on the next proposal at **2 of 2 changed, both
    abstentions**. So a moved `remediation_class` here is evidence about the rejection, not about
    retrieval, and counting it would let the pilot recommend funding a 30-40 pair measurement on an
    effect this repository has already measured at 100%.

    It is still recorded: if it moves in about half the pairs that is T6.3's effect showing up
    again, and if it never moves that is worth knowing too.
    """
    steps = _Steps({("a", CHANGE_ARM): ("bad_deploy", "none")})

    result = run_pilot(steps, ("a",))

    pair = result.pairs[0]
    assert pair.complete
    assert not pair.differs, "the fault class did not move"
    assert pair.remediation_differs
    assert result.differing == []
    assert "[remediation also moved]" in result.render()
    assert "does not decide" in result.render()


def test_a_refused_rejection_loses_the_pair_and_says_so() -> None:
    """The first arm has already been paid for by the time the pilot can know the pair completes -
    an incident is only rejectable once something has proposed on it. A refusal here is recorded in
    `skipped` rather than raised, because a driver that dies holding an injected fault has cost more
    than the pair."""
    steps = _Steps(reject_raises=RuntimeError("409: the rejection cap for this incident is two"))

    result = run_pilot(steps, ("a",))

    pair = result.pairs[0]
    assert not pair.complete
    assert not pair.rejected
    assert "rejection refused" in pair.skipped and "409" in pair.skipped
    assert steps.reverted == ["a", "a"], "both attempts still clean up"
    assert result.cost_usd == pytest.approx(1.2), "each attempt's first arm is still counted"


def test_the_artifact_records_the_channel_the_outcome_was_read_on() -> None:
    """A reader opening the JSON a year from now should not have to infer from the code which of
    the two classes decided, nor that a rejection stood between the arms."""
    steps = _Steps()

    payload = run_pilot(steps, ("a",)).as_dict()

    assert payload["outcome_channel"] == "fault_class"
    assert payload["rejection_reason"] == depthpilot.REJECTION_REASON
    assert "Amendment 1" in payload["amendment"]
    assert payload["pairs"][0]["rejected"] is True
    assert payload["pairs"][0]["remediation_differs"] is False


def test_an_unmounted_reject_route_is_visible_before_anything_is_injected() -> None:
    """**The precondition that would otherwise have been found ten times, at $0.79 each.**

    `api/app.py` mounts the approve and reject routes only when `FAULTLINE_EXECUTOR_TOKEN_KEY` is
    set and **starts anyway when it is not**, on the deliberate ground that *"a missing button is
    not an outage"*. From the pilot's side that is invisible: the screen serves, the read routes
    answer, and the rejection comes back as a bare 404 indistinguishable from a missing incident -
    after the first arm has been paid for.

    So it is read off the process's own `/openapi.json`, which is a statement about what it serves
    rather than a guess, and the path here is the one FastAPI registers.
    """
    served = {"paths": {depthpilot.REJECT_PATH: {"post": {}}, "/healthz": {"get": {}}}}
    read_only = {"paths": {"/api/v1/incidents": {"get": {}}, "/healthz": {"get": {}}}}

    assert depthpilot.reject_route_is_mounted(served)
    assert not depthpilot.reject_route_is_mounted(read_only)
    assert not depthpilot.reject_route_is_mounted({})


def test_the_reject_path_is_the_one_the_app_actually_registers() -> None:
    """The constant is checked against the router rather than against itself, so that a rename of
    the route shows up here instead of as a preflight that passes and a pilot that 404s."""
    source = (REPO_ROOT / "src" / "faultline" / "api" / "approvals.py").read_text()

    assert 'APIRouter(prefix="/api/v1/incidents")' in source
    assert '@router.post("/{incident_id}/reject")' in source
    assert depthpilot.REJECT_PATH == "/api/v1/incidents/{incident_id}/reject"


def test_the_registered_reason_survives_the_machines_own_cleaning() -> None:
    """`record_rejection` requires a reason and `clean_reason` raises on whitespace, so there is no
    reasonless route to `REJECTED`. The constant has to be text a real rejection would accept."""
    from faultline.orchestrator.rejections import clean_reason

    assert clean_reason(depthpilot.REJECTION_REASON)


# --- Amendment 2: spend the ceiling can see, and one re-attempt per scenario --------------------


def test_a_failed_arms_spend_is_counted_against_the_ceiling() -> None:
    """**The defect the fourth dry run exposed, and it reported `$0.00` while doing it.**

    The planner ran, was refused twice on a field `DispatchPlan` forbids, and the incident went to
    `failed`. No verdict - so the old accounting, which summed the verdicts, saw no spend at all.
    Twenty investigations at a discard rate near a sixth is several dollars the $25 ceiling could
    not observe, which is a blind spot in exactly the place a ceiling exists for.

    So the pair's cost is what the **incident** cost, read from the world after each arm.
    """
    steps = _Steps({("a", BASELINE_ARM): None}, cost=0.5)

    result = run_pilot(steps, ("a",))

    assert not any(p.complete for p in result.pairs)
    assert result.cost_usd == pytest.approx(1.0), "two attempts, one dead arm each, both counted"
    assert "spent $0.50" in result.render()


def test_a_dead_pair_is_re_attempted_once_and_only_once() -> None:
    """Amendment 2, fixed before the run. A pair dies whole when either arm fails and the incident
    is then `failed`, which ADR-0016's table makes terminal - so the retry is a fresh injection.

    Both halves must score for a pair to count, so the harness's 16.7% per-run discard rate is
    30.6% per pair. One retry restores the registered ten; a second would be a budget responding to
    its own outcome.
    """
    steps = _Steps({("a", CHANGE_ARM): None})

    result = run_pilot(steps, ("a",))

    assert steps.injected == ["a", "a"]
    assert [p.attempt for p in result.pairs] == [1, 2]
    assert len({i for i, _ in steps.investigations}) == 2, "a fresh incident, not a resumption"


def test_a_scenario_whose_pair_completes_is_not_re_attempted() -> None:
    steps = _Steps()

    result = run_pilot(steps, ("a", "b"))

    assert steps.injected == ["a", "b"]
    assert [p.attempt for p in result.pairs] == [1, 1]


def test_the_re_attempt_keeps_the_arm_order_of_the_attempt_it_replaces() -> None:
    """**A retry that flipped the order would confound the retry with the arm**, which is the one
    thing `arm_order` exists to prevent. The order comes from the scenario's index, never from the
    attempt number."""
    steps = _Steps({("b", BASELINE_ARM): None})

    result = run_pilot(steps, ("a", "b"))

    b_pairs = [p for p in result.pairs if p.scenario_id == "b"]
    assert [p.attempt for p in b_pairs] == [1, 2]
    assert {p.first_arm for p in b_pairs} == {CHANGE_ARM}, "index 1 puts the change arm first"


def test_the_budget_stops_the_pilot_before_spending_not_after() -> None:
    """**A ceiling enforced after the spend is a report, not a limit.**

    Each investigation costs 6.0 here against a ceiling of 10.0: the first pair spends 12.0, and
    the pilot stops before starting the second rather than discovering it overran.
    """
    steps = _Steps(cost=6.0)

    result = run_pilot(steps, ("a", "b", "c"), ceiling_usd=10.0)

    assert result.cost_usd == pytest.approx(12.0)
    assert "budget ceiling" in result.stopped
    assert steps.injected == ["a"], "no further scenario is injected"


def test_the_world_is_reverted_even_when_an_arm_produces_nothing() -> None:
    """**A pilot that leaves a fault injected has cost more than money.** The revert is in a
    `finally`, so a missing verdict, a failed investigation or a budget stop all still clean up."""
    steps = _Steps({("a", CHANGE_ARM): None})

    result = run_pilot(steps, ("a",))

    assert steps.reverted == ["a", "a"], "both attempts clean up after themselves"
    assert not any(p.complete for p in result.pairs)
    assert all("produced no verdict" in p.skipped for p in result.pairs)


def test_a_refused_gate_skips_the_scenario_without_injecting() -> None:
    """T6.3's first defect was a driver whose gate was weaker than the harness's, and a leftover
    incident swallowed the next scenario's alerts. The gate is checked before **every** injection,
    not once at the start - and now, after Q56, re-read until patience runs out."""
    naps: list[int] = []
    steps = _Steps(admits=False)

    result = run_pilot(steps, ("a", "b"), sleeper=naps.append)

    assert steps.injected == []
    assert all("gate refused" in p.skipped for p in result.pairs)
    assert result.complete_pairs == []
    assert steps.gate_readings == depthpilot.GATE_RETRIES * len(result.pairs)
    assert all(f"after {depthpilot.GATE_RETRIES} readings" in p.skipped for p in result.pairs)


# --- Q56: a gate refusal is not a failed attempt ------------------------------------------------


def test_the_driver_waits_the_gate_out_instead_of_burning_an_attempt() -> None:
    """**Q56, and the reason the ten-pair run nearly reported `n = 1`.**

    The pilot took T6.3's lesson that the gate must be re-read before every injection and not
    T6.3's *patience*: `rejectloop` retries ten times at sixty seconds, this refused on the first
    reading. In the live run **9 of 10 first attempts died on the gate**, and Amendment 2's single
    re-attempt - registered for investigation failures, of which there were zero - was consumed by
    them.

    The scarce resource is the re-attempt. A world that merely needed another ninety seconds must
    not cost one.
    """
    naps: list[int] = []
    steps = _Steps(admits=False, admits_after=2, gate_wait=90)

    result = run_pilot(steps, ("a",), sleeper=naps.append)

    assert steps.injected == ["a"], "it injected, rather than giving up"
    assert [p.attempt for p in result.pairs] == [1], "the re-attempt was never spent"
    assert result.pairs[0].complete


def test_the_wait_is_the_gate_s_own_number_not_a_constant_of_the_driver_s() -> None:
    """`gate.Reading.settle_seconds_remaining` is the world's clock. The driver's own constant is
    the floor for refusals that are not clocks - a firing alert can say *no* but not *how long* -
    and the margin exists because a wait computed to the second and slept to the second arrives one
    second early."""
    naps: list[int] = []
    steps = _Steps(admits=False, admits_after=1, gate_wait=207)

    run_pilot(steps, ("a",), sleeper=naps.append)

    assert naps == [207 + depthpilot.GATE_WAIT_MARGIN_SECONDS]


def test_a_gate_that_names_no_clock_still_waits_a_floor() -> None:
    """`settle_seconds_remaining` is 0 for a firing alert or a p95 excursion. Sleeping zero and
    re-reading ten times in a row would be a busy loop against Prometheus."""
    naps: list[int] = []
    steps = _Steps(admits=False, admits_after=1, gate_wait=0)

    run_pilot(steps, ("a",), sleeper=naps.append)

    assert naps == [depthpilot.GATE_MIN_WAIT_SECONDS + depthpilot.GATE_WAIT_MARGIN_SECONDS]


def test_a_scenario_that_never_alerts_is_skipped_and_reverted() -> None:
    steps = _Steps(incident=False)

    result = run_pilot(steps, ("a",))

    assert steps.reverted == ["a", "a"]
    assert all(p.skipped == "no incident" for p in result.pairs)
    assert steps.investigations == [], "nothing is investigated without an incident"


def test_each_arm_sets_both_halves_of_its_configuration() -> None:
    """Neither half is tested alone: `retrieval_k` alone buys two queries of 43, normalisation 2
    alone at `k = 3` buys one, and Q52 measured that choosing among flags at that depth is worse
    than not choosing. A pilot that set one and not the other would measure nothing this
    registration is about."""
    baseline = env_for(BASELINE_ARM, {})
    change = env_for(CHANGE_ARM, {})

    assert baseline["FAULTLINE_CONTEXT_RETRIEVAL_K"] == "3"
    assert baseline["FAULTLINE_CONTEXT_TEXT_NORMALISATION"] == "0"
    assert change["FAULTLINE_CONTEXT_RETRIEVAL_K"] == "5"
    assert change["FAULTLINE_CONTEXT_TEXT_NORMALISATION"] == "2"


def test_the_arm_settings_are_the_ones_the_registration_names() -> None:
    """The configurations are read from the module rather than restated, so a drift between the
    driver and `PREREGISTRATION-Q53.md` §2 shows up here rather than in a spend."""
    assert depthpilot.ARMS[BASELINE_ARM] == {"retrieval_k": 3, "text_normalisation": 0}
    assert depthpilot.ARMS[CHANGE_ARM] == {"retrieval_k": 5, "text_normalisation": 2}
    assert depthpilot.BUDGET_CEILING_USD == 25.0


def test_the_registered_scenarios_are_ten_dev_ones_in_catalog_order() -> None:
    """**No selection.** A pilot whose scenarios were chosen would be measuring the chooser.

    Every one must be `dev`: holdout entries are spent deliberately and none is spent on a pilot.
    """
    from evalharness.scenario import load_catalog

    catalog = {s.id: s for s in load_catalog(REPO_ROOT / "evals/scenarios")}
    assert len(depthpilot.SCENARIOS) == 10
    assert len(set(depthpilot.SCENARIOS)) == 10
    for scenario_id in depthpilot.SCENARIOS:
        assert scenario_id in catalog, scenario_id
        assert catalog[scenario_id].split == "dev", f"{scenario_id} is not dev"
    assert list(depthpilot.SCENARIOS) == sorted(depthpilot.SCENARIOS), "catalog order"


def test_the_pilot_calls_no_model_itself() -> None:
    """**The arms must be the pipeline, not a second implementation of it.**

    `faultline-investigate` is shelled, so a driver that imported an agent role or a model client
    would be measuring something that merely lives in the same repository. The same guard the
    retrieval harness and the reject-loop driver carry.
    """
    source = (REPO_ROOT / "src" / "evalharness" / "depthpilot.py").read_text()
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "anthropic" not in imported
    assert not any(name.startswith("faultline.agents.role") for name in imported)
    assert "faultline.agents.model" not in imported


# --- reading the verdict, which the dry run found broken ---------------------------------------


def test_the_verdict_is_read_from_the_artifact_the_pipeline_writes() -> None:
    """**The defect the $1.20 dry run bought.**

    The first version queried a `proposals` table that does not exist. The lesson is not the wrong
    name: `faultline-investigate --out` writes `<incident>-verdict.json`, `evalharness.run` reads
    exactly that file, and a driver reconstructing the same answer from tables is a second
    implementation of the harness - which this module's docstring says it must not be.

    `fault_class` lives here and **not** in `trajectory_proposals`, which carries
    `remediation_class` only, so the table route could never have answered the question at all.
    """
    payload = {
        "trajectory_id": "c5d32a77",
        "verdict": {"fault_class": "resource_exhaustion", "remediation_class": "scale"},
    }

    verdict = depthpilot.verdict_from_artifact(payload, CHANGE_ARM, cost_usd=0.6)

    assert verdict is not None
    assert verdict.fault_class == "resource_exhaustion"
    assert verdict.remediation_class == "scale"
    assert verdict.trajectory_id == "c5d32a77"
    assert verdict.cost_usd == 0.6


def test_an_artifact_without_a_verdict_yields_none_rather_than_a_blank() -> None:
    """A blank `fault_class` compared against another blank would read as *the arms agree*, which
    is the pilot's outcome reported from an absence of evidence."""
    assert depthpilot.verdict_from_artifact({}, CHANGE_ARM) is None
    assert depthpilot.verdict_from_artifact({"trajectory_id": "t"}, CHANGE_ARM) is None
    assert (
        depthpilot.verdict_from_artifact({"verdict": {"fault_class": "bad_deploy"}}, CHANGE_ARM)
        is None
    )


def test_an_abstention_is_still_a_verdict() -> None:
    """ADR-0022 §1.2: an abstention is an outcome, not an absence. The dry run's one completed arm
    abstained on the proposal and still returned a fault class, and a pilot that discarded it would
    be dropping the answer it exists to compare."""
    payload = {
        "trajectory_id": "t1",
        "verdict": {"fault_class": "resource_exhaustion", "remediation_class": "none"},
    }

    verdict = depthpilot.verdict_from_artifact(payload, BASELINE_ARM)

    assert verdict is not None
    assert verdict.remediation_class == "none"


# --- the settle window between pairs ------------------------------------------------------------


def test_the_pilot_settles_between_pairs_but_not_before_the_first() -> None:
    """**The gap the dry run exposed at $0.**

    Every pair leaves a resolved incident, and a firing inside the orchestrator's 300s window
    reopens it rather than opening a new one - so the next pair's alerts are attributed to the
    previous scenario and the gate refuses. Without this the ten-pair run completes pair one,
    refuses pairs two through ten, and reports `n = 1` for $1.20.

    The gate's own refusal is what made it visible: *"Wait 141s."* `sweep.py` carries the same
    constant for the same reason, and this mirrors it rather than inventing a second number.

    No wait before the first pair: there is nothing to settle from.
    """
    steps = _Steps()
    naps: list[int] = []

    run_pilot(steps, ("a", "b", "c"), settle=300, sleeper=naps.append)

    assert naps == [300, 300], "between pairs, not before the first"


def test_settle_defaults_off_so_a_test_cannot_nap_for_twenty_minutes() -> None:
    """`sweep.py`'s lesson, inherited rather than relearned: *"the first version defaulted without
    a sleeper and tried to nap for twenty minutes."* Waiting is a property of running the pilot,
    not of the function, and a default that sleeps is one nobody can call in a test without knowing
    to disarm it. The CLI passes `SETTLE_SECONDS`."""
    steps = _Steps()
    naps: list[int] = []

    run_pilot(steps, ("a", "b"), sleeper=naps.append)

    assert naps == []
    assert depthpilot.SETTLE_SECONDS == 300
