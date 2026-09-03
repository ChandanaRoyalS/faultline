"""Top-3 accuracy and the culprit-service axis (T4.2).

T4.2 asks for *"root-cause top-1 and top-3 accuracy (LLM judge, semantic equivalence)"*. Top-1
existed; top-3 did not, and **could not be computed from stored trajectories** - a verdict
carrying one root cause can only be scored top-1, and a hypothesis the synthesizer weighed and
set aside leaves no record unless it is asked for. So `Verdict` grew `alternatives`, which moved
the stamp.

It grew `service` in the same move, because top-3 over four fault classes is near 75% by chance
and worth almost nothing. Over thirteen services it is a real claim. Reaching for the second
axis is what exposed the first gap: **the scorer graded triage recall/precision, `fault_class`
and `remediation_class` and nothing else**, so *which service broke* had never been scored, on a
benchmark whose whole subject is finding out which service broke.
"""

from __future__ import annotations

from evalharness.run import culprit_service
from evalharness.scoring import RankedScore, score_ranked


def verdict(service: str, *alternatives: str, fault_class: str = "bad_config") -> dict:
    return {
        "service": service,
        "fault_class": fault_class,
        "alternatives": [
            {"service": name, "fault_class": "bad_deploy", "why_not": "weaker"}
            for name in alternatives
        ],
    }


# --- the ranking is the model's, and the scorer does not improve on it -----------------------


def test_the_verdicts_own_answer_is_rank_one() -> None:
    scored = score_ranked("cartservice", verdict("cartservice", "frontend"), "service")

    assert scored.ranked[0] == "cartservice"
    assert scored.top_1 is True


def test_the_order_is_taken_from_the_model_and_never_re_sorted() -> None:
    """A scorer that reordered the candidates would be scoring its own ranking of the model's
    candidates, which measures the scorer."""
    scored = score_ranked(
        "adservice", verdict("frontend", "checkoutservice", "adservice"), "service"
    )

    assert scored.ranked == ("frontend", "checkoutservice", "adservice")
    assert scored.top_1 is False
    assert scored.top_3 is True


def test_a_repeated_candidate_does_not_buy_a_second_chance() -> None:
    """**The cheapest way to inflate top-3 is to restate top-1.** Keeping the earliest position
    and dropping the repeat means an arm has to offer three *different* answers to be scored over
    three."""
    scored = score_ranked("adservice", verdict("frontend", "frontend", "frontend"), "service")

    assert scored.ranked == ("frontend",)
    assert scored.depth == 1
    assert scored.top_3 is False


def test_empty_and_blank_candidates_are_dropped_rather_than_ranked() -> None:
    payload = {
        "service": "frontend",
        "alternatives": [{"service": ""}, {"service": "   "}, {"service": "adservice"}],
    }

    assert score_ranked("adservice", payload, "service").ranked == ("frontend", "adservice")


def test_only_the_first_three_count_however_many_are_offered() -> None:
    """The contract caps `alternatives` at two by instruction rather than by schema, so a model
    that returns five must not be scored over five."""
    scored = score_ranked("e", verdict("a", "b", "c", "d", "e"), "service")

    assert scored.top_3 is False, "the truth is at rank 5"
    assert scored.depth == 5, "depth still reports what was offered"


# --- depth is what stops top-3 being top-1 under another name --------------------------------


def test_an_arm_that_never_ranks_has_depth_one_and_top_3_equals_top_1() -> None:
    """**The reading error this figure invites.** An arm whose verdicts carry no alternatives
    scores top-3 exactly equal to top-1, which looks like a tie with a ranking arm and is not
    one. `depth` is a property of the arm and travels with the figure."""
    scored = score_ranked("cartservice", verdict("cartservice"), "service")

    assert scored.depth == 1
    assert scored.top_1 is True and scored.top_3 is True
    assert scored.gained_by_ranking is False


def test_gained_by_ranking_is_the_only_thing_top_3_measures_beyond_top_1() -> None:
    """A top-3 figure where this is never true is reporting top-1 under another name, and saying
    so is cheaper than letting a reader work it out."""
    gained = score_ranked("adservice", verdict("frontend", "adservice"), "service")
    did_not = score_ranked("frontend", verdict("frontend", "adservice"), "service")

    assert gained.gained_by_ranking is True
    assert did_not.gained_by_ranking is False


