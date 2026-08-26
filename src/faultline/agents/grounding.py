"""A deterministic cross-check between a verdict and the trajectory it was drawn from.

**RETIRED at T4.3, on its own evidence. Nothing calls this module.** Kept, unwired, because the
idea was sound and the implementation is what failed - and because a retired mechanism whose
record is deleted gets rebuilt identically by the next person with the same good idea.

## The ledger that retired it

| run | fired | verdict |
|---|---|---|
| `e7739dec` (T3.4, historical) | 1 | **true positive** |
| `6b9715de` (T3.4b) | 1 | false positive |
| `f7afdb76` (T3.4c) | 1 | false positive |
| `cart-bad-image-tag` (T4.2 sweep) | 2 | false positives |

**Live: 0 true positives, 4 false positives.** And the one true positive does not survive
scrutiny either: T3.4b diagnosed its cause as a *context-assembly* defect - three `changes`
dispatches collapsing to one in a dict keyed on specialist name - and fixed it. The verdict that
check caught was accurate about what it had been shown. **The defect it was built to catch has
had no instance since the assembly fix, and every firing since has been wrong.**

ADR-0022 §Consequences set the condition in advance: "If a first batch does not improve it, the
honest options are to narrow it further or to retire it - and either is a decision with an ADR,
not a quiet edit." The batch ran. The decision is ADR-0021's addendum.

## Why narrowing was rejected

Each false positive had a *different* cause, and each fix was local:

1. a comma-joined clause whose second half said the service **was** covered (T3.4b) - fixed by
   splitting on `, and`;
2. a clause citing the very `result_id` it qualified (T3.4c) - fixed by skipping self-citing
   clauses;
3. `?` not being a clause boundary, so a service named in a question joined a negation in the
   answer (T4.2);
4. the evidence word `image` matching inside `image-pull`, and `flag` inside `flagged` (T4.2).

Four fixes, four new rules, and the fifth failure would have a fifth cause. **That is what
parsing prose for intent looks like from the inside**: every repair is correct, local, and buys
one round. The list of ways an English sentence can mention a service and a negation without
claiming a dispatch never happened is not finite, and a check whose precision must be maintained
by patching a regex is not a deterministic check - it is a small language model made of regexes,
with none of the calibration and all of the confidence.

## The bar for re-admission

The idea is worth keeping: **a verdict makes claims, and the trajectory can refute some of
them.** What is not worth keeping is inferring which claim a sentence is making.

Re-admission requires a mechanism that **does not parse prose**. The obvious shape is a
structured field: the synthesizer already returns `open_questions` as a list, and a schema that
asked for `unqueried: [{specialist, service}]` alongside them would make the same check a set
comparison - exactly resolvable, no regex, and wrong in ways a schema violation catches. That is
a contracts change and belongs to whoever wants the check back, with this ledger in hand.

Until then: **the trajectory is the record, and a verdict that misdescribes it is a finding for a
human reading the run, not a flag a scorer can trust.**
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
