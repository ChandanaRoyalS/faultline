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
        choices=("b0",),
        default=None,
        help=(
            "run a baseline instead of the agent (T4.7). `b0` is the no-LLM heuristic: no model "
            "call, no context budget, scored by the same code path as the agent - which is what "
            "makes it a control rather than a separate experiment."
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
    if args.out:
        from pathlib import Path

        for path in write_outputs(report, Path(args.out), archive):
            print(f"wrote {path}")
    return int(report.exit_code)


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
