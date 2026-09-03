"""B2 — the model's prior, with nothing to look at (T4.7).

The plan's third permanent baseline: *"B2 — frontier model with alert text and service catalog
but no tool access, isolating how much accuracy comes from the model's prior rather than the
investigation."*

**This is the sharpest of the three**, because it is the one that can embarrass the project. B0
asks whether an agent was needed at all; B1 asks whether the fan-out was needed. B2 asks whether
*looking at the world* was needed - whether a model that has read a great deal about
microservice outages can name the fault class from an alert name and a topology, without a
single observation. If it can, then some fraction of every accuracy figure in this repository is
a measurement of the model's training data rather than of the pipeline, and a reader is entitled
to know which fraction.

## What B2 is given, and what it is not

**Given:** the alert text - alert names, services, severities, times - and the service catalog:
every service the graph knows, the measured call edges between them, and the services the
catalog knows are absent. Also triage's blast radius, for the reason B0 and B1 get it: triage is
the harness's entry point, and the radius is a **deterministic traversal of the catalog it is
already being handed**, not an investigation product. Withholding a derived view of information
it already has would make B2 differently-briefed rather than tool-less.

**Not given:** any tool. Not a narrowed set, not a read-only subset - none. `investigate()` takes
no `Tools` argument at all, so "no tool access" is a fact about the signature rather than an
instruction in a prompt that a model might route around. A test asserts it.

## "Frontier model", read against the purpose clause

The plan says *"frontier model"*, and the purpose clause says *"isolating how much accuracy comes
from the model's prior rather than the investigation"*. Those pull in different directions if
"frontier" is read as *a different, better model*: swapping the model would confound the prior
with the model, and the isolation would be lost.

B2 therefore runs **whatever model the run is configured with**, which is the pipeline's own -
today a frontier model, so both readings are satisfied at once. The effective model is recorded
on the trajectory, as it is for every run, so a B2 figure always states which model's prior it is
measuring. Running B2 on a deliberately stronger model than the pipeline is then a different
experiment, expressible by setting `--model`, and it will be visibly a different configuration in
the eval database rather than a silent substitution.

## Concluding without looking is not an error here

B1 records a verdict reached without a single tool call as an error, because for B1 that is a
failure to investigate. For B2 it is **the entire method**. The same behaviour is a defect in one
baseline and the measurement in the other, which is worth stating plainly: what makes a run
valid is what the run was for.

## What a high B2 score would mean, decided before the number exists

Written now, while it is still cheap to be honest about.

If B2 scores near the pipeline on `fault_class`, the pipeline's advantage is not in classifying -
it is in the parts B2 cannot do at all: naming the culprit *service*, citing evidence, and being
checkable. Those are separately scored, and a headline that leads with fault-class accuracy while
B2 is close behind is a headline choosing its best number. The plan's own words for why baselines
exist - *"you need to be the one who discovers that"* - are the instruction being followed here.

Two properties of this catalog make a high B2 score more likely than it would be in the wild, and
both must travel with the number: `dependency_latency` is the only class with no change signature
(see `baselines.NO_CHANGE_CLASS`), and the fault class determines the remediation class exactly
across all eighteen scenarios, so B2 gets the remediation axis free for every class it guesses
right. A B2 that scores well on remediation has demonstrated something about the benchmark, not
about itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - only a type checker needs these
    from faultline.agents.model import LanguageModel

BASELINE_ID = "B2"

DESCRIPTION = "frontier model, alert text and service catalog, no tool access"


B2_SYSTEM = """You are given an incident report and a map of the services involved. You have
no tools and cannot look at anything: no metrics, no logs, no traces, no change history. You
will not be given any.

Answer from what you are given and from what you know about how systems like this fail.

CHOOSING `fault_class`. The class names what went wrong in the world - the failing mechanism -
not which act caused it.

- `resource_exhaustion`: the service ran out of something it needed - memory, CPU, file
  descriptors, connections, threads - and failed because it ran out.
- `dependency_latency`: something the service depends on became slow, and the service failed
  because it waited.
- `bad_deploy`: the running artifact is not the one that should be running - a wrong image, a
  wrong version, a build that cannot start.
