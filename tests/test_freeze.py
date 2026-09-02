"""The holdout freeze manifest (T4.6, ADR-0022 §3.3).

"Frozen" has to mean something a script can check, or it means nothing. These pin that the seven
items are all present, that the one that is also a contamination check reports a number rather
than folding into a hash, and that `diff` notices when any of them moves.

T7.54 added the seventh, `world`, and with it the rule that **absence reads as `unverifiable`
rather than as unchanged** - the failure mode that let 69 of 97 recorded runs be attributed to a
world generation they did not execute against.
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
        "world": {
            "compose_digest": "f5bd108f",
            "observability_digest": "857d95b4",
            "ffs_stub_source_digest": "8defed31",
            "otel_demo_image_digest": "sha256:97d55955",
            "capability_version": "cap:9c416e0a",
            "unverifiable_fields": [],
        },
    }


def test_all_seven_frozen_items_are_present() -> None:
    """ADR-0022 §3.3 enumerated six and T7.54 added the world. A manifest missing one is a
    freeze with a hole in it, and the hole the world left was not theoretical."""
    m = manifest()
    for item in ("prompts", "corpus", "model_map", "budget", "tool_layer", "judge", "world"):
        assert item in m, item
    assert m["runtime_version"].endswith("53fafe9c12bc"), "and the stamp they exist to protect"


def test_the_world_item_covers_the_whole_provenance_family_not_only_compose() -> None:
    """**A fix that adds one item and leaves a sibling out has not understood why it was
    missing.** The six original items are everything the harness *constructs*; every one of these
    is something it *observes*, which is the seam the omission fell through. `observability_digest`
    has the strongest claim of the lot - it decides what the agent's tools can see at all.

    `capability_version` is here and is *not* folded into the world: `capability.py` argues the two
    guards must stay separate so neither double-fires and teaches a reader to ignore both.
    """
    world = freeze.world_state()
    assert set(world) == {
        "compose_digest",
        "observability_digest",
        "ffs_stub_source_digest",
        "otel_demo_image_digest",
        "capability_version",
        "unverifiable_fields",
    }
    assert world["capability_version"].startswith("cap:")
    assert "ffs_stub_image_id" not in world, (
        "ADR-0014 refuses to compare it; freezing it would fire on nothing"
    )


def test_a_manifest_without_a_world_is_unverifiable_not_unchanged() -> None:
    """**The T7.54 rule.** Every freeze manifest written before T7.54 lacks `world`, and comparing
    two of them says nothing about whether the world moved between them. A check that answers "no
    difference" to a question it cannot see is worse than one that says it cannot see it.
    """
    before = manifest()
    old = {k: v for k, v in before.items() if k != "world"}
    assert "world:unverifiable" in freeze.diff(old, before)
    assert "world:unverifiable" in freeze.diff(old, old), "two blind manifests are still blind"
    assert freeze.diff(before, before) == [], "and a manifest that does record it is not flagged"


def test_a_world_field_that_could_not_be_read_is_unverifiable() -> None:
    """`otel_demo_image_digest` needs a live container. `None` on both sides compares equal, and
    equal would read as "the image did not move" when the truth is that nobody looked."""
    before = manifest()
    after = json.loads(json.dumps(before))
    after["world"]["otel_demo_image_digest"] = None
    after["world"]["unverifiable_fields"] = ["otel_demo_image_digest"]
    assert "world:unverifiable" in freeze.diff(before, after)


def test_diff_names_a_world_move() -> None:
    """The check T7.53 found missing: an entry run today would have passed every freeze item
    while having executed against a different world than entry 3."""
    before = manifest()
    for field in ("compose_digest", "observability_digest", "capability_version"):
        after = json.loads(json.dumps(before))
        after["world"][field] = "moved"
        assert freeze.diff(before, after) == ["world"], field


def test_the_prompt_hash_covers_every_system_constant() -> None:
    """Not the synthesizer's alone. A freeze that watched one prompt would miss a change to
    any of the others.

    **Five since T3.9** - the proposer's prompt joined the four, and the count is asserted
    rather than inferred so that adding a role is a visible act with a stamp move attached.
    """
    from faultline.agents import roles

    hashed = freeze.prompts_hash()
    expected = sorted(
        n for n in dir(roles) if n.endswith("_SYSTEM") and isinstance(getattr(roles, n), str)
    )
    assert hashed["constants"] == expected
    assert expected == [
        "PLANNER_SYSTEM",
        "PROPOSER_SYSTEM",
        "SCRIBE_SYSTEM",
        "SPECIALIST_SYSTEM",
        "SYNTHESIZER_SYSTEM",
    ]


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
    # T7.54: this manifest predates the world item and is expected to lack it. Pinned rather
    # than backfilled - a backfilled digest would claim a world was checked when it was not.
    assert "world" not in frozen, "entry 1's freeze could not see the world, and says so"

    # Known lineage: a manifest naming a pipeline nothing here describes is untraceable.
    from tests.test_harness_run import SWEEP_1_DIGEST, SWEEP_2_DIGEST, SWEEP_4_DIGEST

    known = {SWEEP_1_DIGEST, SWEEP_2_DIGEST, SWEEP_4_DIGEST}
    assert frozen["runtime_version"].rsplit(":", 1)[-1] in known
