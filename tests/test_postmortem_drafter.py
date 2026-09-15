"""T6.5 piece 1b: the drafter, what it is told, and where its prompt is not.

The sharpest test here is the one that fails if someone moves this role into `roles.py`, because
that is the natural place for it and doing so would silently re-stamp every run afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path
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
    assert proposal_lines({"action_id": ""})[0] == pm.ABSTAINED
    assert "not recorded" in "\n".join(proposal_lines({"action_id": ""})), (
        "an abstention with no recorded reasoning says so, rather than dropping the lines and "
        "reading as though the question was never asked"
    )


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


# --- against every proposal this repository has actually recorded -------------------------------

RUNS = Path(__file__).resolve().parents[1] / "evals" / "runs"


def recorded_proposals() -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    if not RUNS.is_dir():
        return out
    for path in sorted(RUNS.glob("*/*-verdict.json")):
        try:
            payload = json.loads(path.read_text())
        except Exception:
            continue
        if payload.get("baseline") or not payload.get("proposal"):
            continue
        out.append((path.parent.name, payload["proposal"]))
    return out


def test_no_recorded_proposal_leaks_into_a_brief() -> None:
    """**The defect this test was written after, and the reason the fixture above was not enough.**

    Over the 121 agent verdict artifacts carrying a proposal, `risk` names `restart` 58 times,
    `revert_config` 36 and `rollback_image` 24 - because the proposer is proposing an action, so
    its prose about risk and blast radius is prose about that action. The first version of
    `proposal_lines` passed `blast_radius` and `if_wrong` through verbatim and **21 of those 121
    briefs would have carried banned vocabulary**. It passed its tests because the synthetic
    fixture happened not to say `restart`.

    Real data, every one of them, or this test is the same mistake again.
    """
    from faultline.context.postmortem import leaked_words

    recorded = recorded_proposals()
    if not recorded:
        return
    leaking = [
        (run, leaked_words("\n".join(proposal_lines(proposal))))
        for run, proposal in recorded
        if leaked_words("\n".join(proposal_lines(proposal)))
    ]

    assert not leaking, f"{len(leaking)} of {len(recorded)} recorded proposals leak: {leaking[:3]}"


def test_a_withheld_field_says_so_rather_than_reading_as_unrecorded() -> None:
    """A dropped line reads as *nothing was recorded*, which is a different and false statement."""
    leaking = {**PROPOSAL, "risk": "Restarting paymentservice would discard in-flight attempts."}

    lines = "\n".join(proposal_lines(leaking))

    assert pm.WITHHELD in lines
    assert "Restarting" not in lines


def test_an_abstentions_reasoning_travels_with_it_where_the_guard_allows() -> None:
    """Registration §1 wants *"abstained with the abstention's reasoning"*; §2 forbids naming the
    remediation, and Q63 settled that §2 governs. Honouring §1 as far as §2 permits is better than
    dropping the clause because the two disagree."""
    clean = {
        "action_id": "",
        "expected_effect": "No action: the dependency was never measured.",
        "if_wrong": "Wrong if a saturation measurement shows a climb before onset.",
    }

    lines = "\n".join(proposal_lines(clean))

    assert "never measured" in lines
    assert "shows a climb before onset" in lines


def test_a_baseline_run_is_not_a_donor() -> None:
    """B0 and B1 are controls for the pipeline, and a postmortem of a control is a document about
    a lookup table."""
    from faultline.agents.postmortem import RecordError, record_from_run

    run = RUNS
    baselines = [
        p.parent
        for p in sorted(RUNS.glob("*/*-verdict.json"))
        if json.loads(p.read_text()).get("baseline")
    ]
    if not baselines:
        return
    run = baselines[0]

    with pytest.raises(RecordError, match="baseline"):
        record_from_run(run)


def test_a_real_run_reads_into_a_record_the_drafter_can_use() -> None:
    """End to end over the archive: the artifact the scorer read is the artifact the drafter
    drafts from, which is what keeps a postmortem about a run that was actually scored."""
    from faultline.agents.postmortem import record_from_run

    usable = []
    for path in sorted(RUNS.glob("*/*-verdict.json")):
        payload = json.loads(path.read_text())
        if payload.get("baseline") or not (payload.get("verdict") or {}).get("root_cause"):
            continue
        if not (path.parent / "manifest.json").is_file():
            continue
        usable.append(path.parent)
    if not usable:
        return

    record = record_from_run(usable[-1])

    assert record.scenario_id
    assert record.verdict.root_cause
    assert record.fate in {"approved", "rejected", "escalated", "abstained", "unknown"}


# --- the drafting command ----------------------------------------------------------------------


class RefusingModel:
    """Answers with a document that names a remediation, every time."""

    def __init__(self) -> None:
        self.calls = 0
        self.seen: list[str] = []

    def complete(self, request: Any) -> ModelResponse:
        self.calls += 1
        self.seen.append(request.messages[0]["content"])
        leaking = {**BODIES, "proposal_rested_on": "We proposed rollback_image on the service."}
        return ModelResponse(
            text=json.dumps(leaking), input_tokens=1000, output_tokens=500, model="scripted"
        )


def a_record() -> Any:
    from faultline.agents.postmortem import Record

    return Record(
        scenario_id="cart-bad-image-tag",
        incident_id="inc-0007",
        verdict=VERDICT,
        proposal=PROPOSAL,
        fate="unknown",
    )


def test_a_clean_draft_comes_back_with_its_tokens_counted() -> None:
    from faultline.agents.postmortem import draft_one

    drafted = draft_one(a_record(), ScriptedModel(BODIES))  # type: ignore[arg-type]

    assert drafted.refusals == []
    assert drafted.attempts == 1
    assert drafted.tokens_in and drafted.tokens_out
    assert "## What was never measured" in drafted.text


def test_a_scenario_whose_every_draft_leaks_still_reports_what_it_spent() -> None:
    """**Q53's failed-arm lesson, applied before the first dollar rather than after it.**

    That driver printed `$0.00` while a failed arm burned tokens, because it priced the verdict
    rather than the work. A scenario that produced nothing here cost exactly as much as one that
    produced a document, and a ceiling that cannot see the failures is not a ceiling.
    """
    from faultline.agents.postmortem import RefusedError, draft_one

    model = RefusingModel()

    with pytest.raises(RefusedError) as refused:
        draft_one(a_record(), model, attempts=2)  # type: ignore[arg-type]

    assert model.calls == 2, "both attempts were made"
    assert len(refused.value.refusals) == 2
    assert refused.value.tokens_in == 2000 and refused.value.tokens_out == 1000
    priced = refused.value.tokens_in / 1_000_000 * 5.0 + refused.value.tokens_out / 1_000_000 * 25.0
    assert priced > 0, "the failure has a price, and a caller that ignored it would walk a ceiling"


def test_the_guards_own_message_is_what_the_next_draft_is_told() -> None:
    """T3.8's shape, and the reason the refusal text is worth keeping: the second attempt is told
    exactly what the parser refused, in the user message, not a paraphrase of it."""
    import contextlib

    from faultline.agents.postmortem import RefusedError, draft_one

    model = RefusingModel()
    with contextlib.suppress(RefusedError):
        draft_one(a_record(), model, attempts=2)  # type: ignore[arg-type]

    assert len(model.seen) == 2
    first, second = model.seen
    assert "refused" not in first, "the first draft has no violation to be told about"
    assert "rollback_image" in second, "the second is told what the guard caught"


def test_the_drafts_do_not_land_where_the_seeder_reads() -> None:
    """**The gate is a person, not a directory.** A draft written into
    `evals/scenarios/artifacts/dev/` would be one accepted row away from the corpus, and
    *"never auto-published"* would be a formality between two folders."""
    from evalharness import postmortem_cli

    assert "artifacts" not in str(postmortem_cli.DEFAULT_OUT)
    assert postmortem_cli.DEFAULT_OUT.name == "postmortems"


def test_the_command_defaults_to_the_registrations_budget() -> None:
    """§6 budgets $5 for postmortem generation inside a $55 ceiling. A budget revised upward
    mid-task is not a budget, so it is the default rather than a suggestion in prose."""
    from evalharness import postmortem_cli

    assert postmortem_cli.MAX_USD == 5.0
    assert postmortem_cli.parser().parse_args([]).max_usd == 5.0


def test_only_dev_scenarios_are_donors() -> None:
    """Registration §8: no holdout scenario is spent on a learning-effect measurement, and a
    holdout postmortem in the corpus is an answer key nothing downstream would notice."""
    from evalharness import postmortem_cli

    scenarios = Path(__file__).resolve().parents[1] / "evals" / "scenarios"
    if not scenarios.is_dir():
        return

    found = postmortem_cli.dev_scenarios(scenarios)

    assert found, "the catalog has dev scenarios"
    assert "ad-memory-squeeze" in found
    for scenario_id in found:
        import yaml

        loaded = yaml.safe_load((scenarios / f"{scenario_id}.yaml").read_text())
        assert loaded["split"] == "dev"


def test_one_postmortem_per_scenario_not_per_run() -> None:
    """A scenario with three scored runs has three tellings of one incident. Seeding all three
    would put it in the corpus three times and let one document win a query with three hits -
    ADR-0018's argument for not storing a narrative twice."""
    from faultline.agents.postmortem import donor_runs

    if not RUNS.is_dir():
        return

    donors = donor_runs(RUNS)

    assert donors, "the archive has usable donors"
    assert len(donors) == len(set(donors)), "keyed by scenario, so one each by construction"
