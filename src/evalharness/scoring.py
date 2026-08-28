"""Deterministic scoring: triage sets, verdict labels, and the categories held out (T4.1).

**Nothing here calls a model.** Root cause and narrative are judged, and the judge is T4.2 with
ADR-0020 §1's decisions governing it. What is here is everything that can be settled by
comparing a recorded run against a committed bundle, which is the part that has to be right
before a judge's opinion is worth collecting.

Three positions from ADR-0022 §1 are implemented rather than restated:

- **Recall and precision are a pair, never combined.** No F-score. ADR-0017's directed
  under-reach hypothesis rides on recall alone, and the live runs returned twelve services
  against four alerting - an F1 would let restraint hide reach.
- **`unknown` is an abstention, not a wrong answer.** Excluded from accuracy, reported as
  coverage. Two of the five stored verdicts are `unknown`; counting them as errors makes a
  system that says so indistinguishable from one that guesses badly.
- **The disputed boundary is counted as a miss *and* named.** ADR-0022 resolved
  `dependency_latency`/`restart` against `bad_config`/`config_revert` on the measured
  fix-test, and required that the losing reading not silently count as wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ABSTENTION = "unknown"
"""The fault class that means the synthesizer declined. `remediation_class` pairs it with
`none`, and both are read as abstention rather than as an answer."""

NO_REMEDIATION = "none"


@dataclass(frozen=True, slots=True)
class ClassDispute:
    """A documented near-miss: a wrong class the ADR has taken a position on.

    **Enumerated here, never inferred by the scorer.** A scorer that decided for itself which
    misses were "nearly right" would be grading on sympathy. Each entry cites the ADR section
    that resolved it and the evidence that resolved it there.

    **The register records where the two readings of the label set disagree** - not where the
    fix tiebreak can settle it (ADR-0022 addendum, T4.3). Those are different tests, and the
    first sweep showed the difference matters: the tiebreak is *silent* on
    `resource_exhaustion`, because both readings land on `config_revert`, so a register defined
    by the tiebreak would have recorded two of the four observations and hidden the other two.

    A register entry is **visibility, not forgiveness**. Every disputed miss is still a miss.
    """

    scenario_id: str
    truth: str
    returned: str
    resolved_by: str
    why: str


CLASS_DISPUTES: tuple[ClassDispute, ...] = (
    ClassDispute(
        scenario_id="cart-dependency-latency",
        truth="dependency_latency",
        returned="bad_config",
        resolved_by="ADR-0022 §1.2",
        why=(
            "A shaping rule on a container's network namespace reads as either 'a dependency "
            "got slow' or 'something was configured wrong'. Resolved against the agent by the "
            "fix test, which was measured: pumba binds to the container present, so a restart "
            "durably clears the delay while there is no configuration to revert."
        ),
    ),
    ClassDispute(
        scenario_id="cart-dependency-latency",
        truth="restart",
        returned="config_revert",
        resolved_by="ADR-0022 §1.2",
        why="The class of fix follows the same fork, and by the same measurement.",
    ),
    ClassDispute(
        scenario_id="ad-memory-squeeze",
        truth="resource_exhaustion",
        returned="bad_config",
        resolved_by="ADR-0022 addendum, T4.3",
        why=(
            "A memory cap was lowered onto the service, and the service then exhausted it. The "
            "label set names the symptom; the agent named the artifact the change touched. The "
            "fix tiebreak cannot settle this one - both readings give `config_revert` - which "
            "is precisely why the register is defined on the readings and not on the tiebreak."
        ),
    ),
    ClassDispute(
        scenario_id="frauddetection-memory-squeeze",
        truth="resource_exhaustion",
        returned="bad_config",
        resolved_by="ADR-0022 addendum, T4.3",
        why=(
            "The same shape as `ad-memory-squeeze`, and the verdict identified the mechanism "
            "correctly - a process killed by the kernel for exceeding its cgroup limit - before "
            "classifying on the change rather than on the symptom."
        ),
    ),
)
"""The four observations of one boundary, not two observations of two boundaries.

