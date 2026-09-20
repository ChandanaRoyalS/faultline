"""README's roadmap table may not disagree with the gate record (CLAUDE.md rule 4).

`tests/test_gates.py` exists because `docs/GATES.md`'s summary row and its evidence section drifted
apart, and *"the table is what a reader scans."* This is the same failure one level out, and it
ran for longer: **until 2026-09-20 README's roadmap showed G0 as *in progress* and every gate after
it unchecked, while `docs/GATES.md` recorded five declarations** - the oldest dated 2026-08-23.
README is the front door. A reviewer who reads it and stops has been told this project has passed
no gates.

The note that stood beneath that table explained it - the marks were *"deliberately not updated
from the results section"*, because a gate passes from a clean clone and *"that has not been re-run
since these measurements were taken."* The reasoning was sound when it was written and false by
2026-09-07, when G5 was declared on three `make demo` runs from a fresh machine. A rule that
excuses a stale table outlives the condition that justified it, which is why this is a test and not
a note.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README = REPO_ROOT / "README.md"
GATES = REPO_ROOT / "docs/GATES.md"

ROW = re.compile(r"^\| (G\d) \| .*? \| (.+?) \|$", re.M)


def _rows(path: Path) -> dict[str, str]:
    return dict(ROW.findall(path.read_text()))


def test_both_tables_name_every_gate() -> None:
    assert sorted(_rows(README)) == sorted(_rows(GATES)) == [f"G{n}" for n in range(8)]


def test_the_front_door_agrees_with_the_record_about_what_passed() -> None:
    """Declared is declared in both places, or the reader is told two different things depending
    on which file they opened first."""
    readme, gates = _rows(README), _rows(GATES)

    disagreements = [
        gate for gate in gates if ("Declared" in readme[gate]) != ("Declared" in gates[gate])
    ]

    assert disagreements == [], (
        f"{disagreements}: README's roadmap and docs/GATES.md disagree about whether the gate "
        "passed. docs/GATES.md is the record; update README to match it."
    )


def test_a_declared_gate_carries_the_same_date_on_the_front_door() -> None:
    """A date that differs between the two is worse than no date: it implies two events."""
    readme, gates = _rows(README), _rows(GATES)

    for gate, status in gates.items():
        if "Declared" not in status:
            continue
        date = re.search(r"\d{4}-\d{2}-\d{2}", status)
        assert date, f"{gate}: docs/GATES.md declares it without a date"
        assert date.group() in readme[gate], (
            f"{gate}: README gives a different date from docs/GATES.md, or none"
        )
