"""The deterministic scorer, pinned against the five stored verdicts (T4.1, ADR-0022).

**The fixtures are real.** Every verdict below was produced by a live investigation and is
recorded in `docs/evidence/`; every expected score is hand-derivable from the bundle beside it.
A scorer tested only against invented inputs is a scorer nobody has checked against the thing it
will actually be pointed at.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evalharness.scoring import (
    CLASS_DISPUTES,
    Categories,
    ScoredRun,
    dispute_for,
    score_label,
    score_triage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def bundle(scenario_id: str, split: str = "dev") -> dict:
    path = REPO_ROOT / "evals/scenarios/artifacts" / split / scenario_id / "manifest.json"
    return json.loads(path.read_text())


# --- the stored verdicts, as fixtures ------------------------------------------
#
# scenario, trajectory, fault_class, remediation_class, evidence README.
STORED = [
    ("shipping-wrong-image", "4e42184d", "unknown", "none", "t3.4-first-investigation"),
    ("shipping-wrong-image", "e7739dec", "bad_deploy", "rollback", "t3.4-first-investigation"),
    ("shipping-wrong-image", "6b9715de", "unknown", "none", "t3.4b-rerun"),
    ("shipping-wrong-image", "f7afdb76", "bad_deploy", "rollback", "t3.4c-rerun"),
    ("cart-dependency-latency", "68ac9a67", "bad_config", "config_revert", "t3.5-runner-smoke"),
]


@pytest.mark.parametrize(("scenario", "trajectory", "fault", "fix", "_evidence"), STORED)
def test_every_stored_verdict_scores_the_way_it_reads(
    scenario: str, trajectory: str, fault: str, fix: str, _evidence: str
) -> None:
    """Hand-derived: two shipping runs are right, two abstained, and the cart run is the
    disputed miss ADR-0022 §1.2 resolved."""
    truth = bundle(scenario)
    fault_score = score_label(scenario, truth["fault_class"], fault)
    fix_score = score_label(scenario, truth["expected_remediation_class"], fix)

    if fault == "unknown":
        assert fault_score.abstained and fix_score.abstained
        assert not fault_score.counts_toward_accuracy, "an abstention leaves the ratio entirely"
        assert not fault_score.correct
    elif scenario == "shipping-wrong-image":
        assert fault_score.correct and fix_score.correct
    else:
        assert not fault_score.correct and not fix_score.correct
        assert fault_score.dispute is not None, "the boundary ADR-0022 named"


def test_the_five_stored_verdicts_give_two_correct_two_abstentions_and_one_disputed_miss() -> None:
    """The whole set at once, because the shape is what a rate would be computed from - and it
    is a shape nobody should compute a rate from: four of the five are one scenario."""
    scores = [
        score_label(scenario, bundle(scenario)["fault_class"], fault)
        for scenario, _t, fault, _f, _e in STORED
    ]
    assert sum(s.correct for s in scores) == 2
    assert sum(s.abstained for s in scores) == 2
    assert sum(s.dispute is not None for s in scores) == 1
    assert sum(s.counts_toward_accuracy for s in scores) == 3, "abstentions are out of the ratio"

    scenarios = {scenario for scenario, *_ in STORED}
    assert len(scenarios) == 2, "five verdicts over two scenarios - not a benchmark yet"


def test_an_abstention_is_not_counted_as_wrong() -> None:
    """The position ADR-0022 §1.2 takes, at its sharpest: `unknown` and a confident wrong
    answer must not be the same number."""
    abstained = score_label("shipping-wrong-image", "bad_deploy", "unknown")
    wrong = score_label("shipping-wrong-image", "bad_deploy", "bad_config")

    assert abstained.abstained and not abstained.correct
    assert not wrong.abstained and not wrong.correct
    assert abstained.counts_toward_accuracy is False
    assert wrong.counts_toward_accuracy is True


def test_none_is_read_as_abstention_for_the_class_of_fix() -> None:
    """`remediation_class: none` is what the synthesizer pairs with `fault_class: unknown`."""
    assert score_label("x", "rollback", "none").abstained
    assert score_label("x", "rollback", None).abstained


# --- the dispute register ------------------------------------------------------


def test_the_dispute_register_is_enumerated_not_inferred() -> None:
    """A scorer that decided for itself which misses were nearly right would be grading on
    sympathy. Every entry names the ADR section that resolved it."""
    assert CLASS_DISPUTES
    for entry in CLASS_DISPUTES:
        assert entry.resolved_by.startswith("ADR-")
        assert entry.why


def test_the_disputed_miss_is_still_a_miss() -> None:
    """ADR-0022 resolved the boundary against the agent's reading. Naming it is not excusing
    it - it is counted wrong and reported under its own line."""
    score = score_label("cart-dependency-latency", "dependency_latency", "bad_config")
    assert not score.correct
    assert score.counts_toward_accuracy
    assert score.dispute is not None


def test_a_dispute_only_applies_to_the_pair_it_was_written_for() -> None:
    """The register is keyed on (scenario, truth, returned). The same wrong class on a
    different scenario is an ordinary miss."""
    assert dispute_for("cart-dependency-latency", "dependency_latency", "bad_config") is not None
    assert dispute_for("shipping-wrong-image", "bad_deploy", "bad_config") is None
    assert dispute_for("cart-dependency-latency", "dependency_latency", "unknown") is None


# --- triage --------------------------------------------------------------------


def test_a_purely_recovery_phase_alert_is_still_excluded() -> None:
    """ADR-0009: "the blast radius blames the fault for damage the fix did". A service whose
    only alert began after the revert is not part of the fault's damage and stays out."""
    alerts = [
        {"service": "cartservice", "began_after_revert": False},
        {"service": "emailservice", "began_after_revert": True},
    ]

    score = score_triage({"cartservice"}, alerts, unmeasured_edges=0)

    assert score.alerted == frozenset({"cartservice"})
    assert score.excluded_after_revert == frozenset({"emailservice"})
    assert "emailservice" not in score.missed, "not a recall miss - not the fault's damage"


