"""Baseline columns, mandatory in every headline table (T4.7).

The plan's deliverable is *"B0/B1/B2 configs in the eval DB + **baseline columns mandatory in
every headline table** + measured manual-RCA reference"*, and its reason is stated as a threat
rather than a preference: *"Baselines pre-empt the sharpest available attack ('is any of this
doing anything?') by answering it in your own README."*

Three baselines that exist as configs nobody prints answer nothing. This module is what makes
them appear.

## Mandatory means *cannot be omitted*, not *should not be*

`compare.py` already states the pattern this follows: the four-part figure rule *"cannot be
violated here, because `variance.Figure` requires all four to construct"*. The same construction
is used again. `BaselinePanel` refuses to exist unless it carries an entry for **every** baseline
in `BASELINES`, so a headline table built from one either has all three or was never built.

A convention - "remember to add the baseline row" - is the thing this project has watched fail
twice in a week: `no-commit-on-main` guarded one door of several, and `TriageJudgement` sat
outside `_CONTRACTS` for a whole sweep. A rule that depends on memory is a rule with a date on it.

## An unrun baseline is a row that says so, never an absent row

**This is the decision that matters, and it is the opposite of the tempting one.** No baseline
has been scored yet: B0's only run is v1's, which is wrong and belongs to a superseded version,
and B1 and B2 have never run because their runs cost money. The tempting rendering is to leave
the rows out until there is something to put in them.

That is exactly backwards. A headline table with no baseline rows reads as a table whose author
did not think to ask; a table with three rows reading **"not run"** reads as a project that knows
what it has not yet measured. The second is true and the first is not, and the difference costs
nothing but a decision made now, before there is a number that would make omission convenient.

So `NOT_RUN` is a rendered value, and `BaselinePanel.complete` reports whether every baseline has
a figure - never used to hide a row, only to caption the table honestly.

## What a baseline row is allowed to be compared against

Nothing here computes a delta between a baseline and the pipeline. `compare.report` does that
between two arms, with `variance.mde` deciding whether the delta is resolvable at all - and at
n≈10, R=1 this catalog's MDE is 28pp, so most baseline-versus-pipeline gaps will be below it.
A panel that printed a bare difference would invite exactly the reading the MDE machinery exists
to prevent. The rows carry each arm's own figure, with n and R attached, and the comparison stays
where the statistics live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from evalharness import variance

if TYPE_CHECKING:  # pragma: no cover
    from evalharness.compare import Arm, Metric

BASELINES: tuple[tuple[str, str, str], ...] = (
    (
        "b0",
        "B0",
        "no-LLM heuristic: alert attribution, most-recent change in window, largest error delta",
    ),
    ("b1", "B1", "one agent, all four tools, no fan-out"),
    ("b2", "B2", "the model's prior: alert text and service catalog, no tools at all"),
)
"""`(config value, display id, description)`. The config value is what a run manifest carries in
`baseline` and what `evaldb.fingerprint` hashes, so this tuple is the join between the three
implementations and the tables that must show them."""

BASELINE_IDS: tuple[str, ...] = tuple(display for _, display, _ in BASELINES)

NOT_RUN = "not run"
"""What an unmeasured baseline renders as. **A value, not an omission** - see the module
docstring: a missing row reads as an author who did not think to ask."""


class IncompleteBaselinePanelError(RuntimeError):
    """A headline table was built without every baseline. **The enforcement.**

    Raised at construction rather than caught at review, for the reason `variance.Figure` refuses
    a figure missing its CI: a rule that can be violated and then noticed is a rule that gets
    violated and not noticed.
    """


@dataclass(frozen=True, slots=True)
class BaselineRow:
    """One baseline's standing on one metric."""

    baseline: str
    description: str
    figure: variance.Figure | None = None
    runs: int = 0
    note: str = ""
    """Why there is no figure, when there is none. Empty when there is one.

    Required in that case by `__post_init__`: *"not run"* with no reason is the kind of blank a
    reader has to guess at, and the guesses available - too expensive, not built, forgotten -
    have very different implications for whether the table can be trusted.
    """

    def __post_init__(self) -> None:
        if self.figure is None and not self.note:
            raise IncompleteBaselinePanelError(
                f"{self.baseline} has no figure and no reason why. An unmeasured baseline must "
                "say what stopped it; a blank invites the reader to guess, and 'too expensive', "
                "'not built' and 'forgotten' are not the same claim."
            )

    def render(self) -> str:
        if self.figure is None:
            return f"| {self.baseline} | *{NOT_RUN}* | — | {self.note} |"
        return f"| {self.baseline} | {self.figure.render()} | {self.runs} | {self.description} |"


