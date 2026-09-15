"""Seeding the past-incident store from the dev split, and refusing anything else (T2.4b).

ADR-0008 makes this a **path** rule rather than a remembered one:

> T2.4b seeds the knowledge stores from `evals/scenarios/artifacts/dev/` alone. Not from
> `evals/scenarios/artifacts/`, not from the repo, and specifically never from `docs/`.
> […] The path-based quarantine only works if exactly one path is read.

So the seeder takes **one root**, and it is the dev directory. There is no `--split` flag, no
filter applied over both trees, and no "seed everything then exclude" - each of those is a
one-character edit away from seeding the holdout, and the ADR names widening the input as
exactly how this defect gets reintroduced.

Three guards, in order of how much they are trusted:

1. **The root may not contain a `holdout` component.** Structural, and the only one that
   cannot be talked out of.
2. **Every narrative's front-matter `split` must be `dev`.** The T1.6 guards already make a
   mismatch near-impossible; the seeder refuses rather than trusts, because the cost of being
   wrong here is a holdout answer key in the retrieval corpus and nothing downstream would
   show it.
3. **A bundle carrying `INVALID.md` is skipped.** Its narrative describes a recording marked
   unusable - `currency-cpu-throttle` and `flag-service-crashloop` are both blocked scenarios
   whose faults produced nothing observable. Seeding them would put two incidents in the
   corpus that never happened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from faultline.context.acceptance import (
    AcceptanceStore,
    InMemoryAcceptanceStore,
    digest_of,
)
from faultline.context.corpus import (
    AUTHORED,
    Chunk,
    chunk_narrative,
    chunk_runbook,
    parse_narrative,
)
from faultline.context.postmortem import chunk_postmortem, parse_postmortem
from faultline.context.runbooks import Runbook, load_runbooks, runbooks_dir
from faultline.context.store import PastIncidentStore, chunk_key

DEV_SPLIT = "dev"
HOLDOUT = "holdout"
NARRATIVE = "incident.md"
MANIFEST = "manifest.json"
INVALID = "INVALID.md"
POSTMORTEM = "postmortem.md"
"""**Beside the narrative, in the same bundle, under the same one root.**

ADR-0008's quarantine is a *path* rule - `require_dev_root` refuses anything that is not
`artifacts/dev/` - and putting postmortems anywhere else would mean a second root and a second
guard. The whole argument in this module's docstring is that widening the input is how the
holdout leaks, so the new document class takes the existing input rather than adding one."""


class QuarantineError(RuntimeError):
    """A seeding input that would breach the split quarantine. Never caught, never softened."""


@dataclass
class SeedResult:
    documents: int = 0
    chunks: int = 0
    pruned: int = 0
    """Orphan chunks removed - sections a document used to have and no longer does.

    Reported rather than silent, because a re-seed that quietly deletes rows and a re-seed that
    quietly leaves them are equally hard to tell apart from the outside (Q40)."""

    seeded: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    """(scenario id, why). Skipping is reported, never silent."""


def require_dev_root(root: Path) -> Path:
    """Refuse any root that is not unambiguously the dev tree.

    Checked on the resolved path, so `artifacts/dev/../holdout` cannot walk out of it.
    """
    resolved = root.resolve()
    parts = [part.lower() for part in resolved.parts]
    if HOLDOUT in parts:
        raise QuarantineError(
            f"{resolved} contains a '{HOLDOUT}' path component. The seeding input is "
            "evals/scenarios/artifacts/dev/ and nothing else (ADR-0008): a holdout "
            "narrative in the retrieval corpus is the answer key to a scenario nothing "
            "downstream would notice had leaked."
        )
    if resolved.name != DEV_SPLIT:
        raise QuarantineError(
            f"{resolved} is not a dev split root - its last component is {resolved.name!r}, "
            f"not {DEV_SPLIT!r}. Seeding reads one directory, deliberately; widening the "
            "input 'just to pick up the runbooks' is how this defect returns (ADR-0008)."
        )
    return resolved


def bundle_chunks(bundle: Path) -> list[Chunk]:
    """Parse one bundle's narrative into chunks, with provenance from its manifest."""
    narrative = parse_narrative(bundle / NARRATIVE)
    if narrative.split != DEV_SPLIT:
        raise QuarantineError(
            f"{bundle / NARRATIVE} declares split={narrative.split!r} but was found under a "
            f"{DEV_SPLIT} root. The path and the front matter disagree about which side of "
            "the quarantine this is, and the seeder refuses rather than picking one."
        )
    manifest = json.loads((bundle / MANIFEST).read_text())
    if manifest.get("origin") != narrative.origin:
        raise QuarantineError(
            f"{bundle.name}: manifest origin {manifest.get('origin')!r} and narrative origin "
            f"{narrative.origin!r} disagree. `origin` is the exclusion key (ADR-0008, axis "
            "2), so a chunk carrying the wrong one is excluded from the wrong scenario."
        )
    return chunk_narrative(
        narrative,
        scenario_fingerprint=str(manifest.get("scenario_fingerprint", "")),
        fault_class=str(manifest.get("fault_class", "")),
        source_path=bundle / NARRATIVE,
    )


