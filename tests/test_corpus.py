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

from faultline.context.acceptance import Acceptance, InMemoryAcceptanceStore, digest_of
from faultline.context.corpus import ANSWER_SECTION, NarrativeError, parse_narrative
from faultline.context.embedding import HashingEmbedder
from faultline.context.postmortem import SECTIONS, parse_postmortem
from faultline.context.seed import (
    POSTMORTEM,
    QuarantineError,
    bundle_chunks,
    require_dev_root,
    seed,
)
from faultline.context.store import InMemoryPastIncidentStore, fuse

ARTIFACTS = Path(__file__).resolve().parents[1] / "evals" / "scenarios" / "artifacts"
DEV = ARTIFACTS / "dev"
HOLDOUT = ARTIFACTS / "holdout"

DEV_DOCUMENTS = 10
"""Ten dev bundles, two marked INVALID. **Pinned so a new narrative is a conscious change**
to this number - a corpus that silently grows is one nobody has read."""

OTHER_WORLD_NARRATIVES = [
    "v2-accounting-bad-credential",
    "v2-payment-telemetry-blackout",
    "v2-product-catalog-freeze",
    "v2-shipping-quote-misconfig",
]
OTHER_WORLD_INVALID = ["v2-cart-valkey-misconfig"]
"""v2 dev bundles marked INVALID: recorded, blocked, and skipped for that reason before their
world is read (`seed.dev_bundles` checks `INVALID.md` first)."""
"""Dev narratives recorded on v2, which the corpus holds out until T7.1's corpus piece (Q92)
decides (`seed.CORPUS_WORLDS`). Pinned for `DEV_DOCUMENTS`'s reason: a v2 narrative landing is a
conscious change here, and the day the corpus takes them this list and that constant move in the
same commit."""

SECTIONS_PER_NARRATIVE = 5
"""Measured across all ten committed narratives: What was observed | What was checked |
Root cause | Resolution | Detection notes. Identical in every one, which is what makes a
section a stable chunk rather than one author's habit."""

DEV_POSTMORTEMS = 10
"""T6.5's ten accepted postmortems, one per valid bundle. Pinned for `DEV_DOCUMENTS`'s reason,
and **separately from it** - the two grow for different reasons, and one total would let one
move under the other."""

SECTIONS_PER_POSTMORTEM = len(SECTIONS)
"""Read off the closed tuple rather than typed again. A second literal here would be a second
opinion about a constant that already refuses to vary."""


def store() -> InMemoryPastIncidentStore:
    return InMemoryPastIncidentStore(HashingEmbedder())


def tree_acceptances() -> InMemoryAcceptanceStore:
    """A ledger admitting exactly the postmortems in the dev tree, **as they are on disk now**.

    `seed`'s ledger argument defaults to an empty store that refuses every postmortem - per
    `UnacceptedError`'s docstring, a caller who has not wired the ledger is a caller who cannot
    check the gate - so a test that wants a seeded corpus must *supply acceptance*, exactly as a
    deployment does. That is why this helper exists rather than a skip flag on the seeder.

    **It is not a relaxation, and the difference is worth stating.** The digest still comes from
    `digest_of` over the parsed document, so editing a postmortem in the tree changes what this
    admits in the same motion as it changes what the seeder asks for. What the helper cannot do
    is refuse: it accepts whatever is there. So it belongs in tests about seeding, provenance and
    exclusion, and **not** in a test about the gate - those live in
    `tests/test_postmortem_acceptance.py`, against a ledger that says no.
    """
    ledger = InMemoryAcceptanceStore()
    for path in sorted(DEV.glob(f"*/{POSTMORTEM}")):
        postmortem = parse_postmortem(path)
        ledger.append(
            Acceptance(
                scenario_id=postmortem.scenario_id,
                body_digest=digest_of(postmortem),
                caller="tests",
            )
        )
    return ledger


# --- parsing -------------------------------------------------------------------


