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
    p.add_argument(
        "--no-runbooks",
        action="store_true",
        help=(
            "skip the authored runbooks (Q15). They are seeded by default: T2.4b's deliverable "
            "names a seeded runbook corpus, and T4.1b's never-excluded branch has nothing to "
            "not-exclude without them"
        ),
    )
    p.add_argument(
        "--import-acceptances",
        action="store_true",
        help=(
            "before seeding, replicate the committed ledger (ACCEPTANCES.json in the dev root) "
            "into this database's postmortem_acceptances, for rows it lacks. Rows go in "
            "verbatim - the caller and date of the original decision - so a fresh deployment "
            "can admit the postmortems a person accepted elsewhere without anyone re-deciding"
        ),
    )
    return p


def run(argv: list[str] | None = None) -> int:
    """Entry point. Imports its backends late, so `--help` needs no Postgres and no model."""
    args = parser().parse_args(argv)

    from faultline.context.acceptance import (
        AcceptanceStore,
        InMemoryAcceptanceStore,
        PostgresAcceptanceStore,
        import_ledger,
        ledger_path,
        ledger_store,
        read_ledger,
    )

    ledger = ledger_path(Path(args.dev_root))
    from faultline.context.seed import QuarantineError, UnacceptedError, seed, seed_runbooks

    if args.dry_run:
        # A store that accepts chunks and keeps nothing, so the guards and the parsing run
        # with no database and no model. This is the cheap way to check a new narrative
        # before spending a download on it.
        from faultline.context.embedding import HashingEmbedder
        from faultline.context.store import InMemoryPastIncidentStore

        store: object = InMemoryPastIncidentStore(HashingEmbedder())
        # **The committed ledger, when the tree carries one** (Q67). A dry run has no database
        # and used to hand `seed` an empty ledger, so it refused every postmortem on a tree
        # where nothing was wrong. The committed rows are the same decisions the database
        # holds; reading them writes nothing, which is what a dry run promises. A tree without
        # the file - a fresh scenario's narrative being checked before a download - still gets
        # the empty ledger and the refusal it always had.
        if ledger.is_file():
            acceptances: AcceptanceStore = ledger_store(ledger)
            print(f"acceptances: {len(read_ledger(ledger))} row(s) read from {ledger}")
        else:
            acceptances = InMemoryAcceptanceStore()
    else:
        import psycopg

        from faultline.context.embedding import SentenceTransformerEmbedder
        from faultline.context.store import PgVectorPastIncidentStore

        connection = psycopg.connect(args.postgres_dsn)
        real = PgVectorPastIncidentStore(connection, SentenceTransformerEmbedder(args.embedder))
        if args.create_schema:
            from faultline.migrate import upgrade_head

            upgrade_head(args.postgres_dsn)
        store = real
        acceptances = PostgresAcceptanceStore(connection)
        if args.import_acceptances:
            rows = read_ledger(ledger)
            appended = import_ledger(rows, acceptances)
            print(f"acceptances: imported {appended} of {len(rows)} row(s) from {ledger}")

    try:
        result = seed(store, Path(args.dev_root), acceptances)  # type: ignore[arg-type]
        # **A second call, not a second root** (Q15). `seed` reads one directory and refuses
        # anything else; the runbooks arrive through their own entry point with their own
        # guard, so neither input can be widened into the other.
        books = None if args.no_runbooks else seed_runbooks(store)  # type: ignore[arg-type]
    except QuarantineError as exc:
        # Same shape as `faultline-inject`: a refusal is an error message and a non-zero
        # exit, not a traceback. The message is the guard's own and says what was refused.
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except UnacceptedError as exc:
        # **Refused, not skipped.** A postmortem nobody accepted is not a seeding input, and a
        # run that seeded the rest and mentioned this in passing would be the warning-nobody-
        # reads that `api/auth.py` argues against.
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total_documents = result.documents + (books.documents if books else 0)
    total_chunks = result.chunks + (books.chunks if books else 0)
    print(f"documents={total_documents} chunks={total_chunks}")
    for name in result.seeded:
        print(f"  seeded  scenario:{name}")
    for name, why in result.skipped:
        print(f"  skipped {name} - {why}")
    if books is None:
        print("  runbooks were not seeded (--no-runbooks)")
    else:
        for name in books.seeded:
            print(f"  seeded  runbook:{name}")
    if args.dry_run:
        print("(dry run - nothing was written)")
    return 0