def _reconcile(store: PastIncidentStore, chunks: list[Chunk]) -> int:
    """Drop rows this document used to produce and no longer does.

    **Add first, then prune.** The other order would empty the document for the duration of the
    write, and a retrieval running concurrently would see a corpus missing a document rather
    than a corpus mid-update. Seeding is not transactional across documents, so the window is
    real even if it is short.

    A document with no chunks at all is not reconciled here: an empty `chunks` means the source
    produced nothing, which is a parsing failure rather than an instruction to delete a document,
    and deleting on it would turn one bad parse into a silently missing document.
    """
    if not chunks:
        return 0
    document_id = chunks[0].document_id
    return store.prune_document(document_id, {chunk_key(chunk) for chunk in chunks})


def dev_bundles(root: Path) -> list[tuple[Path, str | None]]:
    """Every directory under `root`, with why it is skipped or `None` if it seeds.

    **Extracted so the corpus-drift check enumerates what the seeder enumerates** (Q45). A second
    copy of *"skip a bundle with no narrative, skip one marked INVALID"* would make the check
    disagree with the seeder about what the corpus should contain, which is the one thing a drift
    check may not do.
    """
    out: list[tuple[Path, str | None]] = []
    for bundle in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (bundle / NARRATIVE).is_file():
            out.append((bundle, "no incident.md"))
        elif (bundle / INVALID).is_file():
            out.append((bundle, "bundle is marked INVALID"))
        else:
            out.append((bundle, None))
    return out


class UnacceptedError(RuntimeError):
    """A postmortem on disk that no ledger row admits. **Never caught, never softened.**

    Refused rather than skipped, and the asymmetry with `INVALID.md` is the point. A bundle
    marked invalid is a decision someone recorded; an unaccepted postmortem is a document
    somebody wrote and nobody approved, sitting in the path the seeder reads. Skipping it with a
    line in `result.skipped` would make *"never auto-published"* depend on an operator reading
    seeder output, and `api/auth.py` already has this repository's answer to that: **a default
    that is safe only if someone reads a warning is not a default.**
    """


def postmortem_rows(bundle: Path, *, scenario_ids: set[str] | None = None) -> list[Chunk]:
    """One bundle's postmortem as chunks, **with every guard except the ledger's.**

    Extracted so the corpus-drift check enumerates what the seeder enumerates (Q45). Drift reads
    no database, so it cannot ask whether a document was accepted - and it does not need to: its
    question is *does the store hold what the tree says*, and a postmortem in the tree and not in
    the store is a real disagreement whether the reason is that nobody seeded or that nobody
    accepted. `faultline-seed` is what tells the two apart, by reconciling or by refusing.

    A second copy of *parse, check the split, chunk from the manifest* would be the thing a drift
    check may not have: its own opinion of what the corpus should contain.
    """
    path = bundle / POSTMORTEM
    if not path.is_file():
        return []
    postmortem = parse_postmortem(path, scenario_ids=scenario_ids)
    if postmortem.split != DEV_SPLIT:
        raise QuarantineError(
            f"{path} declares split={postmortem.split!r} but was found under a {DEV_SPLIT} "
            "root. The path and the front matter disagree about which side of the quarantine "
            "this is, and the seeder refuses rather than picking one."
        )
    manifest = json.loads((bundle / MANIFEST).read_text())
    return chunk_postmortem(
        postmortem,
        scenario_fingerprint=str(manifest.get("scenario_fingerprint", "")),
        fault_class=str(manifest.get("fault_class", "")),
        source_path=path,
    )


