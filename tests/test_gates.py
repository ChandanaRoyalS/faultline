"""The gate record cannot disagree with itself (CLAUDE.md rule 4).

`docs/GATES.md` exists because *"until 2026-09-01 nothing in this repository recorded whether any
gate had ever passed, so the rule was enforced by memory."* It has a summary table and a section
per declared gate, and **the table is what a reader scans.**

G3 was declared on 2026-09-02 with a full evidence section — and its table row still read *"Not
declared"* until 2026-09-03. A reader scanning the table would have concluded the gate had not
passed while the evidence for it sat forty lines below. That is the same failure the file was
written to fix, one level down: a record enforced by memory, where the memory in question is
remembering to update two places.
"""

from __future__ import annotations

import re
from pathlib import Path

GATES = Path("docs/GATES.md")


def rows() -> dict[str, str]:
    return dict(re.findall(r"^\| (G\d) \| .*? \| (.+?) \|$", GATES.read_text(), re.M))


def sections() -> dict[str, str]:
    return dict(re.findall(r"^## (G\d) — (declared [\d-]+|.*?)$", GATES.read_text(), re.M))


def test_every_gate_has_exactly_one_row() -> None:
    found = rows()

    assert sorted(found) == [f"G{n}" for n in range(8)], "G0 through G7, once each"


def test_the_table_and_the_sections_never_disagree() -> None:
    """**The defect this file was added for.** A gate declared in its section and 'Not declared'
    in the table is a record that contradicts itself, and the contradiction resolves in favour of
    whichever half the reader happened to read."""
    table, body = rows(), sections()

    disagreements = [
        gate
        for gate in table
        if ("Declared" in table[gate]) != body.get(gate, "").startswith("declared")
    ]

    assert disagreements == [], (
        f"{disagreements}: the summary row and the evidence section disagree about whether the "
        "gate passed. Update both, or neither."
    )


def test_a_declared_gate_carries_its_date_in_both_places() -> None:
    """The date is how a reader ties a declaration to the sweep that produced it. A row saying
    'Declared' with no date sends them looking."""
    table, body = rows(), sections()

    for gate, status in table.items():
        if "Declared" not in status:
            continue
        assert re.search(r"\d{4}-\d{2}-\d{2}", status), f"{gate}'s row has no date"
        assert body[gate].split()[-1] in status, f"{gate}'s row and section give different dates"


def test_an_undeclared_gate_has_no_evidence_section_claiming_otherwise() -> None:
    """The reverse drift: a section deleted or downgraded while the row still boasts. Cheap to
    assert and it costs nothing to keep."""
    table, body = rows(), sections()

    for gate, heading in body.items():
        if heading.startswith("declared"):
            assert "Declared" in table[gate], f"{gate} has an evidence section but a bare row"
