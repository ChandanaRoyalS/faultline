"""Q57: what the benchmark's own change log costs the agent (`PREREGISTRATION-Q57.md`).

`injector.changelog` is the **only** writer to `change_records`, so every entry an agent reads is a
fault injection, and the harness injects every ~20 minutes against a tool whose lookback is 24
hours. A window that returns a handful of records in production returns a whole session here.

**The agent is not misreading anything.** Q53's pilot has it saying *"eight image-reference events
... after ~22 quiet hours"*, and the table says exactly that. It read a real log correctly and
reached a false conclusion, because a service accumulating fourteen changes in a day is ordinary
here and would be a screaming signal anywhere else.

## What this module does not do

**It does not decide which records are the harness's.** A record is *stale* if it predates this
run's own `injected_at`, and that is the whole rule. Parsing summaries or matching a catalog would
put a judgement inside the instrument, and the agent reading that log cannot make that judgement
either - which is the finding.

**It reconstructs no windows.** `trajectory_tool_calls.request` carries the window the specialist
actually asked for, with its `window_rule` and `lookback_seconds`. Recomputing the policy here
would be a second implementation of `faultline.tools.window`, which is the defect this repository
keeps writing down.

**It reuses `evaldb.row_of` and `variance.bootstrap_ci`** rather than re-flattening manifests or
writing a second interval. One scoring path, one interval, one seed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_RUNS_PER_SCENARIO = 4
"""A scenario needs four scored runs before its median splits into two halves worth comparing.
Below that the split is one run against one, which `bootstrap_ci` would render as a zero-width
interval around noise."""


@dataclass(frozen=True, slots=True)
class Query:
    """One `change_history` call, as it was recorded."""

    service: str
    start: datetime
    end: datetime

    @classmethod
    def from_request(cls, request: dict[str, Any]) -> Query | None:
        """`None` when the request predates the window fields, rather than a guess."""
        window = request.get("window") or []
        service = request.get("service")
        if not service or len(window) != 2:
            return None
        try:
            start, end = (_moment(w) for w in window)
        except (TypeError, ValueError):
            return None
        return cls(str(service), start, end)


def _moment(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


@dataclass
class Investigation:
    """One scored run, its change queries, and what they contained."""

    run_id: str
    scenario_id: str
    trajectory_id: str
    correct: bool | None
    abstained: bool | None
    injected_at: datetime | None
    reverted_at: datetime | None
    generation: str = ""
    queries: list[Query] = field(default_factory=list)
    own_ids: set[str] = field(default_factory=set)
    stale_ids: set[str] = field(default_factory=set)

    @property
    def own(self) -> int:
        return len(self.own_ids)

    @property
    def stale(self) -> int:
        return len(self.stale_ids)

    @property
    def scorable(self) -> bool:
        """Abstentions are excluded from accuracy and counted, ADR-0022 §1.2."""
        return self.correct is not None and not self.abstained


def classify(
    investigation: Investigation, records: list[tuple[str, str, datetime]]
) -> Investigation:
    """Split the records each query covered into this run's own and the session's leftovers.

    `records` is `(id, service, at)`, the whole table; the queries select from it. Distinct ids,
    so two queries covering one service do not count a record twice.
    """
    if investigation.injected_at is None:
        return investigation
    for query in investigation.queries:
        for record_id, service, at in records:
            if service != query.service or not (query.start <= at <= query.end):
                continue
            if at < investigation.injected_at:
                investigation.stale_ids.add(record_id)
            elif investigation.reverted_at is None or at <= investigation.reverted_at:
                investigation.own_ids.add(record_id)
    return investigation


@dataclass(frozen=True, slots=True)
class ScenarioSplit:
    """One scenario's runs, halved at its own median stale count."""

    scenario_id: str
    threshold: float
    low_accuracy: float
    high_accuracy: float
    low_n: int
    high_n: int
    low_abstentions: int
    high_abstentions: int

    @property
    def delta(self) -> float:
        """`low` minus `high`. **Positive means the noisier half did worse** - prediction 4."""
        return self.low_accuracy - self.high_accuracy


def split_by_stale(investigations: list[Investigation]) -> ScenarioSplit | None:
    """Halve one scenario's runs at its own median stale count.

    **At its own median, not a shared threshold.** Scenarios differ in how much residue they
    accumulate - a cartservice scenario follows every other cartservice scenario - and a global cut
    would sort scenarios rather than runs, which is the confound §3 exists to remove.

    `None` when the split is degenerate: too few runs, or every run on the same side of it.
    """
    if len(investigations) < MIN_RUNS_PER_SCENARIO:
        return None
    threshold = median(i.stale for i in investigations)
    low = [i for i in investigations if i.stale <= threshold]
    high = [i for i in investigations if i.stale > threshold]
    if not low or not high:
        return None
    return ScenarioSplit(
        scenario_id=investigations[0].scenario_id,
        threshold=threshold,
        low_accuracy=_accuracy(low),
        high_accuracy=_accuracy(high),
        low_n=len(low),
        high_n=len(high),
        low_abstentions=sum(1 for i in low if i.abstained),
        high_abstentions=sum(1 for i in high if i.abstained),
    )


def _accuracy(investigations: list[Investigation]) -> float:
    scorable = [i for i in investigations if i.scorable]
    if not scorable:
        return float("nan")
    return sum(1 for i in scorable if i.correct) / len(scorable)