def postmortem_chunks(
    bundle: Path,
    acceptances: AcceptanceStore,
    *,
    scenario_ids: set[str] | None = None,
) -> list[Chunk]:
    """One bundle's postmortem, if it has one **and the ledger admits these exact words**.

    The digest is over title and sections, so editing a paragraph after acceptance leaves no row
    for what is now on disk and this refuses. That is the whole gate: §3's *"draft for human
    edit, never auto-published"* is enforced here or nowhere, because this is the only code path
    between a file and the retrieval corpus.
    """
    rows = postmortem_rows(bundle, scenario_ids=scenario_ids)
    if not rows:
        return []
    path = bundle / POSTMORTEM
    postmortem = parse_postmortem(path, scenario_ids=scenario_ids)
    digest = digest_of(postmortem)
    if acceptances.accepted(postmortem.scenario_id, digest) is None:
        raise UnacceptedError(
            f"{path} has no acceptance for its current text (digest {digest[:12]}). A postmortem "
            "joins the corpus when a person accepts it through the approval surface and not "
            "before; if it was accepted and then edited, the edit needs accepting too - the row "
            "pins the words that were read (PREREGISTRATION-T6.5.md §3)."
        )
    return rows


def seed(
    store: PastIncidentStore,
    dev_root: Path,
    acceptances: AcceptanceStore | None = None,
) -> SeedResult:
    """Seed every valid dev bundle's narrative, and any postmortem a person has accepted.

    **`acceptances` defaults to a store with no rows**, which refuses every postmortem. That is
    the safe default rather than the convenient one: a caller who has not wired the ledger is a
    caller who cannot check the gate, and the alternative default - *no ledger means no check* -
    would let a `faultline-seed` invocation publish an unaccepted document by omitting an
    argument.
    """
    root = require_dev_root(dev_root)
    ledger = acceptances if acceptances is not None else InMemoryAcceptanceStore()
    result = SeedResult()

    for bundle, skip in dev_bundles(root):
        if skip is not None:
            result.skipped.append((bundle.name, skip))
            continue
        chunks = bundle_chunks(bundle)
        result.chunks += store.add(chunks)
        result.pruned += _reconcile(store, chunks)
        result.documents += 1
        result.seeded.append(bundle.name)

        accepted = postmortem_chunks(bundle, ledger)
        if accepted:
            result.chunks += store.add(accepted)
            result.pruned += _reconcile(store, accepted)
            result.documents += 1
            result.seeded.append(f"{bundle.name} (postmortem)")

    return result


def seed_runbooks(
    store: PastIncidentStore, runbooks: tuple[Runbook, ...] | None = None
) -> SeedResult:
    """Seed the authored runbooks. **A second entry point, never a wider first one** (Q15).

    `require_dev_root`'s own refusal message names this exact temptation - *"widening the input
    'just to pick up the runbooks' is how this defect returns"* - so `seed` keeps its one root
    and this function has its own. The two inputs are separately guarded and separately
    refusable, which is the property ADR-0008 asks for; a single seeder taking a list of roots
    would be one argument away from taking the holdout.

    **What guards this input.** The runbooks live in `knowledge/runbooks/`, are `origin:
    authored` by their own front matter (asserted in `tests/test_runbooks.py`), and may not name
    any catalog scenario - dev or holdout - because ADR-0036 makes them the one document class
    T4.1b's filter never excludes. A runbook that named a scenario would be an answer key that
    exclusion cannot reach, which is why that rule is a test rather than a convention.
    """
    catalog = load_runbooks() if runbooks is None else runbooks
    result = SeedResult()
    directory = runbooks_dir()
    for runbook in catalog:
        if runbook.origin != AUTHORED:
            # Refused rather than skipped: an `origin` other than `authored` on a file in this
            # directory means the exclusion key and the directory disagree, and the exclusion
            # key is what T4.1b filters on.
            raise QuarantineError(
                f"runbook {runbook.id!r} declares origin={runbook.origin!r}, not "
                f"{AUTHORED!r}. `origin` is the exclusion key (ADR-0008, axis 2), and a "
                "runbook is the one document class that is never excluded."
            )
        chunks = chunk_runbook(runbook, directory / f"{runbook.id}.md")
        result.chunks += store.add(chunks)
        result.pruned += _reconcile(store, chunks)
        result.documents += 1
        result.seeded.append(runbook.id)
    return result
