"""The docs pack cannot quietly stop describing the tree (T5.3).

T5.3's reason: *"Reviewers read documents before code."* A reviewer reading `ARCHITECTURE.md` has
no way to tell a current claim from a claim that was true four tasks ago, and **this repository has
already shipped that failure twice** — `docs/RESULTS.md` named two different wrong stamps as HEAD,
and `THREAT-MODEL.md`'s thesis 2 described a structural separation that ADR-0019 §4 had corrected
weeks earlier in a file nobody cross-reads.

So the parts that can be checked mechanically are. Not the prose — a fragment of English is not a
property, and this repository has learned that five times — but the **lists**: the ADRs, the roles,
the tools, the exit codes, the paths. Those are the parts that go stale by addition, which is the
way a document goes stale without anybody editing it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ARCHITECTURE = REPO / "docs/ARCHITECTURE.md"
THREAT_MODEL = REPO / "docs/THREAT-MODEL.md"
PLAN = REPO / "docs/PLAN.md"


# --- a headline that disagrees with the table under it -------------------------------------------


def test_the_phase_4_headline_is_the_sum_of_its_own_table() -> None:
    """**The third stale number in this document**, after `RESULTS.md`'s two wrong HEAD stamps and
    a *"still open"* paragraph contradicted by the section above it.

    The headline read `48 of 55` while its own rows summed to 53.5: it was written when five tasks
    had closed and never moved when two more did. Nothing had to be edited for it to go wrong,
    which is the whole failure mode — and it is a figure **a reader can check by addition**, so
    the check belongs here rather than in a reviewer's attention.
    """
    text = PLAN.read_text()
    headline = re.search(r"\*\*([\d.]+) of (\d+) — \d+% — after", text)
    assert headline, "the Phase 4 headline is gone or reworded; this guard needs updating with it"

    rows = re.findall(r"^\| T4\.[0-9b]+ [^|]*\| *(\d+) *\| *\*{0,2}([\d.]+)\*{0,2} *\|", text, re.M)
    gate = re.search(r"^\| G4 \| *(\d+) *\| *(\d+) *\|", text, re.M)
    assert rows and gate, "the Phase 4 grading table is gone or reshaped"

    clauses = sum(int(c) for c, _ in rows) + int(gate.group(1))
    delivered = sum(float(d) for _, d in rows) + float(gate.group(2))

    assert float(headline.group(1)) == delivered, "the headline disagrees with its own rows"
    assert int(headline.group(2)) == clauses


def test_the_headline_does_not_read_as_a_measurement_having_been_taken() -> None:
    """97% grades *is the machinery built*, not *has the measurement been taken*, and for Phase 4
    those come apart badly. A reader quoting the percentage without that sentence beside it would
    be quoting the opposite of what the phase's own purpose is."""
    text = PLAN.read_text()
    section = text[text.index("## Audit against the specification — Phase 4") :][:4000]

    assert "the wrong number to take away" in section
    assert "has not been read since the stamp last moved" in section


# --- the calibration pool ------------------------------------------------------------------------


def test_the_calibration_harness_can_see_the_judged_runs_on_disk() -> None:
    """**It saw zero for a day**, across a run tree holding 78 judged runs, because it read
    `judge["agreement"]` and the judge writes `root_cause_agreement`. It reported that as *"every
    judged run has a grade (0 recorded)"* — a filter matching nothing, rendered as a finished job.

    Asserted against the real tree rather than a fixture, because the fixture had the same bug:
    it hand-wrote the key the reader expected instead of the one the writer emits.
    """
    from evalharness.calibration_cli import judged_runs

    runs = REPO / "evals/runs"
    if not runs.is_dir():  # pragma: no cover - the tree is committed
        pytest.skip("no run tree")

    found = judged_runs(runs)
    assert len(found) > 30, f"only {len(found)} gradable runs; T4.2 needs ~30"
    assert all(entry["narrative"] for entry in found.values()), "a run with nothing to grade"


@pytest.fixture(scope="module")
def architecture() -> str:
    return ARCHITECTURE.read_text()


@pytest.fixture(scope="module")
def threat_model() -> str:
    return THREAT_MODEL.read_text()