def test_every_dev_narrative_parses_into_the_same_five_sections() -> None:
    narratives = sorted(DEV.glob("*/incident.md"))

    assert len(narratives) == 12 + len(OTHER_WORLD_NARRATIVES) + len(OTHER_WORLD_INVALID), (
        "twelve v1 dev bundles carry a narrative (two are INVALID), plus the v2 ones"
    )
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
    incidents in the corpus that never happened.

    **Since T6.5 each valid bundle also carries an accepted postmortem**, so the totals are two
    documents per bundle rather than one. They are asserted as two named terms and not as a sum:
    a single `== 20` would be satisfied by twenty narratives and no postmortems.
    """
    seeded = store()

    result = seed(seeded, DEV, tree_acceptances())

    assert result.documents == DEV_DOCUMENTS + DEV_POSTMORTEMS
    assert result.chunks == (
        DEV_DOCUMENTS * SECTIONS_PER_NARRATIVE + DEV_POSTMORTEMS * SECTIONS_PER_POSTMORTEM
    )
    assert seeded.count() == result.chunks
    assert sum(1 for name in result.seeded if name.endswith("(postmortem)")) == DEV_POSTMORTEMS
    assert sorted(name for name, _ in result.skipped) == sorted(
        [
            "currency-cpu-throttle",
            "flag-service-crashloop",
            *OTHER_WORLD_NARRATIVES,
            *OTHER_WORLD_INVALID,
        ]
    )
    why = dict(result.skipped)
    assert all(
        "INVALID" in why[name]
        for name in ("currency-cpu-throttle", "flag-service-crashloop", *OTHER_WORLD_INVALID)
    )
    assert all("world v2" in why[name] for name in OTHER_WORLD_NARRATIVES), (
        "skipping is reported, not silent"
    )


def test_every_chunk_carries_the_provenance_exclusion_needs() -> None:
    """The point of the provenance is that T4.1b's exclusion is a WHERE clause, not a
    special case - so every field it filters on has to be on every chunk."""
    seeded = store()
    seed(seeded, DEV, tree_acceptances())

    for chunk in seeded.chunks.values():
        assert chunk.origin.startswith("scenario:")
        assert chunk.split == "dev"
        assert chunk.scenario_id and chunk.fault_class
        assert chunk.scenario_fingerprint, "ties the chunk to the label it was recorded against"
        assert chunk.recorded_from.startswith("2026-"), "ties it to one recording"
        assert chunk.document_id in (chunk.origin, f"postmortem:{chunk.scenario_id}")

    origins = {chunk.origin for chunk in seeded.chunks.values()}
    documents = {chunk.document_id for chunk in seeded.chunks.values()}
    assert len(documents) == DEV_DOCUMENTS + DEV_POSTMORTEMS
    assert len(origins) == DEV_DOCUMENTS, (
        "**a postmortem shares its scenario's origin.** Two documents, one exclusion key - which "
        "is what makes T4.1b's WHERE clause remove a scenario's postmortem along with its "
        "narrative, without knowing postmortems exist"
    )


def test_no_seeded_chunk_comes_from_the_holdout() -> None:
    """The assertion that matters most, stated over the result rather than the input."""
    seeded = store()
    seed(seeded, DEV, tree_acceptances())

    assert not any(chunk.split == "holdout" for chunk in seeded.chunks.values())
    holdout_ids = {p.parent.name for p in HOLDOUT.glob("*/incident.md")}
    assert holdout_ids, "there are holdout narratives to have leaked"
    assert not (holdout_ids & {chunk.scenario_id for chunk in seeded.chunks.values()})


# --- retrieval and the axis-2 exclusion ----------------------------------------


def test_retrieval_returns_a_scenarios_own_narrative_when_nothing_is_excluded() -> None:
    """The product case, and the setup for the next test: without an exclusion the nearest
    neighbour to a scenario's symptoms is that scenario's own write-up."""
    seeded = store()
    seed(seeded, DEV, tree_acceptances())
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
    seed(seeded, DEV, tree_acceptances())
    narrative = parse_narrative(DEV / "cart-redis-misconfig" / "incident.md")
    query = dict(narrative.sections)["What was observed"]

    hits = seeded.search(query, k=5, exclude_origins=frozenset({"scenario:cart-redis-misconfig"}))

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
    seed(seeded, DEV, tree_acceptances())
    narrative = parse_narrative(DEV / "shipping-wrong-image" / "incident.md")
    query = narrative.title + " " + dict(narrative.sections)["What was observed"]

    hits = seeded.search(query, k=10, exclude_origins=frozenset({"scenario:shipping-wrong-image"}))

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


def test_the_seed_cli_dry_run_reads_the_committed_ledger_and_reproduces_the_dev_tree(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """**Q67, closed by the ledger travelling with the tree.** From 2026-09-15 to 2026-09-18
    this test pinned the opposite: `--dry-run` had no database, handed `seed` an empty ledger,
    and exited 2 on a tree where nothing was wrong - the flag's stated purpose, *check a new
    narrative before a download is spent on it*, was unavailable against the real dev tree.
    Q67 posed two repairs and this is neither: not a third *unchecked* state, and not a read
    over the DSN that costs the dry run its *no Postgres* property. The committed ledger is the
    same decisions the table holds; reading it writes nothing. A tree without the file still
    gets the empty ledger and the refusal (the test below)."""
    from faultline.context.cli import run

    assert run(["--dry-run", "--no-runbooks", "--dev-root", str(DEV)]) == 0

    out = capsys.readouterr().out
    assert "acceptances: 10 row(s) read from" in out
    assert "documents=" in out


def test_the_dry_run_still_reproduces_a_tree_whose_bundles_carry_no_postmortem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What the test above used to assert, on the input it is actually still true of.

    A tree of narratives alone - a fresh scenario being checked before a download is spent on it,
    which is the case `--dry-run` was built for - still parses, chunks, applies every quarantine
    guard and exits 0. So the flag is narrowed rather than dead, and Q67 is about restoring the
    other half.
    """
    from faultline.context.cli import run

    root = tmp_path / "dev"
    root.mkdir()
    wanted = ("cart-redis-misconfig", "shipping-wrong-image")
    for name in wanted:
        bundle = root / name
        bundle.mkdir()
        (bundle / "incident.md").write_text((DEV / name / "incident.md").read_text())
        (bundle / "manifest.json").write_text((DEV / name / "manifest.json").read_text())

    assert run(["--dry-run", "--no-runbooks", "--dev-root", str(root)]) == 0

    out = capsys.readouterr().out
    assert f"documents={len(wanted)} chunks={len(wanted) * SECTIONS_PER_NARRATIVE}" in out
    assert "runbooks were not seeded" in out
    assert "nothing was written" in out