def test_a_service_that_alerts_during_and_after_stays_in_the_blast_radius() -> None:
    """The case T7.3 fixed, taken from a committed recording rather than invented.

    `product-catalog-flag-failure` has `frontend` alerting during the fault and again in
    recovery. The exclusion is per **episode**: the recovery alert is dropped, and the fault's
    own alert keeps the service in the radius.

    The old code computed `alerted - after` over service names, which removed the service
    entirely and understated the radius - blaming the fault for *less* than it did, which is
    the mirror of the error ADR-0009 was guarding against.

    The historical case is the same shape on a different service: `cart-redis-misconfig`'s
    pre-T7.1 recording, archived at `superseded/20260824T044427Z/`, has `emailservice` raising
    `ServiceNoTraffic` while the fault is live and `ServiceHighErrorRate` during recovery. That
    shape is behind 18 of the 24 re-scored runs, and it is not the fixture here only because
    the live recording no longer contains it.
    """
    truth = bundle("product-catalog-flag-failure")
    during = {a["service"] for a in truth["alerts_over_window"] if not a.get("began_after_revert")}
    after = {a["service"] for a in truth["alerts_over_window"] if a.get("began_after_revert")}
    assert during & after == {"frontend"}, "the committed recording this test is written against"

    score = score_triage({"productcatalogservice"}, truth["alerts_over_window"], unmeasured_edges=1)

    assert "frontend" in score.alerted, "kept on the strength of its during-fault alert"
    assert score.excluded_after_revert == frozenset(), "not excluded, so not listed"
    assert "frontend" in score.missed, "alerted and not predicted - a real recall miss"
    assert score.recall == 1 / 3, "three services alerted during the fault; one was predicted"


def test_the_exclusion_cannot_go_back_to_being_per_service() -> None:
    """A regression guard with the defect written into it.

    Per-service exclusion and per-episode exclusion agree on every input where no service has
    both kinds of alert, which is why this went unnoticed: it is only distinguishable on the
    overlapping case. So the guard is that case, asserted against what the old expression
    would have produced.
    """
    alerts = [
        {"service": "frontend", "began_after_revert": False},
        {"service": "frontend", "began_after_revert": True},
    ]

    score = score_triage({"frontend"}, alerts, unmeasured_edges=0)

    during = {a["service"] for a in alerts if not a.get("began_after_revert")}
    after = {a["service"] for a in alerts if a.get("began_after_revert")}
    assert during - after == frozenset(), "what the old code computed: the service vanishes"
    assert score.alerted == frozenset({"frontend"}), "what the fix computes: it stays"
    assert score.recall == 1.0 and score.precision == 1.0


def test_recall_and_precision_are_both_reported_and_neither_is_combined() -> None:
    """The T3.5 shape: twelve predicted, four alerted, all four matched. Perfect recall and
    a precision of a third - two facts an F-score would blur into one."""
    truth = bundle("cart-dependency-latency")
    predicted = {
        "cartservice",
        "checkoutservice",
        "frontend",
        "loadgenerator",
        "adservice",
        "currencyservice",
        "paymentservice",
        "productcatalogservice",
        "recommendationservice",
        "emailservice",
        "shippingservice",
        "quoteservice",
    }
    score = score_triage(predicted, truth["alerts_over_window"], unmeasured_edges=4)

    assert score.recall == 1.0
    assert score.precision == pytest.approx(4 / 12)
    assert score.missed == frozenset()
    assert len(score.extra) == 8
    assert score.unmeasured_edges == 4
    assert not hasattr(score, "f1"), "there is deliberately no combined figure"