# --- the ADR index goes stale by addition, which is invisible ---------------------------------


def test_every_adr_is_in_the_index(architecture: str) -> None:
    """**The one that would have rotted first.** An index is written once and every later ADR is
    written somewhere else, so the failure needs nobody to edit this file - which is exactly why
    a reviewer cannot tell a complete index from an abandoned one."""
    written = {p.name for p in (REPO / "docs/adr").glob("*.md")} - {"0000-template.md"}
    linked = set(re.findall(r"adr/([0-9]{4}-[a-z0-9-]+\.md)", architecture))

    assert written - linked == set(), "an ADR exists that the index does not list"


def test_every_indexed_adr_exists(architecture: str) -> None:
    """The other direction: a renamed file leaves a link that 404s on GitHub, which is worse than
    a missing entry because it looks like something is there."""
    for name in set(re.findall(r"adr/([0-9]{4}-[a-z0-9-]+\.md)", architecture)):
        assert (REPO / "docs/adr" / name).exists(), f"{name} is linked and does not exist"


def test_the_template_is_not_indexed_as_a_decision(architecture: str) -> None:
    assert "0000-template" not in architecture


# --- the lists that describe the runtime ------------------------------------------------------


def test_the_nine_roles_are_the_nine_the_freeze_records(architecture: str) -> None:
    """`AGENT_ROLES` is nine because it was seven for a whole sweep: `triage` and `proposer` were
    added by Batch B and not added there, so `model_map()` recorded seven models for a run that
    called nine. A document naming a different set is the same defect with a slower fuse."""
    from evalharness.freeze import AGENT_ROLES

    section = architecture[architecture.index("## The nine roles") :]
    section = section[: section.index("\n## ")]

    for role in AGENT_ROLES:
        assert f"`{role}`" in section, f"the role {role!r} is not named in the roles section"
    assert str(len(AGENT_ROLES)) == "9", "the heading says nine; the tuple must agree"


