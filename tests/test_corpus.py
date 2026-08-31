"""T2.4b against the eight dev narratives that are actually in the tree. No Postgres, no model.

The fixtures are the committed bundles under `evals/scenarios/artifacts/dev/`, read from the
tree rather than copied - a corpus test written against a hand-made narrative proves the
parser handles what we imagined we wrote.

Two seams are substituted: the embedder (a deterministic hash, not a model) and the store
(a dict with the same retrieval rule). What that leaves under test is the parsing, the
provenance, the quarantine, and the exclusion - which is where the logic that can be wrong is.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from faultline.context.corpus import ANSWER_SECTION, NarrativeError, parse_narrative
from faultline.context.embedding import HashingEmbedder
from faultline.context.seed import QuarantineError, bundle_chunks, require_dev_root, seed
from faultline.context.store import InMemoryPastIncidentStore, fuse

ARTIFACTS = Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "artifacts"
DEV = ARTIFACTS / "dev"
HOLDOUT = ARTIFACTS / "holdout"

DEV_DOCUMENTS = 10
"""Ten dev bundles, two marked INVALID. **Pinned so a new narrative is a conscious change**
to this number - a corpus that silently grows is one nobody has read."""

SECTIONS_PER_NARRATIVE = 5
"""Measured across all ten committed narratives: What was observed | What was checked |
Root cause | Resolution | Detection notes. Identical in every one, which is what makes a
section a stable chunk rather than one author's habit."""


def store() -> InMemoryPastIncidentStore:
    return InMemoryPastIncidentStore(HashingEmbedder())


# --- parsing -------------------------------------------------------------------


def test_every_dev_narrative_parses_into_the_same_five_sections() -> None:
    narratives = sorted(DEV.glob("*/incident.md"))

    assert len(narratives) == 12, "twelve dev bundles carry a narrative; two are INVALID"
    for path in narratives:
        narrative = parse_narrative(path)
        assert narrative.split == "dev"
        assert narrative.origin.startswith("scenario:")
        assert narrative.title
        assert [s for s, _ in narrative.sections] == [
            "What was observed",
            "What was checked",
            ANSWER_SECTION,
            "Resolution",
            "Detection notes",
        ], f"{path.parent.name} has a different shape"


def test_a_narrative_without_front_matter_refuses(tmp_path: Path) -> None:
    """Front matter is the provenance. Without it a chunk has no origin, and origin is the
    exclusion key - a chunk that cannot be excluded is worse than a chunk that is absent."""
    orphan = tmp_path / "incident.md"
    orphan.write_text("# A title\n\n## What was observed\n\nsomething\n")

    with pytest.raises(NarrativeError, match="no YAML front matter"):
        parse_narrative(orphan)


# --- the quarantine ------------------------------------------------------------


def test_the_holdout_root_refuses() -> None:
    """ADR-0008 makes seeding a path rule. This is the path rule."""
    with pytest.raises(QuarantineError, match="holdout"):
        require_dev_root(HOLDOUT)


def test_a_path_that_walks_into_holdout_refuses() -> None:
    """Checked on the resolved path, so relative traversal cannot get out of the dev tree."""
    with pytest.raises(QuarantineError, match="holdout"):
        require_dev_root(DEV / ".." / "holdout")


def test_the_artifacts_root_refuses_because_it_spans_both_splits() -> None:
    """ "Seed everything and filter" is the shape ADR-0008 warns about: it is one edit away
    from seeding the holdout, and the edit looks harmless."""
    with pytest.raises(QuarantineError, match="not a dev split root"):
        require_dev_root(ARTIFACTS)


def test_a_narrative_whose_front_matter_disagrees_with_its_path_refuses(tmp_path: Path) -> None:
    """The T1.6 guards make this near-impossible. The seeder refuses rather than trusts,
    because the cost of being wrong is a holdout answer key nothing downstream would show."""
    bundle = tmp_path / "dev" / "smuggled"
    bundle.mkdir(parents=True)
    source = next(DEV.glob("*/incident.md"))
    (bundle / "incident.md").write_text(
        source.read_text().replace("split: dev", "split: holdout", 1)
    )
    (bundle / "manifest.json").write_text("{}")

    with pytest.raises(QuarantineError, match="path and the front matter disagree"):
        bundle_chunks(bundle)


