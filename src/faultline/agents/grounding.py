"""A deterministic cross-check between a verdict and the trajectory it was drawn from (T3.4b).

T3.4's first end-to-end run produced a verdict whose highest-value open question was
"no change history has been queried for shippingservice at all". The query existed:
`tr_f536225dc17d`, dispatched in round two, read at high confidence by the changes specialist,
naming the image swap outright. Diagnosis found the finding never reached the synthesizer -
`InvestigationResult.findings` keyed on specialist name, so three `changes` dispatches
collapsed to the last one. That is fixed upstream; every dispatch now reaches every role.

This module is the second line, for the case the assembly fix does not cover: a synthesizer
that was shown the dispatch and asserts its absence anyway. **The claim is flagged, never
stripped.** Editing a model's verdict to agree with the record would destroy the evidence that
it disagreed, and T4.2 has to be able to count these. So the contradiction becomes a flag
carrying the `result_id` that refutes it, and travels with the verdict into scoring.

The rule is deliberately narrow: a sentence that names a dispatched service, names that
dispatch's evidence type, and negates the *act of querying* before naming it. An empty result
reported as empty is not a contradiction - "no change of any kind is recorded for
checkoutservice" is a finding, and eight of the nine rehearsed narratives turn on exactly that
kind of negative.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any, Protocol

NEGATED_QUERY = re.compile(
    r"\b(never|no|not|nothing|none|without)\b[^.;]{0,120}?"
    r"\b(queried|query|queries|examined|checked|inspected|retrieved|run|looked"
    r"|fetched|dispatched)\b",
    re.IGNORECASE,
)
"""Negation *before* the verb, within one clause.

Order matters and is the whole guard against false positives: "the metrics query found no
errors" reads verb-then-negation and is a result, while "no metrics query was run" reads
negation-then-verb and is a claim about the investigation itself.
"""

UNQUERIED = re.compile(r"\bun(queried|examined|checked|inspected)\b", re.IGNORECASE)

EVIDENCE_WORDS: dict[str, tuple[str, ...]] = {
    "changes": ("change", "deploy", "rollout", "config", "flag", "image"),
    "logs": ("log", "stdout", "stderr"),
    "metrics": ("metric", "error rate", "error ratio", "saturation", "latency"),
    "traces": ("trace", "span"),
}
"""How a verdict refers to each specialist's evidence in prose. A verdict does not write
"the logs specialist"; it writes "the logs". Both have to match."""


class Dispatched(Protocol):
    """The part of a `SpecialistRun` this check reads.

    Read-only properties rather than attributes, so a `SpecialistName` literal satisfies the
    `str` the matcher wants.
    """

    @property
    def specialist(self) -> str: ...

    @property
    def service(self) -> str: ...

    @property
    def result(self) -> Any: ...


CLAUSE_BREAK = re.compile(
    "(?<=[.;:])\\s+|\\n|\\s[\\u2014\\u2013]\\s"
    "|,\\s+(?:and|but|so|while|whereas|though|although|yet)\\s"
)
"""Sentences *and* dashed clauses. The dashes are escaped by codepoint - em and en, both of
which models emit, and a literal pair of them here reads as a hyphen.

T3.4's open question is one sentence naming two services: "No change history has been queried
for shippingservice at all — the changes dispatch targeted quoteservice." The negation governs
only the first clause, and a check that read the whole sentence would flag quoteservice for a
query the same sentence says was made.

Comma-plus-conjunction joins are in the list because T3.4b's live run produced a false positive
without them: "no dispatch examined either service, and the empty change results covered only
checkoutservice ..." names checkoutservice in the half that says it *was* covered."""


def _clauses(text: str) -> list[str]:
    return [part.strip() for part in CLAUSE_BREAK.split(text) if part and part.strip()]


def _names_service(sentence: str, service: str) -> bool:
    lowered = sentence.lower()
    variants = {service.lower(), service.lower().replace("service", " service").strip()}
    return any(variant in lowered for variant in variants)


def _names_evidence(sentence: str, specialist: str) -> bool:
    lowered = sentence.lower()
    return any(word in lowered for word in EVIDENCE_WORDS.get(specialist, (specialist,)))


def contradictions(claims: Iterable[str], runs: Iterable[Dispatched]) -> list[str]:
    """Claims that a dispatch never happened, for dispatches that did.

    `claims` is every free-text field of the verdict - root cause, reasoning, and each open
    question. `runs` is the executed dispatches, in trajectory order.
    """
    dispatched = list(runs)
    flags: list[str] = []
    seen: set[str] = set()
    for claim in claims:
        for sentence in _clauses(claim):
            if not (NEGATED_QUERY.search(sentence) or UNQUERIED.search(sentence)):
                continue
            for run in dispatched:
                key = f"{run.specialist}/{run.service}"
                if key in seen:
                    continue
                if run.result.id in sentence:
                    # The clause cites the dispatch it is talking about, so it is qualifying
                    # what that result contained, not denying that it exists. T3.4c's live run:
                    # "No latency percentiles or per-downstream breakdown were retrieved for
                    # checkoutservice (tr_7d4b93d2d99c)" is true of a metrics query that
                    # returned error ratio only, and the id is right there in the sentence.
                    continue
                if _names_service(sentence, run.service) and _names_evidence(
                    sentence, run.specialist
                ):
                    seen.add(key)
                    result_id = getattr(run.result, "id", "unknown")
                    flags.append(
                        f"contradiction: the verdict says {run.specialist} was not queried "
                        f"for {run.service}, and {result_id} is exactly that query"
                    )
    return flags
