"""The A/A check: does the harness invent a delta between a config and itself? (Gate 4)

Gate 4's fourth condition: *"the A/A check passes: the harness run twice under an identical config
declares no significant difference. **A harness that invents a delta between a config and itself
will invent every delta it ever reports** — this is the cheapest possible [check]."*

Everything else in this repository measures the pipeline. This measures the **instrument**, and it
is the only figure here whose failure would invalidate all the others at once.

## It needs R ≥ 2, and every sweep so far has been R = 1

The check pairs a config against itself, and pairing needs each scenario present in **both** arms.
At R = 1 a scenario has exactly one run, so it cannot be in both, and there is no A/A check to
perform - not a small sample, none at all.

Every sweep in this repository has been R = 1. So **the A/A check cannot be run on any data that
currently exists**, and the tier that makes it possible is `weekly` (R = 3) or `published`
(R = 5). `split` refuses rather than quietly comparing whatever it can pair, because an A/A check
computed over the two scenarios that happen to have run twice is a check over two scenarios
wearing the name of a check over the catalog.

## Alternating, not first-half / second-half

Runs of one config are split by **alternating within each scenario** - first run to A, second to
B, third to A. A chronological split would put every early run in one arm and every late one in
the other, so any drift over the sweep - world state, time of day, a service that got slower -
would land entirely on one side and read as a delta. That is precisely the artefact this check
exists to detect, and a split that manufactures it would make the check fail for the one reason it
must not.

## Passing is weak evidence, and saying so is the point

At this catalog's size the MDE is about 28pp at n = 10, R = 1 and near 11pp at R = 5. **Almost any
A/A comparison will report "no measurable effect", because almost any comparison here does.** A
test that nearly always passes is not much of a test, and a green A/A check should not be read as
"the harness is sound".

So `Result` carries the **observed delta** on every metric, not just the verdict. An A/A delta of
0.5pp is reassuring; one of 25pp that is technically "not significant" is alarming, and the two
are indistinguishable if only the verdict is printed. `worst` names the metric that moved most,
and it is the number worth reading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from evalharness import variance

if TYPE_CHECKING:  # pragma: no cover
    from evalharness.compare import Arm, Comparison

MIN_REPEATS = 2
"""Below this there is nothing to pair. See the module docstring: at R = 1 there is no A/A check,
not a weak one."""


class NotEnoughRepeatsError(RuntimeError):
    """The config's runs cannot be split into two paired arms.

    Raised rather than returning a partial comparison, because an A/A check computed over the two
    scenarios that happened to run twice is a check over two scenarios wearing the name of a check
    over the catalog.
    """


def split(arm: Arm) -> tuple[Arm, Arm]:
    """One config's runs, alternating into two arms **within each scenario**.

    Alternating rather than chronological: a first-half/second-half split puts every early run in
    one arm, so drift over the sweep lands entirely on one side and reads as a delta - the exact
    artefact this check exists to detect.

    Every scenario must have at least `MIN_REPEATS` runs. A scenario with one run cannot be paired
    and its silent exclusion would shrink the check to whatever happened to repeat.
    """
    from evalharness.compare import Arm as ArmType
    from evalharness.compare import Run

    by_scenario: dict[str, list[Run]] = {}
    for run in arm.runs:
        by_scenario.setdefault(run.scenario_id, []).append(run)

    thin = sorted(name for name, runs in by_scenario.items() if len(runs) < MIN_REPEATS)
    if thin or not by_scenario:
        raise NotEnoughRepeatsError(
            f"an A/A check needs at least {MIN_REPEATS} runs per scenario and "
            f"{len(thin) or 'every'} scenario(s) have fewer: {', '.join(thin) or 'none ran'}.\n"
            "At R = 1 there is no A/A check to perform - not a small one, none. Use the `weekly` "
            "tier (R = 3) or `published` (R = 5)."
        )

    left: list[Run] = []
    right: list[Run] = []
    for _, runs in sorted(by_scenario.items()):
        for position, run in enumerate(runs):
            (left if position % 2 == 0 else right).append(run)
    return (
        ArmType(
            fingerprint=f"{arm.fingerprint}#A",
            runs=left,
            declared_r=arm.declared_r,
            runtime_version=arm.runtime_version,
        ),
        ArmType(
            fingerprint=f"{arm.fingerprint}#B",
            runs=right,
            declared_r=arm.declared_r,
            runtime_version=arm.runtime_version,
        ),
    )


@dataclass(frozen=True, slots=True)
class Result:
    """What the A/A check found, per metric and overall."""

    fingerprint: str
    comparisons: tuple[Comparison, ...] = field(default_factory=tuple)

    @property
    def passed(self) -> bool:
        """Every metric reports no measurable effect, **and at least one was compared.**

        The `and` is not defensive tidying. `all()` over an empty list is `True`, so without it a
        check that compared nothing - no metric had values on both sides - would report as passed:
        the harness announcing a clean bill of health for an examination it never performed. That
        is the same vacuous-success shape as a guard over an empty vocabulary or a top-3 figure
        over a list of length one, and it is the one this file would have shipped with.

        **Weak evidence even when true** - see the module docstring.
        """
        return bool(self.comparisons) and all(
            "no measurable effect" in c.verdict for c in self.comparisons
        )

    @property
    def failures(self) -> tuple[Comparison, ...]:
        return tuple(c for c in self.comparisons if "no measurable effect" not in c.verdict)

    @property
    def worst(self) -> Comparison | None:
        """The metric that moved most. **The number worth reading**, because passing is nearly
        automatic at this catalog size and a 25pp 'not significant' delta is alarming while a
        0.5pp one is reassuring - and the verdict alone cannot tell them apart."""
        if not self.comparisons:
            return None
        return max(self.comparisons, key=lambda c: abs(c.figure.mean))

    def render(self) -> list[str]:
        if not self.comparisons:
            return ["### A/A check", "", "*no metric could be compared*", ""]
        worst = self.worst
        lines = [
            "### A/A check — `" + self.fingerprint + "` against itself",
            "",
            (
                "**Passed: no metric shows a measurable effect.**"
                if self.passed
                else f"**FAILED on {len(self.failures)} metric(s).** A harness that invents a "
                "delta between a config and itself will invent every delta it ever reports, so "
                "every other figure in this report is suspect until this is explained."
            ),
            "",
        ]
        if worst is not None:
            lines += [
                f"Largest observed delta: **{worst.figure.render()}** ({worst.metric.label}).",
                "",
                "**Read the delta, not the verdict.** At this catalog's size almost any "
                "comparison reports no measurable effect, so passing is close to automatic and "
                "is weak evidence. A delta near zero is reassuring; a large one that happens to "
                "sit under the MDE is not, and the verdict cannot tell them apart.",
                "",
            ]
        for comparison in self.comparisons:
            lines.append(f"- {comparison.figure.render()} — {comparison.verdict}")
        lines.append("")
        return lines


def check(arm: Arm) -> Result:
    """Split one config's runs in two and compare them. **The instrument measuring itself.**"""
    from evalharness.compare import METRICS, compare_metric

    left, right = split(arm)
    comparisons = [
        found
        for metric in METRICS
        if (found := compare_metric(left, right, metric, "all")) is not None
    ]
    return Result(fingerprint=arm.fingerprint, comparisons=tuple(comparisons))


def mde_at(n: int, r: int) -> str:
    """The detectable threshold for this shape, printed beside a pass so it can be judged.

    A pass says the delta was under the MDE. Without the MDE beside it, a reader cannot tell
    whether that means *small* or merely *smaller than a threshold nothing could exceed*.
    """
    return f"MDE {variance.mde(n, r=r) * 100:.1f}pp at n={n}, R={r}"
