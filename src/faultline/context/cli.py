"""`faultline-seed` - seed the past-incident store from the dev split (T2.4b, ADR-0018).

There is deliberately **no `--split` flag and no `--holdout`**. The seeding input is one
directory (ADR-0008), and a CLI that could be pointed at the other one is the same defect as
a seeder that could: the guard in `faultline.context.seed.require_dev_root` still refuses,
but an interface that offers the option invites the argument about whether the guard is too
strict. `--dev-root` exists only so a checkout in another location can be seeded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from faultline.context.settings import ContextSettings

DEFAULT_DEV_ROOT = "evals/scenarios/artifacts/dev"


def parser() -> argparse.ArgumentParser:
    """Flags override `FAULTLINE_CONTEXT_*`, which overrides the defaults."""
    settings = ContextSettings()
    p = argparse.ArgumentParser(
        prog="faultline-seed",
        description=(
            "Seed the past-incident store from rehearsal narratives in the dev split, "
            "one chunk per narrative section (T2.4b, ADR-0018)."
        ),
        epilog=(
            "The dev split is the only seeding input (ADR-0008). A holdout path is refused "
            "structurally, as is a narrative whose front matter disagrees with its path."
        ),
    )
    p.add_argument(
        "--dev-root",
        default=DEFAULT_DEV_ROOT,
        help="the dev artifacts directory (default: %(default)s)",
    )
    p.add_argument("--postgres-dsn", default=settings.postgres_dsn, help="default: %(default)s")
    p.add_argument(
        "--embedder",
        default=settings.embedder,
        help="local sentence-transformers model (default: %(default)s)",
    )
    p.add_argument(
        "--create-schema",
        action="store_true",
        help="create the extension and tables if they do not exist, then continue",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and chunk, applying every quarantine guard, without a database or a model",
    )
    return p


def run(argv: list[str] | None = None) -> int:
    """Entry point. Imports its backends late, so `--help` needs no Postgres and no model."""
    args = parser().parse_args(argv)

    from faultline.context.seed import QuarantineError, seed

    if args.dry_run:
        # A store that accepts chunks and keeps nothing, so the guards and the parsing run
        # with no database and no model. This is the cheap way to check a new narrative
        # before spending a download on it.
        from faultline.context.embedding import HashingEmbedder
        from faultline.context.store import InMemoryPastIncidentStore

        store: object = InMemoryPastIncidentStore(HashingEmbedder())
    else:
        import psycopg

        from faultline.context.embedding import SentenceTransformerEmbedder
        from faultline.context.store import PgVectorPastIncidentStore

        real = PgVectorPastIncidentStore(
            psycopg.connect(args.postgres_dsn), SentenceTransformerEmbedder(args.embedder)
        )
        if args.create_schema:
            real.create_schema()
        store = real

    try:
        result = seed(store, Path(args.dev_root))  # type: ignore[arg-type]
    except QuarantineError as exc:
        # Same shape as `faultline-inject`: a refusal is an error message and a non-zero
        # exit, not a traceback. The message is the guard's own and says what was refused.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"documents={result.documents} chunks={result.chunks}")
    for name in result.seeded:
        print(f"  seeded  {name}")
    for name, why in result.skipped:
        print(f"  skipped {name} - {why}")
    if args.dry_run:
        print("(dry run - nothing was written)")
    return 0
