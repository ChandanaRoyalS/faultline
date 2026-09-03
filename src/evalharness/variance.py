"""Repeat counts, paired comparison, confidence intervals, and the MDE table (T4.6).

The plan's T4.6: *"Repeat counts, paired comparison, and confidence intervals as first-class
properties of every eval run and every comparison report - plus a pre-computed
minimum-detectable-effect table checked into the repo before the first ablation runs."* And
CLAUDE.md rule 6, which predates it: *"any figure that leaves the repo carries n, R, and a 95% CI,
next to a baseline. Below-MDE deltas are 'no measurable effect.'"*

## A figure that cannot be printed without its interval

`Figure` requires `mean`, `low`, `high`, `n` and `r` to construct. There is no path that renders a
number without them, which is the mechanical form of the plan's *"a figure without all four is a
bug in the generator"*: it is not a review rule, it is a constructor signature.

## Pairing, and what it is worth

Comparisons are **paired** - the same scenarios under both configurations, differenced per
scenario before anything is averaged. A scenario that is hard under both arms contributes a delta
near zero rather than variance to both means, so the noise that cancels is the noise between
scenarios, which in this catalog is most of it. The plan calls this *"worth roughly 2x effective
sample size for free"*, and under the correlation this catalog plausibly has it is worth more than
that.

**Only scenarios present in both arms are compared.** A configuration that ran seven scenarios
against one that ran eight is compared on seven, and `n` says seven. Averaging eight against seven
and calling the difference an effect is the error pairing exists to prevent.

## The intervals are bootstrapped, and the seed is fixed

`bootstrap_ci` resamples the per-scenario deltas. Percentile method, 10,000 resamples, seeded -
so a report regenerated from the same rows prints the same interval, and two readers quoting "the
95% CI" mean the same numbers. A resampling interval was chosen over a normal approximation
because at `n = 10` the normal approximation is doing most of the work of the answer.

## The MDE table is derived here, and it does not reproduce the plan's

The plan states *"10 scenarios ~ 20pp (directional only, never publish a number); 30 ~ 10pp; 30
paired at R=5 ~ 6-7pp"*. Computing them found that **those three numbers are not all the same
quantity**:

| the plan's figure | what reproduces it |
|---|---|
| 10 scenarios ~ 20pp | the **95% CI half-width** on a paired difference at `rho = 0.8` (19.6pp) |
| 30 ~ 10pp | the same half-width at `n = 30` (11.3pp) |
| 30 paired at R=5 ~ 6-7pp | the **MDE at 80% power** (7.2pp), a different and stricter quantity |

A CI half-width is what a comparison can **resolve**; an MDE at 80% power is what it can
**reliably detect**, and the second is larger than the first by `(z_alpha + z_beta) / z_alpha` =
1.43. Reporting one under the other's name would understate what this catalog can detect by 43%,
so both columns are computed and both are printed. **The plan's numbers are not wrong** - two of
them are half-widths and one is an MDE, and the table names which is which rather than picking the
flattering one.

`rho` is the correlation between the two arms on the same scenario, and it is **assumed rather
than measured** - this repository has never run the same catalog under two configurations with
repeats, which is the measurement that would settle it. `RHO_ASSUMED = 0.8` is stated everywhere
it is used, and the table prints a column at `rho = 0.5` beside it so a reader can see how much of
the answer the assumption is carrying.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

Z_ALPHA = 1.959963985
"""Two-sided 95%."""

Z_BETA = 0.841621234
"""80% power, the convention the plan's R=5 figure matches."""

RHO_ASSUMED = 0.8
"""Assumed correlation between two arms on the same scenario. **Never measured here.**

Pairing is worth more the more a scenario's difficulty carries across configurations, and in this
catalog a scenario that is hard for one pipeline is usually hard for the next - `shipping-quote-
misconfig` has been wrong under three of them. 0.8 is a defensible reading of that and it is an
assumption; the table prints 0.5 beside it so the reader sees the assumption's weight.
"""

BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20260903
"""Fixed, so a report regenerated from the same rows prints the same interval."""


@dataclass(frozen=True, slots=True)
class Figure:
    """One number that may leave the repository. **Cannot be built without its interval.**

    CLAUDE.md rule 6 in constructor form: `mean`, the interval, `n` and `r` are required
    arguments, so there is no code path that prints a figure missing one.
    """

    label: str
    mean: float
    low: float
    high: float
    n: int
    r: int
    unit: str = "pp"

    @property
    def half_width(self) -> float:
        return (self.high - self.low) / 2

    def render(self) -> str:
        return (
            f"{self.label}: {self._show(self.mean)} "
            f"[95% CI {self._show(self.low)}, {self._show(self.high)}]  "
            f"n={self.n}  R={self.r}"
        )

    def _show(self, value: float) -> str:
        """One quantity, in the unit's own conventions.

        Percentage points scale by 100 and take one decimal; money takes the symbol in front and
        two decimals, because `+0.1$` is both misplaced and too coarse to distinguish a cost
        change worth acting on from one that is noise; milliseconds are whole numbers.
        """
        if self.unit == "pp":
            return f"{value * 100:+.1f}pp"
        if self.unit == "$":
            return f"{'+' if value >= 0 else '-'}${abs(value):.2f}"
        if self.unit == "ms":
            return f"{value:+,.0f}ms"
        return f"{value:+.3f}{self.unit}"

    def as_row(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "mean": self.mean,
            "ci_low": self.low,
            "ci_high": self.high,
            "n": self.n,
            "r": self.r,
            "unit": self.unit,
        }


