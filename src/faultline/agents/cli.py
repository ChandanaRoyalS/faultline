"""`faultline-investigate` - run one investigation over one incident (T3.5).

The fourth command, and the one T4.1 drives. `--help` reaches no Postgres, no Redis and no
model: every backend is imported inside `run()`, the same discipline as the other three.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from faultline.agents.settings import AgentSettings
from faultline.archive import connect_or_none


def parser() -> argparse.ArgumentParser:
    """Flags override `FAULTLINE_AGENT_*` and `FAULTLINE_CONTEXT_*`, which override defaults."""
    settings = AgentSettings()
    p = argparse.ArgumentParser(
        prog="faultline-investigate",
        description=(
            "Investigate one incident end to end - triage, planner, specialists, synthesizer, "
            "scribe - persist the trajectory, and advance the incident's state (T3.5, "
            "ADR-0016 and ADR-0020)."
        ),
        epilog=(
            "Exit codes: 0 a verdict with nothing flagged; 2 a verdict that is flagged "
            "(budget exhausted, a specialist that failed alone, a contradiction) - the run "
            "produced something scoreable and the flag is the finding; 3 refused, nothing ran; "
            "4 no verdict, and the trajectory is persisted up to the failure. "
            "The budget bounds are ADR-0020's placeholders and have no measurements behind "
            "them; set them from T4.1's runs."
        ),
    )
    p.add_argument(
        "incident_id",
        nargs="?",
        help="the incident to investigate; omit with --list",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="show incidents the machine will investigate, and exit",
    )
    p.add_argument("--postgres-dsn", default=None, help="default: FAULTLINE_CONTEXT_POSTGRES_DSN")
    p.add_argument("--model", default=settings.model, help="default: %(default)s")
    p.add_argument(
        "--out",
        default=None,
        metavar="DIR",
        help="write <incident>-verdict.json and <incident>-narrative.md here",
    )
    p.add_argument(
        "--exclude-origin",
        default=None,
        metavar="SCENARIO",
        help=(
            "hold this scenario's own past-incident chunks out of retrieval (ADR-0008 axis 2). "
            "Overrides FAULTLINE_EVAL_SCENARIO. Unset in production, where retrieval sees the "
            "whole corpus"
        ),
    )
    p.add_argument("--retrieval-k", type=int, default=3, help="default: %(default)s")
    p.add_argument(
        "--baseline",
        choices=("b0", "b1", "b2"),
        default=None,
        help=(
            "run a baseline instead of the agent (T4.7). `b0` is the no-LLM heuristic: no model "
            "call, no context budget, scored by the same code path as the agent - which is what "
            "makes it a control rather than a separate experiment. `b1` is one agent with all "
            "four tools and no fan-out: it chooses its own calls, reads every result in one "
            "conversation, and concludes - so a b1-versus-agent gap is about structure rather "
            "than about capability. `b2` is the model's prior alone: alert text and the service "
            "catalog, no tool access at all, one call - it answers how much of any accuracy "
            "figure needed the world to be looked at."
        ),
    )
    p.add_argument(
        "--no-corpus",
        action="store_true",
        help="skip past-incident retrieval (it needs the embeddings extra)",
    )
    p.add_argument(
        "--no-gate",
        action="store_true",
        help="investigate without asking triage whether it is worth it (T3.1's gate)",
    )
    budget = p.add_argument_group("budget (ADR-0020 §5 placeholders)")
    budget.add_argument(
        "--max-tool-calls",
        type=int,
        default=settings.budget_max_tool_calls_per_specialist,
        metavar="N",
        help="per specialist; default: %(default)s",
    )
    budget.add_argument(
        "--max-tokens",
        type=int,
        default=settings.budget_max_tokens,
        help="default: %(default)s",
    )
    budget.add_argument(
        "--wall-clock",
        type=int,
        default=settings.budget_wall_clock_seconds,
        metavar="SECONDS",
        help="default: %(default)s",
    )
    budget.add_argument(
        "--max-tool-calls-changes",
        type=int,
        default=None,
        metavar="N",
        help=(
            "override the tool-call bound for the changes specialist only. T3.4c made a "
            "dispatch name one service, which multiplied change-history needs by the blast "
            "radius; default: same as --max-tool-calls"
        ),
    )
    budget.add_argument(
        "--max-rounds",
        type=int,
        default=settings.budget_max_dispatch_rounds,
        metavar="N",
        help="dispatch rounds; default: %(default)s",
    )
    p.add_argument(
        "--no-notify",
        action="store_true",
        help=(
            "do not send a report-ready notification even if FAULTLINE_NOTIFY_SLACK_WEBHOOK_URL "
            "is set. A scored run (one given --exclude-origin) is already silent (T5.2)"
        ),
    )
    return p


def run(argv: list[str] | None = None) -> int:
    """Entry point. Imports its backends late so `--help` needs no Postgres and no model."""
    args = parser().parse_args(argv)

    import os

    import psycopg

    from faultline.agents.budget import Budget
    from faultline.agents.investigation import Investigation
    from faultline.agents.model import LanguageModel, build_model
    from faultline.agents.roles import (
        Planner,
        Proposer,
        Scribe,
        Synthesizer,
        Triager,
        build_specialists,
    )
    from faultline.agents.runner import (
        Exit,
        NotInvestigableError,
        investigable,
        run_investigation,
        write_outputs,
    )
    from faultline.agents.trajectory import PostgresTrajectoryStore
    from faultline.agents.triage import Triage
    from faultline.context.catalog import ServiceCatalog
    from faultline.context.settings import ContextSettings
    from faultline.orchestrator import machine
    from faultline.orchestrator.store import PostgresIncidentStore
    from faultline.tools.changelog import PostgresChangeLog
    from faultline.tools.settings import ToolSettings
    from faultline.tools.tools import Tools

    context = ContextSettings()
    dsn = args.postgres_dsn or context.postgres_dsn
    settings = AgentSettings()
    store = PostgresIncidentStore(psycopg.connect(dsn))

    if args.list:
        from datetime import datetime

        candidates = [
            incident
            for incident in store.correlation_candidates(datetime.now(UTC))
            if incident.state in machine.INVESTIGABLE
        ]
        if not candidates:
            print("no investigable incidents")
            return 0
        print(f"{len(candidates)} investigable incident(s):")
        for incident in sorted(candidates, key=lambda i: i.opened_at or datetime.min):
            services = sorted({e.service for e in incident.episodes.values() if e.service})
            print(
                f"  {incident.id}  {incident.state.value:14} {len(incident.episodes)} episode(s)"
                f"  {incident.severity.value:8} {', '.join(services)}"
            )
        return 0

    if not args.incident_id:
        parser().error("an incident id is required unless --list is given")

    try:
        incident = investigable(store, args.incident_id)
    except NotInvestigableError as refusal:
        print(f"REFUSED: {refusal}")
        return int(Exit.REFUSED)

    exclude = args.exclude_origin or os.environ.get("FAULTLINE_EVAL_SCENARIO") or None
    if exclude:
        os.environ["FAULTLINE_EVAL_SCENARIO"] = exclude

    triage = Triage(ServiceCatalog.from_snapshot(), context.hop_radius).run(incident)
    anchor = min(e.starts_at for e in incident.episodes.values())
    print(f"incident {incident.id}  state {incident.state.value}  anchor {anchor:%H:%M:%S}")
    print(f"triage: {triage.summary()}")

    if args.baseline == "b0":
        # **Before the corpus and before the model.** B0 has neither, and constructing an
        # embedder and a model client it will not use would make its measured cost and latency
        # describe a pipeline it is not.
        return _run_b0(incident, triage, anchor, exclude, args, dsn, context)
    if args.baseline == "b2":
        # **Before the corpus, before the tool layer.** B2 has no tools by construction, and
        # building a change-log connection it cannot reach would put a connect in its latency.
        return _run_b2(incident, triage, anchor, exclude, args, dsn)
    if args.baseline == "b1":
        # **Before the corpus, after the model.** B1 makes model calls and needs one built; it
        # has no retrieval, and constructing an embedder it will not use would put a
        # sentence-transformer load into its measured latency.
        return _run_b1(incident, triage, anchor, exclude, args, dsn, context)

    corpus = None
    if not args.no_corpus:
        from faultline.context.embedding import SentenceTransformerEmbedder
        from faultline.context.store import PgVectorPastIncidentStore

        corpus = PgVectorPastIncidentStore(
            psycopg.connect(dsn), SentenceTransformerEmbedder(context.embedder)
        )

    # T2.5: retries are transparent, substitution is not. `fallback_models` is empty by
    # default, so this is a retry wrapper unless someone has decided otherwise (ADR-0031).
    from faultline.agents.model import Resilient
    from faultline.agents.settings import AgentSettings as _Settings

    _settings = _Settings()

    def _model(name: str) -> LanguageModel:
        return build_model(name, provider=_settings.provider, base_url=_settings.openai_base_url)

    model = Resilient(
        _model(args.model),
        [_model(name) for name in _settings.fallback_models],
        attempts=_settings.retry_attempts,
        base_delay=_settings.retry_base_delay,
    )
    archive = connect_or_none()
    engine = Investigation(
        planner=Planner(model),
        specialists=build_specialists(
            Tools(ToolSettings(), changes=PostgresChangeLog(psycopg.connect(dsn))), model
        ),
        store=PostgresTrajectoryStore(psycopg.connect(dsn), archive),
        model=model,
        budget=Budget(
            max_tool_calls_per_specialist=args.max_tool_calls,
            per_specialist_tool_calls=(
                {"changes": args.max_tool_calls_changes} if args.max_tool_calls_changes else {}
            ),
            max_tokens=args.max_tokens,
            wall_clock_seconds=args.wall_clock,
            max_dispatch_rounds=args.max_rounds,
        ),
        effort=settings.effort,
        synthesizer=Synthesizer(model),
        scribe=Scribe(model),
        corpus=corpus,
        retrieval_k=args.retrieval_k,
        proposer=Proposer(model),
    )

    report = run_investigation(
        store, incident, engine, triage, anchor, triager=None if args.no_gate else Triager(model)
    )
    _print_report(report)
    announce_report(report, incident.id, exclude=exclude, suppressed=args.no_notify)
    if args.out:
        from pathlib import Path

        for path in write_outputs(report, Path(args.out), archive):
            print(f"wrote {path}")
    return int(report.exit_code)


SCORED_RUN_IS_NOT_AN_INCIDENT = (
    "this is a scored run (--exclude-origin was given), and a benchmark is not an incident "
    "lifecycle"
)


def announce_report(
    report: object,
    incident_id: str,
    *,
    exclude: str | None = None,
    suppressed: bool = False,
    announcer: object | None = None,
) -> object:
    """T5.2's *"report ready"* half. Returns the `Delivery`, so the decision can be tested.

    **A scored run sends nothing, and that is the important case.** `evalharness.run` invokes this
    CLI as a subprocess once per scenario per repeat, so a published sweep is fifty invocations. If
    each posted to Slack, an on-call channel would fill with reports about faults the benchmark
    injected on purpose - and somebody would go and fix one, which corrupts the measurement and
    wastes a responder in the same move. `--exclude-origin` is the harness's own marker (retrieval
    exclusion exists only for scored runs, per ADR-0009's leakage rule), so it is read as the
    signal rather than a second flag the harness would have to remember to pass.

    An operator who passes `--exclude-origin` by hand gets no notification. That is the safe
    direction of the error: a missing message costs a click, and the other way costs a responder
    chasing an injected fault.

    The three baselines return before this is reached at all. A baseline exists to be measured; it
    is never an operational response, so it has no lifecycle to notify about.
    """
    from faultline.notify import SILENT

    if suppressed:
        return SILENT.report_ready(incident_id, report)
    if exclude:
        print(f"\nno notification sent: {SCORED_RUN_IS_NOT_AN_INCIDENT}")
        return SILENT.report_ready(incident_id, report)
    if announcer is None:
        from faultline.notify.slack import from_settings

        announcer = from_settings()
    return announcer.report_ready(incident_id, report)  # type: ignore[attr-defined]


def _print_report(report: object) -> None:
    """The transcript. **Says what did not happen as loudly as what did.**"""
    states = " -> ".join(getattr(report, "states", ()))
    print(f"\nstates: {states}")
    print(f"trajectory: {getattr(report, 'trajectory_id', None) or 'none persisted'}")

    judgement = getattr(report, "judgement", None)
    if judgement is not None:
        duplicate = f" of {judgement.duplicate_of}" if judgement.duplicate_of else ""
        print(
            f"triage judged: {judgement.disposition}{duplicate} ({judgement.confidence} "
            f"confidence, suspects {judgement.suspected_fault_class})"
        )
        print(f"  {judgement.reasoning}")
    error = getattr(report, "judgement_error", None)
    if error:
        print(f"triage could not be asked, so nothing was gated: {error}")
    if getattr(report, "gated", False):
        print("\nGATED BEFORE FAN-OUT: no specialist ran and nothing was spent on this incident")
        return

    error = getattr(report, "error", None)
    if error:
        print(f"\nFAILED MID-INVESTIGATION: {error}")
        print("the trajectory holds everything that ran before the failure")
        return

    result = getattr(report, "result", None)
    if result is None:
        return
    print(f"investigation: {result.summary()}")

    for name, why in result.failed_dispatches:
        print(f"  FAILED DISPATCH {name}: {why}")

    # **The proposal, which the first live run produced and nobody could see** (T3.9). The
    # incident reached `PROPOSING` and the object was written to the verdict JSON, and the
    # transcript said nothing - so the stage Batch B was built for was invisible in the one
    # place a person actually reads. An abstention prints too: it is an outcome, not an absence
    # (ADR-0022 §1.2).
    proposal = getattr(result, "proposal", None)
    if proposal is not None:
        print("\n=== PROPOSAL ===")
        if proposal.remediation_class == "none":
            print("  ABSTAINED - no permitted action fits the evidence")
        else:
            print(f"  action      : {proposal.action_id} ({proposal.remediation_class})")
            print(f"  target      : {proposal.target}")
            print(f"  expect      : {proposal.expected_effect}")
            print(f"  within      : {proposal.confirm_within_seconds}s")
            print(f"  risk        : {proposal.risk}")
            print(f"  blast radius: {proposal.blast_radius}")
        print(f"  if wrong    : {proposal.if_wrong}")
        print(f"  rests on    : {', '.join(proposal.rests_on) or 'nothing cited'}")
        print("  execution   : NOT MEASURED - no executor exists (ADR-0028 §4)")
    for violation in getattr(result, "proposal_violations", []):
        print(f"  PROPOSAL REFUSED: {violation}")
    if getattr(result, "proposal_escalated", False):
        print("  the proposer was refused twice and produced nothing")

    disclosure = getattr(result, "disclosure", None)
    if disclosure is not None:
        row = disclosure.as_row()
        print(
            f"\ncontext: {row['pushed_tokens']} pushed / {row['pulled_tokens']} pulled "
            f"(pull rate {row['pull_rate']}), {row['dropped_sections']} section(s) dropped"
        )

    verdict = result.verdict
    if verdict is None:
        print("\nNO VERDICT: the synthesizer produced nothing that validated")
        return

    print("\n=== VERDICT ===")
    print(f"  fault class : {verdict.fault_class}")
    print(f"  fix class   : {verdict.remediation_class}")
    print(f"  confidence  : {verdict.confidence}")
    print(f"  evidence    : {', '.join(verdict.evidence) or 'none cited'}")
    print(f"  root cause  : {verdict.root_cause}")
    for question in verdict.open_questions:
        print(f"  OPEN        : {question}")

    if result.flags:
        print("\n=== FLAGGED ===")
        for flag in result.flags:
            print(f"  {flag}")
    else:
        print("\nflags: none")

    print(f"\nretrieval: exclude_origin={result.exclude_origin!r}, {len(result.retrieved)} hit(s)")
    if result.narrative is None:
        print(f"NARRATIVE NOT RENDERED: {result.narrative_error}")


def _run_b0(
    incident: Any,
    triage: Any,
    anchor: datetime,
    exclude: str | None,
    args: Any,
    dsn: str,
    context: Any,
) -> int:
    """B0, under the standard harness (T4.7).

    **The same triage, the same tools, the same window policy, the same scorer.** Everything B0
    shares with the agent it shares for a reason: a baseline observed through a different regime
    would make the comparison a comparison of observation regimes rather than of methods. What it
    does not share is the part being controlled for - no planner, no specialists, no synthesizer,
    no model call at all.

    It persists a trajectory like any run, because the harness discards a run whose trajectory has
    no steps and because B0's tool calls are the record of what it actually looked at. The
    trajectory's `model` is `none` and its `runtime_version` is B0's own, so nothing downstream
    can mistake a baseline run for a pipeline run.
    """
    import psycopg

    from evalharness import baselines
    from faultline.agents.trajectory import (
        PostgresTrajectoryStore,
        StepKind,
        ToolCallRecord,
        Trajectory,
        TrajectoryStep,
    )
    from faultline.tools.changelog import PostgresChangeLog
    from faultline.tools.settings import ToolSettings
    from faultline.tools.tools import Tools
    from faultline.tools.window import WindowPolicy

    started = datetime.now(UTC)
    tools = Tools(ToolSettings(), PostgresChangeLog(psycopg.connect(dsn)))
    window = WindowPolicy(ToolSettings()).for_specialist("changes", anchor, started)
    alerting = [member.service for member in triage.alerting]

    signals, calls = baselines.signals_from_tools(tools, alerting, anchor, window)
    prediction = baselines.predict(signals, anchor)

    trajectory = Trajectory(
        incident_id=incident.id,
        model="none",
        effort="none",
        started_at=started,
        runtime_version=baselines.BASELINE_RUNTIME,
    )
    # One step per tool call actually made, each carrying its envelope. No completions: the
    # absence of a COMPLETION step is how a reader of the trajectory sees that no model was asked
    # anything. The `ToolCallRecord` is what v1 omitted, so `trajectory_tool_calls` stayed empty
    # and the metric panel reported *0 tool calls* beside *2 steps* - two true statements that
    # together read as a defect. B0 does make tool calls; they belong in the table the panel reads.
    for seq, call in enumerate(calls, start=1):
        trajectory.add(
            TrajectoryStep(
                seq=seq,
                role="B0",
                kind=StepKind.TOOL_CALL,
                at=datetime.now(UTC),
                payload={"tool": call.tool, **call.request},
                tool_call=ToolCallRecord(
                    tool=call.tool,
                    request=call.request,
                    result_id=call.result_id,
                    envelope=call.envelope,
                ),
            )
        )
    trajectory.ended_at = datetime.now(UTC)
    trajectory.outcome = "baseline"
    PostgresTrajectoryStore(psycopg.connect(dsn)).save(trajectory)

    print(f"B0: {prediction.fault_class} / {prediction.fix_class}")
    for line in prediction.why:
        print(f"  {line}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        payload = baselines.artifact(
            incident_id=incident.id,
            trajectory_id=trajectory.id,
            blast_radius=[m.service for m in triage.blast_radius],
            unmeasured_edges=len(triage.unmeasured_edges),
            exclude_origin=exclude,
            prediction=prediction,
        )
        (out / f"{incident.id}-verdict.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out / f'{incident.id}-verdict.json'}")
    return 0


def _run_b1(
    incident: Any,
    triage: Any,
    anchor: datetime,
    exclude: str | None,
    args: Any,
    dsn: str,
    context: Any,
) -> int:
    """B1, under the standard harness (T4.7).

    **One agent, all four tools, no fan-out.** The same triage, the same tool layer, the same
    window policy and the same scorer as the pipeline; what it does not have is the pipeline -
    no planner, no specialists, no synthesizer, no scribe, no retrieval, no proposer. One model
    chooses each call, reads every envelope in one conversation, and concludes.

    Every model call is recorded as a `COMPLETION` step and every tool call as a `TOOL_CALL` step
    with its `ToolCallRecord`, so T4.3's metric panel reads B1 exactly as it reads the pipeline.
    """
    import psycopg

    from evalharness import baseline_agent
    from faultline.agents.budget import Budget
    from faultline.agents.model import build_model
    from faultline.agents.settings import AgentSettings
    from faultline.agents.trajectory import (
        PostgresTrajectoryStore,
        StepKind,
        ToolCallRecord,
        Trajectory,
        TrajectoryStep,
    )
    from faultline.tools.changelog import PostgresChangeLog
    from faultline.tools.settings import ToolSettings
    from faultline.tools.tools import Tools

    settings = AgentSettings()
    started = datetime.now(UTC)
    tools = Tools(ToolSettings(), PostgresChangeLog(psycopg.connect(dsn)))
    model = build_model(args.model, provider=settings.provider, base_url=settings.openai_base_url)
    budget = Budget(
        max_tool_calls_per_specialist=args.max_tool_calls,
        per_specialist_tool_calls=(
            {"changes": args.max_tool_calls_changes} if args.max_tool_calls_changes else {}
        ),
        max_tokens=args.max_tokens,
        wall_clock_seconds=args.wall_clock,
        max_dispatch_rounds=args.max_rounds,
    )

    run = baseline_agent.investigate(
        incident=incident,
        triage=triage,
        anchor=anchor,
        now=started,
        tools=tools,
        model=model,
        budget=budget,
        effort=settings.effort,
    )

    trajectory = Trajectory(
        incident_id=incident.id,
        model=run.model or args.model,
        effort=settings.effort,
        started_at=started,
        runtime_version=baseline_agent.runtime_version(),
        role_models={baseline_agent.BASELINE_ID.lower(): run.model or args.model},
        budget_exhausted=run.budget_exhausted,
    )
    for seq, look in enumerate(run.looks, start=1):
        trajectory.add(
            TrajectoryStep(
                seq=seq,
                role=baseline_agent.BASELINE_ID,
                kind=StepKind.TOOL_CALL,
                at=datetime.now(UTC),
                payload={"tool": look.tool, "why": look.why, **look.request},
                tool_call=ToolCallRecord(
                    tool=look.tool,
                    request=look.request,
                    result_id=look.result_id,
                    envelope=look.envelope,
                ),
            )
        )
    # One COMPLETION step carrying the whole conversation's usage. **Not one per turn**: the
    # per-turn responses are not retained, and inventing a split across turns would put a number
    # in the record that nothing measured. The turn count is in the payload so a reader can see
    # how many calls the total covers.
    trajectory.add(
        TrajectoryStep(
            seq=len(run.looks) + 1,
            role=baseline_agent.BASELINE_ID,
            kind=StepKind.COMPLETION,
            at=datetime.now(UTC),
            payload={"turns": run.turns, "error": run.error},
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
        )
    )
    trajectory.ended_at = datetime.now(UTC)
    trajectory.outcome = "baseline"
    PostgresTrajectoryStore(psycopg.connect(dsn)).save(trajectory)

    if run.error:
        print(f"\nB1 FAILED: {run.error}")
        print("the trajectory holds every tool call it made before the failure")
    else:
        verdict = run.verdict
        print(f"\nB1: {verdict.fault_class} / {verdict.remediation_class} ({verdict.confidence})")
        print(f"  {verdict.root_cause}")
    print(f"  {run.tool_calls} tool calls over {run.turns} turns", end="")
    print(" (budget exhausted)" if run.budget_exhausted else "")
    for look in run.looks:
        print(f"    {look.tool}:{look.service}  {look.why}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        payload = baseline_agent.artifact(
            incident_id=incident.id,
            trajectory_id=trajectory.id,
            blast_radius=[m.service for m in triage.blast_radius],
            unmeasured_edges=len(triage.unmeasured_edges),
            exclude_origin=exclude,
            run=run,
        )
        (out / f"{incident.id}-verdict.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out / f'{incident.id}-verdict.json'}")
    return 0


def _run_b2(
    incident: Any,
    triage: Any,
    anchor: datetime,
    exclude: str | None,
    args: Any,
    dsn: str,
) -> int:
    """B2, under the standard harness (T4.7).

    **The same triage, the same scorer, and no tool layer at all.** `baseline_prior.investigate`
    takes no `tools` argument, so "no tool access" is enforced by the signature rather than by a
    sentence in a prompt - a rule stated only in a prompt is a rule a model can be argued out of.
    Nothing here constructs `Tools`, and no change-log connection is opened.

    One `COMPLETION` step and no `TOOL_CALL` steps: the trajectory's shape is itself the record
    that B2 looked at nothing, so T4.3's metric panel reports zero tool calls as a measurement
    rather than as a gap.
    """
    import psycopg

    from evalharness import baseline_prior
    from faultline.agents.model import build_model
    from faultline.agents.settings import AgentSettings
    from faultline.agents.trajectory import (
        PostgresTrajectoryStore,
        StepKind,
        Trajectory,
        TrajectoryStep,
    )
    from faultline.context.catalog import ServiceCatalog

    settings = AgentSettings()
    started = datetime.now(UTC)
    model = build_model(args.model, provider=settings.provider, base_url=settings.openai_base_url)

    run = baseline_prior.investigate(
        incident=incident,
        triage=triage,
        catalog=ServiceCatalog.from_snapshot(),
        anchor=anchor,
        model=model,
        effort=settings.effort,
    )

    trajectory = Trajectory(
        incident_id=incident.id,
        model=run.model or args.model,
        effort=settings.effort,
        started_at=started,
        runtime_version=baseline_prior.runtime_version(),
        role_models={baseline_prior.BASELINE_ID.lower(): run.model or args.model},
    )
    trajectory.add(
        TrajectoryStep(
            seq=1,
            role=baseline_prior.BASELINE_ID,
            kind=StepKind.COMPLETION,
            at=datetime.now(UTC),
            payload={"attempts": run.attempts, "error": run.error, "tool_calls": 0},
            tokens_in=run.tokens_in,
            tokens_out=run.tokens_out,
        )
    )
    trajectory.ended_at = datetime.now(UTC)
    trajectory.outcome = "baseline"
    PostgresTrajectoryStore(psycopg.connect(dsn)).save(trajectory)

    if run.error:
        print(f"\nB2 FAILED: {run.error}")
    else:
        verdict = run.verdict
        print(f"\nB2: {verdict.fault_class} / {verdict.remediation_class} ({verdict.confidence})")
        print(f"  {verdict.root_cause}")
        print("  looked at nothing - this is the model's prior")
    if run.invented_evidence:
        # Not a crash and not silently dropped. B2 read no envelopes, so every id it offered is
        # fabricated; the artifact records the claim and empties the citation.
        print(f"  CITED {len(run.invented_evidence)} result id(s) without looking at anything")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        payload = baseline_prior.artifact(
            incident_id=incident.id,
            trajectory_id=trajectory.id,
            blast_radius=[m.service for m in triage.blast_radius],
            unmeasured_edges=len(triage.unmeasured_edges),
            exclude_origin=exclude,
            run=run,
        )
        (out / f"{incident.id}-verdict.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {out / f'{incident.id}-verdict.json'}")
    return 0
