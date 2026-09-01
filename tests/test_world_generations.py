"""Which world each recorded run executed against (T7.54).

**No run manifest records the world.** ADR-0022 §3.3's freeze table froze six things and the world
was not one of them, so the only way to say which world a figure describes is to place its
timestamp against the two re-records. T7.28 published a banner that did that *per file* rather than
per run, and got 69 of the 97 manifest-carrying runs wrong - attributing every pre-T7.1 run to
`299d791c5e0d…` when it ran against `4a7690c6fdda…`.

The freeze item added by T7.54 stops the next one happening. These tests pin the reconstruction
that fixed this one, so the corrected attribution is executable rather than prose.
"""

from __future__ import annotations

from pathlib import Path

from evalharness.generations import (
    T7_1_FIRST_CAPTURE,
    Generation,
    generation_of,
    group_by_generation,
    straddles_a_world_move,
    world_from_stamp,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "evals/runs"


def run_stamps() -> list[str]:
    return sorted(d.name.split("-")[0] for d in RUNS.iterdir() if (d / "manifest.json").exists())


def world_of(stamp: str) -> str:
    """T7.55 moved the boundaries into `evalharness.generations`; this is now one caller of
    the harness's own answer rather than a second copy of it."""
    return world_from_stamp(stamp)


def test_no_run_straddles_a_world_move() -> None:
    """**The invariant that makes attribution possible at all.** A run that started while a
    re-record was in flight executed against a world that was half-changed, and no digest
    describes it. None exists today; this is what says so, and what would catch the next one.
    """
    for stamp in run_stamps():
        assert straddles_a_world_move(stamp) is None, stamp


def test_the_historical_world_split_is_what_the_published_prose_says() -> None:
    """**69 / 12**, over the 97 run directories that carry a manifest. Both numbers are immutable:
    their boundaries are in the past, so no future run can change either. RESULTS.md and README
    quote this split; if it ever fails, one of them has drifted from the record.

    The count of current-world runs is deliberately not pinned - it grows.
    """
    stamps = run_stamps()
    assert sum(1 for s in stamps if world_of(s) == "4a7690c6fdda") == 69
    assert sum(1 for s in stamps if world_of(s) == "299d791c5e0d") == 12
    assert sum(1 for s in stamps if world_of(s) == "f5bd108f4f70") >= 16


def test_every_holdout_run_predates_the_first_world_move() -> None:
    """**All three holdout entries ran on `4a7690c6fdda…`**, which is what T7.54 corrected their
    banners to say. Entry 3 came within fifty minutes of the T7.1 re-record and still cleared it.

    This is the check that answers "were they run against the world their figures are attributed
    to" from the record rather than by inference.
    """
    holdout = [s for s in run_stamps() if _is_holdout(s)]
    assert len(holdout) == 11, "three entries, including entry 2's two discards"
    assert all(world_of(s) == "4a7690c6fdda" for s in holdout)
    assert max(holdout) == "20260828T015130Z" < T7_1_FIRST_CAPTURE


def _is_holdout(stamp: str) -> bool:
    names = (
        "email-wrong-image",
        "productcatalog-dependency-latency",
        "recommendation-memory-squeeze",
    )
    return any(
        d.name.startswith(stamp) and d.name.endswith(names) for d in RUNS.iterdir() if d.is_dir()
    )


def test_an_observed_world_beats_a_reconstructed_one() -> None:
    """**The two provenances are never conflated (T7.55).** A run that froze the world before it
    injected *knows*; a run that predates the freeze path is placed by its timestamp, which is
    correct and weaker. No freeze manifest was backfilled to make the second look like the first.
    """
    observed = generation_of(
        {"run_id": "20260826T000000Z-x", "freeze": {"world": {"compose_digest": "f5bd108f4f70abc"}}}
    )
    assert observed == Generation(world="f5bd108f4f70", provenance="observed")
    assert observed.label == "f5bd108f4f70", "an observed world carries no qualifier"

    # Same run id, no freeze: reconstructed, and it lands on the world T7.54 established.
    guessed = generation_of({"run_id": "20260826T000000Z-x"})
    assert guessed == Generation(world="4a7690c6fdda", provenance="reconstructed")
    assert guessed.label.endswith("(reconstructed)"), "and says so wherever it is printed"
    assert guessed.is_reconstructed


def test_the_freeze_is_what_decides_the_generation_not_the_timestamp() -> None:
    """A recorded observation outranks the reconstruction even when they disagree - the
    reconstruction is a fallback for runs that recorded nothing, not a second opinion."""
    manifest = {
        "run_id": "20260826T000000Z-x",  # reconstructs to 4a7690c6fdda
        "freeze": {"world": {"compose_digest": "299d791c5e0dxyz"}},
    }
    assert generation_of(manifest).world == "299d791c5e0d"


def test_runs_group_by_world_not_by_order() -> None:
    grouped = group_by_generation(
        [
            {"run_id": "20260826T000000Z-a"},
            {"run_id": "20260901T000000Z-b"},
            {"run_id": "20260827T000000Z-c"},
        ]
    )
    assert sorted(grouped) == ["4a7690c6fdda", "f5bd108f4f70"]
    assert len(grouped["4a7690c6fdda"]) == 2