def paired_difference(splits: list[ScenarioSplit]) -> tuple[float, float, float, int]:
    """Mean paired difference and its bootstrapped 95% CI. `variance.bootstrap_ci`'s seed."""
    from evalharness.variance import bootstrap_ci

    deltas = [s.delta for s in splits if s.delta == s.delta]
    if not deltas:
        return (float("nan"), float("nan"), float("nan"), 0)
    mean = sum(deltas) / len(deltas)
    low, high = bootstrap_ci(deltas)
    return (mean, low, high, len(deltas))


def investigations_from(manifests: list[tuple[str, dict[str, Any]]]) -> list[Investigation]:
    """Scored runs only, flattened through `evaldb.row_of` so the scoring path is the one path."""
    from evalharness.evaldb import row_of

    out: list[Investigation] = []
    for run_id, manifest in manifests:
        row = row_of(manifest, run_id)
        if row.outcome != "scored":
            continue
        values = row.values
        trajectory_id = str(values.get("trajectory_id") or "")
        if not trajectory_id:
            continue
        out.append(
            Investigation(
                run_id=row.run_id,
                scenario_id=row.scenario_id,
                trajectory_id=trajectory_id,
                correct=values.get("fault_class_correct"),
                abstained=values.get("fault_class_abstained"),
                injected_at=_maybe(manifest.get("injected_at")),
                reverted_at=_maybe(manifest.get("reverted_at")),
                generation=str(values.get("world_generation") or ""),
            )
        )
    return out


def _maybe(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return _moment(value)
    except (TypeError, ValueError):
        return None


def render(
    investigations: list[Investigation], splits: list[ScenarioSplit]
) -> str:  # pragma: no cover - reporting
    scored = [i for i in investigations if i.injected_at]
    stale = sorted(i.stale for i in scored)
    own = sorted(i.own for i in scored)
    mean, low, high, n = paired_difference(splits)
    lines = [
        f"investigations   : {len(scored)}",
        f"stale records    : median {median(stale) if stale else 0}, max {max(stale, default=0)}",
        f"own records      : median {median(own) if own else 0}",
        f"saw zero stale   : {sum(1 for s in stale if s == 0)} of {len(scored)}",
        f"scenarios split  : {n}",
        f"accuracy low-high: {mean:+.3f}  95% CI [{low:+.3f}, {high:+.3f}]",
        "",
        "  (positive means the noisier half did worse)",
        "",
    ]
    for split in sorted(splits, key=lambda s: -s.delta):
        lines.append(
            f"  {split.scenario_id:34} cut>{split.threshold:<5.1f} "
            f"low {split.low_accuracy:.2f} (n={split.low_n}) "
            f"high {split.high_accuracy:.2f} (n={split.high_n}) "
            f"delta {split.delta:+.2f}"
        )
    return "\n".join(lines)


def run_cli(argv: list[str] | None = None) -> int:  # pragma: no cover - the live path
    import argparse

    parser = argparse.ArgumentParser(
        prog="faultline-change-residue",
        description=(
            "Q57: how much of the change log an investigation reads is the harness's own "
            "leftovers. Reads manifests and Postgres; spends nothing."
        ),
    )
    parser.add_argument("--runs", type=Path, default=REPO_ROOT / "evals" / "runs")
    parser.add_argument("--postgres-dsn", default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    import psycopg

    from faultline.context.settings import ContextSettings

    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    manifests: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(args.runs.glob("*/manifest.json")):
        try:
            manifests.append((path.parent.name, json.loads(path.read_text())))
        except (OSError, ValueError):
            continue

    investigations = investigations_from(manifests)
    by_trajectory = {i.trajectory_id: i for i in investigations}

    with psycopg.connect(dsn) as conn:
        records = [
            (str(r[0]), str(r[1]), r[2])
            for r in conn.execute("SELECT id, service, at FROM change_records")
        ]
        for trajectory_id, request in conn.execute(
            "SELECT trajectory_id, request FROM trajectory_tool_calls WHERE tool = %s",
            ("change_history",),
        ):
            investigation = by_trajectory.get(str(trajectory_id))
            if investigation is None:
                continue
            query = Query.from_request(request or {})
            if query is not None:
                investigation.queries.append(query)

    for investigation in investigations:
        classify(investigation, records)

    by_scenario: dict[str, list[Investigation]] = {}
    for investigation in investigations:
        if investigation.injected_at:
            by_scenario.setdefault(investigation.scenario_id, []).append(investigation)
    splits = [s for s in (split_by_stale(v) for v in by_scenario.values()) if s is not None]

    print(render(investigations, splits))
    if args.out:
        mean, low, high, n = paired_difference(splits)
        args.out.write_text(
            json.dumps(
                {
                    "investigations": [
                        {
                            "run_id": i.run_id,
                            "scenario_id": i.scenario_id,
                            "generation": i.generation,
                            "stale": i.stale,
                            "own": i.own,
                            "queries": len(i.queries),
                            "correct": i.correct,
                            "abstained": i.abstained,
                        }
                        for i in investigations
                        if i.injected_at
                    ],
                    "splits": [
                        {
                            "scenario_id": s.scenario_id,
                            "threshold": s.threshold,
                            "low_accuracy": s.low_accuracy,
                            "high_accuracy": s.high_accuracy,
                            "low_n": s.low_n,
                            "high_n": s.high_n,
                            "low_abstentions": s.low_abstentions,
                            "high_abstentions": s.high_abstentions,
                            "delta": s.delta,
                        }
                        for s in splits
                    ],
                    "paired_difference": {"mean": mean, "ci_low": low, "ci_high": high, "n": n},
                },
                indent=2,
            )
            + "\n"
        )
        print(f"\n-> {args.out}")
    return 0
