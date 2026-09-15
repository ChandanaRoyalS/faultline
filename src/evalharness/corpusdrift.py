"""Q45: does the seeded corpus still say what the repository says?

**The clause most likely to be read as done.** The documents *are* in git and `faultline-seed`
*does* read them, so "git-synced ingest" reads as satisfied until the question is asked precisely:
**what re-seeds a deployed corpus after a merge?** Nothing does. A merge to `main` reaches the
working tree and never reaches Postgres, and no error anywhere says so.

Q45's row names the cheaper half and the one that comes first: **a sync hides the disagreement, a
check reports it.** This is the check.

## Why it can be trusted to disagree correctly

**It hashes through the seeder's own chunkers.** `bundle_chunks`, `postmortem_rows` and
`chunk_runbook` produce the rows the seeder would have written, and `freeze.body_digest_of` is the
function `corpus_state` uses
for `body_sha256`. Two implementations of one digest is a drift checker that can drift, and a
second copy of *"skip a bundle with no narrative, skip one marked INVALID"* would make the check
disagree with the seeder about what the corpus should contain - the one thing a drift check may
not do. `seed.dev_bundles` is that enumeration, extracted rather than restated.

**It reports per document, not just a verdict.** A single global hash answers *"do they disagree"*
and leaves a person to find out where; the interesting output is the three documents that moved.

**It changes nothing.** No write, no re-seed, no refusal - Q45's row asks for the fact, and a check
that repaired what it found would be the sync it deliberately is not.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_ROOT = REPO_ROOT / "evals" / "scenarios" / "artifacts" / "dev"


@dataclass(frozen=True, slots=True)
class Document:
    """One document's digest, from either side."""

    document_id: str
    sections: int
    digest: str


@dataclass
class Drift:
    """What the seeded corpus and the working tree disagree about."""

    seeded_digest: str = ""
    working_digest: str = ""
    seeded_rows: int = 0
    working_rows: int = 0
    only_seeded: list[str] = field(default_factory=list)
    """Documents in the corpus and not in the tree - a deleted or renamed file that nothing
    pruned. Q40 measured this shape happening inside one machine over minutes."""

    only_working: list[str] = field(default_factory=list)
    """Documents in the tree and not in the corpus - the merge-then-forget case Q45 is about."""

    changed: list[str] = field(default_factory=list)
    """Present on both sides, saying different things. **The case `sha256` alone cannot see**:
    edit a runbook's text under an existing heading and `rows`, `sha256` and `documents` stay
    byte-identical while every scored run afterwards reads different words."""

    @property
    def agrees(self) -> bool:
        return self.seeded_digest == self.working_digest

    def as_dict(self) -> dict[str, Any]:
        return {
            "agrees": self.agrees,
            "seeded": {"rows": self.seeded_rows, "body_sha256": self.seeded_digest},
            "working_tree": {"rows": self.working_rows, "body_sha256": self.working_digest},
            "only_seeded": self.only_seeded,
            "only_working": self.only_working,
            "changed": self.changed,
        }

    def render(self) -> str:
        if self.agrees:
            return (
                f"corpus agrees with the working tree: {self.seeded_rows} chunk(s), "
                f"body_sha256 {self.seeded_digest[:12]}"
            )
        lines = [
            "CORPUS AND WORKING TREE DISAGREE",
            f"  seeded       : {self.seeded_rows:4} chunk(s)  "
            f"body_sha256 {self.seeded_digest[:12]}",
            f"  working tree : {self.working_rows:4} chunk(s)  "
            f"body_sha256 {self.working_digest[:12]}",
        ]
        for label, ids in (
            ("in the corpus, not in the tree", self.only_seeded),
            ("in the tree, not in the corpus", self.only_working),
            ("on both sides, saying different things", self.changed),
        ):
            if ids:
                lines.append(f"\n  {label}:")
                lines += [f"    {i}" for i in ids]
        lines.append(
            "\nNothing was changed. `faultline-seed` is what reconciles this; "
            "this command only says that it needs to be run."
        )
        return "\n".join(lines)


