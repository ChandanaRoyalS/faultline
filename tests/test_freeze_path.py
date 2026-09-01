"""The freeze path: the harness produces the manifest, and the checks bite (T7.55).

`freeze.build()` and `freeze.diff()` were tested code with no caller, and the committed FREEZE
manifests were made by hand. ADR-0022 §3.3 claimed the harness refuses to print incomparable
results side by side and nothing did. These pin the three halves of closing that: **where the
freeze is taken**, **what refuses**, and **what will not put two worlds in one table.**
"""

from __future__ import annotations

import inspect

from evalharness import freeze, judge, run
from evalharness.generations import Generation


def test_the_freeze_is_taken_before_anything_is_injected() -> None:
    """**The placement is the load-bearing part and it cannot be asserted from a manifest.**

    A freeze taken after injection describes a world already carrying the fault - injection swaps
    images and attaches sidecars - and one reconstructed afterwards is not an observation at all,
    which is the failure T7.22 had with reachability. The only alternative to reading the source
    here is a live injected run, and a test that needs the world up is a test that does not run.
    """
    source = inspect.getsource(run.main)
    build_at = source.index("freeze.build(")
    inject_at = source.index('"faultline-inject", "start"')
    gate_at = source.index("gate.require(")
    assert gate_at < build_at < inject_at, "after the gate proves the world clean, before the fault"


def test_an_unverifiable_world_refuses_and_a_changed_one_does_not() -> None:
    """**ADR-0022's T7.54 decision, both halves, neither softened.**

    Absence is an error: a run that cannot say what world it ran against is the case the whole
    correction was about, and the one a hand-written manifest could always paper over. A *changed*
    world is a label, because refusing would protect a comparison that broke before the check ran.
    """
    source = inspect.getsource(run.main)
    refusal = source.index("cannot establish what world")
    assert source.index("unverifiable_fields") < refusal
    assert "return 3" in source[refusal : refusal + 1200], "absence refuses"

    label = source.index("NEW COMPARABILITY GENERATION")
    assert "return" not in source[label : source.index("recorded, not refused")], "change labels"


def test_the_contamination_count_is_acted_on_rather_than_only_computed() -> None:
    """`corpus.holdout_chunks` is the one freeze item that is also a contamination check, and
    CLAUDE.md calls a break P0. The freeze already counted it; nothing read the number."""
    source = inspect.getsource(run.main)
    assert 'frozen["corpus"]["holdout_chunks"]' in source
    assert "holdout chunk(s) in the " in source


def _result(scenario: str, run_id: str) -> judge.JudgeResult:
    return judge.JudgeResult(
        scenario_id=scenario,
        run_id=run_id,
        agent_model="claude-opus-5",
        judge_model="claude-haiku-4-5",
        shared_lineage=True,
        lineage_note="",
        scored=True,
        not_scored_because=None,
        agreement="same_mechanism",
        agreement_reason="",
        dead_ends_closed=[],
        dead_ends_missed=[],
        traps=[],
        notes="",
        tokens_in=0,
        tokens_out=0,
    )


def test_two_worlds_are_never_rows_of_one_table() -> None:
    """**Where §3.3's claim finally bites.** `judged_rows` is the only cross-run comparison table
    this repository produces by code, so it is the only place the claim can be enforced at all."""
    results = [_result("a", "run-a"), _result("b", "run-b")]
    gens = {
        "run-a": Generation(world="4a7690c6fdda", provenance="observed"),
        "run-b": Generation(world="f5bd108f4f70", provenance="observed"),
    }
    text = "\n".join(judge.judged_rows(results, gens))
    assert "2 comparability generations" in text
    assert text.count("| scenario |") == 2, "one header per world, never one table over both"
    assert "### World `4a7690c6fdda`" in text
    assert "### World `f5bd108f4f70`" in text


def test_one_world_is_still_one_table_and_names_itself() -> None:
    results = [_result("a", "run-a"), _result("b", "run-b")]
    same = Generation(world="f5bd108f4f70", provenance="observed")
    text = "\n".join(judge.judged_rows(results, {"run-a": same, "run-b": same}))
    assert text.count("| scenario |") == 1
    assert "World: `f5bd108f4f70`" in text, "a table that names no world is how this went wrong"


def test_a_reconstructed_world_says_so_in_the_table() -> None:
    """The value is right and the provenance is weaker; a reader gets told which they are looking
    at. Every run before T7.55 is in this state and none was backfilled to hide it."""
    results = [_result("a", "run-a")]
    gens = {"run-a": Generation(world="4a7690c6fdda", provenance="reconstructed")}
    text = "\n".join(judge.judged_rows(results, gens))
    assert "4a7690c6fdda (reconstructed)" in text


def test_the_world_block_is_still_the_whole_observed_family() -> None:
    """The freeze path is only worth wiring if it freezes what T7.54 decided it should."""
    assert "world" in freeze.FROZEN_KEYS
    assert set(freeze.world_state()) >= {
        "compose_digest",
        "observability_digest",
        "ffs_stub_source_digest",
        "otel_demo_image_digest",
        "capability_version",
    }