def paired_deltas(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    """`b - a` per scenario, over the scenarios **both** arms ran.

    Scenarios missing from either side are dropped rather than imputed. A configuration that ran
    seven against one that ran eight is compared on seven, and every `n` downstream is seven.
    """
    return {key: b[key] - a[key] for key in sorted(set(a) & set(b))}


def bootstrap_ci(
    values: list[float],
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile bootstrap over per-scenario deltas.

    Fewer than two values has no interval to compute and returns the point twice - which renders
    as a zero-width interval and is honest: one scenario is one observation, and a report that
    printed a confident-looking band around it would be inventing the thing this module exists to
    prevent.
    """
    if not values:
        return (0.0, 0.0)
    if len(values) == 1:
        return (values[0], values[0])
    rng = random.Random(seed)
    size = len(values)
    means = sorted(sum(rng.choice(values) for _ in range(size)) / size for _ in range(resamples))
    return (means[int(0.025 * resamples)], means[int(0.975 * resamples) - 1])


def figure(label: str, deltas: dict[str, float], r: int, unit: str = "pp") -> Figure:
    """A paired delta with its bootstrap interval, `n` and `R`. The only constructor callers use."""
    values = list(deltas.values())
    mean = sum(values) / len(values) if values else 0.0
    low, high = bootstrap_ci(values)
    return Figure(label=label, mean=mean, low=low, high=high, n=len(values), r=r, unit=unit)


# --- the minimum detectable effect ------------------------------------------------------


def ci_half_width(n: int, p: float = 0.5, rho: float = RHO_ASSUMED, r: int = 1) -> float:
    """What a paired comparison of this size can **resolve**: the 95% CI half-width.

    `p = 0.5` is the worst case for a proportion and is used throughout, because an MDE quoted at
    a favourable baseline is an MDE for a result nobody has yet.
    """
    return Z_ALPHA * math.sqrt(2 * p * (1 - p) * (1 - rho) / (n * r))


def mde(n: int, p: float = 0.5, rho: float = RHO_ASSUMED, r: int = 1) -> float:
    """What it can **reliably detect**: the effect size with 80% power at two-sided 95%.

    Larger than the half-width by `(Z_ALPHA + Z_BETA) / Z_ALPHA` = 1.43, and this is the number a
    published comparison should be held to - resolving an effect once is not detecting it.
    """
    return (Z_ALPHA + Z_BETA) * math.sqrt(2 * p * (1 - p) * (1 - rho) / (n * r))


def verdict(observed: float, n: int, r: int = 1, rho: float = RHO_ASSUMED) -> str:
    """The plan's rule, applied: *"a delta below its MDE is reported as 'no measurable effect at
    this catalog size'"* - which it calls stronger interview material than a fabricated 3-point
    win, and which is the only honest reading of a delta this catalog cannot detect."""
    threshold = mde(n, r=r, rho=rho)
    if abs(observed) < threshold:
        return (
            f"no measurable effect at this catalog size (|{observed * 100:.1f}pp| < "
            f"MDE {threshold * 100:.1f}pp at n={n}, R={r})"
        )
    return (
        f"above the MDE ({threshold * 100:.1f}pp at n={n}, R={r}) - a delta this size is detectable"
    )


TIERS: dict[str, tuple[int, str]] = {
    "manual": (1, "one run by hand; an observation, never a rate"),
    "ci-smoke": (1, "change detection only, never citable"),
    "nightly": (1, "change detection; not a finding on its own"),
    "weekly": (3, "consolidation"),
    "published": (5, "the only tier a printed comparison may come from - a 5x spend multiplier"),
}
"""The plan's three tiers, plus `published` (which its R=5 figure implies) and `manual`.

**`manual` is not in the plan and is the honest default.** Every scored run in this repository so
far was launched by hand, and labelling those `nightly` would claim a cadence that does not exist.
It carries R = 1 and the same warning CLAUDE.md rule 6 gives: one run is an observation.

*"Cost flagged, not hidden: R=5 is a 5x spend multiplier, confined by the tiering to comparisons
that get published."* At dev sweep 8's measured $0.70 a run, a published 30-scenario paired
comparison at R=5 is 300 runs and roughly **$210** - which is the number that decides whether a
comparison is worth publishing, and it belongs beside the tier rather than in someone's head.
"""

SEED_POLICY = "unseeded: non-deterministic model, live world"
"""T4.6 asks comparisons to use *"the same seeds where seedable"*. **Nothing here is seedable**,
and recording that is the point.

The model is sampled and its provider exposes no seed; the world is a live docker compose stack
whose container start order, scrape alignment and load generator are not reproducible. So a
paired comparison in this project pairs on **scenario**, never on seed, and the per-scenario delta
is doing all of the variance reduction. Written onto every run so a future reader does not have to
infer from an absent field whether seeding was considered and rejected or never thought about.
"""


def table(sizes: tuple[int, ...] = (10, 18, 30), repeats: tuple[int, ...] = (1, 3, 5)) -> list[str]:
    """The MDE table, derived. Written to `evals/MDE.md` and checked in before any ablation."""
    lines = [
        "| scenarios | R | effective | CI half-width | MDE (80% power) | at rho=0.5 |",
        "|---|---|---|---|---|---|",
    ]
    for n in sizes:
        for r in repeats:
            lines.append(
                f"| {n} | {r} | {n * r} | {ci_half_width(n, r=r) * 100:.1f}pp | "
                f"{mde(n, r=r) * 100:.1f}pp | {mde(n, r=r, rho=0.5) * 100:.1f}pp |"
            )
    return lines