def test_a_narrative_whose_origin_disagrees_with_its_manifest_refuses(tmp_path: Path) -> None:
    """`origin` is the exclusion key, so a wrong one excludes the wrong scenario."""
    bundle = tmp_path / "dev" / "mislabelled"
    bundle.mkdir(parents=True)
    source = next(DEV.glob("*/incident.md"))
    (bundle / "incident.md").write_text(source.read_text())
    (bundle / "manifest.json").write_text(json.dumps({"origin": "scenario:something-else"}))

    with pytest.raises(QuarantineError, match="exclusion key"):
        bundle_chunks(bundle)


# --- seeding -------------------------------------------------------------------


def test_seeding_the_dev_tree_yields_exactly_the_ten_valid_narratives() -> None:
    """Nine bundles, two INVALID - `currency-cpu-throttle` and `flag-service-crashloop` are
    blocked scenarios whose faults produced nothing observable. Seeding them would put two
    incidents in the corpus that never happened."""
    seeded = store()

    result = seed(seeded, DEV)

    assert result.documents == DEV_DOCUMENTS
    assert result.chunks == DEV_DOCUMENTS * SECTIONS_PER_NARRATIVE
    assert seeded.count() == result.chunks
    assert sorted(name for name, _ in result.skipped) == [
        "currency-cpu-throttle",
        "flag-service-crashloop",
    ]
    assert all("INVALID" in why for _, why in result.skipped), "skipping is reported, not silent"


def test_every_chunk_carries_the_provenance_exclusion_needs() -> None:
    """The point of the provenance is that T4.1b's exclusion is a WHERE clause, not a
    special case - so every field it filters on has to be on every chunk."""
    seeded = store()
    seed(seeded, DEV)

    for chunk in seeded.chunks.values():
        assert chunk.origin.startswith("scenario:")
        assert chunk.split == "dev"
        assert chunk.scenario_id and chunk.fault_class
        assert chunk.scenario_fingerprint, "ties the chunk to the label it was recorded against"
        assert chunk.recorded_from.startswith("2026-"), "ties it to one recording"
        assert chunk.document_id == chunk.origin

    origins = {chunk.origin for chunk in seeded.chunks.values()}
    assert len(origins) == DEV_DOCUMENTS


def test_no_seeded_chunk_comes_from_the_holdout() -> None:
    """The assertion that matters most, stated over the result rather than the input."""
    seeded = store()
    seed(seeded, DEV)

    assert not any(chunk.split == "holdout" for chunk in seeded.chunks.values())
    holdout_ids = {p.parent.name for p in HOLDOUT.glob("*/incident.md")}
    assert holdout_ids, "there are holdout narratives to have leaked"
    assert not (holdout_ids & {chunk.scenario_id for chunk in seeded.chunks.values()})


# --- retrieval and the axis-2 exclusion ----------------------------------------


def test_retrieval_returns_a_scenarios_own_narrative_when_nothing_is_excluded() -> None:
    """The product case, and the setup for the next test: without an exclusion the nearest
    neighbour to a scenario's symptoms is that scenario's own write-up."""
    seeded = store()
    seed(seeded, DEV)
    narrative = parse_narrative(DEV / "cart-redis-misconfig" / "incident.md")
    query = dict(narrative.sections)["What was observed"]

    hits = seeded.search(query, k=5)

    assert any(hit.chunk.origin == "scenario:cart-redis-misconfig" for hit in hits)