SPELLED = {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine"}
"""Counts as prose spells them. **The sixth instance of one mistake, committed in the file whose
docstring warns about it.**

The first draft asserted `f"{len(surface)} tools" in architecture` and failed: the heading reads
*"five tools"*, because documents spell small numbers. Asserting on a rendering of a number is the
same error as asserting on a fragment of English - the property is the count, and `5` and `five`
are two spellings of it. A `KeyError` here is the honest failure: a surface larger than this map
means somebody has to decide how the document says so.
"""


def test_the_tool_surface_is_the_one_capability_version_hashes(architecture: str) -> None:
    """**Adding a tool moves a frozen key.** `capability_version()` reads the surface by
    introspection precisely so nobody has to remember; this file is the one place that still holds
    a hand-written copy of it, so it gets the same treatment."""
    from evalharness.capability import tool_surface

    surface = tool_surface()
    section = architecture[architecture.index("## The tool surface") :]
    section = section[: section.index("\n---")]

    for tool in surface:
        assert f"`{tool}`" in section
    assert f"{SPELLED[len(surface)]} tools" in section, "the count in the heading must move too"


def test_every_exit_code_is_documented_with_its_integer(architecture: str) -> None:
    """The exit code *is* the contract the harness uses (ADR-0004 keeps the harness outside the
    product), so a table that describes four of five outcomes describes a different contract."""
    from faultline.agents.runner import Exit

    section = architecture[architecture.index("`faultline-investigate`'s exit codes") :]
    section = section[: section.index("\n---")]

    for outcome in Exit:
        assert f"| `{int(outcome)}` |" in section, f"exit code {int(outcome)} is undocumented"


def test_every_path_the_package_table_names_exists(architecture: str) -> None:
    """A path that moved leaves a table entry pointing at nothing, and a reviewer who checks one
    entry and finds it wrong stops trusting the other nine."""
    for path in re.findall(r"^\| `(src/[^`]+)` \|", architecture, re.MULTILINE):
        assert (REPO / path).exists(), f"{path} is in the package table and not on disk"


# --- the diagram fails silently, which is the only reason it is checked here --------------------

MERMAID = re.compile(r"```mermaid\n(.*?)```", re.S)
DECLARED = re.compile(r"(?:^|\s)([A-Za-z][\w]*)(?=[\[\(\{])")
"""A node id immediately followed by a shape opener - `orch[`, `bus[(`, `stop([`. That is how
mermaid declares a node, whether in a subgraph body or inline in an edge."""

EDGE = re.compile(r"^\s*([A-Za-z][\w]*)\s*(?:<?[-=.]{2,}>?|[-=.]{1,2}\|[^|]*\|)")
"""The left-hand end of an edge line. Only the left end: the right end may declare its node
inline, and this guard is about ids that were *meant* to refer to something."""


def test_the_diagrams_reference_no_node_that_was_never_declared() -> None:
    """**A typo'd id does not fail — it draws a new empty box**, which renders as a diagram with
    one more node than the author wrote and no error anywhere. That is the same class of failure
    as T5.1's washed-out text: invisible to a test suite, obvious on sight, and only caught if
    somebody looks. This catches the half a regex can catch; the diagrams were also rendered in
    Chromium and read, which is what caught a clipped edge label and a false Postgres → notifier
    reading that no assertion would have.
    """
    for block in MERMAID.findall(ARCHITECTURE.read_text()):
        declared = set(DECLARED.findall(block)) | set(
            re.findall(r"^\s*subgraph\s+([A-Za-z][\w]*)", block, re.MULTILINE)
        )
        referenced = {
            match.group(1)
            for line in block.splitlines()
            if (match := EDGE.match(line)) and not line.strip().startswith(("subgraph", "style"))
        }

        assert referenced <= declared, (
            f"{sorted(referenced - declared)} starts an edge and is declared nowhere. "
            "Mermaid draws an empty box for it rather than failing."
        )


def test_every_fence_is_closed_and_declares_a_diagram_type() -> None:
    """An unclosed fence swallows the rest of the document into a code block, and GitHub shows no
    error for either failure."""
    text = ARCHITECTURE.read_text()
    blocks = MERMAID.findall(text)

    assert text.count("```mermaid") == len(blocks), "a mermaid fence is not closed"
    for block in blocks:
        assert block.strip().split("\n")[0].split()[0] in {"flowchart", "graph", "stateDiagram-v2"}


# --- the thesis numbers are load-bearing in source comments ------------------------------------


def test_every_thesis_the_source_cites_exists(threat_model: str) -> None:
    """**Renumbering is the silent failure here.** `api/view.py`, `api/incidents.py`,
    `ingest/app.py` and `tools/envelope.py` all cite a thesis *by number*. Inserting a thesis at
    the top would leave every one of those comments pointing at the wrong argument, with nothing
    failing - which is why theses 4, 5 and 6 were appended rather than ordered by importance."""
    cited = set()
    for source in (REPO / "src").rglob("*.py"):
        cited |= {int(n) for n in re.findall(r"[Tt]hesis ([0-9]+)", source.read_text())}

    assert cited, "the guard is worthless if nothing cites a thesis; it would pass vacuously"
    headings = {int(n) for n in re.findall(r"^## Thesis ([0-9]+)", threat_model, re.MULTILINE)}
    assert cited <= headings, f"source cites {sorted(cited - headings)}, which no heading defines"


def test_the_theses_are_numbered_without_gaps(threat_model: str) -> None:
    """A gap means one was deleted, and a deleted thesis is a claim withdrawn silently."""
    numbers = [int(n) for n in re.findall(r"^## Thesis ([0-9]+)", threat_model, re.MULTILINE)]

    assert numbers == list(range(1, len(numbers) + 1))


# --- the correction is the point of the rewrite, so it has to stay --------------------------------


def test_thesis_two_describes_the_write_path_that_now_exists(threat_model: str) -> None:
    """**The defect this rewrite fixed.** The old text read *"Write credentials exist only in the
    executor service, which validates actions against an allowlist and a single-use, action-bound
    human-approval token"* - present tense, about a component that is not built (it is T6.2/T6.3).

    ADR-0019 §4 had already corrected the credential half (*"read-only is therefore a property of
    the tool surface, not of the credential ... that has to be stated rather than assumed by anyone
    reading thesis 2"*) and this file never heard about it. Asserted structurally rather than by
    string match: **if an executor is ever built, this test is what tells you to rewrite thesis 2**,
    and it fails loudly instead of leaving the document describing the old world.

    **And this guard did not fire when the executor was built.** It matched on module *stems*, and
    `faultline/executor/` contains `core.py`, `cli.py`, `tokens.py`, `audit.py`, `settings.py` and
    `app.py` - not one of which has "executor" in its file name. T6.2 rewrote thesis 2 because
    somebody noticed, which is exactly the thing the test was written to make unnecessary. It
    fired at T6.3, a day late, on `api/executor_client.py`. A guard that matches file names is a
    guard about file names.

    Rewritten to watch the **packages**, and to hold what is true now rather than what was: the
    executor exists, the approval surface exists, and thesis 2 has to describe both - including
    which process holds the minting key, which is the escalation `PREREGISTRATION-T6.3.md` §2.1
    registered.
    """
    src = REPO / "src"
    executor_exists = (src / "faultline" / "executor" / "core.py").exists()
    surface_exists = (src / "faultline" / "api" / "approvals.py").exists()

    if executor_exists:
        # The sentence stays in the document - struck, dated, with the paragraph it headed kept
        # underneath, because it was true for the whole of Phases 3-5 and the distinction it drew
        # still matters. What it must not be is *standing*.
        assert "~~**There is no executor.**~~" in threat_model, (
            "the executor package exists, so thesis 2's old claim has to be struck rather than "
            "left as an assertion (or deleted, which would lose why it was ever true)"
        )
        assert "What holds since T6.2" in threat_model
    if surface_exists:
        assert "the approval surface holds the minting key" in threat_model, (
            "a write surface now exists and holds the key that signs approvals; thesis 2 has to "
            "say so, and say what bounds a compromise of it (PREREGISTRATION-T6.3.md §2.1)"
        )


def test_the_status_line_does_not_claim_the_security_pass_happened(threat_model: str) -> None:
    """T6.8 has not run. A threat model that reads as though it has is the single most misleading
    document this repository could ship, because it is the one a reviewer is least able to check."""
    opening = threat_model[: threat_model.index("## Scope")]

    assert "adversarial testing not done" in opening
    assert "Nothing below has been attacked" in opening


# --- the register is the register ----------------------------------------------------------------


QUEUE = REPO / "docs/QUEUE.md"
Q_MENTION = re.compile(r"\bQ(\d{1,3})\b")
Q_ROW = re.compile(r"^\|\s*(?:~~|\*\*)+Q(\d{1,3})(?:~~|\*\*)+\s*\|", re.MULTILINE)


def test_every_queued_change_has_a_row() -> None:
    """A `Q` number cited anywhere in the record resolves to a row in the register.

    *"A PLAN entry saying 'queued' with no row here is the defect this file exists to prevent."*

    **This test would not have caught the defect that prompted it, and claiming otherwise would be
    the same optimism four T6.4 write-ups already had to correct.** T6.4 deferred five clauses of
    its plan row *by name* - "cross-encoder rerank", "recency weighting" - and never assigned them
    numbers, so there was no `Q` to look up and nothing here to fail. Q41-Q45 exist now; the hole
    they came through is still open.

    What this does hold is narrower and still real: **once a change has a number, the number
    resolves.** A struck row counts, because dropping a change is a decision and the register
    records decisions. Whether a row is any *good* is a reading, and this repository has learned
    not to assert readings mechanically.

    The uncovered case - a deferral written in prose with no number at all - is caught by a person
    reading a pre-registration against the register, which is how this one was found.
    """
    rows = {int(n) for n in Q_ROW.findall(QUEUE.read_text())}
    assert rows, "no queue rows parsed; this test would pass vacuously"

    mentioned: dict[int, set[str]] = {}
    for path in sorted((REPO / "docs").rglob("*.md")) + sorted((REPO / "evals").rglob("*.md")):
        for number in Q_MENTION.findall(path.read_text()):
            mentioned.setdefault(int(number), set()).add(str(path.relative_to(REPO)))

    orphans = {n: sorted(where) for n, where in mentioned.items() if n not in rows}
    assert not orphans, f"cited with no row in QUEUE.md: {orphans}"
