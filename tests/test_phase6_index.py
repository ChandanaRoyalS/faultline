"""The Phase 6 index exists, is complete, and does not repeat the claim it corrected (T6 audit).

Before 2026-09-07 `docs/PLAN.md` carried entries for two of the eight Phase 6 tasks and said in
six places that the action plane *"has no task number"*. The execution plan - in `docs/spec/` since
T5.3 - numbers it T6.2 and T6.3. A reconstruction that outlives the arrival of the thing it
reconstructed is the staleness `test_results_staleness` guards against, one document over.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLAN = REPO / "docs" / "PLAN.md"

PHASE_6 = {
    "T6.1": "trace analyst",
    "T6.2": "action plane",
    "T6.3": "approve / reject",
    "T6.4": "RAG",
    "T6.5": "scribe",
    "T6.6": "self-observability",
    "T6.7": "reliability",
    "T6.8": "security",
}
"""The eight tasks of `docs/spec/execution-plan-rev9.pdf` §9, by id and the noun the plan uses."""


def _phase_6_table() -> str:
    text = PLAN.read_text()
    start = text.index("## Phase 6 — audited")
    return text[start : text.index("## Phase 5 — audited", start)]


def test_every_phase_6_task_has_a_row_in_the_plans_index() -> None:
    """Two of eight had entries; a reader of the index could not have learned the other six
    existed. Each row also has to carry its fraction, because a row without one is a name."""
    table = _phase_6_table()

    for task, noun in PHASE_6.items():
        row = re.search(rf"^\| \*\*{re.escape(task)}\*\*[^\n]*$", table, re.M)
        assert row, f"{task} ({noun}) has no row in the Phase 6 table"
        assert re.search(r"~\d+%", row.group(0)), f"{task}'s row carries no pre-existing fraction"


def test_the_index_quotes_gate_6_including_the_clause_it_inherits() -> None:
    """Gate 6 re-asserts Gate 4's thresholds with the full pipeline. The latency clause is failing
    today, and a Phase 6 index that did not say so would let the phase discover it at its gate."""
    table = _phase_6_table()

    assert "≤ 3 minutes" in table and "2 per" in table
    assert "latency does not" in table or "latency clause" in table


def test_nothing_current_says_the_action_plane_has_no_task_number() -> None:
    """The claim was true of the reconstruction and false of the plan, and it lived in source,
    tests and three documents. Historical passages may keep it struck through; live prose and code
    may not say it. ADR bodies and the PLAN's own *Discovered omissions* section are records and are
    allowed the phrase because they record why it was ever said."""
    live = [
        *(REPO / "src").rglob("*.py"),
        *(REPO / "tests").rglob("*.py"),
        REPO / "docs" / "ARCHITECTURE.md",
        REPO / "docs" / "THREAT-MODEL.md",
        REPO / "README.md",
    ]
    offenders = []
    for path in live:
        if path.name == Path(__file__).name:
            continue
        text = path.read_text()
        # A struck-through sentence is a correction, not a claim.
        text = re.sub(r"~~.*?~~", "", text, flags=re.S)
        if re.search(r"no task number", text):
            offenders.append(str(path.relative_to(REPO)))
    assert offenders == [], offenders


def test_the_stub_names_the_tasks_that_will_replace_it() -> None:
    from faultline.orchestrator import machine

    assert "T6.2" in (machine.record_approval_outcome.__doc__ or "")
    assert "T6.3" in (machine.record_approval_outcome.__doc__ or "")
