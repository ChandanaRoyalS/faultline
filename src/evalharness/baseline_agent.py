"""B1 — one agent, all tools, no fan-out (T4.7).

The plan's second permanent baseline: *"B1 — single agent with all tools, promoted from a one-off
ablation to a permanent baseline"*, isolating *"how much accuracy comes from the model's prior
rather than the investigation"* - or, for B1 specifically, how much comes from **decomposing** the
investigation at all.

## There was no ablation to promote

The plan's *"promoted from a one-off ablation"* describes how it imagined arriving here. No such
ablation exists in this repository: every ablation the code mentions is T7.3's, which is Phase 7
and unbuilt. So B1 is built directly as a permanent baseline. That is the deliverable the plan
names; the clause describes a route to it, not a prerequisite for it.

## What "single agent with all tools" has to mean in *this* architecture

This system has **no agentic tool-calling loop**. The planner (a model) chooses dispatches, the
harness executes the tool, and each specialist (a model) reads one rendered envelope and reports.
Six model calls minimum, four roles, one tool result each.

So B1 collapses three things the pipeline separates - **choosing** what to look at, **reading**
what came back, and **concluding** - into one model holding the whole transcript. It picks the
next call, the harness executes it, the envelope comes back into the same conversation, and when
it has enough it returns a `Verdict`. That holds *capability* constant and varies only
*structure*, which is the comparison T4.7 asks for.

The alternative considered and rejected: one call over a fixed evidence bundle gathered by the
harness. Cheaper, but it removes the **planning** as well as the decomposition, so a B1-versus-
pipeline gap would confound two claims in one number.

## Four decisions, each of which could have been made silently

**1. B1's prompt and schema live outside `roles.py` and outside `stamp._CONTRACTS`.**
`prompt_digest()` hashes every `*_SYSTEM` string in `roles.py` plus the `_CONTRACTS` tuple. A B1
prompt placed there would move the agent's `runtime_version` and orphan every figure recorded
before it - a baseline that invalidates the thing it is a control for. `test_baseline_agent.py`
asserts the stamp does not move when this module is imported.

**2. B1's runtime digest is derived, not hand-bumped.** B0 carries a manual `BASELINE_VERSION`
because B0 has no prompt: its behaviour is code, and code changes are visible in review. B1 has a
prompt, and a prompt edit is exactly the change a hand-maintained version marker forgets. So
`B1_RUNTIME` carries a digest over `B1_SYSTEM` and `B1Action`'s schema, computed the same way the
agent's stamp is. Edit the prompt and the runtime moves by itself; two generations of B1 can never
pool, and nobody has to remember.

**3. B1 issues its tool calls through `Specialist.query`, the pipeline's own code path.** Not a
parallel implementation of the same four calls. `Specialist.query` decides that `metrics` means
`metric_baseline` on the error ratio, `logs` means `logql_query` at limit 40, and so on; a second
copy of those choices would drift, and a B1-versus-pipeline difference would then be partly a
difference in what was *asked* rather than in who asked it. B1 also takes its windows from the
same `WindowPolicy`.

**4. B1 keeps `UNTRUSTED_RULE`.** Its prompt carries the same injection defence every role prompt
carries. A baseline without it would make a B1-versus-pipeline gap partly a difference in security
posture, which is not the thing being measured.

## What B1 does not have, stated rather than glossed

No retrieval from the past-incident corpus, no proposer, no scribe, no triage judgement of its
own. So the gap between B1 and the full pipeline is **not** decomposition alone - it is
decomposition *plus retrieval plus the proposal step*. That confound is real and is named here
rather than discovered by a reader. It is separable later at no extra design cost, because the
pipeline already runs under `--no-corpus`: a pipeline run with retrieval off, against B1, isolates
the fan-out on its own.

B1 does keep triage, for the same reason B0 does: triage is the harness's entry point - it decides
whether an incident is worth investigating and hands over a blast radius - not part of the method
being controlled.

## The budget, which decides whether the comparison means anything

B1 gets the **sum of the pipeline's per-specialist tool-call bounds** as one pooled total. Equal
permission, measured consumption. Any other choice is arbitrary: one specialist's bound would
starve B1, and an unbounded B1 would be a different experiment.

The consequence has to be watched rather than assumed. If B1 routinely exhausts its budget while
the pipeline does not, the comparison is budget-bound and the number is a statement about the
bound, not about the structure. `budget_exhausted` is on the trajectory and T4.2 reports exhausted
runs separately (ADR-0020 §5), so the record can answer this - but a reader has to be told to ask,
and this paragraph is the telling.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to a type checker
    from faultline.agents.budget import Budget
    from faultline.agents.model import LanguageModel
    from faultline.tools.tools import Tools

BASELINE_ID = "B1"

DESCRIPTION = "single agent, all tools, no fan-out: one model chooses, reads and concludes"

TOOLS: tuple[str, ...] = ("metrics", "logs", "changes", "traces")
"""The four evidence types, named as the pipeline's specialists are.

