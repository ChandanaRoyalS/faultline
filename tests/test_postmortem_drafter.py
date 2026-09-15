"""T6.5 piece 1b: the drafter, what it is told, and where its prompt is not.

The sharpest test here is the one that fails if someone moves this role into `roles.py`, because
that is the natural place for it and doing so would silently re-stamp every run afterwards.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from faultline.agents import postmortem as pm
from faultline.agents.contracts import Verdict
from faultline.agents.model import ModelResponse
from faultline.agents.postmortem import (
    POSTMORTEM_SYSTEM,
    PostmortemDraft,
    PostmortemScribe,
    document,
    fate_lines,
    proposal_lines,
)
from faultline.context.postmortem import SECTIONS, parse_postmortem_text

VERDICT = Verdict(
    root_cause="the checkout path stopped answering after the container reference moved",
    service="cartservice",
    fault_class="bad_deploy",
    remediation_class="rollback",
    confidence="medium",
    evidence=["r1"],
    reasoning="repeated boot banners with no request handling",
    open_questions=["whether the caller retried"],
)

PROPOSAL = {
    "action_id": "rollback_image",
    "remediation_class": "rollback",
    "target": "cart-service",
    "preconditions": ["a prior container reference is recorded"],
    "blast_radius": "one service; callers see a reset",
    "if_wrong": "if no prior reference exists the proposal has no target",
    "confirm_within_seconds": 120,
}

BODIES = {
    "title": "Checkout stopped answering",
    "concluded": "The checkout path stopped answering at T+2m.",
    "ruled_out": "Repeated boot banners with no request handling; leaves answered normally.",
    "proposal_rested_on": "A prior container reference was in the change log, inside the window.",
    "approval_boundary": "Refused - the target sat outside scoped topology.",
    "never_measured": "Whether the caller retried, and with what timeout.",
}


class ScriptedModel:
    """One canned reply, and it records what it was asked."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.requests: list[Any] = []

    def complete(self, request: Any) -> ModelResponse:
        self.requests.append(request)
        return ModelResponse(
            text=json.dumps(self.payload), input_tokens=10, output_tokens=10, model="scripted"
        )


# --- where the prompt lives -----------------------------------------------------------------


def test_the_drafters_prompt_is_not_in_the_investigations_stamp() -> None:
    """**The test that fails if someone files this role where roles live.**

    `stamp.prompt_digest` hashes every `*_SYSTEM` attribute of `faultline.agents.roles` plus every
    schema in `_CONTRACTS`. A prompt added there moves `runtime_version` on every trajectory
    written afterwards, and this repository treats a different stamp as a different experiment -
    so every at-stamp figure in README and RESULTS would become *the previous stamp*, and T6.5's
    own floors would sit across a boundary from the runs measured against them.

    **And it would be false.** The stamp describes the agent that produced the verdict. This role
    produces none, runs after the trajectory closes, and emits a draft a person must accept.
    """
    from faultline.agents import roles
    from faultline.agents.stamp import _CONTRACTS

    in_roles = [n for n in dir(roles) if n.endswith("_SYSTEM") and "POSTMORTEM" in n]

    assert not in_roles, (
        f"{in_roles} is in roles.py, so it is inside prompt_digest and every run after this "
        "commit is at a new stamp. The postmortem drafter belongs outside it - see "
        "faultline/agents/postmortem.py's module docstring"
    )
    assert PostmortemDraft not in _CONTRACTS, "a schema in _CONTRACTS is in the stamp too"


def test_the_stamp_does_not_move_when_this_module_is_imported() -> None:
    """The weaker half of the test above, and worth having separately: importing the drafter must
    not change the digest, however it comes to be imported."""
    from faultline.agents.stamp import prompt_digest

    before = prompt_digest()
    import faultline.agents.postmortem  # noqa: F401

    prompt_digest.cache_clear()

    assert prompt_digest() == before


def test_the_corpus_digest_is_what_sees_a_postmortem_instead() -> None:
    """The effect a postmortem actually has is on what future runs retrieve, and since Q61 that
    is a frozen input on both axes - `corpus_sha256` when one is added, `corpus_body_sha256` when
    its words change. The mechanism exists where the effect is."""
    from evalharness.evaldb import FINGERPRINT_INPUTS

    assert "corpus_sha256" in FINGERPRINT_INPUTS
    assert "corpus_body_sha256" in FINGERPRINT_INPUTS


# --- what the drafter is told -----------------------------------------------------------------


def test_the_brief_never_carries_the_action_or_its_class() -> None:
    """**§2 enforced before the model writes, not only after.**

    `CLASS_TO_REMEDIATION` is one-to-one across eighteen scenarios, so `rollback_image` and
    `rollback` each hand the reader `bad_deploy` through a lookup table. A model that never sees
    them cannot write them down, and the guard is a better last line than a first one.
    """
    lines = "\n".join(proposal_lines(PROPOSAL))

    assert "rollback" not in lines and "rollback_image" not in lines
    assert "cart-service" in lines, "the target is not the leak; the action is"
    assert "prior container reference" in lines
    assert "if no prior reference exists" in lines, "the falsifier survives"


