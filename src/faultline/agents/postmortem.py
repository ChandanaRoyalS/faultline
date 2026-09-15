"""The postmortem drafter (T6.5, piece 1b): the record a responder takes to the next incident.

The document class, its closed section list and its leak guard are `context/postmortem.py`. This
is the agent that writes one, **after the incident closed**, from what the record holds.

## Why this prompt is not in `roles.py`, and why that is a decision rather than a filing choice

`stamp.prompt_digest` hashes **every `*_SYSTEM` attribute of `faultline.agents.roles`** together
with every schema in `contracts._CONTRACTS`, and `runtime_version` is that digest. So a role
prompt added to `roles.py` moves the stamp on every trajectory written afterwards, and this
repository treats a different stamp as a different experiment: every at-stamp figure in README and
RESULTS would become *the previous stamp*, and T6.5's own floors - sweep 12's A/A noise, the
catalog's MDE - would sit on the far side of a boundary from the runs being measured against them.

**That cost would buy a false statement.** The stamp describes *the agent that produced the
verdict*. This role produces no verdict, runs after the trajectory is closed, and emits a draft a
person must accept before it reaches anything. A run's comparability does not depend on it, and
recording that it does would be wrong in the record.

**What should see a postmortem's effect is the corpus digest, not the prompt digest**, and since
Q61 both of them are frozen inputs: `corpus_sha256` when a postmortem is added,
`corpus_body_sha256` when its words change. The mechanism exists one layer over, where the effect
actually is. `tests/test_postmortem_drafter.py` pins this module out of the stamp so the natural
instinct - *a new role belongs in `roles.py`* - fails loudly rather than quietly.

## What the briefing withholds, and why that is not the guard doing its job twice

`context/postmortem.py` bans every allowlist action id and every performable remediation class,
because `CLASS_TO_REMEDIATION` is one-to-one across eighteen scenarios and a named remediation is
the fault class in another spelling (registration §2, Q63).

**So the brief does not contain them.** The model is given the proposal's *target*, preconditions,
blast radius and falsifier, and is not given `action_id`, `remediation_class` or `fault_class` at
all. A model cannot leak what it never saw, and a guard is a better last line than a first one.

**This changes what prediction 6 measures, and the registration should be read knowing it.**
*"No postmortem trips the leak guard on its first draft"* was registered as the one expected to
fail, on the reasoning that *"the model has the fault class and the remediation in the record it
drafts from"*. It no longer does. What is now being scored is whether a model that was never told
the remediation names one anyway - a fairer question about the model and a weaker test of the
guard, and the difference is recorded here rather than left for the write-up to explain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from faultline.agents.briefing import Briefing, Section, assemble
from faultline.agents.contracts import REPORTED
from faultline.agents.model import LanguageModel, ModelRequest
from faultline.agents.roles import DEFAULT_BRIEFING_TOKENS, Completion, ask
from faultline.context.postmortem import SECTIONS

if TYPE_CHECKING:
    from faultline.agents.contracts import Verdict

POSTMORTEM_SYSTEM = """You are writing the postmortem for an incident that is now closed. A
responder will read it months from now, while a different service is failing, and will want one
thing from it: how this one was told apart from the things it resembled.

Write from the responder's chair, in your own words, with no absolute timestamps - offsets like
T+3m. Say what was observed only where it discriminates; the symptom surface is already recorded
elsewhere and repeating it wastes the reader's attention.

**Say what the mechanism was, never what fixed it.** Do not name a remediation, an action or a
class of either - not `rollback`, `restart`, `revert`, `config_revert`, nor any id like
`rollback_image` or `restart_service`, in any spelling or with any punctuation. Describe the
observable shape instead: "repeated boot banners with no request handling", "fast-fail at the
client span with no server span", "a near-constant floor on every leaf regardless of command".
That is what a reader actually carries to the next incident.

You may not use any of these words, in any case: inject, injected, injection, injector,
faultline, chaos, scenario, rehearsal, rehearse, pumba, netem, bad_deploy, bad_config,
dependency_latency, resource_exhaustion. Do not name the incident's identifier.

Never claim the system recovered or that a fix worked. Nobody ran one. Saying so would be false.

