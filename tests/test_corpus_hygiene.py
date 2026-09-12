"""T6.4 §2.5 - three small things the survey turned up, each with the guard it needed.

None of the three was a bug anyone reported. Each was found by reading the code while building
something else, and each had been wrong since it was written.
"""

from __future__ import annotations

from dataclasses import replace

from faultline.agents.cli import parser as investigate_parser
from faultline.agents.investigation import _label
from faultline.context.corpus import Chunk
from faultline.context.embedding import HashingEmbedder
from faultline.context.settings import ContextSettings
from faultline.context.store import InMemoryPastIncidentStore, chunk_key


def _chunk(document_id: str, index: int, scenario_id: str = "") -> Chunk:
    return Chunk(
        document_id=document_id,
        section=f"Section {index}",
        section_index=index,
        text=f"body {index}",
        origin="authored" if scenario_id == "" else f"scenario:{scenario_id}",
        split="dev",
        scenario_id=scenario_id,
        fault_class="",
        scenario_fingerprint="",
        recorded_from="",
        title="t",
        source_path="p",
    )


def test_the_setting_agrees_with_production_rather_than_describing_a_pipeline_nobody_runs() -> None:
    """**Was 5, and read by nothing.**

    `Investigation.__init__` and `faultline-investigate` each defaulted to 3 independently, so
    the field described a `k` no run ever used. A setting that disagrees with production and is
    never consulted is worse than no setting: it is a number a reader will quote.
    """
    assert ContextSettings().retrieval_k == 3

    args = investigate_parser().parse_args([])
    assert args.retrieval_k == ContextSettings().retrieval_k


def test_a_retrieved_runbook_no_longer_renders_with_a_leading_empty_field() -> None:
    """**The wart the model has been reading since runbooks were seeded.**

    The line is `f"{label} / {section}: {text}"` and a runbook has no `scenario_id` - it belongs
    to no scenario, deliberately - so every authored document arrived as `" / Acting on it: …"`.
    """
    runbook = _chunk("runbook:service-frontend", 0)
    assert _label(runbook) == "runbook:service-frontend"
    assert not _label(runbook).startswith(" ")


def test_a_narrative_renders_exactly_as_it_did() -> None:
    """The fix must not move the lines that were already right.

    A narrative carries a `scenario_id`, so it keeps it. Only the documents whose label was
    empty change, which is what makes this a repair rather than a reformat of everything the
    model reads.
    """
    narrative = _chunk("scenario:cart-redis-misconfig", 2, scenario_id="cart-redis-misconfig")
    assert _label(narrative) == "cart-redis-misconfig"


def test_re_seeding_removes_a_section_a_document_no_longer_has() -> None:
    """**Q40, and it had already happened.**

    A chunk's key is `document_id#section_index`, so `add` upserts the sections that still exist
    and says nothing about the ones that do not. T6.4's first retrieval measurement ran against
    263 chunks over 50 documents whose seed had just reported 261.
    """
    store = InMemoryPastIncidentStore(HashingEmbedder())
    first = [_chunk("runbook:x", i) for i in range(3)]
    store.add(first)
    assert store.count() == 3

    shorter = first[:2]
    store.add(shorter)
    assert store.count() == 3, "add alone leaves the orphan - this is the defect"

    removed = store.prune_document("runbook:x", {chunk_key(c) for c in shorter})
    assert removed == 1
    assert store.count() == 2


def test_pruning_one_document_does_not_touch_another() -> None:
    store = InMemoryPastIncidentStore(HashingEmbedder())
    store.add([_chunk("runbook:x", 0), _chunk("runbook:y", 0), _chunk("runbook:y", 1)])
    store.prune_document("runbook:x", set())
    assert store.count() == 2


def test_a_document_that_parsed_to_nothing_is_not_treated_as_a_deletion() -> None:
    """**Add first, then prune, and never prune on an empty parse.**

    An empty chunk list means the source produced nothing, which is a parsing failure rather
    than an instruction to delete a document. Pruning on it would turn one bad parse into a
    silently missing document - the failure mode that is hardest to notice, because the corpus
    still looks like a corpus.
    """
    from faultline.context.seed import _reconcile

    store = InMemoryPastIncidentStore(HashingEmbedder())
    store.add([_chunk("runbook:x", 0)])
    assert _reconcile(store, []) == 0
    assert store.count() == 1


def test_a_renamed_section_is_reconciled_by_index_not_by_title() -> None:
    """Renaming a heading keeps the index, so it upserts rather than orphaning. Removing one
    shifts every later index down and orphans the last - which is exactly what editing headings
    across ten runbooks did."""
    store = InMemoryPastIncidentStore(HashingEmbedder())
    original = [_chunk("runbook:x", i) for i in range(3)]
    store.add(original)
    renamed = [replace(c, section=f"Renamed {c.section_index}") for c in original]
    store.add(renamed)
    assert store.count() == 3
