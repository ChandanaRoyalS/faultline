"""`faultline-orchestrate` - run the consumer loop against Redis and Postgres (T2.2)."""

from __future__ import annotations

import argparse

from faultline.orchestrator.settings import OrchestratorSettings


def parser() -> argparse.ArgumentParser:
    """Flags override `FAULTLINE_ORCH_*`, which overrides the defaults."""
    settings = OrchestratorSettings()
    p = argparse.ArgumentParser(
        prog="faultline-orchestrate",
        description=(
            "Consume alert-episode transitions from the Redis stream, correlate them into "
            "incidents, and persist the incident machine to Postgres (T2.2, ADR-0016)."
        ),
        epilog=(
            "Placeholders: --max-concurrent, --settle-window all have reasons recorded in "
            "ADR-0016 and no measurements behind them. Set them from T4.1's runs."
        ),
    )
    p.add_argument("--redis-url", default=settings.redis_url, help="default: %(default)s")
    p.add_argument("--stream", default=settings.stream, help="default: %(default)s")
    p.add_argument("--group", default=settings.group, help="default: %(default)s")
    p.add_argument("--consumer", default=settings.consumer, help="default: %(default)s")
    p.add_argument("--postgres-dsn", default=settings.postgres_dsn, help="default: %(default)s")
    p.add_argument(
        "--max-concurrent",
        type=int,
        default=settings.max_concurrent,
        help="investigation concurrency cap (placeholder; default: %(default)s)",
    )
    p.add_argument(
        "--settle-window",
        type=int,
        default=settings.settle_window_seconds,
        metavar="SECONDS",
        help=(
            "how long a resolved incident still accepts a firing "
            "(placeholder; default: %(default)s)"
        ),
    )
    p.add_argument(
        "--create-schema",
        action="store_true",
        help="create the incident tables if they do not exist, then continue",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="process one batch and exit, instead of looping",
    )
    p.add_argument(
        "--no-notify",
        action="store_true",
        help=(
            "do not send incident-opened notifications even if FAULTLINE_NOTIFY_SLACK_WEBHOOK_URL "
            "is set. Use this when running against a world a benchmark is injecting faults into "
            "(T5.2)"
        ),
    )
    return p


def run(argv: list[str] | None = None) -> int:
    """Entry point. Imports its backends late so `--help` needs no Redis and no Postgres."""
    args = parser().parse_args(argv)

    from datetime import timedelta

    import psycopg

    from faultline.orchestrator.cap import InvestigationCap
    from faultline.orchestrator.consumer import ConsumerLoop, RedisEventSource
    from faultline.orchestrator.core import Orchestrator
    from faultline.orchestrator.correlation import TimeOverlapPolicy
    from faultline.orchestrator.store import PostgresIncidentStore

    settings = OrchestratorSettings()
    # `connect` builds the client with a socket timeout sized for `block_ms`. Doing it here
    # by hand is how the first live smoke crashed - see consumer.py's module docstring.
    source = RedisEventSource.connect(
        args.redis_url,
        stream=args.stream,
        group=args.group,
        consumer=args.consumer,
        idle_ms=settings.claim_idle_seconds * 1000,
        dead_letter_stream=settings.dead_letter_stream,
        block_ms=settings.block_ms,
    )
    source.ensure_group()

    if args.create_schema:
        from faultline.migrate import upgrade_head

        upgrade_head(args.postgres_dsn)

    store = PostgresIncidentStore(psycopg.connect(args.postgres_dsn))

    # T5.2. **The orchestrator cannot tell a benchmark's fault from a real one, and that is by
    # design**: ADR-0004 keeps the harness outside the product, and a scenario injects a genuine
    # fault into the demo world precisely so the pipeline meets it as one. Nothing in the alert
    # says "this is a measurement". So the eval profile suppresses notifications by
    # configuration - an unset webhook, or `--no-notify` - and there is no code path that could
    # do it instead. `faultline-investigate` *is* told (the harness passes `--exclude-origin`)
    # and suppresses its own half; this half is operational discipline, recorded rather than
    # papered over.
    from faultline.notify import SILENT
    from faultline.notify.slack import from_settings as notifier_from_settings

    announcer = SILENT if args.no_notify else notifier_from_settings()

    settle = timedelta(seconds=args.settle_window)
    loop = ConsumerLoop(
        source=source,
        orchestrator=Orchestrator(
            store=store,
            policy=TimeOverlapPolicy(settle),
            cap=InvestigationCap(args.max_concurrent),
            settle_window=settle,
            announcer=announcer,
        ),
        batch=settings.batch_size,
    )

    if args.once:
        applied = loop.run_once(block=False)
        print(f"applied {len(applied)} event(s)")
        return 0
    print(f"consuming {args.stream} as {args.group}/{args.consumer}")
    loop.run_forever()
    return 0
