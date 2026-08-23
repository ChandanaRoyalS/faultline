"""`faultline-inject` - the operator's view of the chaos injector (T1.4).

Four verbs: list, start, status, stop. The output is what a human reads during
a demo and what an investigation transcript will later quote, so `start` prints
the concrete changes it made rather than a success banner.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from injector.docker import CommandError
from injector.engine import Engine, InjectorError, StopResult
from injector.faults import FaultUsageError
from injector.models import (
    ActiveInjection,
    ComposeServiceRestore,
    CpuQuotaRestore,
    FaultDefinition,
    MemoryLimitRestore,
    PumbaRestore,
    RestoreState,
)
from injector.settings import InjectorSettings

EXIT_OK = 0
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="faultline-inject",
        description="Inject and revert labelled faults in the target environment.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="show available fault definitions")
    commands.add_parser("status", help="show currently active injections")

    start = commands.add_parser("start", help="inject a fault")
    start.add_argument("fault_id", metavar="ID")

    stop = commands.add_parser("stop", help="revert a fault")
    stop.add_argument("fault_id", metavar="ID", nargs="?")
    stop.add_argument("--all", action="store_true", help="revert every active injection")

    return parser


def _params(definition: FaultDefinition) -> str:
    return ", ".join(f"{k}={v}" for k, v in definition.params.items()) or "-"


def _describe_restore(state: RestoreState) -> str:
    match state:
        case MemoryLimitRestore():
            return f"memory limit {state.memory_bytes}B on {state.container}"
        case ComposeServiceRestore():
            return f"recreate {state.service} without {state.override_file}"
        case CpuQuotaRestore():
            return (
                f"recreate {state.service} without {state.override_file} "
                f"(cpu quota was {state.nano_cpus}n)"
            )
        case PumbaRestore():
            return f"stop sidecar {state.helper_container}"


def _cmd_list(engine: Engine) -> int:
    active = engine.active()
    for definition in engine.catalog:
        marker = "  [ACTIVE]" if definition.id in active else ""
        print(f"{definition.id}{marker}")
        print(f"    class : {definition.fault_class}")
        print(f"    target: {definition.target}")
        print(f"    params: {_params(definition)}")
        print(f"    {definition.description}")
        print()
    return EXIT_OK


def _cmd_status(engine: Engine) -> int:
    active = engine.active()
    if not active:
        print("no active injections")
        return EXIT_OK

    print(f"{len(active)} active injection(s)  [state: {engine.settings.state_file}]")
    for injection in sorted(active.values(), key=lambda i: i.started_at):
        print(f"\n{injection.definition.id}")
        print(f"    class  : {injection.definition.fault_class}")
        print(f"    target : {injection.definition.target}")
        print(f"    started: {injection.started_at.isoformat()} ({_elapsed(injection)})")
        print(f"    params : {_params(injection.definition)}")
        print(f"    revert : {_describe_restore(injection.restore)}")
    return EXIT_OK


def _elapsed(injection: ActiveInjection) -> str:
    seconds = int((datetime.now(UTC) - injection.started_at).total_seconds())
    if seconds < 60:
        return f"{seconds}s ago"
    return f"{seconds // 60}m{seconds % 60:02d}s ago"


def _cmd_start(engine: Engine, fault_id: str) -> int:
    result = engine.start(fault_id)
    definition = result.injection.definition
    print(f"injected {definition.id} ({definition.fault_class}) on {definition.target}")
    for change in result.changes:
        print(f"  - {change}")
    print(f"revert with: faultline-inject stop {definition.id}")
    return EXIT_OK


def _report_stop(result: StopResult) -> None:
    if result.error is not None:
        print(f"FAILED to revert {result.fault_id}: {result.error}", file=sys.stderr)
        return
    if not result.was_active:
        print(f"{result.fault_id} is not active; nothing to revert")
        return
    print(f"reverted {result.fault_id}")
    for change in result.changes:
        print(f"  - {change}")


def _cmd_stop(engine: Engine, fault_id: str | None, revert_all: bool) -> int:
    if revert_all:
        results = engine.stop_all()
        if not results:
            print("no active injections")
        for result in results:
            _report_stop(result)
    elif fault_id is None:
        raise InjectorError("stop needs a fault ID, or --all")
    else:
        results = [engine.stop(fault_id)]
        _report_stop(results[0])

    return EXIT_ERROR if any(r.error for r in results) else EXIT_OK


def main(argv: Sequence[str] | None = None, engine: Engine | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = engine if engine is not None else Engine(InjectorSettings())

    try:
        match args.command:
            case "list":
                return _cmd_list(engine)
            case "status":
                return _cmd_status(engine)
            case "start":
                return _cmd_start(engine, args.fault_id)
            case "stop":
                return _cmd_stop(engine, args.fault_id, args.all)
            case _:  # pragma: no cover - argparse rejects anything else first
                raise InjectorError(f"unknown command {args.command!r}")
    except (InjectorError, FaultUsageError, CommandError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


def run() -> None:
    """Console-script entry point."""
    raise SystemExit(main())


if __name__ == "__main__":  # pragma: no cover
    run()
