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
            "got slow' or 'something was configured wrong'. The tiebreak is which fix works, "
            "and that was measured: pumba binds to the container present, so a restart durably "
            "clears the delay (1.9ms -> ~650ms -> 1.9ms, sidecar still running) while there is "
            "no configuration to revert. Counted as a miss; named so a reader can see how much "
            "of a class error rate is this boundary."
        ),
    ),
    ClassDispute(
        scenario_id="cart-dependency-latency",
        truth="restart",
        returned="config_revert",
        resolved_by="ADR-0022 §1.2",
        why="The class of fix follows the same fork, and by the same measurement.",
    ),
)


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
    `began_after_revert` is true are excluded from both sides. Three bundles have them -
    emailservice in `cart-bad-image-tag` and `cart-redis-misconfig`, frontend in
    `shipping-wrong-image`. The flag is *omitted* rather than false where there is no revert to
    compare against, so this reads it as falsy-by-absence deliberately.
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

    @property
    def any(self) -> bool:
        return bool(
            self.flagged or self.failed_alone or self.contradictions or self.budget_exhausted_reason
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
        }


CONTRADICTION_LEDGER = (
    "The contradiction check has fired twice live and been wrong both times "
    "(0 true positives, 2 false positives). Its one true positive is historical, and the "
    "context-assembly fix that shipped beside it removed that verdict's cause (ADR-0022 §2)."
)
"""Printed next to any non-zero contradiction count, until a batch gives it a denominator.
A flag whose live precision is 0/2 is not yet evidence about an agent."""


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
            + (f"  {'; '.join(c.contradictions)}" if c.contradictions else ""),
            f"  budget exhausted        {c.budget_exhausted_reason or 'no'}",
        ]
        if c.contradictions:
            lines.append(f"  NOTE: {CONTRADICTION_LEDGER}")
        lines += [
            "",
            f"COST  in {self.tokens_in} / out {self.tokens_out} tokens   ${self.cost_usd:.4f}",
            f"MODELS {self.models or '{}'}",
            "",
            "n=1. A single run is an observation, not a rate (CLAUDE.md rule 6).",
        ]
        return "\n".join(lines)
