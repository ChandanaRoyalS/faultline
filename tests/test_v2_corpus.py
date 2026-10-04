"""T7.3's trial, Addendum 4: a v2 corpus, and the leave-one-out claim made by absence.

The owner's decision of 2026-10-04, after the trial's Faultline runs met a v1-only corpus on the v2
world: a planner dispatched `productcatalogservice` (v1's name) twice and failed, and every
leave-one-out exclusion removed nothing. v1's corpus must stay exactly what it was.
"""

from __future__ import annotations

from typing import Any

import pytest

from evalharness import run
from evalharness.corpusdrift import working_tree_rows
from faultline.context.seed import runbook_in_corpus
from faultline.context.store import InMemoryPastIncidentStore, PgVectorPastIncidentStore

V2_RUNBOOKS = {
    "action-restart-service",
    "action-revert-config",
    "action-rollback-image",
    "action-scale-unavailable",
    "alert-high-error-rate",
    "class-bad-config",
    "class-bad-deploy",
    "class-datastore-corruption",
    "class-dependency-latency",
    "class-disk-fill",
    "class-feature-flag",
    "class-network-partition",
    "class-process-freeze",
    "class-resource-exhaustion",
}


def _documents(world: str) -> set[str]:
    return {d for d, _, _ in working_tree_rows(world=world)}


def test_v1_s_corpus_is_exactly_what_it_was() -> None:
    from evalharness.freeze import shape_digest_of
    from evalharness.generations import CURRENT_CORPUS_SHAPE, corpus_pins

    rows = working_tree_rows(world="v1")
    assert len(rows) == 334 and len({d for d, _, _ in rows}) == 65
    assert shape_digest_of([(d, s) for d, s, _ in rows]) == CURRENT_CORPUS_SHAPE
    assert corpus_pins("v1")[0] == CURRENT_CORPUS_SHAPE


def test_v2_s_corpus_is_v2_s_narratives_and_fourteen_world_neutral_runbooks() -> None:
    from evalharness import sweep

    docs = _documents("v2")
    narratives = {d.split(":", 1)[1] for d in docs if d.startswith("scenario:")}
    runbooks = {d.split(":", 1)[1] for d in docs if d.startswith("runbook:")}

    assert narratives == set(sweep.runnable(world="v2"))
    assert runbooks == V2_RUNBOOKS
    assert not any(d.startswith("postmortem:") for d in docs)
    assert not docs & {f"scenario:{s}" for s in sweep.runnable(world="v2", holdout=True)} - {
        f"scenario:{s}" for s in sweep.runnable(world="v2")
    }, "no holdout narrative"


def test_a_runbook_naming_a_v1_service_or_describing_v1_s_world_stays_out_of_v2() -> None:
    assert runbook_in_corpus("service-cartservice", ["cartservice"], "cart", "v2") is False
    assert runbook_in_corpus("world-log-volume", ["any"], "logs", "v2") is False
    assert runbook_in_corpus("alert-x", ["any"], "see checkoutservice", "v2") is False
    assert runbook_in_corpus("class-x", ["any"], "a frozen process", "v2") is True
    assert runbook_in_corpus("service-cartservice", ["cartservice"], "x", "v1") is True
    with pytest.raises(ValueError, match="no corpus is defined"):
        runbook_in_corpus("class-x", ["any"], "x", "v3")


def test_replace_leaves_only_the_documents_the_seed_wrote() -> None:
    from faultline.context.corpus import Chunk
    from faultline.context.embedding import HashingEmbedder

    store = InMemoryPastIncidentStore(HashingEmbedder())
    store.chunks = {"a#0": _chunk(Chunk, "doc:a"), "b#0": _chunk(Chunk, "doc:b")}

    assert store.prune_except({"doc:a"}) == 1
    assert set(store.chunks) == {"a#0"}


def _chunk(chunk_type: Any, document_id: str) -> Any:
    fields = chunk_type.__dataclass_fields__ if hasattr(chunk_type, "__dataclass_fields__") else {}
    values = {name: "" for name in fields}
    values.update(document_id=document_id, section_index=0)
    return chunk_type(**values)


def test_replace_refuses_to_empty_the_store() -> None:
    store = object.__new__(PgVectorPastIncidentStore)
    with pytest.raises(ValueError, match="empty corpus"):
        store.prune_except(set())


def test_faultline_seed_takes_a_world_and_replace() -> None:
    from faultline.context.cli import parser

    args = parser().parse_args(["--world", "v2", "--replace"])
    assert args.world == "v2" and args.replace
    assert parser().parse_args([]).world == "v1"


def test_v2_s_pins_are_the_ingested_corpus_which_is_the_tree_s() -> None:
    import json
    from pathlib import Path

    from evalharness import batch
    from evalharness.freeze import body_digest_of, shape_digest_of
    from evalharness.generations import corpus_pins

    shape, body = corpus_pins("v2")
    rows = working_tree_rows(world="v2")
    assert shape == shape_digest_of([(d, s) for d, s, _ in rows])
    assert body == body_digest_of(rows)
    record = json.loads(
        (
            Path(__file__).resolve().parents[1] / "docs/evidence/t7.3/corpus-of-record-v2.json"
        ).read_text()
    )
    assert (record["sha256"], record["body_sha256"]) == (shape, body)
    assert record["holdout_chunks"] == 0 and record["rows"] == 200

    ok, _ = batch.corpus_frozen({**record}, "v2")
    assert ok
    ok, detail = batch.corpus_frozen({**record, "sha256": "0" * 64}, "v2")
    assert not ok and "world v2's pin" in detail
    with pytest.raises(ValueError):
        corpus_pins("v3")


# --- the leave-one-out claim, made by absence ------------------------------------------------


def _silent(origin: str) -> dict[str, Any]:
    return {"silent": [{"seq": 1, "exclude_origins": [origin]}], "missing_own": []}


def test_a_holdout_or_another_world_s_narrative_is_absent_by_design() -> None:
    assert "holdout" in str(run.absence_by_design("v2-payment-freeze", "v2"))
    assert "world v2" in str(run.absence_by_design("v2-cart-freeze", "v1"))
    assert run.absence_by_design("v2-cart-freeze", "v2") is None
    assert run.absence_by_design("cart-bad-image-tag", "v1") is None


def test_absence_is_accepted_only_when_designed_and_counted_and_aimed_at_the_scenario() -> None:
    own = "scenario:v2-payment-freeze"
    why = "a holdout scenario's artifacts never enter any corpus"

    accepted = run.absence_assertion(_silent(own), own, why, 0)
    assert accepted == {"own_origin": own, "absent_by_design": why, "chunks_of_own_origin": 0}

    assert run.absence_assertion(_silent(own), own, None, 0) is None, "expected in the corpus"
    assert run.absence_assertion(_silent(own), own, why, 3) is None, "it is there after all"
    assert run.absence_assertion(_silent("scenario:other"), own, why, 0) is None
    wrong = {**_silent(own), "missing_own": [{"seq": 2}]}
    assert run.absence_assertion(wrong, own, why, 0) is None
    assert run.absence_assertion({"silent": [], "missing_own": []}, own, why, 0) is None


def test_the_harness_invalidates_on_silence_only_when_absence_was_not_asserted() -> None:
    import inspect

    source = inspect.getsource(run.main)
    assert 'if (enforcement["silent"] and absent is None) or enforcement["missing_own"]:' in source
    assert "absence_by_design(args.scenario_id, tools_world())" in source
