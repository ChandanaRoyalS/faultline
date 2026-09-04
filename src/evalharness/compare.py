"""The comparison report between any two configurations (T4.4, with T4.6's figures).

T4.4: *"generate a comparative report between any two versions"*, where *"the report generator
emits mean, 95% CI, n, and R on every figure it prints, and a figure without all four is a bug in
the generator"*, and *"reports break out dev vs holdout - headline numbers follow T1.6's policy:
full-set with labeled split and explicit n until the catalog reaches 30+, holdout-only
thereafter."*

## The four-part figure is not enforced here

It cannot be violated here, because `variance.Figure` requires all four to construct. This module
never formats a number by hand; every printed quantity comes from `Figure.render()` or is a count
that a reader can check against the run table. That is the difference between a generator that
follows the rule and one that cannot break it.

## What is compared, and what is dropped

**Only `scored` runs.** A discarded run produced no number and an invalid one produced a number
that may not be used (T4.1b); both are counted in the report's header, because the discard rate
is a property of a comparison and not an operational footnote, and neither contributes to a
figure.

**Only scenarios both arms ran.** Pairing is the whole variance argument, so a scenario present in
one arm and absent from the other is excluded and named. Excluding it silently would let a
comparison quietly become a comparison of different catalogs.

**Abstentions are excluded from accuracy and counted separately**, per ADR-0022 §1.2: an
abstention is neither right nor wrong, and scoring it either way would make "say nothing" a
strategy with a payoff.

## The split, and why both halves print at this catalog size

T1.6's policy is full-set-with-labeled-split until the catalog reaches 30, holdout-only
thereafter. This catalog is 18. So the report prints the combined figure **and** the dev and
holdout figures beside it with explicit `n` on each - which is the policy, and is also the only
honest presentation when a holdout arm of three or four scenarios cannot carry a headline on its
own.

## The verdict is the plan's, applied to every figure

*"A delta below its MDE is reported as 'no measurable effect at this catalog size'"*. At `n = 10`
and `R = 1` the MDE is 28pp, so most deltas this repository can currently produce will say exactly
that. **That is the report working**, not the report failing: it is the difference between a
benchmark and a demo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from evalharness import variance
from evalharness.sweep import runnable


@dataclass(frozen=True, slots=True)
class Metric:
    """One comparable quantity, and which direction is better."""

    key: str
    label: str
    unit: str = "pp"
    higher_is_better: bool = True
    skip_when_abstained: bool = False
    """Accuracy metrics only. ADR-0022 §1.2: an abstention is neither right nor wrong."""


BASELINE_REASONS: dict[str, str] = {
    "B0": "v1's single run is superseded; B0.2 has not run",
    "B1": "built and tested; runs need credits",
    "B2": "built and tested; runs need credits",
}
"""Why each baseline has no figure yet, as of 2026-09-03.

