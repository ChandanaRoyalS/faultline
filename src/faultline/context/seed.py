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

from faultline.context.corpus import Chunk, chunk_narrative, parse_narrative
from faultline.context.store import PastIncidentStore

DEV_SPLIT = "dev"
HOLDOUT = "holdout"
NARRATIVE = "incident.md"
MANIFEST = "manifest.json"
INVALID = "INVALID.md"


class QuarantineError(RuntimeError):
    """A seeding input that would breach the split quarantine. Never caught, never softened."""


@dataclass
class SeedResult:
    documents: int = 0
    chunks: int = 0
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


def seed(store: PastIncidentStore, dev_root: Path) -> SeedResult:
    """Seed every valid dev bundle's narrative. One root, and it is the only argument."""
    root = require_dev_root(dev_root)
    result = SeedResult()

    for bundle in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (bundle / NARRATIVE).is_file():
            result.skipped.append((bundle.name, "no incident.md"))
            continue
        if (bundle / INVALID).is_file():
            result.skipped.append((bundle.name, "bundle is marked INVALID"))
            continue
        chunks = bundle_chunks(bundle)
        result.chunks += store.add(chunks)
        result.documents += 1
        result.seeded.append(bundle.name)

    return result