def test_a_miss_is_reported_as_the_number_adr_0017_asked_for() -> None:
    """ "A directed 2-hop traversal that under-reaches shows up there as a recall miss on
    services that alerted and were not predicted." That is this field."""
    truth = bundle("cart-dependency-latency")
    score = score_triage({"cartservice"}, truth["alerts_over_window"], unmeasured_edges=0)

    assert score.missed == frozenset({"checkoutservice", "frontend", "loadgenerator"})
    assert score.recall == pytest.approx(0.25)


def test_an_empty_prediction_gives_no_precision_rather_than_zero() -> None:
    """0/0 is not 0. A run that predicted nothing has no precision to report, and printing
    0.00 would assert something the data does not support."""
    truth = bundle("cart-dependency-latency")
    score = score_triage(set(), truth["alerts_over_window"], unmeasured_edges=0)
    assert score.precision is None
    assert score.recall == 0.0


# --- the categories held out ---------------------------------------------------


def test_zero_observation_categories_are_printed_at_zero() -> None:
    """ADR-0022 §2: "a rate that only appears once it is non-zero is a rate nobody
    calibrated". `failed_alone` has had zero observations across every stored trajectory."""
    report = ScoredRun("r", "s", "t", categories=Categories()).report()
    assert "specialists failed alone 0" in report
    assert "flagged verdicts        0" in report
    assert "contradiction firings   0" in report
    assert "budget exhausted        no" in report
    assert "narrative refused       no" in report


# Verbatim from run 3's verdict artifact.
RUN3_REFUSAL = (
    "the narrative mentions ['fault']. This text becomes corpus material at T2.4b, so it is "
    "written from the responder's chair - what was visible, not what we know because we "
    "caused it (ADR-0020 section 4, evals/scenarios/ARTIFACTS.md)."
)


def test_a_refused_narrative_is_reported_and_says_the_judge_has_nothing_to_score() -> None:
    """**The fifth category, added at T4.2.** Run 3 produced a correct verdict, exited 0, and
    wrote no narrative - and the scored report said nothing about it. T4.2's judge scores
    narratives; a report that is silent about there being none turns a fact about the run into
    what looks like a gap in the judging."""
    categories = Categories(narrative_refused=RUN3_REFUSAL)
    report = ScoredRun("r", "s", "t", categories=categories).report()

    assert "narrative refused       yes" in report
    assert "nothing to score" in report
    assert categories.as_dict()["narrative_refused"] is True
    assert categories.as_dict()["narrative_refused_reason"] == RUN3_REFUSAL


def test_a_refused_narrative_is_not_averaged_into_anything() -> None:
    """Like the other four: reported beside the headline, never subtracted from it. A run whose
    narrative was refused still has a verdict, and that verdict still scores."""
    scored = ScoredRun(
        "r",
        "cart-redis-misconfig",
        "t",
        fault_class=score_label("cart-redis-misconfig", "bad_config", "bad_config"),
        categories=Categories(narrative_refused=RUN3_REFUSAL),
    )
    assert scored.fault_class is not None and scored.fault_class.correct
    assert scored.reached_a_class
    assert scored.as_dict()["categories"]["narrative_refused"] is True


def test_the_contradiction_ledger_says_the_check_is_retired() -> None:
    """**Retired at T4.3** on a ledger of 0 true positives and 4 false positives. A non-zero
    count can now only come from a run recorded before the retirement, and the report has to say
    so - otherwise an old firing reads as live evidence about the agent."""
    categories = Categories(contradictions=("contradiction: metrics was not queried",))
    report = ScoredRun("r", "s", "t", categories=categories).report()
    assert "RETIRED at T4.3" in report
    assert "0 true positives and 4 false positives" in report


def test_a_run_with_no_firings_says_the_check_is_retired_rather_than_nothing() -> None:
    """Going forward the count is always zero, and a bare zero would read as "the check looked
    and found nothing" rather than "the check is gone"."""
    report = ScoredRun("r", "s", "t", categories=Categories()).report()
    assert "contradiction firings   0 (check retired)" in report


def test_budget_exhaustion_names_the_bound_that_bit() -> None:
    """ "metrics tool calls: 2 of 2 used" - which bound is the actionable part, and a boolean
    discards it. Taken from trajectory 4e42184d."""
    categories = Categories(
        budget_exhausted_reason="budget exhausted: metrics tool calls: 2 of 2 used"
    )
    assert "2 of 2 used" in ScoredRun("r", "s", "t", categories=categories).report()


