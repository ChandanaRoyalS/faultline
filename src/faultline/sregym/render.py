"""The verdict as the text SREGym's judge grades (T7.2).

**Frozen by the run's registration** (`evals/runs/PREREGISTRATION-T7.2-run.md`, *The rendering,
frozen*), because how a verdict becomes prose moves the headline number: the judge's D2 asks for
*"concrete mutated details"* and D3 for *"all components"*, which a one-line root cause cannot hold
(`docs/design/t7.2-the-harness-read.md`, second addendum). No model call. `remediation_class` is
left out: the run is diagnosis only. Changing anything here after a scored attempt is changing the
benchmark's input, and `tests/test_sregym.py` holds it to a golden text.
"""

from __future__ import annotations

from collections.abc import Iterable

from faultline.agents.contracts import Verdict
from faultline.agents.evidence import Evidence

NO_VERDICT = "Faultline reached no verdict."


def _evidence_line(item: Evidence) -> str:
    detail = f"{item.kind}, from {item.tool} on {item.service}"
    if item.note:
        detail += f"; why: {item.note}"
    if item.query:
        detail += f"; query: {item.query}"
    return f"- {item.claim} ({detail})"


def cited(verdict: Verdict, evidence: Iterable[Evidence]) -> list[Evidence]:
    """The entries the verdict cites, in its citation order, each result's entries in the order
    they were bound. A cited id with no bound entry is skipped: there is nothing to render."""
    by_result: dict[str, list[Evidence]] = {}
    for item in evidence:
        by_result.setdefault(item.result_id, []).append(item)
    seen: set[str] = set()
    out: list[Evidence] = []
    for result_id in verdict.evidence:
        if result_id in seen:
            continue
        seen.add(result_id)
        out.extend(by_result.get(result_id, []))
    return out


def render(verdict: Verdict | None, evidence: Iterable[Evidence] = ()) -> str:
    """The submission. Samples are never included: `Evidence` lines render the claim only."""
    if verdict is None:
        return NO_VERDICT
    lines = [
        f"Root cause: {verdict.root_cause}",
        f"Faulty component: {verdict.service or 'not named'}",
        f"Fault type: {verdict.fault_class}",
        f"Confidence: {verdict.confidence}",
        "",
        "Evidence:",
    ]
    items = cited(verdict, evidence)
    lines += [_evidence_line(item) for item in items] or ["none"]
    lines += ["", "Reasoning:", verdict.reasoning, "", "Alternatives considered:"]
    lines += [
        f"{n}. {alt.service}: {alt.root_cause} ({alt.fault_class}). "
        f"Ranked lower because: {alt.why_not}"
        for n, alt in enumerate(verdict.alternatives, start=1)
    ] or ["none"]
    lines += ["", "Open questions:"]
    lines += [f"- {question}" for question in verdict.open_questions] or ["none"]
    return "\n".join(lines)