def test_the_whole_briefing_carries_no_banned_vocabulary() -> None:
    """The brief assembled, not just one helper - including the verdict, which carries
    `fault_class` and `remediation_class` as fields and must not render them."""
    from faultline.context.postmortem import leaked_words

    model = ScriptedModel(BODIES)
    scribe = PostmortemScribe(model)  # type: ignore[arg-type]
    scribe.draft(VERDICT, proposal=PROPOSAL, fate="rejected", fate_reason="outside topology")

    assert scribe.briefing is not None
    assert leaked_words(scribe.briefing.text) == []


def test_an_abstention_is_described_as_a_finding_not_an_absence() -> None:
    """ADR-0028 §4: abstention is a first-class output. *The evidence did not support an action*
    is something a responder wants to read; an empty section is not."""
    assert proposal_lines(None) == [pm.ABSTAINED]
    assert proposal_lines({"action_id": ""}) == [pm.ABSTAINED]


def test_an_unrecorded_fate_says_so_rather_than_inventing_a_decision() -> None:
    """`unknown` is a real state - a proposal nobody acted on - and calling it *declined* would
    put a decision in the record that no one made."""
    assert "does not say" in " ".join(fate_lines("unknown"))
    assert "refused" in " ".join(fate_lines("rejected")).lower()


def test_an_operator_reason_is_quoted_rather_than_paraphrased() -> None:
    """Operator text is untrusted in exactly the sense telemetry is, and reaches the model in the
    user message like every other untrusted string."""
    lines = " ".join(fate_lines("rejected", "the target was outside the blast radius"))

    assert '"the target was outside the blast radius"' in lines


def test_the_system_prompt_forbids_claiming_a_fix_worked() -> None:
    """Registration §1: no scored run executes a remediation, so *the system recovered* would be
    false and would leak the harness into the corpus in one sentence."""
    assert "never claim the system recovered" in POSTMORTEM_SYSTEM.lower()
    assert "nobody ran one" in POSTMORTEM_SYSTEM.lower()


# --- the draft, and the document it becomes ---------------------------------------------------


def test_the_schema_has_one_field_per_section_and_no_room_for_a_sixth() -> None:
    """A `list[Section]` schema would hand the model the freedom the closed section list exists to
    remove, and leave the parser to refuse it after a document had been written."""
    fields = set(PostmortemDraft.model_fields) - {"title"}

    assert len(fields) == len(SECTIONS)


def test_a_draft_renders_to_a_document_the_parser_accepts() -> None:
    """**One validator, reached by both paths.** The drafter's output goes through exactly the
    guard a hand-edited file goes through, which is what the accept route was built for."""
    draft = PostmortemDraft(**BODIES)

    text = document(draft, scenario_id="cart-bad-image-tag", split="dev", incident_id="inc-0007")
    parsed = parse_postmortem_text(text)

    assert parsed.scenario_id == "cart-bad-image-tag"
    assert parsed.origin == "scenario:cart-bad-image-tag"
    assert [name for name, _ in parsed.sections] == list(SECTIONS)


def test_a_leaking_draft_is_refused_at_the_same_boundary_a_file_is() -> None:
    """Prediction 6's scoring surface. The brief withholds the remediation; if the model names one
    anyway, this is where it stops."""
    from faultline.context.postmortem import PostmortemLeakError

    leaking = PostmortemDraft(**{**BODIES, "proposal_rested_on": "We proposed rollback_image."})
    text = document(leaking, scenario_id="cart-bad-image-tag", split="dev", incident_id="i")

    with pytest.raises(PostmortemLeakError, match="rollback_image"):
        parse_postmortem_text(text)


def test_the_sections_come_out_in_the_order_the_document_class_fixes() -> None:
    draft = PostmortemDraft(**BODIES)

    body = document(draft, scenario_id="s", split="dev", incident_id="i")
    order = [line[3:] for line in body.splitlines() if line.startswith("## ")]

    assert order == list(SECTIONS)


def test_a_refused_draft_is_told_why_in_the_user_message_not_the_system_prompt() -> None:
    """`Scribe.draft`'s rule: the system prompt is a frozen input, so a draft that never tripped
    the guard sees byte-for-byte the prompt it would have seen before this argument existed."""
    model = ScriptedModel(BODIES)
    scribe = PostmortemScribe(model)  # type: ignore[arg-type]

    scribe.draft(VERDICT, proposal=PROPOSAL, violation="it mentioned ['rollback_image']")

    request = model.requests[-1]
    assert request.system == POSTMORTEM_SYSTEM
    assert "rollback_image" in request.messages[0]["content"]