def test_the_runbooks_are_seeded_by_default_and_carry_the_never_excluded_origin() -> None:
    """**Q15**: the corpus was found empty of authored documents on 2026-09-01 - all seven
    stored documents were `scenario:*` - so T4.1b's *never excluded* branch had nothing to
    not-exclude and T3.9's proposer had no institutional knowledge to retrieve.

    Every runbook, every one `origin: authored`, which is the one value the exclusion filter
    never removes (ADR-0008 axis 2, ADR-0036).

    **Counted against the directory, not against a constant** (T6.4). This read `== 15` and
    failed the moment the corpus grew, which is the wrong thing for it to be sensitive to: the
    property is *every runbook on disk is seeded and none is skipped*, and a hard-coded count
    tests the size of the corpus in a file about seeding it. `test_runbooks.py` is where the
    size belongs, and the check there is already a floor rather than an equality."""
    from faultline.context.embedding import HashingEmbedder
    from faultline.context.runbooks import runbooks_dir
    from faultline.context.seed import seed_runbooks
    from faultline.context.store import InMemoryPastIncidentStore

    store = InMemoryPastIncidentStore(HashingEmbedder())
    result = seed_runbooks(store)

    on_disk = len(list(runbooks_dir().glob("*.md")))
    assert result.documents == on_disk, "a runbook on disk that is not seeded is invisible"
    assert on_disk >= 15
    assert result.chunks > result.documents, "sectioned, not one chunk per file"
    stored = list(store.chunks.values())
    assert {chunk.origin for chunk in stored} == {"authored"}
    assert all(chunk.document_id.startswith("runbook:") for chunk in stored)
    # The scenario-shaped fields are empty on purpose: a runbook belongs to no scenario, was
    # recorded against no label, and filling those in would make an authored document look
    # like a rehearsal in every query that returns it.
    assert {chunk.scenario_id for chunk in stored} == {""}
    assert {chunk.scenario_fingerprint for chunk in stored} == {""}
    assert {chunk.recorded_from for chunk in stored} == {""}


def test_seeding_the_runbooks_is_a_second_entry_point_not_a_wider_first_one() -> None:
    """`require_dev_root`'s own refusal names this temptation - *"widening the input 'just to
    pick up the runbooks' is how this defect returns"*. So the narrative seeder still takes one
    root and still refuses everything else, and the runbooks arrive through their own door."""
    import inspect

    assert "runbook" not in inspect.getsource(seed).lower()
    with pytest.raises(QuarantineError):
        seed(object(), HOLDOUT)  # type: ignore[arg-type]


