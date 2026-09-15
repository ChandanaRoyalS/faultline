"""T6.5's document class: what a postmortem may say, and where it sits in the corpus.

Most of what is asserted here is a **refusal**. The registration's §2 is a leak rule that costs
the artefact realism, and a rule with no test is an intention; the tests that matter are the
ones showing the guard fires on the sentence a careful drafter would actually write.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.context import postmortem as pm
from faultline.context.postmortem import (
    SECTIONS,
    Postmortem,
    PostmortemError,
    PostmortemLeakError,
    chunk_postmortem,
    leaked_words,
    parse_postmortem,
    remediation_vocabulary,
    render,
)

FRONT = """---
scenario_id: cart-bad-image-tag
origin: scenario:cart-bad-image-tag
split: dev
incident_id: inc-0007
recorded_from: 2026-09-01T03:11:37Z
---
"""

BODIES = {
    "What the investigation concluded": "The checkout path stopped answering at 03:12.",
    "What ruled the alternatives out": (
        "Repeated boot banners with no request handling, so the process was starting and not "
        "serving. Downstream leaves answered normally throughout."
    ),
    "What the proposal rested on": (
        "A prior container reference for this service was in the change log, and the change "
        "sat inside the window. Its falsifier: if the prior reference were absent the proposal "
        "had no target."
    ),
    "What happened at the approval boundary": "Refused - the target sat outside scoped topology.",
    "What was never measured": "Whether the caller retried, and with what timeout.",
}


def document(**overrides: str) -> str:
    bodies = {**BODIES, **overrides}
    lines = [FRONT, "# Checkout stopped answering at 03:12", ""]
    for section in SECTIONS:
        lines += [f"## {section}", "", bodies[section], ""]
    return "\n".join(lines)


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "postmortem.md"
    path.write_text(text)
    return path


# --- the shape --------------------------------------------------------------------------------


def test_a_well_formed_postmortem_parses(tmp_path: Path) -> None:
    parsed = parse_postmortem(write(tmp_path, document()))

    assert parsed.scenario_id == "cart-bad-image-tag"
    assert parsed.origin == "scenario:cart-bad-image-tag"
    assert parsed.document_id == "postmortem:cart-bad-image-tag"
    assert [name for name, _ in parsed.sections] == list(SECTIONS)


def test_the_section_list_is_closed_so_an_outcome_claim_has_nowhere_to_go(tmp_path: Path) -> None:
    """**The registration's §1 as a parse error.** No scored run executes a remediation, so
    *"Did the fix work"* has no true answer - and an open section list is one heading away from
    a postmortem that answers it anyway, in the corpus, forever."""
    text = document() + "\n## Did the fix work\n\nThe service recovered.\n"

    with pytest.raises(PostmortemError, match="exactly"):
        parse_postmortem(write(tmp_path, text))


def test_a_postmortem_without_its_limits_section_is_refused(tmp_path: Path) -> None:
    """*What was never measured* is not optional. A document that states conclusions and drops
    their limits is the shape every registration in this repo exists to avoid."""
    text = document()
    text = text[: text.index("## What was never measured")]

    with pytest.raises(PostmortemError, match="exactly"):
        parse_postmortem(write(tmp_path, text))


def test_an_empty_section_is_not_a_short_one(tmp_path: Path) -> None:
    with pytest.raises(PostmortemError, match="empty"):
        parse_postmortem(write(tmp_path, document(**{"What was never measured": ""})))


def test_an_origin_that_disagrees_with_the_scenario_is_refused(tmp_path: Path) -> None:
    """`origin` is the exclusion key. A wrong one is not a typo: the postmortem is excluded from
    the wrong scenario and read by the one it is about."""
    text = document().replace("origin: scenario:cart-bad-image-tag", "origin: scenario:cart-oops")

    with pytest.raises(PostmortemError, match="exclusion key"):
        parse_postmortem(write(tmp_path, text))


def test_acceptance_is_not_a_field_on_the_document(tmp_path: Path) -> None:
    """**The field this class carried for one commit, and why it is gone.**

    1a made `accepted_by` required so the class could not represent an unaccepted document, and
    its own docstring said what was wrong with that: *a name in front matter is a string anyone
    can type*. Acceptance is an append-only row naming the authenticated caller, and a field
    beside it would be a second answer to one question, editable by whoever edits the file.

    `extra="forbid"`, so the old spelling is now a parse error rather than a value nobody reads.
    """
    parsed = parse_postmortem(write(tmp_path, document()))

    assert not hasattr(parsed, "accepted_by")
    assert not hasattr(parsed, "accepted_at")


def test_a_postmortem_round_trips_through_render(tmp_path: Path) -> None:
    parsed = parse_postmortem(write(tmp_path, document()))

    assert parse_postmortem(write(tmp_path, render(parsed))) == parsed


# --- the leak boundary ------------------------------------------------------------------------


def test_the_remediation_vocabulary_is_read_from_the_catalog_not_listed_here() -> None:
    """An allowlist entry added at T6.2 is guarded the day it lands, not the day someone
    remembers this module. `knowledge/allowlist.yaml` is read-only by construction (ADR-0032),
    which is what makes deriving a guard from it safe."""
    from faultline.context.allowlist import load_allowlist

    vocabulary = remediation_vocabulary()

    for action in load_allowlist().actions:
        assert action.id in vocabulary, f"{action.id} is an action a postmortem could name"


def test_every_performable_remediation_class_is_banned() -> None:
    """**Why the ban exists at all.** `CLASS_TO_REMEDIATION` is one-to-one across all eighteen
    scenarios, so a named remediation is the fault class in another spelling and a transfer
    measurement over it would be measuring a lookup table."""
    from evalharness.baselines import CLASS_TO_REMEDIATION

    vocabulary = remediation_vocabulary()

    for fault_class, remediation in CLASS_TO_REMEDIATION.items():
        assert remediation in vocabulary, (
            f"{remediation!r} names {fault_class!r} through a one-to-one mapping"
        )


def test_the_word_that_hurts_is_banned_anyway() -> None:
    """**`restart`, and `flag-service-crashloop`'s whole observable is restart looping.**

    Banned regardless, because `dependency_latency` maps to `restart`. The registration wrote
    the paraphrase itself in §2 - *repeated boot banners with no request handling* - which is
    the sentence a responder writes and names no remediation. That is the cost §7 records: the
    guard is survivable, and survivable by paraphrase.
    """
    assert leaked_words("The service was restarted and came back.") == ["restart"]
    assert leaked_words("Repeated boot banners with no request handling.") == []


def test_scale_is_not_banned_and_the_asymmetry_is_principled() -> None:
    """`scale_service` is `unperformable` (ADR-0029: Compose refuses to scale a service
    declaring `container_name`, and 25 of this world's services declare one), so no scenario
    maps to it and the word carries no class. Banning ordinary English that leaks nothing is
    how `fault` cost run 3 its entire narrative."""
    assert leaked_words("The incident did not scale beyond one service.") == []
    assert "scale_service" in remediation_vocabulary(), "the id is still an action id"


def test_an_action_id_is_caught_in_three_spellings() -> None:
    """The underscored id is what a model copies out of a proposal record; the other two are
    what it writes when it is paraphrasing. `tests/test_runbooks.py` matches scenario ids the
    same way under ADR-0036."""
    for spelling in ("rollback_image", "rollback-image", "rollback image"):
        assert leaked_words(f"We proposed {spelling} on the service.") != [], spelling


def test_the_existing_harness_rules_still_apply() -> None:
    """A postmortem joins the same corpus a narrative does and is retrieved by the same agents,
    so the injector's vocabulary and the four class labels are banned here too."""
    assert "bad_deploy" in leaked_words("The root cause was a bad_deploy.")
    assert "injected" in leaked_words("The latency was injected at 03:10.")


def test_the_guard_keeps_the_narrative_guard_s_false_positive_fix() -> None:
    """`default` contains `fault`, and that cost run 3 its whole narrative
    (`docs/evidence/t4.1-first-scored-run/`). The boundary matcher is shared with the narrative
    guard precisely so this cannot regress in one place and not the other."""
    sentence = "It is unsettled whether 6380 replaced a working endpoint or was a default."

    assert leaked_words(sentence) == []


def test_a_leaking_postmortem_fails_the_parse_not_the_seed(tmp_path: Path) -> None:
    """**One layer earlier than the narrative's guard runs, deliberately.** A narrative is
    checked in `render` because the scribe composes it; a postmortem can also arrive as a
    hand-edited file, and a guard only the writing path runs is one an editor walks around."""
    text = document(**{"What the proposal rested on": "We proposed rollback_image on the service."})

    with pytest.raises(PostmortemLeakError, match="rollback_image"):
        parse_postmortem(write(tmp_path, text))


def test_a_postmortem_may_not_name_its_own_scenario_in_prose(tmp_path: Path) -> None:
    """The scenario belongs in `origin`, where the exclusion reads it. In the text it is the
    answer key, exactly as it is in a runbook (ADR-0036)."""
    text = document(
        **{"What the investigation concluded": "This was the cart_bad_image_tag incident."}
    )

    with pytest.raises(PostmortemLeakError, match="cart-bad-image-tag"):
        parse_postmortem(write(tmp_path, text), scenario_ids={"cart-bad-image-tag"})


# --- where it sits in the corpus ---------------------------------------------------------------


def parsed_fixture(tmp_path: Path) -> Postmortem:
    return parse_postmortem(write(tmp_path, document()))


def test_a_postmortem_chunk_is_excluded_by_the_column_that_already_excludes(
    tmp_path: Path,
) -> None:
    """**`origin` is shared with the narrative on purpose.** T4.1b's self-exclusion covers the
    postmortem for free, and §4's WITHOUT arm - which excludes every dev scenario in the class -
    reaches it through the same column with no second mechanism."""
    chunks = chunk_postmortem(
        parsed_fixture(tmp_path),
        scenario_fingerprint="abc123",
        fault_class="bad_deploy",
        source_path=tmp_path / "postmortem.md",
    )

    assert {c.origin for c in chunks} == {"scenario:cart-bad-image-tag"}


def test_the_document_id_does_not_collide_with_the_narrative_s(tmp_path: Path) -> None:
    """**The bug this pairing avoids, stated so it stays avoided.** `_reconcile` prunes rows by
    `document_id`; reusing `scenario:<id>` would make the seeder's narrative pass and postmortem
    pass each delete the other's rows, quietly, on every seed."""
    chunks = chunk_postmortem(
        parsed_fixture(tmp_path),
        scenario_fingerprint="abc123",
        fault_class="bad_deploy",
        source_path=tmp_path / "postmortem.md",
    )

    assert {c.document_id for c in chunks} == {"postmortem:cart-bad-image-tag"}
    assert all(c.document_id != c.origin for c in chunks), "a narrative's are equal; these differ"


def test_one_chunk_per_section_indexed_in_order(tmp_path: Path) -> None:
    """ADR-0018: the section is the unit, because that is what a live incident resembles."""
    chunks = chunk_postmortem(
        parsed_fixture(tmp_path),
        scenario_fingerprint="abc123",
        fault_class="bad_deploy",
        source_path=tmp_path / "postmortem.md",
    )

    assert [c.section for c in chunks] == list(SECTIONS)
    assert [c.section_index for c in chunks] == list(range(len(SECTIONS)))
    assert {c.fault_class for c in chunks} == {"bad_deploy"}, "metadata, not text"


def test_there_is_no_observed_section_so_a_postmortem_is_not_a_copy() -> None:
    """*What was observed* is the narrative's first section and is already in the corpus for
    every dev scenario with a bundle. Repeating it would double one incident's symptom prose in
    every query that returns both, and reduce T6.5 to the scheduling change the design note's
    §4.1 says would not be worth doing."""
    assert not any("observed" in section.lower() for section in SECTIONS)


def test_nothing_here_writes_to_the_store() -> None:
    """`context/seed.py` is the only writer to the pgvector store, and this module is a parser
    and a chunker. A document class that could seed itself would put an unaccepted postmortem in
    the corpus the moment one parsed."""
    source = Path(pm.__file__).read_text()

    assert not any(name in source for name in ("PastIncidentStore", "INSERT", "store.add"))
