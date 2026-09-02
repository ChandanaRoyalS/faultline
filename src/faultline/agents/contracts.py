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

from faultline.context.allowlist import ActionStatus, load_allowlist
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


TriageDisposition = Literal["investigate", "duplicate", "noise"]


class TriageJudgement(BaseModel):
    """What triage decides that a graph traversal cannot (T3.1).

    The specification asks triage to classify *"severity, affected service, blast radius,
    duplicate-of, suspected fault category — as a validated structured output driving the state
    machine"*, from a *"small model, strict output schema"*. **Severity and blast radius are not
    on this object, and their absence is the decision.** They are measured: severity comes from
    the alert labels, and the radius is `ServiceGraph.blast_radius` over edges whose kinds were
    measured from recorded bundles. T3.1 scores that radius against those bundles, so a model
    that could restate it could move a scored number while nothing about the world changed.

    What is left is exactly what a traversal has no way to answer, and what the deliverable's
    second half - *"noise gated before fan-out"* - requires somebody to answer:

    - **`disposition`**, the gate itself. An expensive investigation is launched, declined as
      noise, or refused as a duplicate of an incident already being worked.
    - **`duplicate_of`**, which needs incident history rather than topology. T2.1's fingerprint
      dedupe owns *exact* duplicates; this is the cross-fingerprint case the plan names.
    - **`suspected_fault_class`**, a cheap prior the planner may use and must not be bound by.
      It is not scored: ADR-0022 scores the *verdict's* class, and scoring a guess made before
      any evidence was gathered would reward confidence at the cheapest point in the pipeline.
    - **`confidence`** and **`reasoning`**, so a declined investigation can be argued with.
    """

    model_config = ConfigDict(extra="forbid")

    disposition: TriageDisposition
    duplicate_of: str | None = Field(
        default=None, description="The incident id this duplicates, when disposition is duplicate"
    )
    suspected_fault_class: FaultClass = "unknown"
    confidence: Literal["high", "medium", "low"]
    reasoning: str = Field(description="Why, in one or two sentences a responder can argue with")


class Proposal(BaseModel):
    """A remediation proposal: **a falsifiable claim about a change, never the change** (T3.9).

    ADR-0028 §1 fixes the shape and the reasons. Three of them, in the ADR's order of weight:
    a command string can be diffed against ground truth and nothing else, while a predicate can
    be *evaluated against the world* - the only thing that would make this benchmark measure
    remediation rather than phrasing; a command string is untrusted text with an execution path
    attached, arriving through the one role that was supposed to have no tools; and the four
    tools already define the vocabulary an expected effect can be written in.

    **`action_id` and `target` are drawn from catalogs, not written free.** The action is an id
    in the allowlist catalog; the target is a service the catalog knows, canonicalised the
    way dispatch services are. ADR-0011's reason: this world has two naming schemes and they are
    not interchangeable, so a proposer emitting `cartservice` where the action plane needs
    `cart-service` is a class of failure worth designing out rather than measuring.

    **Abstention is a first-class output** (ADR-0022 §1.2, ADR-0028 §4): `remediation_class:
    "none"` with `action_id: ""` is neither right nor wrong, and given the approval boundary it
    is frequently the correct answer.
    """

    model_config = ConfigDict(extra="forbid")

    remediation_class: RemediationClass
    action_id: str = Field(description="An id from the allowlist catalog, or empty when abstaining")
    target: str = Field(description="The one service the change lands on, or empty when abstaining")
    rests_on: list[str] = Field(description="result_ids this proposal rests on")
    expected_effect: str = Field(
        description="What should be observed afterwards, as a predicate over metrics or logs"
    )
    confirm_within_seconds: int = Field(
        ge=0,
        le=3600,
        description="How long that should take, so 'it did not work' is decidable",
    )
    if_wrong: str = Field(description="What observation would falsify this proposal")
    risk: str = Field(description="What this change could break if the diagnosis is wrong")
    blast_radius: str = Field(description="Who else sees the change, from the dependency graph")
    """`risk` and `blast_radius` are **mandatory**, which is the plan's own word for them in
    T3.9's method column. Neither has a default: a proposal that declines to say what it could
    break is the proposal an approver most needs to see refuse."""


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