def test_exclude_origin_removes_a_scenarios_own_narrative_from_its_own_retrieval() -> None:
    """**ADR-0008's axis 2.** When scoring scenario S the nearest neighbour in the store is
    the rehearsal of S - a document containing S's true root cause in the label author's own
    words. The agent does not diagnose the incident; it looks up the answer key.

    This is within-split leakage: a dev scenario retrieving its own dev rehearsal violates no
    split rule at all, and the path quarantine is structurally blind to it. The defence is the
    exclusion, and it is an argument in the signature from day one so T4.1b passes one rather
    than patching a query.
    """
    seeded = store()
    seed(seeded, DEV)
    narrative = parse_narrative(DEV / "cart-redis-misconfig" / "incident.md")
    query = dict(narrative.sections)["What was observed"]

    hits = seeded.search(query, k=5, exclude_origin="scenario:cart-redis-misconfig")

    assert hits, "the corpus still answers - other incidents remain retrievable"
    assert not any(hit.chunk.origin == "scenario:cart-redis-misconfig" for hit in hits)
    assert not any(
        hit.chunk.section == ANSWER_SECTION and hit.chunk.scenario_id == "cart-redis-misconfig"
        for hit in hits
    ), "the answer-key section of the scenario under test, specifically"


def test_exclusion_applies_to_both_arms_of_the_hybrid() -> None:
    """A dense arm that filters and a text arm that does not is a leak with a clean-looking
    query beside it. Asserted by excluding an origin whose prose the text arm would rank
    first on shared vocabulary."""
    seeded = store()
    seed(seeded, DEV)
    narrative = parse_narrative(DEV / "shipping-wrong-image" / "incident.md")
    query = narrative.title + " " + dict(narrative.sections)["What was observed"]

    hits = seeded.search(query, k=10, exclude_origin="scenario:shipping-wrong-image")

    assert all(hit.chunk.origin != "scenario:shipping-wrong-image" for hit in hits)
    assert any(hit.text_rank is not None for hit in hits), "the text arm did run"
    assert any(hit.dense_rank is not None for hit in hits), "so did the dense arm"


def test_fusion_ranks_on_agreement_between_the_arms() -> None:
    """Reciprocal rank fusion, on ranks rather than scores - a cosine distance and a
    `ts_rank_cd` have no common scale, and normalising them invents a relationship."""
    fused = fuse([["a", "b", "c"], ["c", "a", "d"]], limit=4)

    assert next(iter(fused)) == "a", "top-3 in both arms beats first-in-one"
    assert fused["b"][1] == [2, None], "arm positions are kept, so a hit can be explained"


# --- the embedder seam ---------------------------------------------------------


def test_the_test_embedder_is_deterministic_across_processes() -> None:
    """`hashlib`, not `hash()`, whose seed is randomised per process. A corpus test that
    passed or failed depending on PYTHONHASHSEED would be worse than no test."""
    first = HashingEmbedder().embed(["cart pointed at the wrong redis port"])[0]
    second = HashingEmbedder().embed(["cart pointed at the wrong redis port"])[0]

    assert first == second
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9, "unit length"


# --- the CLI -------------------------------------------------------------------


def test_the_seed_cli_offers_no_way_to_point_at_the_holdout() -> None:
    """There is deliberately no `--split` and no `--holdout`.

    The guard would refuse either way. An interface that offers the option is still worse:
    it invites the argument about whether the guard is too strict, which is the argument
    ADR-0008 exists to have already had.
    """
    from faultline.context.cli import parser

    flags = {action.option_strings[0] for action in parser()._actions if action.option_strings}

    assert "--dev-root" in flags
    assert not {"--split", "--holdout", "--all-splits"} & flags


def test_the_seed_cli_dry_run_reproduces_the_ten_documents(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--dry-run` applies every guard with no database and no model, so a new narrative can
    be checked before a download is spent on it."""
    from faultline.context.cli import run

    assert run(["--dry-run", "--dev-root", str(DEV)]) == 0

    out = capsys.readouterr().out
    assert f"documents={DEV_DOCUMENTS} chunks={DEV_DOCUMENTS * SECTIONS_PER_NARRATIVE}" in out
    assert "skipped currency-cpu-throttle - bundle is marked INVALID" in out
    assert "nothing was written" in out


def test_the_seed_cli_refuses_a_holdout_root_with_an_error_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same convention as `faultline-inject`: a refusal is a message and a non-zero exit."""
    from faultline.context.cli import run

    assert run(["--dry-run", "--dev-root", str(HOLDOUT)]) == 2
    assert "holdout" in capsys.readouterr().err