- `bad_config`: a configuration value is itself wrong - it names the wrong address, port,
  credential, limit or flag - and the wrongness of that value is the failure.

The service that alerts first is often the one that noticed rather than the one that broke.
Errors propagate toward the caller.

**Say how confident you are, honestly.** You are guessing from a name and a topology, and a
`low` confidence that turns out right is worth more to a reader than a `high` one that does not.
`evidence` must be an empty list: you have no result ids because you looked at nothing, and
inventing one would be worse than leaving it empty. Put what you would have needed to look at in
`open_questions`.

Reply with JSON only, matching this schema:
{"root_cause": "<one sentence>", "fault_class":
 "resource_exhaustion|dependency_latency|bad_deploy|bad_config",
 "remediation_class": "<remediation class>", "confidence": "high|medium|low",
 "evidence": [], "reasoning": "<why>", "open_questions": ["<what you would need to look at>"]}"""
"""B2's whole prompt. **Not in `roles.py`**, for the reason B1's is not: the stamp scans that
module for `*_SYSTEM` names, and a baseline's prompt is not a prompt the agent is held to."""


def digest() -> str:
    """A digest over B2's prompt and the verdict schema it is held to.

    Derived rather than hand-bumped, as B1's is. B2's behaviour is *entirely* a prompt - it has
    no tools and no loop - so a hand-maintained version marker would be the only thing standing
    between two incomparable generations, and it would be the thing that gets forgotten.
    """
    from faultline.agents.contracts import Verdict

    parts = {"prompt": B2_SYSTEM, "verdict": Verdict.model_json_schema()}
    encoded = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:12]


def runtime_version() -> str:
    """B2's stamp, e.g. `faultline/0.0.1+baseline:B2:1a2b3c4d5e6f`."""
    from faultline.agents.stamp import _package_version

    return f"faultline/{_package_version()}+baseline:{BASELINE_ID}:{digest()}"


def alert_text(incident: Any) -> str:
    """The alert text, as a responder's pager would have shown it.

    Alert name, service, severity and start time per episode, oldest first. **Nothing derived**:
    no fault hints, no scenario id, no injector vocabulary - the change-log leak boundary
    (`faultline.tools.changes`) applies here for the same reason, one layer up. A baseline handed
    a labelled incident measures the label.
    """
    episodes = sorted(
        getattr(incident, "episodes", {}).values(), key=lambda e: (e.starts_at, e.episode_key)
    )
    if not episodes:
        return "no alert episodes recorded"
    lines = []
    for episode in episodes:
        severity = getattr(episode.severity, "value", episode.severity)
        lines.append(
            f"  {episode.starts_at:%H:%M:%S}  {episode.alertname or 'unnamed'}  "
            f"service={episode.service or 'unknown'}  severity={severity}"
        )
    return "\n".join(lines)


def catalog_text(catalog: Any, limit: int = 60) -> str:
    """The service catalog: what exists, what calls what, and what is known absent.

    The edges are the measured ones - `ServiceGraph.from_snapshot` drops the artifact edges - so
    this is the same topology triage traverses. Capped, because a catalog longer than the
    incident is a briefing that buries it; the cap is stated in the text so the model knows it is
    reading a truncated map rather than a complete one.
    """
    graph = getattr(catalog, "graph", None)
    edges = list(getattr(graph, "edges", []) or [])
    shown = edges[:limit]
    lines = [f"  {edge.parent} -> {edge.child}" for edge in shown]
    if len(edges) > limit:
        lines.append(f"  ... and {len(edges) - limit} more measured edges, not shown")
    # `services` and `usable` are the catalog's public pair. Reaching into `_entries` would be
    # the same read-it-by-guess habit `tests/test_result_shapes.py` exists to stop.
    absent = sorted(service for service in catalog.services if not catalog.usable(service))
    if absent:
        lines.append(f"  known absent from the graph: {', '.join(absent)}")
    return "\n".join(lines) or "  no topology available"