`bad_config` was returned for five of the sweep's seven scenarios, and the agent returned only
two values across the whole sweep: `bad_deploy` where the change touched an image, `bad_config`
everywhere else. It never returned a symptom class for any scenario. That single rule predicts
all seven rows, including the four it got right - and the register exists so a reader can see
that from the scored output rather than by reading seven verdicts.
"""


def dispute_for(scenario_id: str, truth: str, returned: str) -> ClassDispute | None:
    for entry in CLASS_DISPUTES:
        if (entry.scenario_id, entry.truth, entry.returned) == (scenario_id, truth, returned):
            return entry
    return None


# --- triage --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TriageScore:
    """Blast radius against `alerts_over_window`. **Recall and precision, side by side.**"""

    predicted: frozenset[str]
    alerted: frozenset[str]
    excluded_after_revert: frozenset[str]
    unmeasured_edges: int

    @property
    def matched(self) -> frozenset[str]:
        return self.predicted & self.alerted

    @property
    def missed(self) -> frozenset[str]:
        """Alerted and not predicted. **This is ADR-0017's number.**

        "A directed 2-hop traversal that under-reaches shows up there as a recall miss on
        services that alerted and were not predicted. That is the number to look at, and it
        does not exist yet." It exists now.
        """
        return self.alerted - self.predicted

    @property
    def extra(self) -> frozenset[str]:
        return self.predicted - self.alerted

    @property
    def recall(self) -> float | None:
        return len(self.matched) / len(self.alerted) if self.alerted else None

    @property
    def precision(self) -> float | None:
        return len(self.matched) / len(self.predicted) if self.predicted else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "recall": self.recall,
            "precision": self.precision,
            "matched": sorted(self.matched),
            "missed_alerted_not_predicted": sorted(self.missed),
            "predicted_not_alerted": sorted(self.extra),
            "excluded_began_after_revert": sorted(self.excluded_after_revert),
            "unmeasured_edges_crossed": self.unmeasured_edges,
            "n_alerted": len(self.alerted),
            "n_predicted": len(self.predicted),
        }


def score_triage(
    predicted: set[str],
    alerts_over_window: list[dict[str, Any]],
    unmeasured_edges: int,
) -> TriageScore:
    """Compare the blast radius to what actually alerted, minus the recovery phase.

    ADR-0009: "the blast radius blames the fault for damage the fix did", so entries whose
    `began_after_revert` is true are excluded from both sides. The flag is *omitted* rather
    than false where there is no revert to compare against, so this reads it as
    falsy-by-absence deliberately.

    **Known defect, recorded at T7.1 and not fixed there.** The exclusion is keyed on the
    *service*: `alerted - after` removes a service from the blast radius even when it also
    alerted during the fault, which understates the radius. Until T7.1's re-record every
    after-revert alert in the catalog belonged to a service that alerted *only* after the
    revert - emailservice in two cart bundles, frontend in `shipping-wrong-image` - so the
    sets were disjoint and the subtraction was harmless. The re-record retired all three and
    produced the first overlapping case, `product-catalog-flag-failure`, where frontend
    alerts during the fault and again in recovery.

    The fix is to exclude per alert rather than per service. It changes triage numbers, so it
    belongs with a decision to re-measure rather than with the task that moved the world.
    """
    alerted: set[str] = set()
    after: set[str] = set()
    for entry in alerts_over_window:
        service = entry.get("service")
        if not isinstance(service, str):
            continue
        (after if entry.get("began_after_revert") else alerted).add(service)
    return TriageScore(
        predicted=frozenset(predicted),
        alerted=frozenset(alerted - after),
        excluded_after_revert=frozenset(after),
        unmeasured_edges=unmeasured_edges,
    )


# --- verdict -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LabelScore:
    """One label compared to ground truth, with abstention held apart from error."""

    truth: str
    returned: str | None
    abstained: bool
    dispute: ClassDispute | None

    @property
    def correct(self) -> bool:
        return not self.abstained and self.returned == self.truth

    @property
    def counts_toward_accuracy(self) -> bool:
        """An abstention is neither right nor wrong, so it leaves both sides of the ratio."""
        return not self.abstained

    def as_dict(self) -> dict[str, Any]:
        return {
            "truth": self.truth,
            "returned": self.returned,
            "correct": self.correct,
            "abstained": self.abstained,
            "dispute": None if self.dispute is None else self.dispute.resolved_by,
        }


def score_label(scenario_id: str, truth: str, returned: str | None) -> LabelScore:
    abstained = returned in (None, ABSTENTION, NO_REMEDIATION)
    return LabelScore(
        truth=truth,
        returned=returned,
        abstained=abstained,
        dispute=None if abstained else dispute_for(scenario_id, truth, returned or ""),
    )


# --- the categories held out ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Categories:
    """ADR-0022 §2. **Every field is printed, including the zeroes.**

    "The category is reported anyway, at zero, because a rate that only appears once it is
    non-zero is a rate nobody calibrated." `failed_alone` has had zero observations across every
    stored trajectory, and that is a fact about the system worth printing.
    """

    flagged: tuple[str, ...] = ()
    failed_alone: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    budget_exhausted_reason: str | None = None
    narrative_refused: str | None = None
    """The render refusal, if there was one. **A fifth category, added at T4.2.**

    T4.2's judge scores narratives. Run 3 produced a correct verdict, exited 0, and wrote no
    narrative at all - the leak guard refused the render - and nothing in the scored report said
    so. A judge reading that report would have had nothing to score and no way to know that was
    the reason rather than an oversight. The other four categories describe an investigation that
    fell short; this one describes an output that does not exist.
    """

    @property
    def any(self) -> bool:
        return bool(
            self.flagged
            or self.failed_alone
            or self.contradictions
            or self.budget_exhausted_reason
            or self.narrative_refused
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "flagged": list(self.flagged),
            "n_flagged": len(self.flagged),
            "failed_alone": list(self.failed_alone),
            "n_failed_alone": len(self.failed_alone),
            "contradictions": list(self.contradictions),
            "n_contradictions": len(self.contradictions),
            "budget_exhausted": self.budget_exhausted_reason is not None,
            "budget_exhausted_reason": self.budget_exhausted_reason,
            "narrative_refused": self.narrative_refused is not None,
            "narrative_refused_reason": self.narrative_refused,
        }


CONTRADICTION_LEDGER = (
    "The contradiction check was RETIRED at T4.3 (ADR-0021 addendum) after a live ledger of "
    "0 true positives and 4 false positives. A non-zero count here therefore comes from a run "
    "recorded before the retirement, and is not evidence about the agent."
)
"""Printed next to any non-zero contradiction count.

