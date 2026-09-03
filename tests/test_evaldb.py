"""The eval database's fingerprint rules and manifest flattening (T4.4).

The database itself is exercised against real Postgres in `test_integration_store.py`; everything
here is the part that decides *what* gets written, which is where the judgement lives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evalharness import evaldb

RUNS = Path("evals/runs")


def manifest(**overrides: object) -> dict:
    base = {
        "run_id": "20260903T000000Z-cart-redis-misconfig",
        "scenario_id": "cart-redis-misconfig",
        "split": "dev",
        "models": {"planner": "claude-opus-5"},
        "efforts": {"default": "medium"},
        "budget": {"max_tokens": 120000},
        "score": {"runtime_version": "faultline/0.0.1+prompts:7c6894e9dd92"},
    }
    base.update(overrides)
    return base


# --- the fingerprint ---------------------------------------------------------------------


def test_the_same_present_settings_fingerprint_the_same() -> None:
    """Canonical JSON with sorted keys, so key order in a manifest cannot make one configuration
    look like two."""
    a = evaldb.fingerprint(manifest(models={"planner": "x", "logs": "y"}))
    b = evaldb.fingerprint(manifest(models={"logs": "y", "planner": "x"}))

    assert a.fingerprint == b.fingerprint


def test_a_changed_setting_moves_the_fingerprint() -> None:
    before = evaldb.fingerprint(manifest())
    after = evaldb.fingerprint(manifest(budget={"max_tokens": 60000}))

    assert before.fingerprint != after.fingerprint


def test_an_absent_input_is_recorded_missing_and_never_defaulted() -> None:
    """**The property the whole history rests on.**

    These manifests span six generations and the earlier ones carry no freeze block and none of
    T4.6's fields, because those did not exist. Substituting a default would be making a claim
    about a run that nobody made, and would let a pre-T4.6 run share a fingerprint with a post-
    T4.6 one - which is precisely the silent comparison this design exists to prevent.
    """
    without = evaldb.fingerprint(manifest())
    with_r = evaldb.fingerprint(manifest(repeat_count=1))

    assert "repeat_count" in without.missing
    assert "repeat_count" not in with_r.missing
    assert without.fingerprint != with_r.fingerprint, (
        "a run that never stated its repeat count must not collide with one that stated R = 1"
    )


def test_a_complete_fingerprint_is_not_a_quality_claim() -> None:
    """`complete` says every known input was present, nothing more. No run in this repository
    has one yet, because T4.6's three inputs do not exist."""
    assert evaldb.fingerprint(manifest()).complete is False


# --- outcomes ----------------------------------------------------------------------------


def test_invalid_outranks_scored_because_the_question_is_may_these_numbers_be_used() -> None:
    """T4.1b's silent-filter run produces a score and is then refused. Both facts are true and
    the column answers the second one."""
    assert evaldb.outcome_of(manifest(invalid={"reason": "filter did not fire"})) == "invalid"
    assert evaldb.outcome_of(manifest()) == "scored"
    assert (
        evaldb.outcome_of(manifest(discarded={"reason": "run failed"}, score=None)) == "discarded"
    )
    assert evaldb.outcome_of({"paused": {"reason": "settle window"}}) == "paused"


def test_a_manifest_with_no_score_and_no_marker_is_a_discard_not_a_success() -> None:
    """The conservative reading. A run that recorded no score did not produce one, and counting
    it as scored would inflate every rate computed over the table."""
    assert evaldb.outcome_of({"scenario_id": "x"}) == "discarded"


# --- the freeze stamp is not a fallback for a baseline run ---------------------------------

AGENT_STAMP = "faultline/0.0.1+prompts:7c6894e9dd92"


def test_a_scored_run_takes_its_runtime_from_the_trajectory_not_the_freeze() -> None:
    """Both live in the manifest: `freeze.runtime_version` is the agent stamp taken before
    injection as provenance of the harness code, `score.runtime_version` is read off the
    trajectory and says what actually ran. The score block wins, which is why a scored B0 run
    records `+baseline:B0` even though the freeze above it says otherwise."""
    row = evaldb.row_of(
        manifest(
            baseline="b0",
            score={"runtime_version": "faultline/0.0.1+baseline:B0.2"},
            freeze={"runtime_version": AGENT_STAMP},
        )
    )

    assert row.config.runtime_version == "faultline/0.0.1+baseline:B0.2"