**Stated rather than left blank**, because *"not run"* with no reason is a blank a reader has to
guess at, and 'too expensive', 'not built' and 'forgotten' have very different implications for
whether the rest of the table can be trusted. Each line here should shrink to nothing as the runs
happen; a stale entry is visible the moment a baseline has a figure beside it.
"""

METRICS = (
    Metric("fault_class_correct", "fault class accuracy", skip_when_abstained=True),
    Metric("fix_class_correct", "fix class accuracy", skip_when_abstained=True),
    Metric("triage_recall", "triage recall"),
    Metric("triage_precision", "triage precision"),
    Metric("cost_usd", "cost per run", unit="$", higher_is_better=False),
    Metric("latency_ms", "latency", unit="ms", higher_is_better=False),
)


@dataclass(frozen=True, slots=True)
class Run:
    """One scored run, as the comparison needs it."""

    scenario_id: str
    split: str | None
    values: dict[str, Any] = field(default_factory=dict)
    abstained: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Arm:
    """Every scored run under one configuration."""

    fingerprint: str
    runs: list[Run] = field(default_factory=list)
    declared_r: int | None = None
    runtime_version: str | None = None
    discarded: int = 0
    invalid: int = 0

    @property
    def scenarios(self) -> set[str]:
        return {run.scenario_id for run in self.runs}

    @property
    def observed_r(self) -> float:
        """Runs per scenario, actually observed. **Reported beside `declared_r`, never instead of
        it**: a configuration declared at R = 5 that ran three scenarios once each is not an R = 5
        comparison, and only printing the declaration would hide that."""
        return len(self.runs) / len(self.scenarios) if self.scenarios else 0.0

    def per_scenario(self, metric: Metric) -> dict[str, float]:
        """One value per scenario: the mean over that scenario's runs in this arm.

        Runs with no value for the metric are skipped rather than read as zero - a run recorded
        before latency was measured has no latency, and averaging it in as zero would report an
        instantaneous investigation.
        """
        collected: dict[str, list[float]] = {}
        for run in self.runs:
            if metric.skip_when_abstained and run.abstained.get(metric.key):
                continue
            value = run.values.get(metric.key)
            if value is None:
                continue
            collected.setdefault(run.scenario_id, []).append(float(value))
        return {name: sum(v) / len(v) for name, v in collected.items() if v}


@dataclass(frozen=True, slots=True)
class Comparison:
    """One metric, compared across two arms, at one split."""

    metric: Metric
    scope: str
    figure: variance.Figure
    verdict: str
    scenarios: list[str]


def compare_metric(
    a: Arm, b: Arm, metric: Metric, scope: str, only: set[str] | None = None
) -> Comparison | None:
    """`b - a` on one metric, paired by scenario. `None` when no scenario is shared."""
    left, right = a.per_scenario(metric), b.per_scenario(metric)
    if only is not None:
        left = {k: v for k, v in left.items() if k in only}
        right = {k: v for k, v in right.items() if k in only}
    deltas = variance.paired_deltas(left, right)
    if not deltas:
        return None
    r = min(int(a.declared_r or 1), int(b.declared_r or 1))
    return Comparison(
        metric=metric,
        scope=scope,
        figure=variance.figure(f"{metric.label} ({scope})", deltas, r=r, unit=metric.unit),
        verdict=variance.verdict(sum(deltas.values()) / len(deltas), n=len(deltas), r=r)
        if metric.unit == "pp"
        else "MDE applies to proportions; this figure is reported with its interval only",
        scenarios=sorted(deltas),
    )


def splits_of(a: Arm, b: Arm) -> dict[str, set[str]]:
    """Scenario names by split, over the scenarios both arms ran."""
    shared = a.scenarios & b.scenarios
    by_split: dict[str, set[str]] = {}
    for run in [*a.runs, *b.runs]:
        if run.scenario_id in shared and run.split:
            by_split.setdefault(run.split, set()).add(run.scenario_id)
    return by_split


CATALOG_HOLDOUT_THRESHOLD = 30
"""T1.6's switch: full-set with labeled split and explicit n below this, holdout-only above."""


