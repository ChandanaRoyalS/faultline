"""`faultline-investigate` - run one investigation over one incident (T3.5).

The fourth command, and the one T4.1 drives. `--help` reaches no Postgres, no Redis and no
model: every backend is imported inside `run()`, the same discipline as the other three.
"""

from __future__ import annotations

import argparse
from datetime import UTC

from faultline.agents.settings import AgentSettings


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
        "--no-corpus",
        action="store_true",
        help="skip past-incident retrieval (it needs the embeddings extra)",
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
    from faultline.agents.model import AnthropicModel
    from faultline.agents.roles import Planner, Scribe, Synthesizer, build_specialists
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
    model = Resilient(
        AnthropicModel(args.model),
        [AnthropicModel(name) for name in _settings.fallback_models],
        attempts=_settings.retry_attempts,
        base_delay=_settings.retry_base_delay,
    )
    engine = Investigation(
        planner=Planner(model),
        specialists=build_specialists(
            Tools(ToolSettings(), changes=PostgresChangeLog(psycopg.connect(dsn))), model
        ),
        store=PostgresTrajectoryStore(psycopg.connect(dsn)),
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
    )

    report = run_investigation(store, incident, engine, triage, anchor)
    _print_report(report)
    if args.out:
        from pathlib import Path

        for path in write_outputs(report, Path(args.out)):
            print(f"wrote {path}")
    return int(report.exit_code)


def _print_report(report: object) -> None:
    """The transcript. **Says what did not happen as loudly as what did.**"""
    states = " -> ".join(getattr(report, "states", ()))
    print(f"\nstates: {states}")
    print(f"trajectory: {getattr(report, 'trajectory_id', None) or 'none persisted'}")

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