def test_a_discarded_baseline_run_is_not_labelled_with_the_agents_stamp() -> None:
    """**The hole the score block was hiding.** A discard has no score block, so `_setting` fell
    through to the freeze - and the freeze carries the *agent's* digest over role prompts and
    contract schemas, which a no-LLM baseline never touched. A discarded B0 run would have been
    recorded, and its `eval_configs` row permanently labelled, under the runtime of the pipeline
    it is a control for. Worse than a NULL, because it reads as authoritative.

    On this catalog roughly a third of runs discard, so this is a matter of when.
    """
    row = evaldb.row_of(
        manifest(baseline="b0", score=None, freeze={"runtime_version": AGENT_STAMP})
    )

    assert row.config.runtime_version is None, "not recorded is the true answer"
    assert row.config.runtime_version != AGENT_STAMP


def test_it_is_not_backfilled_with_the_current_baseline_version_either() -> None:
    """`BASELINE_RUNTIME` is the *current* version. Stamping a discarded v1 run with it would make
    v1 poolable with v2 - precisely the pooling the version marker exists to prevent. The run did
    not record what ran and the manifest cannot reconstruct it."""
    from evalharness import baselines

    row = evaldb.row_of(
        manifest(baseline="b0", score=None, freeze={"runtime_version": AGENT_STAMP})
    )

    assert row.config.runtime_version != baselines.BASELINE_RUNTIME


def test_a_discarded_agent_run_still_falls_back_to_the_freeze() -> None:
    """The narrowing is to baseline runs only. Agent runs store `baseline: null`, which is falsy,
    so their behaviour is unchanged - and for them the freeze stamp *is* the right answer, because
    it is their own."""
    row = evaldb.row_of(
        manifest(baseline=None, score=None, freeze={"runtime_version": AGENT_STAMP})
    )

    assert row.config.runtime_version == AGENT_STAMP


# --- flattening --------------------------------------------------------------------------


def test_the_scored_fields_are_lifted_into_columns() -> None:
    row = evaldb.row_of(
        manifest(
            score={
                "runtime_version": "faultline/0.0.1+prompts:7c6894e9dd92",
                "trajectory_id": "t-1",
                "cost_usd": 0.4785,
                "fault_class": {"truth": "bad_config", "returned": "bad_config", "correct": True},
                "fix_class": {"truth": "config_revert", "returned": None, "abstained": True},
                "triage": {"recall": 1.0, "precision": 0.67},
            }
        )
    )

    assert row.values["fault_class_correct"] is True
    assert row.values["fix_class_abstained"] is True
    assert row.values["triage_precision"] == 0.67
    assert row.values["cost_usd"] == 0.4785


def test_every_column_the_loader_writes_has_a_value_from_the_flattener() -> None:
    """A guard on the two lists agreeing. The loader builds its insert by name, so a column added
    to the schema and not to `row_of` fails here rather than writing NULL forever."""
    row = evaldb.row_of(manifest())
    named = {
        **row.values,
        "run_id": row.run_id,
        "scenario_id": row.scenario_id,
        "outcome": row.outcome,
        "config_fingerprint": row.config.fingerprint,
        "manifest": "{}",
    }

    assert [column for column in evaldb.COLUMNS if column not in named] == []


# --- the real record ---------------------------------------------------------------------


@pytest.mark.skipif(not RUNS.is_dir(), reason="run tree not present")
def test_every_recorded_manifest_flattens_without_special_casing() -> None:
    """**The backfill, run against the actual history.** Six generations of manifest, including
    two that predate `run_id` and take it from the directory name. If this needs a special case
    later, the special case belongs in `row_of` with a comment naming the generation."""
    rows = evaldb.read_runs(RUNS)

    assert len(rows) > 100
    assert all(row.run_id for row in rows), "every row must be identifiable"
    assert all(row.scenario_id for row in rows)
    assert {row.outcome for row in rows} <= {"scored", "discarded", "paused", "invalid"}
