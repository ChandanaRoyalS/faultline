"""The typed `Evidence` object: the only currency roles exchange (T3.6).

The plan's T3.6: *"The typed Evidence object: claim, source query, time range, raw-result hash,
sample payload — the only currency agents may exchange."* Method: *"Strict schemas per modality;
provenance mandatory; every Evidence object carries the trust label its source tool attached in
the runtime; raw results archived so every citation can be re-verified later."* Deliverable:
*"Evidence store with full provenance chain."*

**Every part of that existed and no object held it.** The Phase 3 audit found the chain split
across three places: `SpecialistFindings.found[i]` held the claim and a `result_id`; the
`ToolResult` subclasses held the modality, the trust label, the window and the query; and
`ToolCallRecord` held the rendered envelope and its `envelope_sha256`. Joining them meant
walking a trajectory. A citation could be *resolved* - the narrative renderer does it - and the
provenance behind it could not be *read off the thing being cited*.

## The runtime binds it; no model writes it

**A model produces the claim and the `result_id`, and nothing else on this object.** Everything
else is copied from the tool result the runtime already holds. That is what the plan means by
*"the trust label its source tool attached in the runtime"*, and it is the whole security
argument: a field a model could fill is a field a model could fabricate, and provenance that can
be fabricated is decoration. `bind` is therefore a function of a `SpecialistRun`, not a schema
the specialist is held to - `Evidence` is deliberately **not** a `_CONTRACTS` member, and the
stamp does not move for it.

## The sample, and the boundary it crosses

The plan asks Evidence to carry a *sample payload* so the synthesizer sees *"a curated evidence
board, not transcripts"*. ADR-0020 kept raw envelopes away from the synthesizer, and the two are
reconcilable rather than in conflict: what that decision refuses is the *transcript* - arming the
role with tools, or pasting whole envelopes into the context that writes durable material. A
bounded excerpt is the curation the plan is asking for.

**Marked decision: the sample is bounded, neutralised, and rendered inside a trust envelope
wherever it reaches a model.** `neutralise` is the tool layer's own function - the one that
strips control sequences and defuses anything shaped like a closing delimiter - so a log line in
a sample cannot close the frame that contains it, exactly as it cannot in a specialist's
envelope. The bound is `SAMPLE_CHARS`, and a truncated sample says so rather than looking
complete: `truncated` on this object means *the sample was cut*, distinct from the tool's own
`truncated`, which means *the result was capped*. Both travel, because they answer different
questions.

## What this does not change

`Finding` and `RuledOut` keep their shapes and their prompts. The specialists are asked for
exactly what they were asked for before. The envelope is still stored verbatim under its
`result_id` and still archived; `raw_sha256` is the same digest `ToolCallRecord.envelope_sha256`
computes, carried here so a reader holding one `Evidence` row can check the envelope it names
without first finding the step that produced it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict

from faultline.tools.envelope import neutralise
from faultline.tools.results import ToolResult, Trust

if TYPE_CHECKING:  # pragma: no cover - a type-only import, to keep roles importing evidence
    from faultline.agents.roles import SpecialistRun

SAMPLE_CHARS = 400
"""How much of a result body an `Evidence` object carries.

Enough for the shapes the rehearsed narratives turn on - a JVM startup banner, a changed
environment value with its before and after, a ratio line - and far short of a transcript. The
full text is in the store under `result_id` and in the archive; this is the excerpt a reader
sees beside the claim, and `truncated` says when there is more.
"""

EvidenceKind = Literal["found", "ruled_out"]


class Evidence(BaseModel):
    """One claim, bound to the provenance of the tool result it rests on.

    Assembled by the runtime from a `SpecialistRun`. Never produced by a model, never accepted
    from one: `bind` is the only constructor used in the pipeline.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # --- the claim, which is the model's ---------------------------------------
    kind: EvidenceKind
    claim: str
    """`Finding.statement`, or `RuledOut.hypothesis` with its `why` in `note`."""

    note: str = ""
    confidence: str = ""
    """Empty for a ruled-out hypothesis: the specialist contract does not ask for one, and
    inventing a value here would put a number on the object that nobody stated."""

    # --- the provenance, which is the runtime's --------------------------------
    result_id: str
    specialist: str
    service: str
    question: str
    tool: str
    source: str
    trust: Trust
    query: str = ""
    """The source query as the tool issued it: the PromQL expression, the LogQL selector, or the
    canonical service for the trace and change tools, which take no query language."""

    window_start: datetime | None = None
    window_end: datetime | None = None
    raw_sha256: str
    """The digest of the rendered envelope - the same value `ToolCallRecord.envelope_sha256`
    computes. Carried so a citation can be re-verified from the evidence row alone."""

    sample: str = ""
    truncated: bool = False
    """The **sample** was cut. `result_truncated` is the tool's own cap."""

    result_empty: bool = False
    result_truncated: bool = False
    result_error: str | None = None
    """An empty result is evidence and an errored one is not - ADR-0019's distinction, carried
    onto the object a synthesizer reads rather than left in the envelope text."""

    def window(self) -> str:
        if self.window_start is None or self.window_end is None:
            return "no window"
        return f"{self.window_start.isoformat()}..{self.window_end.isoformat()}"

    def render(self, sample: bool = True) -> str:
        """One evidence-board entry, with the sample delimited and labelled untrusted.

        The delimiter is the same shape the tool layer uses and the sample is already
        neutralised, so content cannot close a frame it is inside of.

        **`sample=False` is for the scribe, and it is not a preference.** ADR-0020 §4 draws its
        leak boundary at exactly one role: the scribe's output becomes corpus material, so a
        hostile log line copied into it is thesis 1 with a persistence layer. The synthesizer
        and the proposer emit structured objects that a validator checks; the scribe emits prose
        that gets stored and retrieved months later. So the board reaches all three roles and
        the *samples* reach only the two that cannot publish them.
        """
        head = (
            f"[{self.result_id}] {self.kind.upper()} ({self.specialist} on {self.service})"
            f"{f' ({self.confidence})' if self.confidence else ''}: {self.claim}"
        )
        lines = [head]
        if self.note:
            lines.append(f"    why: {self.note}")
        lines.append(
            f"    from {self.tool} on {self.source}, window {self.window()}, "
            f"trust {self.trust.value}, sha256 {self.raw_sha256[:12]}"
        )
        if self.query:
            lines.append(f"    query: {self.query}")
        if self.result_error is not None:
            lines.append(f"    the query FAILED: {self.result_error} - this is not a negative")
        elif self.result_empty:
            lines.append("    the window was observed and held nothing - an empty answer")
        if sample and self.sample:
            suffix = " (cut)" if self.truncated else ""
            lines.append(f'    <sample trust="untrusted"{suffix}>')
            lines += [f"      {line}" for line in self.sample.splitlines()]
            lines.append("    </sample>")
        return "\n".join(lines)