def validate_proposal(proposal: Proposal, scoped: set[str]) -> None:
    """A proposal names a real action, on a service inside the incident's own topology (T3.9).

    **Canonicalises `target` in place**, the way `validate_dispatch_services` does, and raises
    `ValueError` so a violation takes the same bounded re-ask as any other schema failure
    (ADR-0003) rather than a lenient parse.

    Four checks, and each has a reason in ADR-0028:

    - **Abstention is legal and complete.** `remediation_class: "none"` must carry no action and
      no target; an abstention with a target attached is a proposal pretending not to be one.
    - **The action is an allowlist id**, and one whose `status` is `available`. `scale_service`
      is in the catalog and unperformable - ADR-0029 measured why - so proposing it is refused
      here rather than discovered at approval time. Read through `load_allowlist`, which is the
      only thing that names the catalog file (`tests/test_allowlist.py` asserts it).
    - **The class matches the action's own class.** The catalog says what `rollback_image`
      remediates; a proposal that pairs it with `restart` is inconsistent with the document it
      cites.
    - **The target is inside the incident's scoped topology.** ADR-0032 puts this check at the
      point where the incident is in scope, which is here and not in the catalog: the allowlist
      names a *selector* (`incident_scoped_service`) and never a service. THREAT-MODEL's action
      plane hard-rejects a mismatch before an approval is even requested; refusing it at
      proposal time means the approver never sees one.
    """
    if proposal.remediation_class == "none":
        if proposal.action_id or proposal.target:
            raise ValueError(
                "an abstaining proposal (remediation_class 'none') must name no action and no "
                "target; leave action_id and target empty"
            )
        return

    catalog = load_allowlist()
    action = catalog.by_id(proposal.action_id)
    if action is None:
        legal = ", ".join(sorted(a.id for a in catalog.performable))
        raise ValueError(
            f"action_id {proposal.action_id!r} is not in the allowlist catalog. "
            f"Legal values: {legal}."
        )
    if action.status is not ActionStatus.AVAILABLE:
        raise ValueError(
            f"action {action.id!r} is listed but cannot be performed in this world: "
            f"{(action.unperformable_reason or '').strip()} Propose a different action, or "
            f"abstain with remediation_class 'none'."
        )
    if action.remediation_class != proposal.remediation_class:
        raise ValueError(
            f"action {action.id!r} is a {action.remediation_class!r} action and the proposal "
            f"calls it {proposal.remediation_class!r}. The catalog decides which class an "
            f"action belongs to."
        )

    canonical = _legal(_catalog(), proposal.target)
    if canonical is None:
        raise ValueError(
            f"target {proposal.target!r} is not a service this system knows. "
            f"Legal values: {', '.join(sorted(_catalog().services))}."
        )
    if canonical not in scoped:
        raise ValueError(
            f"target {canonical!r} is outside this incident's blast radius "
            f"({', '.join(sorted(scoped))}). An action may only touch a service the incident "
            f"reached; propose one of those, or abstain with remediation_class 'none'."
        )
    proposal.target = canonical


def validate_triage(judgement: TriageJudgement, known_incidents: set[str]) -> None:
    """A duplicate names an incident that exists; nothing else names one (T3.1).

    Raised as `ValueError`, so it takes ADR-0003's one bounded re-ask like any other contract
    violation. Two checks, both about the same failure: a `duplicate_of` the store has never
    heard of would send an incident to `DUPLICATE_MERGED` against nothing, and a `duplicate_of`
    attached to an `investigate` decision is a model telling the state machine two things at
    once. The state machine takes one transition, so the contract admits one claim.
    """
    if judgement.disposition == "duplicate":
        if not judgement.duplicate_of:
            raise ValueError(
                "disposition 'duplicate' requires duplicate_of to name the incident this "
                "duplicates. If you cannot name one, the disposition is 'investigate'."
            )
        if judgement.duplicate_of not in known_incidents:
            listed = ", ".join(sorted(known_incidents)) or "none are open"
            raise ValueError(
                f"duplicate_of {judgement.duplicate_of!r} is not an incident in the history you "
                f"were given. Open incidents: {listed}."
            )
        return
    if judgement.duplicate_of:
        raise ValueError(
            f"duplicate_of names {judgement.duplicate_of!r} but the disposition is "
            f"{judgement.disposition!r}. Only a 'duplicate' disposition may name one."
        )
