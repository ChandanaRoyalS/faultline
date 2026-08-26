"""What the planner and the specialists produce, as schemas rather than as prose (T3.3).

ADR-0003 requires "schema-validated structured outputs with bounded re-ask", so these are the
contracts the model is held to, and a reply that does not validate is re-asked once rather than
parsed leniently.

**`ruled_out` is a required field, not optional prose.** `ARTIFACTS.md` says the dead ends "are
the most useful thing in the document - they are what makes a retrieved incident a piece of
experience rather than a lookup table", and ADR-0020 recorded that nothing in the nine roles
owned them. A specialist that returns only what it found has thrown away the half of its work
the corpus values most, and a default of `[]` would let it do that silently.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from faultline.context.catalog import ServiceCatalog

_CATALOG: ServiceCatalog | None = None

SpecialistName = Literal["metrics", "logs", "changes", "traces"]

SPECIALISTS: tuple[SpecialistName, ...] = ("metrics", "logs", "changes", "traces")


class Dispatch(BaseModel):
    """One specialist, one question, **one service**, one window.

    "One service" was a docstring and nothing else until T3.4c. The field was a bare `str`, and
    T3.4b's planner put four names in it - `"paymentservice, currencyservice, cartservice,
    productcatalogservice"` - which the contract accepted, the tool layer turned into a PromQL
    label value that cannot match any `service_name`, and the specialist reported as an empty
    result. Two of six dispatches went that way.

    **This is where ADR-0019's empty-is-not-error principle stops.** An empty answer from a
    well-formed query is evidence, and eight of the nine rehearsed narratives turn on one. A
    selector that *cannot* match anything is a contract error at construction time, and reading
    its emptiness as evidence is the defect - it is the one shape of empty that means nothing at
    all while looking exactly like the shape that means everything.
    """

    model_config = ConfigDict(extra="forbid")

    specialist: SpecialistName
    service: str
    question: str = Field(description="What this specialist is being asked, in one sentence")
    reason: str = Field(description="Why this is worth a dispatch for this incident")


class SkippedSpecialist(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specialist: SpecialistName
    reason: str


class DispatchPlan(BaseModel):
    """**A plan is a choice, not a broadcast.**

    The load table is why the planner exists: change and metrics are needed by 10 of 10
    rehearsed investigations, logs by 7, traces by 2 (ADR-0020 §2). A planner that always
    dispatches four is a fan-out with a prompt in front of it, and `skipped` is where it has to
    say what it decided against - an empty `skipped` on a four-dispatch plan is a plan that
    chose nothing.
    """

    model_config = ConfigDict(extra="forbid")

    dispatches: list[Dispatch] = Field(min_length=1)
    skipped: list[SkippedSpecialist] = Field(
        description="Specialists deliberately not dispatched, each with why"
    )
    rationale: str


class Finding(BaseModel):
    """One thing a specialist found. **Evidence is a `result_id`, never pasted text.**

    ADR-0020 §4: quoting by reference against a stored envelope is what keeps a hostile log line
    out of the incident record and therefore out of next month's corpus. A finding that carried
    its evidence as free text would be the pass-through path that rule removes.
    """

    model_config = ConfigDict(extra="forbid")

    statement: str
    result_id: str = Field(description="The tool result this rests on")
    confidence: Literal["high", "medium", "low"]


class RuledOut(BaseModel):
    """One thing a specialist checked and eliminated. Required output, not a bonus."""

    model_config = ConfigDict(extra="forbid")

    hypothesis: str
    result_id: str
    why: str


class SpecialistFindings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    found: list[Finding]
    ruled_out: list[RuledOut]
    """No default. The schema requires the key, so a specialist cannot omit its dead ends by
    saying nothing about them."""

    note: str = ""


FaultClass = Literal[
    "bad_deploy", "bad_config", "dependency_latency", "resource_exhaustion", "unknown"
]
RemediationClass = Literal["rollback", "restart", "config_revert", "scale", "none"]


class Verdict(BaseModel):
    """What the synthesizer concluded. Cited, and citable back to stored evidence.

    `ARCHITECTURE.md` requires the RCA be **cited and citation-validated**, so `evidence` is a
    list of `result_id`s a validator can resolve rather than prose a reader has to trust.
    """

    model_config = ConfigDict(extra="forbid")

    root_cause: str
    fault_class: FaultClass
    remediation_class: RemediationClass
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(description="result_ids this verdict rests on")
    reasoning: str
    open_questions: list[str]
    """What the evidence did not settle. A verdict that claims to have settled everything on
    six dispatches is a verdict nobody should trust, and the field makes saying so cheap."""


class NarrativeSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    body: str = Field(description="The scribe's own words. Never pasted tool output.")
    citations: list[str] = Field(
        description="result_ids whose stored evidence supports this section"
    )


class NarrativeDraft(BaseModel):
    """The scribe's structured output. **Prose is generated from this, not from context.**

    ADR-0020 §4: this record becomes corpus material at T2.4b, so a hostile log line copied
    into it is retrieved next month as institutional knowledge with the trust label gone -
    thesis 1 with a persistence layer. The draft carries references; the renderer resolves them
    against the store. Free-form pass-through from tool output to corpus has nowhere to happen.
    """

    model_config = ConfigDict(extra="forbid")

    title: str
    sections: list[NarrativeSection] = Field(min_length=1)


def _catalog() -> ServiceCatalog:
    """The catalog, built once. Lazy because a snapshot read at import time is a side effect
    every consumer of these schemas would pay for, validator or not."""
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = ServiceCatalog.from_snapshot()
    return _CATALOG


def _legal(catalog: ServiceCatalog, named: str) -> str | None:
    entry = catalog.get(named.strip())
    return entry.service if entry is not None else None


def _why_illegal(named: str, legal: str) -> str:
    named = named.strip()
    if "," in named or " and " in named:
        return (
            f"dispatch service {named!r} names more than one service. A dispatch is one "
            f"specialist asking one question about one service; to cover three services, "
            f"make three dispatches. Legal values: {legal}."
        )
    return f"dispatch service {named!r} is not a service this system knows. Legal values: {legal}."


def validate_dispatch_services(plan: DispatchPlan) -> None:
    """Every dispatch names exactly one service the catalog knows. **Canonicalises in place.**

    Raised as `ValueError` so it takes the same bounded re-ask as any other schema failure
    (ADR-0003): the planner is told what was wrong and what the legal values are, once, and a
    second failure fails the dispatch alone rather than being parsed leniently.

    Either naming scheme is accepted - `cart-service` and `cartservice` are the same service and
    `canonical_service` is what says so - and the stored value is normalised to the compose name,
    so everything downstream of the plan sees one identity.
    """
    catalog = _catalog()
    legal = ", ".join(sorted(catalog.services))
    for dispatch in plan.dispatches:
        canonical = _legal(catalog, dispatch.service)
        if canonical is None:
            raise ValueError(_why_illegal(dispatch.service, legal))
        dispatch.service = canonical


def partition_dispatch_services(plan: DispatchPlan) -> list[str]:
    """Keep the legal dispatches, drop the rest, and say why each was dropped.

    **After the one re-ask, not instead of it.** A plan that still names an illegal service on
    its second attempt loses that dispatch and nothing else: three good dispatches and one bad
    one is three dispatches' worth of evidence, and throwing the round away to punish the fourth
    would cost the investigation more than the fourth was worth. Each drop is recorded as a
    failed dispatch, the same route a specialist takes when its own output will not validate
    twice.
    """
    catalog = _catalog()
    legal = ", ".join(sorted(catalog.services))
    kept: list[Dispatch] = []
    rejected: list[str] = []
    for dispatch in plan.dispatches:
        canonical = _legal(catalog, dispatch.service)
        if canonical is None:
            rejected.append(_why_illegal(dispatch.service, legal))
            continue
        dispatch.service = canonical
        kept.append(dispatch)
    plan.dispatches = kept
    return rejected