def source_query(result: ToolResult) -> str:
    """What the tool actually asked, per modality.

    Read off the typed result rather than reconstructed: `promql_query` carries its expression,
    `logql_query` its selector, and the trace and change tools take a service and no query
    language at all - which is worth recording as the empty case rather than papering over with
    a synthesised string that was never sent.
    """
    for attribute in ("query", "selector"):
        value = getattr(result, attribute, None)
        if isinstance(value, str) and value:
            return value
    return ""


def sample_of(result: ToolResult) -> tuple[str, bool]:
    """A bounded, neutralised excerpt of the result body, and whether it was cut."""
    body = neutralise(result.body())
    if len(body) <= SAMPLE_CHARS:
        return body, False
    return body[:SAMPLE_CHARS].rstrip(), True


def bind(run: SpecialistRun) -> list[Evidence]:
    """Every claim in one dispatch, bound to that dispatch's provenance.

    Ruled-out hypotheses are bound too. `ARTIFACTS.md` calls what a responder eliminated the
    most valuable content in a narrative, and an evidence board that carried only positives
    would drop half of what the specialists were required to produce.
    """
    result = run.result
    window = result.window
    common: dict[str, Any] = {
        "specialist": run.specialist,
        "service": run.service,
        "question": run.question,
        "tool": result.tool,
        "source": result.source,
        "trust": result.trust,
        "query": source_query(result),
        "window_start": window.start if window is not None else None,
        "window_end": window.end if window is not None else None,
        "raw_sha256": _sha256(run.envelope),
        "result_empty": result.empty,
        "result_truncated": result.truncated,
        "result_error": result.error,
    }
    sample, cut = sample_of(result)
    bound: list[Evidence] = []
    for finding in run.findings.found:
        bound.append(
            Evidence(
                kind="found",
                claim=finding.statement,
                confidence=finding.confidence,
                result_id=finding.result_id,
                sample=sample,
                truncated=cut,
                **common,
            )
        )
    for ruled in run.findings.ruled_out:
        bound.append(
            Evidence(
                kind="ruled_out",
                claim=ruled.hypothesis,
                note=ruled.why,
                result_id=ruled.result_id,
                sample=sample,
                truncated=cut,
                **common,
            )
        )
    return bound


def board(runs: list[SpecialistRun]) -> list[Evidence]:
    """The whole investigation's evidence, in dispatch order."""
    return [item for run in runs for item in bind(run)]


def render_board(items: list[Evidence], sample: bool = True) -> list[str]:
    """The board as a model reads it: **each dispatch's sample printed once.**

    Every `Evidence` object carries its own sample, because the object is the unit of
    provenance and one that referred elsewhere for half of it would be the split this task
    exists to close. The *rendering* is a different question: a dispatch that produced four
    claims would otherwise print the same 400 characters four times, which spends the
    synthesizer's context on a copy of something it has already read. The sample goes with the
    first claim from each `result_id`; the rest carry the reference and the provenance line,
    which is what a reader needs to know they are the same evidence.
    """
    seen: set[str] = set()
    rendered: list[str] = []
    for item in items:
        first = item.result_id not in seen
        seen.add(item.result_id)
        rendered.append(item.render(sample=sample and first))
    return rendered


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


ALLOWED_FIELDS_FROM_MODEL = frozenset({"kind", "claim", "note", "confidence", "result_id"})
"""What a model's output contributes to an `Evidence` object. Asserted by test.

The rest is copied from the tool result the runtime holds, and the test that pins this set is
the mechanism behind the docstring's claim - provenance a model could write is provenance a
model could fabricate.
"""