def test_an_empty_alternatives_list_is_a_legal_answer_not_a_missing_field() -> None:
    """An incident whose evidence admits one explanation should say so. A synthesizer that always
    produces two runners-up is padding, and padding would inflate top-3 without representing any
    reasoning."""
    scored = score_ranked("frontend", {"service": "frontend", "alternatives": []}, "service")

    assert scored.depth == 1
    assert scored.as_dict()["depth"] == 1


def test_an_also_correct_answer_counts_at_whatever_rank_it_appears() -> None:
    """ADR-0027's two-right-remediations case, applied to a ranked list: grading on which of two
    measured-correct answers an arm happened to rank first would be grading on taste."""
    scored = RankedScore(
        truth="config_revert",
        ranked=("rollback", "restart"),
        also_correct=frozenset({"restart"}),
    )

    assert scored.top_1 is False
    assert scored.top_3 is True


# --- the culprit-service axis ----------------------------------------------------------------


def test_the_culprit_is_read_from_the_scenario_and_canonicalised() -> None:
    """**The identity step is load-bearing, not tidy.** The scenario names a compose service
    (`ad-service`) and the agent names an OTel `service.name` (`adservice`). ADR-0017 makes those
    one identity; comparing the raw strings would score every correct answer wrong.
    """
    assert culprit_service("ad-memory-squeeze") == "adservice"
    assert culprit_service("cart-redis-misconfig") == "cartservice"


def test_an_unknown_scenario_yields_no_culprit_rather_than_a_guess() -> None:
    assert culprit_service("no-such-scenario") == ""


def test_every_catalog_scenario_has_a_resolvable_culprit() -> None:
    """**Run against the real catalog**, because a new axis that silently scores half the
    scenarios against an empty string would report a uniform failure as a measurement."""
    from pathlib import Path

    scenarios = sorted(p.stem for p in Path("evals/scenarios").glob("*.yaml"))
    assert len(scenarios) >= 18, "the catalog"

    unresolved = [name for name in scenarios if not culprit_service(name)]
    assert unresolved == [], f"no culprit service resolves for: {unresolved}"


# --- the contract carries what the scoring needs ---------------------------------------------


def test_the_verdict_contract_carries_the_two_new_fields() -> None:
    from faultline.agents.contracts import Verdict

    fields = set(Verdict.model_fields)

    assert {"service", "alternatives"} <= fields


def test_a_verdict_recorded_before_the_fields_existed_still_validates() -> None:
    """Both default, so no stored artifact becomes unreadable. A run that predates the field was
    never asked, and the scorer records `None` rather than scoring it wrong."""
    from faultline.agents.contracts import Verdict

    old = Verdict(
        root_cause="r",
        fault_class="bad_config",
        remediation_class="config_revert",
        confidence="low",
        evidence=[],
        reasoning="r",
        open_questions=[],
    )

    assert old.service == ""
    assert old.alternatives == []


def test_a_candidate_must_say_what_demotes_it() -> None:
    """**The field that makes the list worth having.** Three plausible causes cost nothing to
    emit and would inflate top-3 without representing reasoning. Making the model say what
    demotes each one is the cheapest available check that a ranking is a ranking."""
    import pytest
    from pydantic import ValidationError

    from faultline.agents.contracts import Candidate

    with pytest.raises(ValidationError):
        Candidate(root_cause="r", service="s", fault_class="bad_config")  # type: ignore[call-arg]


def test_the_nested_candidate_schema_is_covered_by_the_agents_digest() -> None:
    """`Candidate` is not listed in `stamp._CONTRACTS` and does not need to be: it reaches the
    digest through `Verdict.model_json_schema()`'s `$defs`. Asserted rather than assumed, because
    a schema the model is held to and the stamp does not cover is exactly the `TriageJudgement`
    defect Batch C fixed."""
    import json

    from faultline.agents.contracts import Verdict

    schema = json.dumps(Verdict.model_json_schema())

    assert "Candidate" in schema
    assert "why_not" in schema