def test_the_report_says_n_equals_one() -> None:
    """CLAUDE.md rule 6 travels with the number, not with the reader's memory."""
    assert "n=1" in ScoredRun("r", "s", "t").report()


def test_the_four_categories_are_disjoint() -> None:
    """A run whose budget was exhausted has one flag, and it belongs to exactly one category.
    Leaving it in `flagged` as well counted `ad-memory-squeeze` twice in the first sweep's
    totals, which is the failure mode "reported separately" exists to prevent."""
    from evalharness.run import score

    artifact = {
        "trajectory_id": "t",
        "blast_radius": ["adservice"],
        "unmeasured_edges": 1,
        "verdict": {"fault_class": "bad_config", "remediation_class": "config_revert"},
        "flags": ["budget exhausted: changes tool calls: 4 of 4 used"],
        "failed_dispatches": [],
    }
    scored = score("r", "ad-memory-squeeze", bundle("ad-memory-squeeze"), artifact, {}, {})
    cats = scored.categories

    assert cats.budget_exhausted_reason is not None
    assert cats.flagged == (), "the budget flag is not also an unattributed flag"
    assert (
        len(cats.flagged) + len(cats.contradictions) + (1 if cats.budget_exhausted_reason else 0)
        == 1
    )


def test_the_budget_travels_with_the_figure_and_not_inside_the_stamp() -> None:
    """**Budget bounds are experiment parameters the stamp does not cover** (T4.7).

    The stamp answers "which agent is this" - the prompts it was given, the contracts it was
    held to. The budget answers "how much was it allowed to spend". Both matter and they are
    different questions: T4.7 exists to compare *the same agent* under different bounds, and
    folding the budget into the stamp would make that comparison unexpressible and orphan every
    figure recorded before it. So it rides beside the stamp, in the manifest and in the report.
    """
    bounds = {
        "max_tool_calls_per_specialist": 4,
        "per_specialist_tool_calls": {"changes": 8},
        "max_tokens": 120_000,
        "wall_clock_seconds": 600,
        "max_dispatch_rounds": 2,
    }
    scored = ScoredRun("r", "s", "t", runtime_version="faultline/0.0.1+prompts:x", budget=bounds)

    assert scored.as_dict()["budget"] == bounds, "all four bounds, not the two a CLI takes"
    report = scored.report()
    assert "BUDGET" in report and "'changes': 8" in report
    assert "prompts:x" in report, "and the stamp is still there, beside it"


# --- reachability is reported and never acted on (T7.5) -----------------------


def _scored(reachability: dict[str, object]) -> ScoredRun:
    """One run, identical in every way except what its target could have answered."""
    return ScoredRun(
        run_id="r",
        scenario_id="s",
        trajectory_id="t",
        triage=score_triage(
            {"cartservice"},
            [{"service": "cartservice", "began_after_revert": False}],
            unmeasured_edges=0,
        ),
        fault_class=score_label("s", "bad_config", "unknown"),
        fix_class=score_label("s", "config_revert", "none"),
        reachability=reachability,
    )


def test_reachability_changes_no_figure_at_all() -> None:
    """The whole point of recording it rather than acting on it.

    An abstention on a scenario whose target can answer nothing is a different event from one
    where the evidence was there, and a reader should see which. But nothing is forgiven: two
    runs with the same verdict and different reachability score identically, to the byte.
    """
    blind = _scored({"answers_idle_or_absent": [], "none_can_answer": True, "target_log_lines": 0})
    sighted = _scored({"answers_idle_or_absent": ["runtime", "logs"], "none_can_answer": False})

    for field_name in ("triage", "fault_class", "fix_class"):
        assert getattr(blind, field_name).as_dict() == getattr(sighted, field_name).as_dict()
    assert blind.reached_a_class == sighted.reached_a_class, "coverage is untouched"
    assert blind.fault_class.abstained and sighted.fault_class.abstained

    scores = [
        {k: v for k, v in run.as_dict().items() if k != "reachability"} for run in (blind, sighted)
    ]
    assert scores[0] == scores[1], "every scored field but reachability itself is identical"


def test_a_zero_class_scenario_says_so_in_its_report_without_excusing_itself() -> None:
    """Visible, and explicitly not a mitigation."""
    report = _scored(
        {"answers_idle_or_absent": [], "none_can_answer": True, "target_log_lines": 0}
    ).report()

    assert "NO evidence class can answer" in report
    assert "still counts exactly as one" in report, "the report refuses to soften the result"
    assert "ABSTAINED (excluded from accuracy; counted in coverage)" in report


def test_a_scenario_with_classes_available_lists_them() -> None:
    report = _scored(
        {"answers_idle_or_absent": ["runtime", "logs"], "none_can_answer": False}
    ).report()

    assert "reachability answerable by: runtime, logs" in report
    assert "NO evidence class" not in report