def report(
    a: Arm,
    b: Arm,
    catalog_size: int = 18,
    at: datetime | None = None,
    baselines: dict[str, Arm] | None = None,
    baseline_reasons: dict[str, str] | None = None,
) -> list[str]:
    """The comparison report. Every figure carries mean, 95% CI, n and R by construction.

    **Every metric section carries a baseline panel** (T4.7): *"baseline columns mandatory in
    every headline table"*. `baselines` is keyed by display id and may be empty - a baseline with
    no runs is rendered as a row saying so, never left out, because a table without baseline rows
    reads as one whose author did not think to ask. `baseline_columns.BaselinePanel` refuses to
    construct if a baseline is missing entirely, so this cannot silently regress.
    """
    from evalharness import baseline_columns

    when = (at or datetime.now(UTC)).date().isoformat()
    shared = sorted(a.scenarios & b.scenarios)
    only_a = sorted(a.scenarios - b.scenarios)
    only_b = sorted(b.scenarios - a.scenarios)
    by_split = splits_of(a, b)

    lines = [
        f"# Comparison — `{a.fingerprint}` → `{b.fingerprint}`",
        "",
        f"Generated {when} by `evalharness.compare`. **Every figure carries mean, 95% CI, n and "
        "R**, which is not a review convention here: `variance.Figure` cannot be constructed "
        "without them.",
        "",
        "| | A | B |",
        "|---|---|---|",
        f"| config fingerprint | `{a.fingerprint}` | `{b.fingerprint}` |",
        f"| runtime | `{a.runtime_version or 'not recorded'}` | "
        f"`{b.runtime_version or 'not recorded'}` |",
        f"| declared R | {a.declared_r if a.declared_r else 'not recorded'} | "
        f"{b.declared_r if b.declared_r else 'not recorded'} |",
        f"| observed runs per scenario | {a.observed_r:.2f} | {b.observed_r:.2f} |",
        f"| scored runs | {len(a.runs)} | {len(b.runs)} |",
        f"| discarded | {a.discarded} | {b.discarded} |",
        f"| invalid | {a.invalid} | {b.invalid} |",
        "",
    ]

    if a.declared_r is None or b.declared_r is None:
        # **Not the same thing as a mismatch**, and the first real report said the wrong one: it
        # printed "the figures below use the lower declared R" for two arms that declared none.
        # These configurations predate T4.6, so `repeat_count` was not a fingerprint input when
        # they ran and cannot be added retroactively - the figures fall back to R = 1.
        lines += [
            "> **Neither arm recorded a declared R.** Both predate the repeat count becoming a "
            f"fingerprint input (T4.6), and observed runs per scenario are {a.observed_r:.2f} and "
            f"{b.observed_r:.2f}. The figures below are computed at **R = 1** - the honest "
            "fallback, and a floor on what they claim rather than a description of what ran.",
            "",
        ]
    elif a.declared_r != a.observed_r or b.declared_r != b.observed_r:
        lines += [
            "> **Declared R and observed runs per scenario differ.** The figures below use the "
            "lower declared R, because a configuration declared at one repeat count that ran a "
            "different number of times is not the comparison its declaration claims.",
            "",
        ]

    lines += [
        f"**Paired on {len(shared)} scenario(s)** that both arms ran. Pairing is the variance "
        "argument, so a scenario only one arm ran is excluded rather than averaged in.",
        "",
    ]
    if only_a or only_b:
        lines += [
            f"- only in A: {', '.join(f'`{s}`' for s in only_a) or 'none'}",
            f"- only in B: {', '.join(f'`{s}`' for s in only_b) or 'none'}",
            "",
        ]

    if catalog_size < CATALOG_HOLDOUT_THRESHOLD:
        lines += [
            f"**Split policy (T1.6).** The catalog is {catalog_size} scenarios, below the "
            f"{CATALOG_HOLDOUT_THRESHOLD} at which headline numbers become holdout-only. So the "
            "full set is reported with a labeled split and explicit n on every figure, and no "
            "figure here is a headline number.",
            "",
        ]
    else:  # pragma: no cover - the catalog has never been this size
        lines += [
            f"**Split policy (T1.6).** The catalog is {catalog_size} scenarios, at or above the "
            "threshold, so the holdout figures are the headline and the dev figures are "
            "diagnostic.",
            "",
        ]

    for metric in METRICS:
        rows = [compare_metric(a, b, metric, "all")]
        for split in sorted(by_split):
            rows.append(compare_metric(a, b, metric, split, only=by_split[split]))
        found = [row for row in rows if row is not None]
        if not found:
            continue
        lines.append(f"## {metric.label}")
        lines.append("")
        direction = "higher is better" if metric.higher_is_better else "lower is better"
        lines.append(f"*{direction}. Reported as B minus A.*")
        lines.append("")
        for row in found:
            lines.append(f"- {row.figure.render()}")
            lines.append(f"  - {row.verdict}")
            # **A metric's n is not the pairing count, and the first real report never said so.**
            # `compare_metric` drops a scenario that lacks this metric in *either* arm, silently -
            # so the header said "paired on 8 scenario(s)" and fault class then reported n=6 with
            # nothing to tell a reader whether two scenarios were missing a score or the harness
            # had a bug. The list is already carried on `Comparison.scenarios`; only the saying
            # was missing.
            expected = len(by_split[row.scope]) if row.scope in by_split else len(shared)
            if len(row.scenarios) < expected:
                absent = sorted(
                    (by_split[row.scope] if row.scope in by_split else set(shared))
                    - set(row.scenarios)
                )
                lines.append(
                    f"  - n is {len(row.scenarios)} of {expected} paired scenario(s): "
                    f"{', '.join(f'`{name}`' for name in absent)} recorded no value for this "
                    "metric in one arm or both, so the pair could not be formed"
                )
        lines.append("")
        # T4.7. Printed for every metric, including when no baseline has run: the panel type
        # refuses to exist without all three, so the only way this section disappears is if
        # someone deletes these two lines, which a test catches.
        lines += baseline_columns.panel(metric, baselines or {}, baseline_reasons).render()

    lines += [
        "## What this report does not say",
        "",
        "It does not attribute a difference to a cause. Two configurations differ by whatever "
        "differs between their fingerprints, and a fingerprint can move for several reasons at "
        "once - the settings object under each is in `eval_configs.settings` and is the only "
        "place the actual difference can be read.",
        "",
        "It does not treat a below-MDE delta as an absence of effect. It reports that **this "
        "catalog at this size cannot detect one**, which is a statement about the benchmark "
        "rather than about the pipelines.",
        "",
    ]
    return lines


