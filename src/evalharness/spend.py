"""What a sweep has spent so far, read between launches (Q70).

## The gap

`faultline-sweep` printed an estimate - `budget about $N` from `MEDIAN_RUN_USD` and `DISCARD_RATE`
- and then ran the catalog to the end whatever it cost. Every registered hard ceiling this
repository had written was enforced by an operator watching, or by cutting the sweep into blocks
small enough that stopping between them was enough: T6.5 §6 registered *"Hard ceiling: $55.
Reaching it stops the run where it stands and reports the arms it did not complete"*, Amendment 3
raised it to $70, and nothing in the harness implemented that sentence. Amendment 7 §4 enforced it
at block boundaries by hand, which worked and was not what the registration said.

## Where the number is

**In the trajectory store, not in the sweep.** `MEDIAN_RUN_USD`'s docstring says why the estimate
cannot be recomputed from the tree - a run's cost lives in `trajectory_steps` as tokens. So the
sweep reads it from there: the manifests that carry this sweep's id (`manifest["sweep"]["id"]`,
Q60) name the incidents the sweep opened, and the store holds every token spent under them,
**including runs that failed before scoring and therefore have no `score.cost_usd`** - which is
the case a manifest-only sum would miss and a ceiling most needs to see. Priced at the harness's
own table (`run.USD_PER_MTOK_*`), the same one that scores `cost_usd`, so the ceiling and the
figures it protects are in the same dollars.

Without a database the sum falls back to the manifests' `score.cost_usd` and says so; a ceiling
read from manifests alone under-counts failed runs, and the report names its source so a reader
can tell which number they are looking at.

## What the ceiling is not

It is checked **before each launch**, so a sweep that stands at $69.90 against a $70 ceiling
launches one more run and stops after it - the overshoot is bounded by one run, and the report
prints the spend that made it stop. It is not a per-run cap (`Budget.max_usd` is), and it is not a
projection: a run in flight is not counted until its steps are written, which is when it has been
paid for.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from faultline.pgread import reading

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / "evals" / "runs"

USD_PER_MTOK_IN = 5.0
USD_PER_MTOK_OUT = 25.0
"""Restated from `evalharness.run`, which imports half the harness; a test holds them equal."""


@dataclass(frozen=True, slots=True)
class Spend:
    usd: float
    runs: int
    """Manifests in `evals/runs/` carrying this sweep's id - every slot that got as far as a run
    directory, scored or not."""
    source: str
    """`trajectory store` or `manifests`. Read it before trusting `usd`: the second under-counts."""

    def render(self) -> str:
        return f"${self.usd:.2f} over {self.runs} run(s), from the {self.source}"


def manifests_of(session: str, root: Path = RUN_ROOT) -> list[dict[str, Any]]:
    """Every manifest whose `sweep.id` is this session, in run order."""
    found: list[dict[str, Any]] = []
    if not root.is_dir():
        return found
    for path in sorted(root.iterdir()):
        manifest = path / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            loaded = json.loads(manifest.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(loaded, dict) and (loaded.get("sweep") or {}).get("id") == session:
            found.append(loaded)
    return found


def session_spend(
    session: str,
    dsn: str | None,
    *,
    root: Path = RUN_ROOT,
    connect: Callable[[str], Any] | None = None,
) -> Spend:
    """What this sweep id has cost so far - across every block that carried it, because a
    ceiling registered for a task is a ceiling on the task and not on one invocation."""
    manifests = manifests_of(session, root)
    incidents = [m["incident_id"] for m in manifests if m.get("incident_id")]
    if dsn and incidents:
        connector = connect or _connect
        with connector(dsn) as conn, reading(conn) as cur:
            cur.execute(
                "SELECT COALESCE(SUM(s.tokens_in), 0), COALESCE(SUM(s.tokens_out), 0) "
                "FROM trajectory_steps s JOIN trajectories t ON t.id = s.trajectory_id "
                "WHERE t.incident_id = ANY(%s)",
                (incidents,),
            )
            tokens_in, tokens_out = cur.fetchone() or (0, 0)
        usd = int(tokens_in) / 1e6 * USD_PER_MTOK_IN + int(tokens_out) / 1e6 * USD_PER_MTOK_OUT
        return Spend(usd=usd, runs=len(manifests), source="trajectory store")
    usd = sum(float((m.get("score") or {}).get("cost_usd") or 0.0) for m in manifests)
    return Spend(usd=usd, runs=len(manifests), source="manifests")


def _connect(dsn: str) -> Any:  # pragma: no cover - the real connection
    import psycopg

    return psycopg.connect(dsn)