@dataclass(frozen=True, slots=True)
class BaselinePanel:
    """Every baseline's standing on one metric. **Cannot be built with any of them missing.**"""

    metric_label: str
    rows: tuple[BaselineRow, ...]

    def __post_init__(self) -> None:
        present = [row.baseline for row in self.rows]
        missing = [name for name in BASELINE_IDS if name not in present]
        if missing:
            raise IncompleteBaselinePanelError(
                f"a headline table on {self.metric_label!r} is missing {', '.join(missing)}. "
                "T4.7 makes baseline columns mandatory in every headline table, and the plan's "
                "reason is a threat rather than a preference: baselines pre-empt 'is any of "
                "this doing anything?' by answering it in your own README. A baseline that "
                "has not run is a row saying so, never an absent row."
            )
        duplicated = sorted({name for name in present if present.count(name) > 1})
        if duplicated:
            raise IncompleteBaselinePanelError(
                f"{', '.join(duplicated)} appears more than once. Two rows for one baseline are "
                "two different measurements presented as one baseline's standing."
            )

    @property
    def complete(self) -> bool:
        """Every baseline has a figure. **Never used to decide whether to print the panel** -
        only to caption it, so a reader knows whether the comparison is fully grounded."""
        return all(row.figure is not None for row in self.rows)

    def render(self) -> list[str]:
        caption = (
            "Every baseline below ran under the same gate, the same injection, the same triage "
            "and the same scorer as the pipeline."
            if self.complete
            else (
                f"**{sum(1 for r in self.rows if r.figure is None)} of {len(self.rows)} "
                "baselines have not run.** The rows are printed anyway: a table without them "
                "reads as one whose author did not ask, and this project knows what it has not "
                "measured."
            )
        )
        return [
            f"### Baselines — {self.metric_label}",
            "",
            caption,
            "",
            "| baseline | figure | runs | note |",
            "|---|---|---|---|",
            *[row.render() for row in self.rows],
            "",
        ]


def panel(
    metric: Metric,
    arms: dict[str, Arm],
    reasons: dict[str, str] | None = None,
) -> BaselinePanel:
    """Build the panel for one metric from whichever baseline arms exist.

    `arms` is keyed by display id (`"B0"`), and a baseline absent from it gets a `NOT_RUN` row
    carrying `reasons[id]` - or a default that says the run has not happened rather than
    pretending to know why. Every baseline gets a row either way; that is the point of the type.
    """
    reasons = reasons or {}
    rows: list[BaselineRow] = []
    for _, display, description in BASELINES:
        arm = arms.get(display)
        values = list(arm.per_scenario(metric).values()) if arm else []
        if arm is None or not values:
            rows.append(
                BaselineRow(
                    baseline=display,
                    description=description,
                    note=reasons.get(display)
                    or f"no scored run on this metric yet — {description}",
                )
            )
            continue
        low, high = variance.bootstrap_ci(values)
        rows.append(
            BaselineRow(
                baseline=display,
                description=description,
                figure=variance.Figure(
                    label=f"{display} {metric.label}",
                    mean=sum(values) / len(values),
                    low=low,
                    high=high,
                    n=len(values),
                    r=arm.declared_r or 1,
                    unit=metric.unit,
                ),
                runs=len(arm.runs),
            )
        )
    return BaselinePanel(metric_label=metric.label, rows=tuple(rows))


def baseline_arms(dsn: str) -> dict[str, Any]:  # pragma: no cover - exercised in integration
    """Load one `Arm` per baseline from the eval database, keyed by display id.

    A baseline's runs are the ones whose configuration carries that `baseline` value, which is a
    fingerprint input - so this is a lookup in `eval_configs.settings` rather than a guess from a
    runtime string. Several fingerprints can carry the same baseline (different models, budgets
    or world generations), and the **most recently seen** is used: pooling them would average two
    configurations that the fingerprint exists to keep apart.

    Not unit-tested, for the same reason `compare.arm` is not: the SQL belongs to the integration
    suite, and a mock of a query is a test of the mock.
    """
    import psycopg

    from evalharness.compare import arm as load_arm

    arms: dict[str, Any] = {}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for value, display, _ in BASELINES:
            cur.execute(
                "SELECT fingerprint FROM eval_configs WHERE settings->>'baseline' = %s "
                "ORDER BY first_seen DESC LIMIT 1",
                (value,),
            )
            row = cur.fetchone()
            if row:
                arms[display] = load_arm(dsn, row[0])
    return arms