The category is kept rather than removed: runs recorded before the retirement still carry
firings, and a category that disappears takes its history with it. Going forward it prints at
zero, which is the point."""


@dataclass
class ScoredRun:
    """One run, scored. What the report renders and what the manifest stores."""

    run_id: str
    scenario_id: str
    trajectory_id: str | None
    triage: TriageScore | None = None
    fault_class: LabelScore | None = None
    fix_class: LabelScore | None = None
    categories: Categories = field(default_factory=Categories)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    models: dict[str, str] = field(default_factory=dict)
    runtime_version: str = ""
    budget: dict[str, Any] = field(default_factory=dict)
    """The bounds this run was given. **Printed beside the stamp, never folded into it.**

    The stamp answers "which agent is this" - the prompts it was given and the contracts it was
    held to. The budget answers "how much was it allowed to spend", which is an experiment
    parameter rather than an identity, and the two comparisons are both wanted: T4.7 exists to
    compare *the same agent* under different bounds. Folding the budget into the stamp would
    make that comparison unexpressible and orphan every figure recorded before it.
    """

    @property
    def reached_a_class(self) -> bool:
        """Coverage: did the run produce a fault class at all? Reported beside accuracy,
        never apart from it (ADR-0022 §1.2)."""
        return self.fault_class is not None and not self.fault_class.abstained

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "trajectory_id": self.trajectory_id,
            "runtime_version": self.runtime_version,
            "budget": self.budget,
            "reached_a_class": self.reached_a_class,
            "triage": None if self.triage is None else self.triage.as_dict(),
            "fault_class": None if self.fault_class is None else self.fault_class.as_dict(),
            "fix_class": None if self.fix_class is None else self.fix_class.as_dict(),
            "categories": self.categories.as_dict(),
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "cost_usd": round(self.cost_usd, 4),
            "models": self.models,
        }

    def report(self) -> str:
        """The human form. **n and the caveats travel with every number.**"""
        lines = [
            f"run {self.run_id}   scenario {self.scenario_id}",
            f"trajectory {self.trajectory_id or 'none'}   runtime {self.runtime_version or '?'}",
            "",
        ]
        if self.triage is not None:
            t = self.triage
            recall = "n/a" if t.recall is None else f"{t.recall:.2f}"
            precision = "n/a" if t.precision is None else f"{t.precision:.2f}"
            lines += [
                "TRIAGE (blast radius vs alerts_over_window)",
                f"  recall    {recall}  ({len(t.matched)}/{len(t.alerted)} alerted services "
                f"predicted)",
                f"  precision {precision}  ({len(t.matched)}/{len(t.predicted)} predicted "
                f"services alerted)",
                "  reported as a pair and never combined - ADR-0017's under-reach question "
                "rides on recall alone",
                f"  missed (alerted, not predicted): {', '.join(sorted(t.missed)) or 'none'}",
                f"  extra  (predicted, not alerted): {', '.join(sorted(t.extra)) or 'none'}",
                f"  unmeasured edges crossed: {t.unmeasured_edges} - membership reached "
                "through one is not evidence at the same strength",
            ]
            if t.excluded_after_revert:
                lines.append(
                    f"  excluded as recovery-phase (began_after_revert): "
                    f"{', '.join(sorted(t.excluded_after_revert))}"
                )
            lines.append("")

        lines.append("VERDICT")
        for name, score in (("fault class", self.fault_class), ("fix class", self.fix_class)):
            if score is None:
                lines.append(f"  {name:11} not produced")
                continue
            if score.abstained:
                mark = "ABSTAINED (excluded from accuracy; counted in coverage)"
            elif score.correct:
                mark = "correct"
            else:
                mark = "WRONG"
            lines.append(f"  {name:11} {score.returned} vs {score.truth} - {mark}")
            if score.dispute is not None:
                lines.append(
                    f"    disputed boundary, {score.dispute.resolved_by}: {score.dispute.why}"
                )
        lines.append(f"  coverage: {'reached a class' if self.reached_a_class else 'abstained'}")
        lines.append("")

        c = self.categories
        lines += [
            "REPORTED SEPARATELY (never averaged into the above)",
            f"  flagged verdicts        {len(c.flagged)}"
            + (f"  {'; '.join(c.flagged)}" if c.flagged else ""),
            f"  specialists failed alone {len(c.failed_alone)}"
            + (f"  {'; '.join(c.failed_alone)}" if c.failed_alone else ""),
            f"  contradiction firings   {len(c.contradictions)}"
            + (f"  {'; '.join(c.contradictions)}" if c.contradictions else " (check retired)"),
            f"  budget exhausted        {c.budget_exhausted_reason or 'no'}",
            f"  narrative refused       {'yes' if c.narrative_refused else 'no'}",
        ]
        if c.narrative_refused:
            lines += [
                f"    {c.narrative_refused}",
                "    NOTE: this run produced no narrative. T4.2's judge has nothing to score "
                "for it, and that is a fact about the run rather than a gap in the judging.",
            ]
        if c.contradictions:
            lines.append(f"  NOTE: {CONTRADICTION_LEDGER}")
        lines += [
            "",
            f"COST  in {self.tokens_in} / out {self.tokens_out} tokens   ${self.cost_usd:.4f}",
            f"MODELS {self.models or '{}'}",
            f"BUDGET {self.budget or '{}'}",
            "",
            "n=1. A single run is an observation, not a rate (CLAUDE.md rule 6).",
        ]
        return "\n".join(lines)
