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

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS = REPO_ROOT / "evals/runs"

# The re-record windows, read from the `t_inject` of the bundles each re-record wrote. A world
# move is not instantaneous: it starts when the compose edit is applied and is observable from the
# first capture taken against the result.
T7_1_FIRST_CAPTURE = "20260828T024126Z"
T7_1_LAST_CAPTURE = "20260828T052049Z"
T7_28_FIRST_CAPTURE = "20260829T225404Z"
T7_28_LAST_CAPTURE = "20260830T013651Z"

WORLDS = {
    "4a7690c6fdda": "T1.5 through T7.1",
    "299d791c5e0d": "T7.1 through T7.28",
    "f5bd108f4f70": "T7.28 onward - current",
}


def run_stamps() -> list[str]:
    return sorted(d.name.split("-")[0] for d in RUNS.iterdir() if (d / "manifest.json").exists())


def world_of(stamp: str) -> str:
    if stamp < T7_1_FIRST_CAPTURE:
        return "4a7690c6fdda"
    if stamp < T7_28_FIRST_CAPTURE:
        return "299d791c5e0d"
    return "f5bd108f4f70"


def test_no_run_straddles_a_world_move() -> None:
    """**The invariant that makes attribution possible at all.** A run that started while a
    re-record was in flight executed against a world that was half-changed, and no digest
    describes it. None exists today; this is what says so, and what would catch the next one.
    """
    for stamp in run_stamps():
        assert not (T7_1_FIRST_CAPTURE <= stamp <= T7_1_LAST_CAPTURE), stamp
        assert not (T7_28_FIRST_CAPTURE <= stamp <= T7_28_LAST_CAPTURE), stamp


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
