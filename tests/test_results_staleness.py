"""`docs/RESULTS.md` may not claim a stamp is HEAD unless it is (T4.4).

**This is the most externally-visible document in the repository.** A reader deciding whether to
believe the figures reads it, and it is the one place where a stale claim costs the most.

It went wrong in the way documents with good discipline go wrong. RESULTS.md *had* a staleness
banner - *"HEAD is no longer this pipeline"* - written on 2026-09-02 and correct that day. Then
the stamp moved four more times, and **the banner itself went stale**: it named
`prompts:a7330c098770` as HEAD while HEAD had become `ba8684b01201`. Three other passages still
called `prompts:1b0e7cbb4c47` *"current HEAD"*, five generations after it stopped being one.

A banner is a snapshot. The fix for a snapshot going stale is not a better snapshot; it is a check
that fails when it does.
"""

from __future__ import annotations

import re
from pathlib import Path

RESULTS = Path("docs/RESULTS.md")

STAMP = re.compile(r"`prompts:([0-9a-f]{12})`")
"""A stamp as the document writes one."""

PRESENT_TENSE_CLAIMS = (
    re.compile(r"HEAD(?: today)? is `prompts:([0-9a-f]{12})`"),
    re.compile(r"`prompts:([0-9a-f]{12})`[^.|]{0,60}?\bis HEAD\b"),
    re.compile(r"`prompts:([0-9a-f]{12})`[^.|]{0,60}?current HEAD"),
    re.compile(r"current HEAD[^.|]{0,60}?`prompts:([0-9a-f]{12})`"),
)
"""**Explicit present-tense claims, not a proximity window.**

The first version of this guard flagged any stamp within 90 characters of the word HEAD. That is
a fragment of English, not a property: it fired on the corrected lineage sentence, which lists
four superseded stamps *and then* says which one is current - a sentence that is entirely correct
and which the guard called four violations.

It is the same mistake as asserting the word "adjacent" is absent from a rubric that lists all
three levels, and as asserting "min" is absent from a passage quoting *"three minutes to a
report"*. Three times in one session, which is enough: **a substring near another substring is
not a claim.** These patterns match the claim.

The tense carries the whole distinction. *"is HEAD"* and *"current HEAD"* are assertions about
the present and go stale; ***"was HEAD when it ran"* is a historical statement and never does** -
which is exactly how the corrected passages are worded.
"""


def head_claims() -> list[str]:
    """Every stamp the document asserts, in the present tense, is HEAD."""
    text = RESULTS.read_text()
    return [stamp for pattern in PRESENT_TENSE_CLAIMS for stamp in pattern.findall(text)]


def test_no_stamp_is_called_head_unless_it_is() -> None:
    """**The guard, and the reason it exists rather than a re-read.**

    Every quoted stamp sitting next to the word HEAD is a claim about the present, and a document
    full of claims about the present is a document that expires. This fails the moment the stamp
    moves, which is the only moment at which fixing it is cheap.
    """
    from faultline.agents.stamp import prompt_digest

    current = prompt_digest()
    wrong = sorted({stamp for stamp in head_claims() if stamp != current})

    assert wrong == [], (
        f"docs/RESULTS.md calls {wrong} HEAD, but HEAD is {current}. The stamp moved and the "
        "document did not. Update the passage, or reword it so it describes a past generation "
        "rather than the present one."
    )


def test_no_document_anywhere_says_head_is_a_stamp_that_it_is_not() -> None:
    """**The same defect lives next door, and the first version of this guard did not look.**

    `RESULTS.md` was fixed and this file was scoped to it - so the identical stale claim sat in
    `docs/PLAN.md` (twice) and in `README.md`'s reach, unexamined, because the guard was pointed
    at the file where the problem had been noticed rather than at the class of problem.

    Only the unambiguous ordering is matched here: `HEAD is <stamp>` asserts the present in any
    document and cannot be a report of someone else's claim. The looser patterns above stay
    scoped to RESULTS.md, whose prose is disciplined enough for them; applied repository-wide they
    flag passages that *describe* a stale claim, which is the fragment-of-English mistake again.

    **PLAN.md is a chronological log, and a log must not use the present tense for a moving
    value.** Both offending entries were correct on the day they were written; the fix is
    "HEAD became X" and "HEAD was then X", not a newer stamp.
    """
    from faultline.agents.stamp import prompt_digest

    current = prompt_digest()
    asserts_head = re.compile(r"HEAD(?: today)? is \*{0,2}`(?:prompts:)?([0-9a-f]{12})`")
    stale: list[str] = []
    for path in [*sorted(Path("docs").rglob("*.md")), Path("README.md")]:
        if not path.is_file():
            continue
        if path.parts[:2] == ("docs", "adr"):
            # **ADRs are exempt, and this is a category distinction rather than an escape hatch.**
            # An ADR records what was decided and what was true when it was decided; a sentence in
            # one is dated by construction, not an assertion about the present, and editing it to
            # stay current would destroy the only thing it is for. ADR-0023 is the case in point -
            # it says HEAD is `53fafe9c12bc`, which expired five stamps ago - and it carries a
            # dated addendum saying so, which is the mitigation this exemption owes a reader.
            continue
        for stamp in asserts_head.findall(path.read_text()):
            if stamp != current:
                stale.append(f"{path}: {stamp}")

    assert stale == [], (
        f"{stale} — HEAD is {current}. A document asserting the present tense about a value that "
        "moves will go stale; in a chronological log, write what HEAD *became*."
    )


def test_the_document_still_says_which_generation_its_figures_describe() -> None:
    """The guard above must not be satisfiable by deleting every mention of the stamp. The figures
    describe *some* pipeline, and a results document that does not say which is worse than one
    that says the wrong thing - at least the wrong thing is checkable."""
    text = RESULTS.read_text()

    assert STAMP.search(text), "no stamp is named at all"
    assert "1b0e7cbb4c47" in text, "the generation the figures were recorded under"


def test_the_staleness_notice_names_the_current_stamp() -> None:
    """A notice saying *"HEAD is no longer this pipeline"* is only useful if a reader can tell
    what HEAD became. The 2026-09-02 notice named a stamp that has since moved four times."""
    from faultline.agents.stamp import prompt_digest

    assert prompt_digest() in RESULTS.read_text(), (
        "the staleness notice does not name the current stamp, so a reader cannot tell how far "
        "behind the figures are"
    )
