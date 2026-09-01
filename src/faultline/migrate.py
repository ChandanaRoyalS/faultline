"""Applying the schema (T2.3, "migrations from day one").

Before this existed, four modules each carried a `CREATE TABLE IF NOT EXISTS` block and each
applied its own. That works for exactly as long as every change is additive: `IF NOT EXISTS`
can add a table or a column and can express nothing else - no rename, no type change, no
backfill, and no ordering between the four modules. It also hid a real defect for months, an
`ALTER` above the `CREATE` it depended on, which was invisible because no database had ever
been built from nothing.

One history now, for one database. `faultline-migrate` applies it; `--stamp` records an
existing database as already current without running anything, which is what an established
deployment needs on the first upgrade after this change.
"""

from __future__ import annotations

import argparse
from functools import cache
from pathlib import Path

from alembic import command
from alembic.config import Config

INI_NAME = "alembic.ini"


@cache
def ini_path() -> Path:
    """Walk up for `alembic.ini`. Repository data, like `knowledge/` - see ADR-0032."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / INI_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"no {INI_NAME} above {__file__}")


def _config(dsn: str | None) -> Config:
    cfg = Config(str(ini_path()))
    cfg.set_main_option("script_location", str(ini_path().parent / "migrations"))
    if dsn is not None:
        # Passed through `attributes` rather than an environment variable: a migration run
        # must go to the database the caller named, and mutating the environment to say so
        # would leak into everything else the process does afterwards.
        cfg.attributes["dsn"] = dsn
    return cfg


def upgrade_head(dsn: str | None = None) -> None:
    """Bring `dsn` (or the configured database) to the newest revision."""
    command.upgrade(_config(dsn), "head")


def stamp_head(dsn: str | None = None) -> None:
    """Record a database as current without running anything.

    For a database created by the pre-migration `create_schema()` path: its tables already
    match revision 0001, and running 0001 against it would be harmless but dishonest - the
    version table should say what actually happened.
    """
    command.stamp(_config(dsn), "head")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply the Faultline database schema.")
    parser.add_argument("--dsn", default=None, help="defaults to FAULTLINE_ORCH_POSTGRES_DSN")
    parser.add_argument(
        "--stamp",
        action="store_true",
        help="mark an existing schema as current instead of applying anything",
    )
    args = parser.parse_args()
    (stamp_head if args.stamp else upgrade_head)(args.dsn)
