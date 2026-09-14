"""Q45's check, against fixtures and against the real working tree.

**A drift check that can itself drift is worse than none**, so most of what is asserted here is
that this module computes what the seeder and the freeze compute, rather than something that
resembles them.
"""

from __future__ import annotations

from pathlib import Path

from evalharness import corpusdrift
from evalharness.corpusdrift import compare, documents_of, working_tree_rows

REPO_ROOT = Path(__file__).resolve().parents[1]

SEEDED = [
    ("runbook:class-bad-deploy", "Symptoms", "the image reference moved"),
    ("runbook:class-bad-deploy", "What to check", "the change log"),
    ("scenario:cart-bad-image-tag", "Narrative", "cart stopped answering"),
]


def test_a_corpus_that_matches_the_tree_agrees() -> None:
    drift = compare(SEEDED, list(SEEDED))

    assert drift.agrees
    assert drift.only_seeded == [] and drift.only_working == [] and drift.changed == []
    assert "agrees with the working tree" in drift.render()


def test_a_document_merged_but_never_re_seeded_is_named() -> None:
    """**The case Q45 is about.** A merge reaches the working tree and never reaches Postgres,
    and nothing anywhere raises. The row records that the misreading already happened once, in
    conversation, by the person who wrote it."""
    working = [*SEEDED, ("runbook:world-the-settle-window", "Body", "wait 300s")]

    drift = compare(SEEDED, working)

    assert not drift.agrees
    assert drift.only_working == ["runbook:world-the-settle-window"]
    assert "in the tree, not in the corpus" in drift.render()


def test_a_document_deleted_from_the_tree_but_left_in_the_corpus_is_named() -> None:
    """The other direction, and not hypothetical: Q40 measured `faultline-seed` taking the corpus
    263 -> 261 on first contact, which is this shape resolving itself inside one machine."""
    drift = compare(SEEDED, [r for r in SEEDED if "class-bad-deploy" not in r[0]])

    assert drift.only_seeded == ["runbook:class-bad-deploy"]
    assert "in the corpus, not in the tree" in drift.render()


def test_a_rewrite_under_an_existing_heading_is_the_case_sha256_alone_cannot_see() -> None:
    """**Why `body_sha256` exists at all** (Q36). Edit a runbook's text under a heading that does
    not move and `rows`, `sha256` and `documents` stay byte-identical, while every scored run
    afterwards reads different words. A check built on shape would call this agreement."""
    working = [
        (d, s, "SOMETHING ENTIRELY DIFFERENT" if s == "What to check" else b) for d, s, b in SEEDED
    ]

    drift = compare(SEEDED, working)

    assert not drift.agrees
    assert drift.changed == ["runbook:class-bad-deploy"]
    assert drift.only_seeded == [] and drift.only_working == []
    assert drift.seeded_rows == drift.working_rows, "same shape, different words"


def test_the_digest_is_the_one_the_freeze_records() -> None:
    """**Two implementations of one digest is a drift checker that can drift.** `corpus_state`
    computes `body_sha256` with `freeze.body_digest_of`, and so does this."""
    from evalharness.freeze import body_digest_of

    assert compare(SEEDED, SEEDED).seeded_digest == body_digest_of(SEEDED)


def test_the_digest_does_not_depend_on_the_order_rows_arrive_in() -> None:
    """The SQL orders by `document_id, section, body` and a caller hashing chunks off disk does
    not. Sorting inside the digest is what lets both sides be compared at all."""
    from evalharness.freeze import body_digest_of

    assert body_digest_of(list(reversed(SEEDED))) == body_digest_of(SEEDED)


def test_per_document_digests_localise_the_disagreement() -> None:
    """A single global hash answers *do they disagree* and leaves a person to go and find out
    where. The useful output is which documents moved."""
    docs = documents_of(SEEDED)

    assert set(docs) == {"runbook:class-bad-deploy", "scenario:cart-bad-image-tag"}
    assert docs["runbook:class-bad-deploy"].sections == 2
    assert docs["scenario:cart-bad-image-tag"].sections == 1


# --- against the real tree ----------------------------------------------------------------------


def test_the_working_tree_reads_through_the_seeder_s_own_chunkers() -> None:
    """`bundle_chunks` and `chunk_runbook` produce the rows the seeder would have written. A
    second chunker here would make the check disagree with the seeder about what the corpus should
    contain, which is the one thing a drift check may not do."""
    rows = working_tree_rows()
    documents = {d for d, _, _ in rows}

    assert rows, "the repository has a corpus"
    assert any(d.startswith("runbook:") for d in documents), "runbooks are one entry point"
    assert all(d.startswith(("runbook:", "scenario:")) for d in documents)
    assert compare(rows, rows).agrees


def test_the_check_enumerates_dev_bundles_the_way_the_seeder_does() -> None:
    """`seed.dev_bundles` is extracted rather than restated, so *skip a bundle with no narrative,
    skip one marked INVALID* has one implementation."""
    from faultline.context.seed import dev_bundles

    root = corpusdrift.DEV_ROOT
    if not root.is_dir():
        return
    seeded_names = {b.name for b, skip in dev_bundles(root) if skip is None}
    documents = {d for d, _, _ in working_tree_rows() if d.startswith("scenario:")}

    assert {d.removeprefix("scenario:") for d in documents} <= seeded_names


def test_the_check_writes_nothing() -> None:
    """Q45's row asks for the fact. A check that repaired what it found would be the sync it
    deliberately is not, and would hide the disagreement it exists to report."""
    import ast

    source = (REPO_ROOT / "src" / "evalharness" / "corpusdrift.py").read_text()
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert "faultline.context.seed" in imported
    assert not any(name in source for name in ("store.add", "INSERT", "UPDATE ", "DELETE "))
    assert "seed(" not in source.replace("faultline-seed", "").replace("dev_bundles", "")