Reply with JSON only, matching this schema:
{"title": "<short title, no timestamps>",
 "concluded": "<the cause as finally stated, after the investigation closed>",
 "ruled_out": "<the observations that discriminated, and what they eliminated>",
 "proposal_rested_on": "<the preconditions, the blast radius, and the falsifier - as mechanism>",
 "approval_boundary": "<what happened to the proposal: accepted, refused and why, escalated, or
 declined - and on what reasoning>",
 "never_measured": "<what the evidence did not settle>"}"""


class PostmortemDraft(BaseModel):
    """The drafter's structured output. **Five fields, because the section list is closed.**

    `context/postmortem.SECTIONS` is a fixed tuple so that an extra heading cannot smuggle in an
    outcome claim, and a `list[Section]` schema would hand the model exactly that freedom back and
    leave the parser to refuse it afterwards. Flat named fields make the closed list a property of
    the schema, so a draft with a sixth thing to say has nowhere to put it and the re-ask in `ask`
    does the work before a document exists.

    `REPORTED`, not `forbid`, for the reason `contracts.REPORTED` records: one unexpected key
    would destroy a whole draft, and $0.73 was spent twice learning that. It is **not** in
    `contracts._CONTRACTS`, deliberately - see the module docstring.
    """

    model_config = REPORTED

    title: str
    concluded: str = Field(description="the cause as finally stated, after the investigation")
    ruled_out: str = Field(description="what discriminated, and what it eliminated")
    proposal_rested_on: str = Field(description="preconditions, blast radius, falsifier")
    approval_boundary: str = Field(description="the proposal's fate and the reasoning")
    never_measured: str = Field(description="what the evidence did not settle")

    def bodies(self) -> list[str]:
        """The five section bodies, in `SECTIONS` order."""
        return [
            self.concluded,
            self.ruled_out,
            self.proposal_rested_on,
            self.approval_boundary,
            self.never_measured,
        ]


ABSTAINED = "no action was proposed; the evidence did not support one"


def proposal_lines(proposal: dict[str, Any] | None) -> list[str]:
    """What the drafter is told about the proposal. **Not the action, and not its class.**

    `action_id` and `remediation_class` are withheld rather than redacted downstream, for the
    module docstring's reason: `baselines.CLASS_TO_REMEDIATION` is one-to-one, so either one hands
    the reader the fault class through a lookup table, and a model that never sees them cannot
    write them down.

    An abstention is a first-class outcome (ADR-0028 §4) and is described as one rather than as an
    absence, because *"the evidence did not support an action"* is a finding a responder wants and
    an empty section is not.
    """
    if not proposal or not proposal.get("action_id"):
        return [ABSTAINED]
    preconditions = [f"  - {line}" for line in proposal.get("preconditions") or []]
    return [
        f"Target: {proposal.get('target') or 'not recorded'}",
        "Preconditions it rested on:",
        *(preconditions or ["  - none recorded"]),
        f"Blast radius: {proposal.get('blast_radius') or 'not recorded'}",
        f"Falsifier - what would show it wrong: {proposal.get('if_wrong') or 'not recorded'}",
        f"Confirm within: {proposal.get('confirm_within_seconds') or 'not recorded'}s",
    ]


def fate_lines(fate: str, reason: str = "") -> list[str]:
    """The proposal's fate at the validator boundary, as the record holds it.

    Four outcomes and no default. `unknown` is a real state - a proposal nobody acted on - and
    calling it *declined* would put a decision in the record that no one made.
    """
    known = {
        "approved": "A person approved it and the executor performed it.",
        "rejected": "A person refused it.",
        "escalated": "It was refused twice and escalated; no one acted on it.",
        "abstained": "No action was proposed, so nothing reached the boundary.",
        "unknown": "The record does not say what became of it. Say that, rather than guessing.",
    }
    lines = [known.get(fate, known["unknown"])]
    if reason:
        # Operator text, quoted rather than paraphrased, and it reaches the model in the **user**
        # message like every other untrusted string (THREAT-MODEL.md thesis 1).
        lines.append(f'Their stated reason: "{reason}"')
    return lines


class PostmortemScribe:
    """Writes a postmortem draft from a closed incident. **No tools, and nothing to execute.**

    It reads what the record already holds and emits prose. Like the proposer (T3.9), it has no
    path to the world; unlike the proposer, its output is not even a claim about one - it is a
    document that a person edits and then accepts, and until they do it reaches nothing.
    """

    ROLE = "postmortem"

    def __init__(
        self,
        model: LanguageModel,
        max_tokens: int = 3000,
        effort: str = "medium",
        briefing_tokens: int = DEFAULT_BRIEFING_TOKENS,
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._effort = effort
        self._briefing_tokens = briefing_tokens
        self.briefing: Briefing | None = None

    def draft(
        self,
        verdict: Verdict,
        *,
        proposal: dict[str, Any] | None = None,
        fate: str = "unknown",
        fate_reason: str = "",
        violation: str | None = None,
    ) -> Completion:
        """One draft, or the regeneration after the leak guard refused the last one.

        `violation` arrives in the **user** message, on `Scribe.draft`'s rule: the system prompt
        is a frozen input, and a draft that never tripped the guard must see byte-for-byte the
        prompt it would have seen before this argument existed.
        """
        sections = [
            Section(
                name="conclusion",
                priority=0,
                essential=True,
                lines=[
                    f"The cause as finally stated: {verdict.root_cause}",
                    f"Service blamed: {verdict.service or 'not recorded'}",
                    f"Confidence: {verdict.confidence}",
                    f"The reasoning behind it: {verdict.reasoning}",
                ],
            ),
            Section(
                name="alternatives",
                priority=6,
                essential=True,
                lines=["What else was considered, best first:"]
                + [
                    f"  - {c.hypothesis}: {c.why_not}"
                    for c in getattr(verdict, "alternatives", []) or []
                ]
                or ["No alternative was recorded, which is itself worth saying."],
            ),
            Section(
                name="proposal",
                priority=4,
                essential=True,
                lines=["What was proposed, and what it rested on:", *proposal_lines(proposal)],
            ),
            Section(
                name="fate",
                priority=4,
                essential=True,
                lines=["At the approval boundary:", *fate_lines(fate, fate_reason)],
            ),
            Section(
                name="open",
                priority=2,
                essential=True,
                lines=["What the evidence did not settle:"]
                + [f"  - {q}" for q in verdict.open_questions]
                or ["  - the verdict recorded nothing open, which is itself worth saying"],
            ),
            Section(
                name="refusal",
                priority=5,
                essential=True,
                lines=(
                    [
                        "Your previous draft was refused before it could be accepted:",
                        f"  {violation}",
                        "Write it again. Describe the mechanism - the observable shape - and "
                        "name no remediation, no action, and no class of failure.",
                    ]
                    if violation is not None
                    else []
                ),
            ),
        ]
        self.briefing = assemble(self.ROLE, sections, self._briefing_tokens)
        return ask(
            self._model,
            ModelRequest(
                system=POSTMORTEM_SYSTEM,
                messages=[{"role": "user", "content": self.briefing.text}],
                role=self.ROLE,
                max_tokens=self._max_tokens,
                effort=self._effort,
            ),
            PostmortemDraft,
        )


def document(
    draft: PostmortemDraft,
    *,
    scenario_id: str,
    split: str,
    incident_id: str,
    recorded_from: str = "",
) -> str:
    """A draft as the file a person edits and then submits to the accept route.

    **Rendered here and validated elsewhere.** `context/postmortem.parse_postmortem_text` is what
    says whether this is admissible, and it runs over this output like it runs over a hand-edited
    file - one validator, reached by both paths, which is the property the accept route was built
    for.
    """
    front = [
        "---",
        f"scenario_id: {scenario_id}",
        f"origin: scenario:{scenario_id}",
        f"split: {split}",
        f"incident_id: {incident_id}",
        f"recorded_from: {recorded_from}",
        "---",
        "",
    ]
    lines = [*front, f"# {draft.title}", ""]
    for heading, body in zip(SECTIONS, draft.bodies(), strict=True):
        lines += [f"## {heading}", "", body.strip(), ""]
    return "\n".join(lines).rstrip() + "\n"
