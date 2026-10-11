"""README's v2 headline block is `analysis_headline_v2.py --readme`'s output, byte for byte.

**The same rule `test_scenario_table.py` holds the v1 table to**: a hand-written figure on the
front door goes stale the moment the tree moves, so the block is generated and this test
regenerates it. The script is standard library and reads `evals/runs/` directly, which is why it
is run as a subprocess rather than imported: what the README shows is what a reader's own
`python3` would print.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
SCRIPT = REPO / "evals" / "runs" / "analysis_headline_v2.py"
RUNS = REPO / "evals" / "runs"
BEGIN = "<!-- headline-v2:begin -->"
END = "<!-- headline-v2:end -->"


def _generated() -> str:
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), str(RUNS), "--readme"],
        capture_output=True,
        text=True,
        check=True,
        timeout=600,
    )
    return done.stdout.strip()


def test_the_block_matches_the_tree() -> None:
    text = README.read_text()
    assert BEGIN in text and END in text, "README carries the v2 headline block"
    shown = text[text.index(BEGIN) : text.index(END) + len(END)].strip()
    assert shown == _generated(), (
        "README.md's v2 headline block does not match evals/runs/. Regenerate: "
        "python3 evals/runs/analysis_headline_v2.py evals/runs --readme"
    )


def test_the_headline_sentence_matches_the_block() -> None:
    """The two figures in the prose above the block are read back against the block."""
    text = README.read_text()
    glance = text[text.index("## Results at a glance") : text.index(BEGIN)]
    block = text[text.index(BEGIN) : text.index(END)]
    f_row = next(line for line in block.splitlines() if line.startswith("| F |"))
    cells = [c.strip() for c in f_row.strip("|").split("|")]
    fault = re.match(r"(\d+)/(\d+)", cells[1])
    service = re.match(r"(\d+)/(\d+)", cells[3])
    said_fault = re.search(r"fault class on (\d+) of (\d+)", glance)
    said_service = re.search(r"culprit service on (\d+) of (\d+)", glance)
    assert fault and said_fault and said_fault.groups() == fault.groups()
    assert service and said_service and said_service.groups() == service.groups()


def test_the_v2_block_sits_above_the_v1_table() -> None:
    text = README.read_text()
    assert text.index(BEGIN) < text.index("### The v1 world, at the shipping stamp")
    assert text.index("### The v1 world") < text.index("<!-- scenario-table:begin -->")
