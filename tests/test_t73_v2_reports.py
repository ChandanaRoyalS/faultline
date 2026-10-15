"""T7.3's reports carry `analysis_t73_v2.py`'s blocks byte for byte.

**The rule `test_headline_v2_readme.py` holds README to**, applied to the nine ablation reports
and `docs/ABLATIONS.md`: every figure in them sits inside a generated block, and this test
regenerates each block from `evals/runs/` and compares. A hand-edited number, or a run added to
the tree without the reports being regenerated, fails here.

The script is standard library and is run as a subprocess (`python3 -I`), as a reader would run
it; one run prints every block, and the blocks are cut out of its output by their markers.
"""

from __future__ import annotations

import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from evalharness import variance

REPO = Path(__file__).resolve().parents[1]
RUNS = REPO / "evals" / "runs"
SCRIPT = RUNS / "analysis_t73_v2.py"
ABLATIONS = REPO / "docs" / "ABLATIONS.md"
EXPERIMENTS = ("E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8", "E9")
SLUG = {
    "E1": "single-agent",
    "E2": "topology-scoping",
    "E3": "raw-context",
    "E4": "model-tier",
    "E5": "retrieval-off",
    "E6": "dense-only",
    "E7": "rerank",
    "E8": "temporal-scoping",
    "E9": "push-briefings",
}


def report(e: str) -> Path:
    return RUNS / f"ABLATION-2026-10-15-{e}-{SLUG[e]}.md"


@cache
def generated() -> str:
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(RUNS)],
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    return done.stdout


def block(text: str, name: str) -> str:
    match = re.search(rf"<!-- t73:{name}:begin -->.*?<!-- t73:{name}:end -->", text, re.S)
    assert match, f"no t73:{name} block"
    return match.group(0).strip()


@pytest.mark.parametrize("e", EXPERIMENTS)
def test_each_report_carries_its_block(e: str) -> None:
    path = report(e)
    assert path.exists(), f"{path.name} is missing: T7.3 owes a report per experiment"
    assert block(path.read_text(), e) == block(generated(), e), (
        f"{path.name}'s generated block does not match evals/runs/. Regenerate: "
        f"python3 evals/runs/analysis_t73_v2.py evals/runs --block {e}"
    )


@pytest.mark.parametrize("name", ["overview", "aa", "record", "supplement"])
def test_ablations_md_carries_the_series(name: str) -> None:
    assert block(ABLATIONS.read_text(), name) == block(generated(), name), (
        f"docs/ABLATIONS.md's t73:{name} block does not match evals/runs/. Regenerate: "
        f"python3 evals/runs/analysis_t73_v2.py evals/runs --block {name}"
    )


@pytest.mark.parametrize("e", [e for e in EXPERIMENTS if e != "E2"])
def test_the_mde_is_stated_before_the_result(e: str) -> None:
    """The plan's T7.3 row: *every report states its MDE before its result*."""
    text = report(e).read_text()
    assert text.index("The MDE, stated first") < text.index(f"Paired, {e} - F")


def test_the_scripts_mde_is_the_harness_formula() -> None:
    """The script copies `variance.mde` to stay standard library; the two must not drift."""
    sys.path.insert(0, str(RUNS))
    try:
        import analysis_t73_v2 as t73
    finally:
        sys.path.remove(str(RUNS))
    for n in (8, 9, 10, 11, 12, 30):
        for rho in (0.5, 0.8):
            assert t73.mde(n, rho=rho) == pytest.approx(variance.mde(n, rho=rho))
