"""`docs/RESULTS.md`'s run counts are read from the tree, not remembered (G7, 2026-09-20).

Its sibling `test_results_staleness.py` guards *stamp* claims for a reason it states well: *"a
banner is a snapshot. The fix for a snapshot going stale is not a better snapshot; it is a check
that fails when it does."* The counts had the same problem and no check. The paragraph read **80
scored pipeline runs** on the current world, **65** of them at the reporting observability digest,
from before T6.5's sixty runs and T6.8's ten - so the most-read document in the repository
understated its own evidence base by more than half, for nine days.

README had the same defect in the same week (*"19 scored runs"*, nine days stale) and was fixed by
deleting the number and pointing at a generated table. That is not available here: this document's
whole job is to state what the record holds. So the number stays and the memory does not.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from evalharness import evaldb

REPO_ROOT = Path(__file__).resolve().parents[1]
RESULTS = REPO_ROOT / "docs/RESULTS.md"
RUNS = REPO_ROOT / "evals/runs"

WORLD = "90e9f29e"
BLIND = "f3011ba8"
"""ADR-0037 §2: the first Tempo configuration was blind to the last five minutes; its runs are in
no figure and the banner counts them separately rather than dropping them."""

CLAIM = re.compile(
    r"\*\*(\d+) scored\n> pipeline runs\*\* on `90e9f29e…` \((\d+) at the observability digest "
    r"this document reports,\n> (\d+) at the blind one\)"
)


def _counted() -> tuple[int, int, int]:
    total = reporting = blind = 0
    for manifest in sorted(RUNS.glob("*/manifest.json")):
        payload = json.loads(manifest.read_text())
        world = (payload.get("freeze") or {}).get("world") or {}
        if str(world.get("compose_digest") or "")[:8] != WORLD:
            continue
        if evaldb.outcome_of(payload) != "scored":
            continue
        total += 1
        if str(world.get("observability_digest") or "")[:8] == BLIND:
            blind += 1
        else:
            reporting += 1
    return total, reporting, blind


def test_the_banner_counts_what_the_tree_holds() -> None:
    claim = CLAIM.search(RESULTS.read_text())

    assert claim, (
        "docs/RESULTS.md no longer carries the run-count sentence this test reads. If it was "
        "reworded, reword this pattern with it; if the count was removed, remove this test and "
        "say in the commit why the document no longer states its own size."
    )
    assert tuple(map(int, claim.groups())) == _counted()


def test_the_two_parts_sum_to_the_whole() -> None:
    """A banner whose parts do not add up is worse than one with no parts: it reads as precision."""
    total, reporting, blind = _counted()

    assert reporting + blind == total