def documents_of(rows: list[tuple[str, str, str]]) -> dict[str, Document]:
    """Per-document digests from `(document_id, section, body)` triples, either side."""
    from evalharness.freeze import body_digest_of

    grouped: dict[str, list[tuple[str, str, str]]] = {}
    for document_id, section, body in rows:
        grouped.setdefault(document_id, []).append((document_id, section, body))
    return {
        document_id: Document(document_id, len(triples), body_digest_of(triples))
        for document_id, triples in grouped.items()
    }


def working_tree_rows(dev_root: Path | None = None) -> list[tuple[str, str, str]]:
    """What `faultline-seed` would write, computed without a store.

    **Both of the seeder's entry points, because it has two and they are separately guarded**
    (Q15): dev bundles through `seed`, authored runbooks through `seed_runbooks`. A check that
    read one root would report the other as missing on every run.
    """
    from faultline.context.corpus import chunk_runbook
    from faultline.context.runbooks import load_runbooks, runbooks_dir
    from faultline.context.seed import bundle_chunks, dev_bundles, postmortem_rows

    root = dev_root or DEV_ROOT
    rows: list[tuple[str, str, str]] = []
    if root.is_dir():
        for bundle, skip in dev_bundles(root):
            if skip is None:
                rows += [(c.document_id, c.section, c.text) for c in bundle_chunks(bundle)]
                # **Postmortems too, and without asking whether they were accepted** (T6.5).
                # This check reads no database, so it cannot ask - and it does not need to. Its
                # question is *does the store hold what the tree says*, and a postmortem in the
                # tree and not in the store is a real disagreement whether nobody seeded or
                # nobody accepted. `faultline-seed` is what tells those apart, by reconciling
                # or by refusing with the reason. `postmortem_rows` is the seeder's own parse
                # and chunking, extracted rather than restated.
                rows += [(c.document_id, c.section, c.text) for c in postmortem_rows(bundle)]
    directory = runbooks_dir()
    for runbook in load_runbooks():
        chunks = chunk_runbook(runbook, directory / f"{runbook.id}.md")
        rows += [(c.document_id, c.section, c.text) for c in chunks]
    return rows


def compare(seeded: list[tuple[str, str, str]], working: list[tuple[str, str, str]]) -> Drift:
    """The two sides, and what they disagree about."""
    from evalharness.freeze import body_digest_of

    left, right = documents_of(seeded), documents_of(working)
    return Drift(
        seeded_digest=body_digest_of(seeded),
        working_digest=body_digest_of(working),
        seeded_rows=len(seeded),
        working_rows=len(working),
        only_seeded=sorted(set(left) - set(right)),
        only_working=sorted(set(right) - set(left)),
        changed=sorted(d for d in set(left) & set(right) if left[d].digest != right[d].digest),
    )


def seeded_rows(dsn: str) -> list[tuple[str, str, str]]:  # pragma: no cover - the database path
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT document_id, section, body FROM incident_chunks "
            "ORDER BY document_id, section, body"
        )
        return [(str(d), str(s), str(b)) for d, s, b in cur.fetchall()]


def run_cli(argv: list[str] | None = None) -> int:  # pragma: no cover - the live path
    import argparse

    parser = argparse.ArgumentParser(
        prog="faultline-corpus-drift",
        description=(
            "Q45: does the seeded corpus still say what the repository says? Reads both and "
            "reports; changes nothing. Exit 0 when they agree, 1 when they do not."
        ),
    )
    parser.add_argument("--postgres-dsn", default=None)
    parser.add_argument("--dev-root", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    from faultline.context.settings import ContextSettings

    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    drift = compare(seeded_rows(dsn), working_tree_rows(args.dev_root))
    print(drift.render())
    if args.out:
        args.out.write_text(json.dumps(drift.as_dict(), indent=2) + "\n")
        print(f"\n-> {args.out}")
    # **Exit 1 on disagreement, and that is a report rather than a refusal.** A person running
    # this wants a usable exit code in a shell; nothing downstream treats it as a gate, because
    # Q45's row asks for the fact and not for an enforcement nobody has argued for.
    return 0 if drift.agrees else 1