@dataclass(slots=True)
class B2Run:
    """One B2 answer, and what it cost. **No `looks`, because there is nothing to look at.**"""

    verdict: Any = None
    error: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""
    attempts: int = 0
    invented_evidence: list[str] = field(default_factory=list)
    """Result ids the model cited despite having read nothing.

    **Recorded rather than silently dropped.** B2 has no result ids, so any id here is
    fabricated - and a baseline that invents citations is a finding about what happens when a
    model is asked for evidence it does not have. T6.x's territory, surfaced for free.
    """


def brief(incident: Any, triage: Any, catalog: Any, anchor: datetime) -> str:
    alerting = ", ".join(member.service for member in triage.alerting) or "none recorded"
    radius = ", ".join(member.service for member in triage.blast_radius) or "none computed"
    return (
        f"INCIDENT\n"
        f"  {getattr(incident, 'title', '') or incident.id}\n"
        f"  onset {anchor.isoformat()}\n\n"
        f"ALERTS\n{alert_text(incident)}\n\n"
        f"SERVICES ALERTING, EARLIEST FIRST\n  {alerting}\n\n"
        f"BLAST RADIUS (graph traversal from the alerting set)\n  {radius}\n\n"
        f"SERVICE CATALOG\n{catalog_text(catalog)}\n\n"
        f"What is the root cause? You have no tools."
    )


def investigate(
    incident: Any,
    triage: Any,
    catalog: Any,
    anchor: datetime,
    model: LanguageModel,
    effort: str = "medium",
    max_tokens: int = 4000,
) -> B2Run:
    """B2's whole method: one model call, no tools.

    **There is no `tools` parameter, and that is the enforcement.** "No tool access" stated only
    in a prompt is a rule a model can be argued out of; stated in a signature it is a rule that
    cannot be reached. Nothing in this module imports the tool layer.
    """
    from faultline.agents.contracts import Verdict
    from faultline.agents.model import ModelRequest
    from faultline.agents.roles import SchemaValidationError, ask

    run = B2Run(model=getattr(model, "name", ""))
    try:
        completion = ask(
            model,
            ModelRequest(
                system=B2_SYSTEM,
                messages=[{"role": "user", "content": brief(incident, triage, catalog, anchor)}],
                role=BASELINE_ID.lower(),
                max_tokens=max_tokens,
                effort=effort,
            ),
            Verdict,
        )
    except SchemaValidationError as exc:
        run.error = f"B2 produced no valid verdict: {exc}"
        return run
    run.tokens_in = completion.response.input_tokens
    run.tokens_out = completion.response.output_tokens
    run.attempts = completion.attempts
    run.verdict = completion.value
    run.invented_evidence = list(getattr(completion.value, "evidence", []) or [])
    return run


def artifact(
    incident_id: str,
    trajectory_id: str,
    blast_radius: list[str],
    unmeasured_edges: int,
    exclude_origin: str | None,
    run: B2Run,
) -> dict[str, object]:
    """The verdict artifact, in exactly the shape `evalharness.run.score` reads.

    `evidence` is emptied here even when the model supplied ids, because those ids resolve to
    nothing: B2 read no envelopes, so a citation validator would reject every one. What was
    claimed is kept in the baseline block instead, where it is a measurement about the model
    rather than a citation about the world.
    """
    verdict = run.verdict
    return {
        "incident_id": incident_id,
        "trajectory_id": trajectory_id,
        "states": ["triaging"],
        "blast_radius": list(blast_radius),
        "unmeasured_edges": unmeasured_edges,
        "exclude_origin": exclude_origin,
        "verdict": {
            "fault_class": getattr(verdict, "fault_class", None),
            "remediation_class": getattr(verdict, "remediation_class", None),
            "summary": getattr(verdict, "root_cause", "") or "",
            "confidence": getattr(verdict, "confidence", None),
            "evidence": [],
            "reasoning": getattr(verdict, "reasoning", "") or "",
            "open_questions": list(getattr(verdict, "open_questions", []) or []),
        },
        "flags": ["invented_evidence"] if run.invented_evidence else [],
        "retrieved": [],
        "failed_dispatches": [],
        "narrative_error": run.error,
        "disclosure": {},
        "proposal": None,
        "triage_judgement": None,
        "baseline": {
            "baseline": BASELINE_ID,
            "tool_calls": 0,
            "attempts": run.attempts,
            "cited_without_looking": list(run.invented_evidence),
        },
    }