# --- the database reader ------------------------------------------------------------------


def arm(dsn: str, fingerprint: str) -> Arm:
    """Load one configuration's arm from `eval_runs`."""
    import psycopg

    columns = [metric.key for metric in METRICS]
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT repeat_count, runtime_version FROM eval_runs WHERE config_fingerprint = %s "
            "AND repeat_count IS NOT NULL LIMIT 1",
            (fingerprint,),
        )
        found = cur.fetchone()
        declared_r, runtime_version = (found[0], found[1]) if found else (None, None)
        if runtime_version is None:
            # **`IS NOT NULL` matters here and its absence was a real defect.** A discarded run
            # has no score block and therefore no `runtime_version`, so an unfiltered `LIMIT 1`
            # returns whichever row the planner happens to reach first - and on an arm with
            # discards that is often one of them, which printed `not recorded` for a
            # configuration whose runtime the same table knows. Found on the first live
            # comparison, where arm B showed `not recorded` and arm A, which had no discards,
            # did not.
            cur.execute(
                "SELECT runtime_version FROM eval_runs WHERE config_fingerprint = %s "
                "AND runtime_version IS NOT NULL LIMIT 1",
                (fingerprint,),
            )
            row = cur.fetchone()
            runtime_version = row[0] if row else None

        cur.execute(
            f"SELECT scenario_id, split, outcome, fault_class_abstained, fix_class_abstained, "
            f"{', '.join(columns)} FROM eval_runs WHERE config_fingerprint = %s",
            (fingerprint,),
        )
        runs: list[Run] = []
        discarded = invalid = 0
        for row in cur.fetchall():
            scenario_id, split, outcome, fault_abstained, fix_abstained = row[:5]
            if outcome == "invalid":
                invalid += 1
                continue
            if outcome != "scored":
                discarded += 1
                continue
            runs.append(
                Run(
                    scenario_id=str(scenario_id),
                    split=split,
                    values=dict(zip(columns, row[5:], strict=True)),
                    abstained={
                        "fault_class_correct": bool(fault_abstained),
                        "fix_class_correct": bool(fix_abstained),
                    },
                )
            )
    return Arm(
        fingerprint=fingerprint,
        runs=runs,
        declared_r=declared_r,
        runtime_version=runtime_version,
        discarded=discarded,
        invalid=invalid,
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - console entry point
    """`faultline-compare A B` — a comparison report between two config fingerprints.

    Writes to `evals/reports/` and prints to stdout. `--list` names the fingerprints available,
    because a comparison begins with not knowing them.
    """
    import argparse
    from pathlib import Path

    from faultline.context.settings import ContextSettings

    parser = argparse.ArgumentParser(
        prog="faultline-compare",
        description="A comparative report between any two eval configurations (T4.4).",
    )
    parser.add_argument("a", nargs="?", help="baseline config fingerprint")
    parser.add_argument("b", nargs="?", help="candidate config fingerprint")
    parser.add_argument("--list", action="store_true", help="list configurations and exit")
    parser.add_argument(
        "--aa",
        metavar="FINGERPRINT",
        default=None,
        help=(
            "Gate 4's A/A check: split one configuration's runs in two and compare it against "
            "itself. Needs R >= 2 - at R = 1 a scenario has one run and cannot be in both arms, "
            "so there is no check to perform rather than a weak one."
        ),
    )
    # **Counted, not typed.** It was hardcoded `18` and the catalog is 19 with 2 unrunnable, so
    # every generated report stated a size that was never right. The number decides whether T1.6's
    # headline policy has switched to holdout-only, so a stale constant here is a stale policy
    # claim in the report - `sweep.runnable()` is the same list a sweep would actually run.
    parser.add_argument("--catalog-size", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("evals/reports"))
    parser.add_argument("--postgres-dsn", default=None)
    args = parser.parse_args(argv)

    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    import psycopg

    try:
        if args.aa:
            from evalharness import aa as aa_check

            single = arm(dsn, args.aa)
            if not single.runs:
                print(f"REFUSED: {args.aa} has no scored runs")
                return 3
            try:
                result = aa_check.check(single)
            except aa_check.NotEnoughRepeatsError as thin:
                # **Not a failure of the check** - the check could not be performed. Exit 3, the
                # code every other "nothing ran" refusal uses, so a caller cannot read it as the
                # harness having invented a delta.
                print(f"REFUSED: {thin}")
                return 3
            print("\n".join(result.render()))
            print(aa_check.mde_at(len(single.scenarios), single.declared_r or 1))
            # **Exit 1 on failure, so CI can gate on it.** Gate 4 makes this a condition, and a
            # condition nothing can fail is not one.
            return 0 if result.passed else 1

        if args.list:
            with psycopg.connect(dsn) as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT c.fingerprint, count(*) FILTER (WHERE r.outcome = 'scored'), "
                    "min(r.scenario_id), c.runtime_version FROM eval_configs c "
                    "LEFT JOIN eval_runs r ON r.config_fingerprint = c.fingerprint "
                    "GROUP BY c.fingerprint, c.runtime_version ORDER BY 2 DESC"
                )
                print(f"{'fingerprint':14} {'scored':>7}  runtime")
                for fingerprint, scored, _, runtime in cur.fetchall():
                    print(f"{fingerprint:14} {scored or 0:>7}  {runtime or '-'}")
            return 0

        if not args.a or not args.b:
            parser.error("two fingerprints are required, or --list")

        left, right = arm(dsn, args.a), arm(dsn, args.b)
        # T4.7's baseline columns, loaded from the same database. A baseline that has never run
        # simply is not here, and `baseline_columns.panel` turns that into a row rather than a
        # silence - so this returning `{}` is a supported state, not a degraded one.
        from evalharness.baseline_columns import baseline_arms

        loaded_baselines = baseline_arms(dsn)
    except psycopg.OperationalError as unreachable:
        print(f"REFUSED: the database is not reachable - {unreachable}")
        return 2

    if not left.runs or not right.runs:
        print(
            f"REFUSED: {args.a} has {len(left.runs)} scored run(s) and {args.b} has "
            f"{len(right.runs)}. A comparison needs both arms to have run something."
        )
        return 3

    text = (
        "\n".join(
            report(
                left,
                right,
                catalog_size=args.catalog_size or len(runnable()),
                baselines=loaded_baselines,
                baseline_reasons=BASELINE_REASONS,
            )
        )
        + "\n"
    )
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"COMPARISON-{args.a}-vs-{args.b}.md"
    target.write_text(text)
    print(text)
    print(f"written: {target}")
    return 0


def run_cli() -> None:  # pragma: no cover - console entry point
    import sys

    sys.exit(main())
