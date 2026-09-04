"""The eval database's fingerprint rules and manifest flattening (T4.4).

The database itself is exercised against real Postgres in `test_integration_store.py`; everything
here is the part that decides *what* gets written, which is where the judgement lives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evalharness import evaldb, sweep

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
        # **A run that started.** Without this a discard is indistinguishable from a gate
        # refusal, which is the distinction `outcome_of` recovers - see its docstring.
        "injected_at": "2026-09-03T00:05:00+00:00",
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


def test_a_manifest_with_no_score_and_no_marker_is_never_read_as_a_success() -> None:
    """The conservative reading, and it is still conservative. A run that recorded no score did
    not produce one, and counting it as scored would inflate every rate computed over the table.

    **Which kind of non-success it is now turns on `injected_at`**, the same question the labelled
    branch asks. This test previously pinned the answer to `discarded` outright, which is what
    made `else "discarded"` look correct: a run with no marker *and no injection* is a refusal,
    and calling it a discard puts a run that never happened into the rate for runs that did.
    """
    assert evaldb.outcome_of({"scenario_id": "x"}) == "refused", "nothing was injected"
    assert evaldb.outcome_of({"scenario_id": "x", "injected_at": "2026-09-04T08:00:00Z"}) == (
        "discarded"
    ), "the fault went in and nothing came out"
    for outcome in ("refused", "discarded"):
        assert outcome != "scored"


def test_the_premise_the_recovery_rests_on_holds_on_the_committed_record() -> None:
    """**`injected_at` is present on every manifest that produced a score.**

    The whole recovery reads an absent `injected_at` as "nothing was injected". If a scored run
    could lack the field, that reading would quietly move real results into `refused` - so the
    premise is asserted against the tree rather than trusted from a docstring. Measured today:
    61 manifests lack `injected_at` and not one of them carries a `score`.
    """
    import json

    offenders = [
        d.name
        for d in sorted(RUNS.iterdir())
        if d.is_dir() and (d / "manifest.json").is_file()
        if (m := json.loads((d / "manifest.json").read_text())).get("score")
        and not m.get("injected_at")
    ]
    assert offenders == [], f"scored runs with no injected_at break the recovery: {offenders}"


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
    assert {row.outcome for row in rows} <= {
        "scored",
        "discarded",
        "refused",
        "paused",
        "invalid",
    }


def test_a_gate_refusal_is_not_a_discard_even_when_it_was_written_as_one() -> None:
    """**Measured over the 132 runs on disk: 44 discards, 22 of which never injected anything.**

    10 `baseline gate refused`, 10 `pipeline-down`, 2 others. So the discard rate this repository
    quoted, budgeted sweeps against, and recorded in `docs/PLAN.md` as *"a headline property of
    this harness"* — **33%** — was double the truth of **16.7%**. `HeadroomExhaustedError` had
    already made this argument for itself and carried `is_pause`; nothing carried it for the rest.

    The correction is a **reading** of the record, not an edit to it. `injected_at` is on every
    manifest ever written, so a refusal mislabelled as a discard is recoverable without touching
    a byte — which matters, because captured evidence is never rewritten.
    """
    started = manifest(discarded={"reason": "run failed"}, score=None)
    never_started = manifest(discarded={"reason": "pipeline-down"}, score=None, injected_at=None)

    assert evaldb.outcome_of(started) == "discarded", "the fault went in and the run happened"
    assert evaldb.outcome_of(never_started) == "refused", "nothing was injected"


def test_a_manifest_with_no_outcome_label_at_all_is_not_a_discard_by_default() -> None:
    """**The defect the loose bound above was hiding.**

    The pre-flight refusal path wrote a manifest carrying a `preflight` block and nothing else -
    no `discarded`, no `refused`, no `score`. `outcome_of` recovered the mislabelled case in the
    branch above and then fell through to `else "discarded"`, so the unlabelled case became a
    discard by default. Thirty of these landed on 2026-09-04 and the recorded discard rate went
    from 16.7% to 28.6% in one afternoon - the exact inflation this function exists to stop,
    arriving through its own default.
    """
    unlabelled = manifest(score=None, injected_at=None)
    unlabelled.pop("discarded", None)
    unlabelled["preflight"] = {"checked": True, "ok": False, "detail": "no credential"}

    assert evaldb.outcome_of(unlabelled) == "refused"


def test_an_unlabelled_manifest_that_did_inject_is_still_a_discard() -> None:
    """The recovery must not run the other way. A run that injected and recorded no outcome is a
    run that happened and produced no result, which is what a discard is."""
    crashed = manifest(score=None)
    crashed.pop("discarded", None)

    assert evaldb.outcome_of(crashed) == "discarded"


def test_the_correction_holds_on_the_committed_record() -> None:
    """Asserted against the real tree rather than a fixture, because the whole finding is about
    what the real tree contains.

    **The bound is stated against the runs that started, not against every directory.** A refusal
    costs nothing and injected nothing, so counting it in the denominator of a discard *rate*
    dilutes the number a sweep budgets against - the more refusals a bad afternoon produces, the
    healthier the pipeline would look.
    """
    import collections
    import json

    counts = collections.Counter(
        evaldb.outcome_of(json.loads((d / "manifest.json").read_text()))
        for d in sorted(RUNS.iterdir())
        if d.is_dir() and (d / "manifest.json").is_file()
    )

    assert counts["refused"] > 0, "the record holds refusals that were written as discards"
    started = counts["discarded"] + counts["scored"]
    assert counts["discarded"] / started == pytest.approx(sweep.DISCARD_RATE, abs=0.02), (
        "the constant sweeps budget against must track the record it is derived from"
    )
