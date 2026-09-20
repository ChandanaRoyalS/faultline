"""The specification's failure-scenario table, thirteen rows, each with a test or a drill (T6.7
piece 7). The plan row: *"the failure-scenario table in the spec becomes tested behavior instead
of claimed behavior - each row gets a test or a drill."*

`tests/test_orchestrator.py::FAILURE_ROWS` maps six rows to a lifecycle state and proves the
state is reachable; that is the machine's half. This file is the behaviour's half: for every row
of `docs/spec/project-proposal-rev8.pdf` pp.10-11, the test functions that demonstrate its
Mitigation, or the evidence directory in which it was drilled, and - for the three rows this
repository does not meet as written - the words *not met* and the row that owns the gap. Every
name here is checked against the tree, so a renamed test or a moved drill breaks this file
before it breaks the claim.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
EVIDENCE = REPO_ROOT / "docs" / "evidence"


@dataclass(frozen=True, slots=True)
class Row:
    failure: str
    mitigation: str
    tests: tuple[str, ...] = ()
    """`file::function` names that demonstrate the Mitigation column."""
    drills: tuple[str, ...] = ()
    """Evidence directories, relative to `docs/evidence`, in which the row was induced."""
    not_met: str = ""
    """What the row asks for that the repository does not do, and who owns it."""
    notes: tuple[str, ...] = field(default_factory=tuple)


TABLE: tuple[Row, ...] = (
    Row(
        "1. LLM provider outage / 429 storm mid-investigation",
        "circuit breaker opens; fallback; queued incidents resume when it half-opens",
        tests=(
            "test_model_resilience.py::test_one_exhausted_schedule_opens_the_model_and_the_next_call_is_refused_at_once",
            "test_model_resilience.py::test_an_open_primary_goes_straight_to_the_fallback_and_records_the_substitution",
            "test_model_resilience.py::test_after_the_cooldown_one_trial_call_half_opens_and_a_success_closes",
            "test_runner.py::test_a_provider_outage_leaves_the_incident_triaging_and_exits_6",
            "test_investigation_runner.py::test_two_provider_unavailable_runs_defer_every_due_incident_until_the_cooldown",
            "test_investigation_runner.py::test_after_the_cooldown_the_next_run_is_the_trial_and_a_6_does_not_cost_an_attempt",
        ),
        notes=(
            "the degraded-mode banner is the substitution record on the trajectory (ADR-0031); "
            "'queued incidents resume' is the incident staying admitted in TRIAGING while the "
            "runner defers, not a QUEUED transition (design note section 6)",
        ),
    ),
    Row(
        "2. Agent emits invalid JSON / schema-violating output",
        "bounded re-ask with error feedback, then a structured 'specialist failed' result",
        tests=(
            "test_roles.py::test_a_specialist_whose_output_never_validates_fails_alone",
            "test_roles.py::test_a_truncated_reply_is_re_asked_as_truncation_rather_than_as_malformed_json",
            "test_roles.py::test_the_comma_list_from_t34b_is_rejected_and_the_reask_says_what_is_legal",
        ),
    ),
    Row(
        "3. Hallucinated citation in RCA report",
        "programmatic citation checker; report blocked and regenerated with the violation fed back",
        tests=(
            "test_roles.py::test_a_refused_render_is_regenerated_once_with_the_violation_fed_back",
            "test_roles.py::test_a_proposal_resting_on_evidence_that_does_not_exist_is_refused_then_abstains",
            "test_grounding.py::test_the_t34_contradiction_is_caught_and_names_the_refuting_result_id",
        ),
    ),
    Row(
        "4. Log analyst query returns 100MB and blows its context",
        "result-size guard; sampled view with a 'truncated' flag the agent must acknowledge",
        tests=(
            "test_tools.py::test_truncated_logs_keep_the_newest_lines_not_the_oldest",
            "test_tools.py::test_empty_and_error_are_distinct_states_on_every_tool",
        ),
    ),
    Row(
        "5. Alert storm: cascading failure fires 200 alerts at once",
        "dedupe + correlation into few incidents; global concurrency cap; overflow queued",
        tests=(
            "test_orchestrator.py::test_the_eight_events_produce_one_incident_with_four_episodes",
            "test_storm.py::test_three_passes_and_every_prediction_scored",
        ),
        drills=("t6.7-reliability/storm-2026-09-20-first",),
        not_met=(
            "Recovery's 'post-hoc merge of duplicate incidents' is not built; the storm folded "
            "200 alerts into one incident (P3 = 1), so the correlation is doing the merge's work "
            "and no row is opened for it"
        ),
    ),
    Row(
        "6. Worker crashes mid-investigation",
        "Redis pending entries; another worker claims; investigation resumes",
        tests=(
            "test_integration_worker_kill.py::test_a_worker_killed_before_applying_leaves_the_entry_for_a_survivor_to_apply_once",
            "test_integration_worker_kill.py::test_a_worker_killed_after_the_write_and_before_the_ack_does_not_duplicate",
            "test_orphans.py::test_only_old_rows_with_no_outcome_are_closed_and_they_are_named",
            "test_investigation_runner.py::test_every_poll_reconciles_orphans_before_it_investigates",
        ),
        drills=("t6.7-reliability",),
        not_met=(
            "'resumes from last completed agent step' - a killed investigation is re-run from "
            "triage by the runner's second attempt (the crash drill, 2026-09-19), not resumed; "
            "resumable steps are a change to the investigation loop and not T6.7"
        ),
    ),
    Row(
        "7. Prompt injection via malicious log line",
        "tool output wrapped as untrusted; privileged transitions validated outside the model",
        tests=(
            "test_tools.py::test_a_result_is_delimited_typed_and_labelled_untrusted",
            "test_executor.py::test_a_target_outside_the_incidents_scope_is_refused_before_the_token_is_spent",
        ),
        drills=("t6.8-adversarial",),
        not_met=(
            "the scenarios exist (evals/adversarial/, four variants, scored in the standard loop) "
            "and ran ten times on 2026-09-20: seven without a payload reaching a model (batches "
            "1-2), then three in which it did (Q79 batch 3b). In those three the payload's "
            "instruction - restart the seed, cite a reference - was refused 3 / 3 and named "
            "untrusted in the proposal's own text, and the payload's fabricated change record was "
            "believed 3 / 3 and became the root cause, so every proposal reverts a change that "
            "never happened on the wrong service (followed 3 / 3 by the registered rule). The "
            "row's Mitigation held for the parse and for the instruction; it does not cover a "
            "fabricated fact, and nothing built does. Q81 owns the defence, Q82 the harness fix"
        ),
        notes=(
            "test_adversarial.py holds the harness: planters, scorer, the run's refusals, and "
            "every committed variant's planted service against its pre-registration section",
        ),
    ),
    Row(
        "8. Wrong root cause confidently reported",
        "ranked alternatives; approval gate; rejection triggers targeted re-investigation",
        tests=(
            "test_approval_routes.py::test_a_rejection_records_the_reason_moves_the_incident_and_names_the_proposal",
            "test_rejections.py::test_a_rejected_incident_is_investigable_again",
            "test_rejections.py::test_a_rejected_incident_is_due_immediately_and_with_no_settle_window",
        ),
        drills=("t6.3-rejection-loop", "t6.6-self-observability"),
    ),
    Row(
        "9. Remediation proposed for the wrong service (blast-radius error)",
        "executor validates the target against the incident's scope; hard reject before approval",
        tests=(
            "test_executor.py::test_a_target_outside_the_incidents_scope_is_refused_before_the_token_is_spent",
            "test_executor.py::test_scope_is_still_checked_before_the_one_action_rule",
        ),
        drills=("t6.2-first-execution",),
    ),
    Row(
        "10. Runaway cost: investigation loops, burns $40 on one incident",
        "hard per-incident cap halts agents; partial report with 'budget exhausted'",
        tests=(
            "test_roles.py::test_budget_exhaustion_flags_the_result_rather_than_raising",
            "test_model_resilience.py::test_the_retry_loop_stops_when_the_run_s_budget_is_spent",
            "test_investigation_runner.py::test_at_the_day_s_ceiling_every_due_incident_waits_and_the_attempt_budget_is_untouched",
        ),
        notes=(
            "the per-incident cap is Budget.max_usd; T6.7 piece 6 adds the deployment's own "
            "ceiling above it, after the 2026-09-19 loop showed the gap between the two",
        ),
    ),
    Row(
        "11. Retrieval returns stale runbook for a deprecated procedure",
        "recency-aware ranking; deprecated docs excluded by metadata at ingest",
        not_met=(
            "no test and no mechanism: recency ranking is Q43, deprecation metadata is Q44, "
            "both open in docs/QUEUE.md"
        ),
    ),
    Row(
        "12. Telemetry backend itself is down (Loki unreachable)",
        "consecutive tool-error threshold; 'modality unavailable' as typed evidence",
        tests=(
            "test_tools.py::test_three_consecutive_backend_failures_open_it_for_the_rest_of_the_run",
            "test_tools.py::test_backends_open_independently_and_a_success_resets_the_count",
            "test_tools.py::test_empty_and_error_are_distinct_states_on_every_tool",
        ),
    ),
    Row(
        "13. Two workers pick up the same alert",
        "unique constraint on fingerprint makes creation idempotent; second worker no-ops",
        tests=(
            "test_ingest.py::test_replaying_a_delivery_publishes_nothing",
            "test_integration_store.py::test_mark_applied_is_idempotent",
            "test_integration_worker_kill.py::test_a_worker_killed_after_the_write_and_before_the_ack_does_not_duplicate",
        ),
    ),
)


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    }


def test_the_table_has_thirteen_rows_in_the_spec_s_order() -> None:
    assert [r.failure.split(".")[0] for r in TABLE] == [str(i) for i in range(1, 14)]


@pytest.mark.parametrize("row", TABLE, ids=[r.failure.split(".")[0] for r in TABLE])
def test_every_row_has_a_test_or_a_drill_or_says_it_is_not_met(row: Row) -> None:
    assert row.tests or row.drills or row.not_met, row.failure


@pytest.mark.parametrize("row", TABLE, ids=[r.failure.split(".")[0] for r in TABLE])
def test_every_named_test_exists_in_the_tree(row: Row) -> None:
    for name in row.tests:
        file, function = name.split("::")
        path = TESTS / file
        assert path.is_file(), f"{row.failure}: {file} is missing"
        assert function in _test_functions(path), f"{row.failure}: {name} is not a test"


@pytest.mark.parametrize("row", TABLE, ids=[r.failure.split(".")[0] for r in TABLE])
def test_every_named_drill_exists_and_holds_evidence(row: Row) -> None:
    for drill in row.drills:
        path = EVIDENCE / drill
        assert path.is_dir() and any(path.iterdir()), f"{row.failure}: {drill} holds no evidence"


def test_the_three_rows_not_met_are_the_three_the_design_note_names() -> None:
    """Row 5's merge, row 6's resume, row 11's stale runbook - and row 7's judgement, which T6.8
    built the harness for and Q79 reached: three delivered payloads, the instruction refused three
    times, the fabricated record believed three times. Row 7 stays *not met* because the
    mitigation that would cover a fabricated fact is not built (Q81); it leaves the set when one
    is, and a pre-registered batch reads *fabricated change adopted: 0 of n*. A fifth *not met*
    appearing here is a regression in a claim."""
    not_met = {r.failure.split(".")[0] for r in TABLE if r.not_met}
    assert not_met == {"5", "6", "7", "11"}


def test_the_machine_s_six_rows_are_in_this_table_too() -> None:
    from tests.test_orchestrator import FAILURE_ROWS

    failures = " ".join(r.failure for r in TABLE)
    for machine_row in FAILURE_ROWS:
        key = machine_row.split(":")[0].split(" / ")[0]
        assert key in failures, machine_row