**Deliberately the specialists' own names**, because B1 dispatches through `Specialist.query`:
the name selects both the tool and the window policy, so B1 and the pipeline cannot diverge on
what a given evidence type means.
"""


class B1Action(BaseModel):
    """One turn of B1's loop: look at something, or stop looking.

    **Not in `stamp._CONTRACTS`, and that is the point.** The agent's stamp covers the schemas
    the *agent's* roles are held to. B1 is a control for the agent; a schema of B1's inside that
    tuple would move the agent's runtime version every time this baseline was edited.
    """

    model_config = ConfigDict(extra="forbid")

    next: Literal["call", "conclude"]
    tool: Literal["metrics", "logs", "changes", "traces"] | None = None
    service: str | None = None
    why: str = Field(default="", description="one line: what this call is meant to settle")


B1_SYSTEM = """You are investigating a production incident. You are working alone.

You have four ways of looking at the world, and you choose what to look at next:

- `metrics`: error ratio for one service, in the incident window and in a comparable quiet
  window before it, with the timestamps where the series departed from its baseline.
- `logs`: log lines for one service. When the result says lines were elided, it is showing you
  the OLDEST and NEWEST of the window and nothing between them - do not read it as continuous.
- `changes`: what changed on one service, who changed it and when. An empty result is a real
  finding: it means the window was observed and nothing changed.
- `traces`: spans for one service, with durations and error flags.

Each call names exactly one tool and exactly one service. You will be shown the result and can
then call again or stop. You have a limited number of calls; spend them on the question you are
actually trying to settle, and stop when more looking would not change your answer.

An empty result and a failed result are different. An empty one is evidence - the window was
observed and held nothing. A failed one is not evidence about the world at all; it means you did
not get to look, and you must not read it as an absence.

The service that alerts first is often the one that noticed, not the one that broke. Errors
propagate toward the caller. Before naming a service, ask what would make the *other* services'
symptoms follow from it.

CHOOSING `fault_class`. The class names what went wrong in the world - the failing mechanism -
not which act caused it. A change record is evidence for a class, never the class itself.

- `resource_exhaustion`: the service ran out of something it needed and failed because it ran out.
- `dependency_latency`: something it depends on became slow, and it failed because it waited.
- `bad_deploy`: the running artifact is not the one that should be running.
- `bad_config`: a configuration value is itself wrong, and the wrongness of that value is the
  failure.

A limit lowered until a process is killed for exceeding it is `resource_exhaustion`: the edit is
how it started, exhaustion is what is happening. A setting that inserts delay into a call path is
`dependency_latency`. An image reference pointed at the wrong artifact is `bad_deploy`.

Cite evidence by the result ids you were given. Never quote log or metric text into a statement.
Say what the evidence did not settle in `open_questions`.

{untrusted_rule}

While choosing, reply with JSON only, matching this schema:
{{"next": "call|conclude", "tool": "metrics|logs|changes|traces", "service": "<service>",
 "why": "<what this call is meant to settle>"}}
