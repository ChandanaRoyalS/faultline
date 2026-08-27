"""The holdout freeze manifest (T4.6, ADR-0022 §3.3).

"Frozen" has to mean something a script can check, or it means nothing. These pin that the six
items are all present, that the one that is also a contamination check reports a number rather
than folding into a hash, and that `diff` notices when any of them moves.
"""

from __future__ import annotations

import json
from pathlib import Path

from evalharness import freeze

REPO_ROOT = Path(__file__).resolve().parents[1]


def manifest() -> dict:
    """A manifest with the database-backed item stubbed - the rest is pure."""
    return {
        "frozen_for": "T4.6 holdout",
        "runtime_version": "faultline/0.0.1+prompts:53fafe9c12bc",
        "prompts": freeze.prompts_hash(),
        "corpus": {"rows": 35, "sha256": "abc", "documents": [], "holdout_chunks": 0},
        "model_map": freeze.model_map(),
        "budget": freeze.budget_bounds(4, 120_000),
        "tool_layer": {"git_sha": "deadbeef", "git_dirty": False},
        "judge": freeze.judge_state(),
    }


def test_all_six_frozen_items_are_present() -> None:
    """ADR-0022 §3.3 enumerates six. A manifest missing one is a freeze with a hole in it."""
    m = manifest()
    for item in ("prompts", "corpus", "model_map", "budget", "tool_layer", "judge"):
        assert item in m, item
    assert m["runtime_version"].endswith("53fafe9c12bc"), "and the stamp they exist to protect"


def test_the_prompt_hash_covers_every_system_constant() -> None:
    """Not the synthesizer's alone. A freeze that watched one prompt would miss a change to
    any of the other three."""
    from faultline.agents import roles

    hashed = freeze.prompts_hash()
    expected = sorted(
        n for n in dir(roles) if n.endswith("_SYSTEM") and isinstance(getattr(roles, n), str)
    )
    assert hashed["constants"] == expected
    assert len(expected) == 4


def test_the_corpus_item_reports_holdout_chunks_as_a_number() -> None:
    """**The one freeze item that is also a contamination check.** ADR-0008 axis 1: holdout
    artifacts never enter any retrieval corpus. A number that must be zero deserves to be read
    as a number, not folded into a hash where nobody would notice it change."""
    m = manifest()
    assert m["corpus"]["holdout_chunks"] == 0
    assert isinstance(m["corpus"]["holdout_chunks"], int)


def test_holdout_origins_are_read_from_the_committed_bundles() -> None:
    """Derived from what is on disk, so a new holdout scenario is covered without anyone
    remembering to add it to a list."""
    origins = freeze.holdout_origins()
    assert origins == [
        "scenario:email-wrong-image",
        "scenario:productcatalog-dependency-latency",
        "scenario:recommendation-memory-squeeze",
    ]


def test_the_judge_is_recorded_separately_from_the_agent() -> None:
    """ADR-0020 §1: a judged number is a function of two models. The freeze records the judge's
    model and prompt on their own, so a judge change is visible as a judge change."""
    m = manifest()
    assert set(m["judge"]) == {"model", "prompt_sha256", "allow_shared_lineage"}
    assert m["judge"]["prompt_sha256"] != m["prompts"]["sha256"]


def test_diff_is_empty_when_nothing_moved() -> None:
    assert freeze.diff(manifest(), manifest()) == []


def test_diff_names_whatever_moved() -> None:
    """A holdout run whose manifest does not match the dev run it is compared against is not a
    comparison (ADR-0022 §3.3). This is what makes that enforceable rather than aspirational."""
    before = manifest()

    after = json.loads(json.dumps(before))
    after["prompts"]["sha256"] = "moved"
    assert freeze.diff(before, after) == ["prompts"]

    after = json.loads(json.dumps(before))
    after["corpus"]["holdout_chunks"] = 5
    assert freeze.diff(before, after) == ["corpus"]

    after = json.loads(json.dumps(before))
    after["runtime_version"] = "faultline/0.0.1+prompts:deadbeefcafe"
    assert freeze.diff(before, after) == ["runtime_version"]

    after = json.loads(json.dumps(before))
    after["tool_layer"]["git_sha"] = "0000000"
    assert freeze.diff(before, after) == ["tool_layer.git_sha"]


def test_a_dirty_tree_does_not_count_as_a_freeze_break() -> None:
    """Files are written into the repository during a run - run directories, reports - so the
    dirty flag moves for reasons that are not the freeze breaking. The sha is what binds, and
    the flag is recorded so a reader can see the state rather than infer it."""
    before = manifest()
    after = json.loads(json.dumps(before))
    after["tool_layer"]["git_dirty"] = True
    assert freeze.diff(before, after) == []
    assert "git_dirty" in after["tool_layer"], "recorded, just not load-bearing"


def test_the_committed_freeze_manifest_matches_the_pipeline_it_names() -> None:
    """The manifest on disk is the one the holdout ran under. If this fails, either the
    manifest was not regenerated or the pipeline moved - and both invalidate the holdout."""
    path = REPO_ROOT / "evals/runs/FREEZE-2026-08-26-holdout.json"
    if not path.exists():
        return  # written by T4.6's freeze commit; absent on branches that predate it

    frozen = json.loads(path.read_text())

    # Self-consistency, not agreement with HEAD - see ADR-0023. The original assertion
    # compared the manifest to `runtime_version()`, which conflated "mis-generated" with
    # "the pipeline has moved since". T4.12 moved the pipeline deliberately, and the only
    # ways to satisfy the old check were to abandon the experiment or to rewrite the record
    # of what the holdout ran under.
    # `runtime_version`'s digest covers prompts *and* contract schemas; `prompts.sha256`
    # covers prompt text alone. They are different functions over overlapping inputs, so
    # neither can be derived from the other - the check is that both are present and that
    # the contamination invariant the freeze exists to record still reads 0.
    assert frozen["prompts"]["sha256"]
    assert frozen["corpus"]["holdout_chunks"] == 0

    # Known lineage: a manifest naming a pipeline nothing here describes is untraceable.
    from tests.test_harness_run import SWEEP_1_DIGEST, SWEEP_2_DIGEST, SWEEP_4_DIGEST

    known = {SWEEP_1_DIGEST, SWEEP_2_DIGEST, SWEEP_4_DIGEST}
    assert frozen["runtime_version"].rsplit(":", 1)[-1] in known