def test_the_seed_cli_refuses_a_holdout_root_with_an_error_not_a_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Same convention as `faultline-inject`: a refusal is a message and a non-zero exit."""
    from faultline.context.cli import run

    assert run(["--dry-run", "--dev-root", str(HOLDOUT)]) == 2
    assert "holdout" in capsys.readouterr().err


def test_excluded_count_counts_by_origin_not_by_candidates_dropped() -> None:
    """**T4.1b's count, and why it is taken this way.**

    A dropped-candidate count would be a number about the ranking: retrieval has two arms, each
    takes its own top-k, and neither ever sees most of the corpus. What ADR-0008 axis 2 asserts
    is that a scenario's own artifacts were *unreachable*, and this counts exactly those - so it
    is the same number whatever the query was, which is what makes it an assertion about the
    boundary rather than about one search.
    """
    from faultline.context.corpus import Chunk

    def chunk(key: str, origin: str, section: str, index: int) -> Chunk:
        return Chunk(
            document_id=origin,
            section=section,
            section_index=index,
            text=f"body of {key}",
            origin=origin,
            split="dev",
            scenario_id=origin.removeprefix("scenario:"),
            fault_class="bad_config",
            scenario_fingerprint="fp",
            recorded_from="t",
            title=key,
            source_path=f"{key}.md",
        )

    held = store()
    held.add(
        [
            chunk("a", "scenario:cart-redis-misconfig", "Answer", 0),
            # A second **section** of the same narrative, because the store is keyed on
            # `document_id|section` - one document, many chunks, and the count is over chunks.
            chunk("b", "scenario:cart-redis-misconfig", "Timeline", 1),
            chunk("c", "authored", "Answer", 0),
        ]
    )

    assert held.excluded_count("scenario:cart-redis-misconfig") == 2
    assert held.excluded_count("authored") == 1
    assert held.excluded_count("scenario:never-seeded") == 0


# --- the exclusion as a set (T6.5, ADR-0018 Addendum 1) -----------------------------------------


def test_a_bare_string_exclusion_is_refused_rather_than_iterated() -> None:
    """**The footgun the widening created, closed in the same change.**

    `str` is a `Collection[str]`, so `exclude_origins="scenario:cart-redis-misconfig"` would
    type-check at most call sites and exclude twenty-eight single characters: matching no origin,
    excluding nothing, and reporting a healthy `excluded_count` of zero - which T4.1b reads as
    *the corpus does not hold this scenario*. A leave-one-out that silently does not happen is
    exactly what ADR-0008 axis 2 exists to prevent, so the old spelling raises.
    """
    import pytest

    from faultline.context.store import normalise_exclusions

    with pytest.raises(TypeError, match="not the string"):
        normalise_exclusions("scenario:cart-redis-misconfig")  # type: ignore[arg-type]


def test_none_and_the_empty_set_both_mean_exclude_nothing() -> None:
    from faultline.context.store import normalise_exclusions

    assert normalise_exclusions(None) == frozenset()
    assert normalise_exclusions(frozenset()) == frozenset()


def test_excluding_a_whole_fault_class_removes_every_one_of_its_scenarios() -> None:
    """**What the measurement's WITHOUT arm does**, and the reason `exclude_origin` became a set
    at all: §4's arms sit on one corpus, so the difference between them has to be expressible as
    a wider WHERE clause rather than as a re-seed."""
    seeded = store()
    seed(seeded, DEV, tree_acceptances())
    origins = sorted({c.origin for c in seeded.chunks.values() if c.origin.startswith("scenario:")})
    if len(origins) < 2:
        return

    excluded = frozenset(origins[:2])
    hits = seeded.search("errors in the checkout path", k=20, exclude_origins=excluded)

    assert not any(hit.chunk.origin in excluded for hit in hits)
    assert seeded.excluded_count(excluded) == sum(
        1 for c in seeded.chunks.values() if c.origin in excluded
    )


def test_the_count_is_over_the_whole_set_which_is_why_it_stopped_carrying_t4_1b() -> None:
    """A positive count now means *something in the set was unreachable*, not *S's own artifacts
    were*. `run.classify_retrievals` takes the scenario's own origin for that reason; this test
    pins the weakening so the reason stays visible."""
    seeded = store()
    seed(seeded, DEV, tree_acceptances())
    origins = sorted({c.origin for c in seeded.chunks.values() if c.origin.startswith("scenario:")})
    if len(origins) < 2:
        return

    others = frozenset(origins[1:])

    assert seeded.excluded_count(others) > 0, "healthy-looking, and says nothing about origins[0]"


def test_a_bundle_names_its_world_and_absence_means_v1(tmp_path: Path) -> None:
    """`seed.bundle_world` is what keeps v2 narratives out of v1's corpus (Q92 decides when they
    join). Every v1 bundle predates the field, so absence has to read as v1, and a v2 block has to
    read as v2, whether it is well formed or the string #444 once wrote."""
    from faultline.context.seed import CORPUS_WORLDS, bundle_world

    shapes = {
        "no-manifest": None,
        "v1-no-world-name": {"world": {"compose_digest": "c0ffee"}},
        "v2-block": {"world": {"world_name": "v2", "compose_digest": "c0ffee"}},
        "v2-string": {"world": "v2"},
    }
    for name, manifest in shapes.items():
        (tmp_path / name).mkdir()
        if manifest is not None:
            (tmp_path / name / "manifest.json").write_text(json.dumps(manifest))

    assert [bundle_world(tmp_path / n) for n in shapes] == ["v1", "v1", "v2", "v2"]
    assert CORPUS_WORLDS == ("v1",)