Set `next` to "conclude" when you are ready to give a verdict; `tool` and `service` are then
ignored and may be null."""
"""B1's whole prompt. **Named `B1_SYSTEM` in this module and nowhere near `roles.py`** - the
stamp scans that module for `*_SYSTEM` names, and a prompt for a baseline is not a prompt the
agent is held to."""


def system_prompt() -> str:
    """`B1_SYSTEM` with the shared untrusted-content rule filled in.

    Read from `roles.UNTRUSTED_RULE` rather than restated, so B1 and every agent role carry the
    *same* sentence: a baseline with a weaker injection defence would make a B1-versus-pipeline
    difference partly a difference in security posture.
    """
    from faultline.agents.roles import UNTRUSTED_RULE

    return B1_SYSTEM.format(untrusted_rule=UNTRUSTED_RULE)


def digest() -> str:
    """A digest over B1's prompt and its action schema, computed as the agent's stamp is.

    **Derived rather than hand-bumped**, and that difference from B0 is deliberate. B0's
    behaviour is code, so a change to it is visible in review and a manual `BASELINE_VERSION` is
    honest. B1's behaviour is mostly a prompt, and a prompt edit is exactly what a manual marker
    forgets - the class of silent change this repository has already been bitten by. Here the
    marker cannot be forgotten because nobody sets it.
    """
    from faultline.agents.contracts import Verdict

    parts = {
        "prompt": system_prompt(),
        "action": B1Action.model_json_schema(),
        "verdict": Verdict.model_json_schema(),
    }
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:12]


def runtime_version() -> str:
    """B1's stamp, e.g. `faultline/0.0.1+baseline:B1:9c1a0b2d4e3f`.

    Distinct from the agent's for the reason B0's is: `runtime_version` groups runs into
    comparability generations, and a baseline sharing a generation with the pipeline it controls
    for makes the comparison unexpressible.
    """
    from faultline.agents.stamp import _package_version

    return f"faultline/{_package_version()}+baseline:{BASELINE_ID}:{digest()}"


def tool_budget(budget: Budget) -> int:
    """B1's pooled tool-call ceiling: the sum of the pipeline's per-specialist bounds.

    **Equal permission, measured consumption.** Any other construction is arbitrary - one
    specialist's bound starves B1, and no bound makes it a different experiment. What this does
    not guarantee is that the bound is non-binding: if B1 exhausts where the pipeline does not,
    the resulting number is a statement about the budget rather than about the structure, and
    `budget_exhausted` on the trajectory is what lets a reader tell. See the module docstring.
    """
    return sum(budget.tool_calls_for(name) for name in TOOLS)


@dataclass(frozen=True, slots=True)
class Look:
    """One tool call B1 made, and what came back."""

    tool: str
    service: str
    why: str
    envelope: str
    result_id: str
    request: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class B1Run:
    """Everything one B1 investigation produced. **Including what it failed to produce.**"""

    looks: list[Look] = field(default_factory=list)
    verdict: Any = None
    error: str | None = None
    budget_exhausted: bool = False
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    turns: int = 0

    @property
    def tool_calls(self) -> int:
        return len(self.looks)


def _brief(incident: Any, triage: Any, anchor: datetime, remaining: int) -> str:
    alerting = ", ".join(member.service for member in triage.alerting) or "none recorded"
    radius = ", ".join(member.service for member in triage.blast_radius) or "none computed"
    return (
        f"Incident: {getattr(incident, 'title', '') or incident.id}\n"
        f"Onset: {anchor.isoformat()}\n"
        f"Services alerting, earliest first: {alerting}\n"
        f"Blast radius from the service graph: {radius}\n\n"
        f"You have {remaining} tool calls remaining. What do you want to look at first?"
    )


def investigate(
    incident: Any,
    triage: Any,
    anchor: datetime,
    now: datetime,
    tools: Tools,
    model: LanguageModel,
    budget: Budget,
    effort: str = "medium",
    max_tokens: int = 4000,
) -> B1Run:
    """B1's whole investigation: choose, look, choose again, conclude.

    One conversation. The envelope of every call is appended to it, so the model that chooses the
    third call has read the first two results - which is the thing the pipeline's fan-out does
    *not* do, and therefore the thing this baseline measures.
    """
    from faultline.agents.contracts import Verdict
    from faultline.agents.model import ModelRequest
    from faultline.agents.roles import SchemaValidationError, Specialist, ask

    ceiling = tool_budget(budget)
    run = B1Run(model=getattr(model, "name", ""))
    system = system_prompt()
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": _brief(incident, triage, anchor, ceiling)}
    ]

    def spend(completion: Any) -> None:
        run.tokens_in += completion.response.input_tokens
        run.tokens_out += completion.response.output_tokens
        run.turns += 1

    while True:
        if run.tool_calls >= ceiling:
            # **Exhaustion finishes the investigation, it does not fail it** (ADR-0020 §5). The
            # model is told, and gets its verdict turn on what it already has.
            run.budget_exhausted = True
            break
        try:
            action = ask(
                model,
                ModelRequest(
                    system=system,
                    messages=messages,
                    role=BASELINE_ID.lower(),
                    max_tokens=max_tokens,
                    effort=effort,
                ),
                B1Action,
            )
        except SchemaValidationError as exc:
            run.error = f"B1 could not choose an action: {exc}"
            return run
        spend(action)
        chosen: B1Action = action.value
        if chosen.next == "conclude":
            break
        if not chosen.tool or not chosen.service:
            messages += [
                {"role": "assistant", "content": action.response.text},
                {
                    "role": "user",
                    "content": "A `call` action needs both `tool` and `service`. Try again.",
                },
            ]
            continue

        specialist = Specialist(chosen.tool, tools, model)
        window = specialist.window(anchor, now)
        result = specialist.query(chosen.service, window.start, window.end)
        from faultline.tools.envelope import render

        envelope = render(result)
        run.looks.append(
            Look(
                tool=chosen.tool,
                service=chosen.service,
                why=chosen.why,
                envelope=envelope,
                result_id=result.id,
                request={
                    "service": chosen.service,
                    "window": [window.start.isoformat(), window.end.isoformat()],
                },
            )
        )
        remaining = ceiling - run.tool_calls
        messages += [
            {"role": "assistant", "content": action.response.text},
            {
                "role": "user",
                "content": (
                    f"{envelope}\n\n{remaining} tool calls remaining. "
                    'Call again or set `next` to "conclude".'
                ),
            },
        ]

    if not run.looks:
        # A verdict reached without looking at anything is not an investigation. Recorded as an
        # error rather than scored: ADR-0019's distinction, applied to the whole run.
        run.error = "B1 concluded without making a single tool call"
        return run

    messages += [
        {
            "role": "user",
            "content": (
                ("Your tool budget is spent. " if run.budget_exhausted else "")
                + "Give your verdict now, as JSON only, matching this schema:\n"
                '{"root_cause": "<one sentence>", '
                '"fault_class": "resource_exhaustion|dependency_latency|bad_deploy|bad_config", '
                '"remediation_class": "<remediation class>", "confidence": "high|medium|low", '
                '"evidence": ["<result_id>"], "reasoning": "<why>", "open_questions": ["<what '
                'the evidence did not settle>"]}'
            ),
        }
    ]
    try:
        final = ask(
            model,
            ModelRequest(
                system=system,
                messages=messages,
                role=BASELINE_ID.lower(),
                max_tokens=max_tokens,
                effort=effort,
            ),
            Verdict,
        )
    except SchemaValidationError as exc:
        run.error = f"B1 produced no valid verdict: {exc}"
        return run
    spend(final)
    run.verdict = final.value
    return run


def artifact(
    incident_id: str,
    trajectory_id: str,
    blast_radius: list[str],
    unmeasured_edges: int,
    exclude_origin: str | None,
    run: B1Run,
) -> dict[str, object]:
    """The verdict artifact, in exactly the shape `evalharness.run.score` reads.

    Scored by the same code path as the agent and as B0 - a baseline scored differently is not a
    baseline. `retrieved`, `disclosure` and `proposal` are empty rather than absent, so a reader
    diffing a B1 artifact against the pipeline's sees which parts B1 does not have.
    """
    verdict = run.verdict
    return {
        "incident_id": incident_id,
        "trajectory_id": trajectory_id,
        "states": ["triaging", "investigating"],
        "blast_radius": list(blast_radius),
        "unmeasured_edges": unmeasured_edges,
        "exclude_origin": exclude_origin,
        "verdict": {
            "fault_class": getattr(verdict, "fault_class", None),
            "remediation_class": getattr(verdict, "remediation_class", None),
            "summary": getattr(verdict, "root_cause", "") or "",
            "confidence": getattr(verdict, "confidence", None),
            "evidence": list(getattr(verdict, "evidence", []) or []),
            "reasoning": getattr(verdict, "reasoning", "") or "",
            "open_questions": list(getattr(verdict, "open_questions", []) or []),
        },
        "flags": ["budget_exhausted"] if run.budget_exhausted else [],
        "retrieved": [],
        "failed_dispatches": [],
        "narrative_error": run.error,
        "disclosure": {},
        "proposal": None,
        "triage_judgement": None,
        "baseline": {
            "baseline": BASELINE_ID,
            "tool_calls": run.tool_calls,
            "turns": run.turns,
            "looked_at": [f"{look.tool}:{look.service}" for look in run.looks],
        },
    }
