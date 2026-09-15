"""What a seeded past incident is: a narrative, split into retrievable chunks (T2.4b).

`incident.md` is the only file seeded (ADR-0008, ARTIFACTS.md). It has a fixed shape,
measured rather than assumed - all nine committed narratives carry YAML front matter, one
`# Title`, and exactly the same five `## ` sections:

    What was observed | What was checked | Root cause | Resolution | Detection notes

That consistency is what makes a section a stable unit rather than one author's habit, and
it is why the chunk is a section (ADR-0018).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TITLE = re.compile(r"^#\s+(.*)$", re.MULTILINE)
SECTION = re.compile(r"^##\s+(.*)$", re.MULTILINE)

ANSWER_SECTION = "Root cause"
"""The section that states the answer outright.

Named because it is the one a leave-one-out failure hands over verbatim: retrieving your own
narrative's root cause is not diagnosis, it is a lookup (ADR-0008, axis 2). It is legitimate
content for *every other* scenario, which is why the defence is an exclusion at query time
and not a redaction at seed time.
"""


class NarrativeError(ValueError):
    """A narrative that cannot be parsed, or that disagrees with where it was found."""


@dataclass(frozen=True, slots=True)
class Chunk:
    """One retrievable unit, carrying the provenance that makes exclusion a WHERE clause."""

    document_id: str
    """`scenario:<id>` - the same value as `origin`. One narrative, one document."""

    section: str
    section_index: int
    text: str

    origin: str
    """`scenario:<id>` or `authored`. **The exclusion key** (ADR-0008, axis 2)."""

    split: str
    scenario_id: str
    fault_class: str
    scenario_fingerprint: str
    """From the bundle manifest. Ties a chunk to the exact label it was recorded against, so
    a corpus entry cannot outlive a scenario whose scored fields changed."""

    recorded_from: str
    """The narrative's front matter, which copies the manifest's `t_inject`. Ties the chunk
    to one recording - a re-record moves it, and a stale chunk is then detectable."""

    title: str
    source_path: str


@dataclass(frozen=True, slots=True)
class Narrative:
    """One parsed `incident.md`, before chunking."""

    front_matter: dict[str, Any]
    title: str
    sections: list[tuple[str, str]] = field(default_factory=list)

    @property
    def origin(self) -> str:
        return str(self.front_matter.get("origin", ""))

    @property
    def split(self) -> str:
        return str(self.front_matter.get("split", ""))


def parse_narrative(path: Path) -> Narrative:
    """Front matter, title, and sections. Raises rather than guessing at a broken file."""
    text = path.read_text()
    match = FRONT_MATTER.match(text)
    if match is None:
        raise NarrativeError(f"{path}: no YAML front matter, so it carries no provenance")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise NarrativeError(f"{path}: front matter is not a mapping")

    body = text[match.end() :]
    title_match = TITLE.search(body)
    if title_match is None:
        raise NarrativeError(f"{path}: no `# Title` heading")

    headings = list(SECTION.finditer(body))
    if not headings:
        raise NarrativeError(f"{path}: no `## ` sections, so there is nothing to chunk")

    sections: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        sections.append((heading.group(1).strip(), body[heading.end() : end].strip()))

    return Narrative(front_matter=loaded, title=title_match.group(1).strip(), sections=sections)


def chunk_narrative(
    narrative: Narrative, *, scenario_fingerprint: str, fault_class: str, source_path: Path
) -> list[Chunk]:
    """One chunk per section. The document is reconstructable through `document_id`.

    ADR-0018: the section is the unit because that is what a live incident resembles - an
    agent arrives holding symptoms, and "What was observed" is the symptom surface. Returning
    a whole narrative as one chunk buries that under four sections of other content; storing
    both would put the same prose in the corpus twice and make one document win a query with
    two hits.
    """
    origin = narrative.origin
    return [
        Chunk(
            document_id=origin,
            section=section,
            section_index=index,
            text=text,
            origin=origin,
            split=narrative.split,
            scenario_id=origin.removeprefix("scenario:"),
            fault_class=fault_class,
            scenario_fingerprint=scenario_fingerprint,
            recorded_from=str(narrative.front_matter.get("recorded_from", "")),
            title=narrative.title,
            source_path=str(source_path),
        )
        for index, (section, text) in enumerate(narrative.sections)
    ]


AUTHORED = "authored"
"""The origin every runbook carries. **The one value T4.1b's filter never excludes** (ADR-0008):
runbooks are institutional knowledge a responder would legitimately have, so excluding them
while scoring a scenario would measure an agent working without its own documentation."""


def body_digest_of(rows: list[tuple[str, str, str]]) -> str:
    """A digest over `(document_id, section, body)` triples. **The content, not the shape.**

    **Extracted so there is one of it** (Q45). The corpus-drift check hashes the working tree and
    compares against `corpus_state`'s `body_sha256`; two implementations of the same digest is a
    drift checker that can drift, which is the joke this repository does not need to make.

    The ordering is the SQL's - `document_id, section, body` - so a caller hashing chunks off
    disk sorts the same way or gets a different answer for the same corpus.

    **It lives here rather than in `evalharness.freeze`, where it was written.** T6.5's
    acceptance ledger pins a postmortem by this digest, and production may not import the
    harness - so the function moved down and `freeze` re-exports it. Moving it was the only way
    to keep the "one of it" property that its own docstring is about.
    """
    joined = "\n\x00\n".join(f"{d}|{s}|{b}" for d, s, b in sorted(rows))
    return hashlib.sha256(joined.encode()).hexdigest()


def shape_digest_of(rows: list[tuple[str, str]]) -> str:
    """A digest over `(document_id, section)` pairs. **The shape, not the content.**

    `body_digest_of`'s twin, extracted for the same reason and one defect later. The shape digest
    was computed inline in `freeze.corpus_state` from a `SELECT ... ORDER BY document_id,
    section`, so **the row order came from the database's collation** and the digest with it.

    Measured 2026-09-15 on `en_US.utf8`, libc provider: Postgres orders *"Acting on it"* before
    *"A reading of its error ratio was withdrawn"*, because en_US ignores the space at primary
    weight; Python compares code points and orders them the other way. The same 311 chunks
    therefore hashed `ee7c7bb277cf` in the database and `844fe623366c` off the working tree.

    That makes the digest a property of **where it was computed** rather than of the corpus - so
    two hosts disagree about one corpus, and one host disagrees with itself across a libc or ICU
    upgrade, which is the same class of change that silently invalidates text indexes. `sorted`
    here is Python's, over the pairs, which is why `body_digest_of` never had the problem.

    **Every archived `corpus_sha256` was computed the other way** and none of them can be
    recovered. What this buys is that every future one names a corpus rather than a locale.
    """
    joined = "\n".join(f"{d}|{s}" for d, s in sorted(rows))
    return hashlib.sha256(joined.encode()).hexdigest()


def chunk_runbook(runbook: Any, source_path: Path) -> list[Chunk]:
    """One authored runbook, as retrievable chunks (Q15, T2.4b's third deliverable).

    **Sectioned the same way a narrative is**, for ADR-0018's reason: the section is what a
    live incident resembles. A whole runbook returned as one chunk would bury the paragraph
    that matches under four that do not.

    The scenario-shaped fields are empty and that is the record, not a gap. A runbook has no
    `scenario_id` because it belongs to no scenario, no `scenario_fingerprint` because it was
    not recorded against a label, and no `recorded_from` because it was authored rather than
    captured. Filling them with plausible values would make an authored document look like a
    rehearsal in every query that returns it.
    """
    headings = list(SECTION.finditer(runbook.body))
    sections: list[tuple[str, str]] = []
    if headings:
        for index, heading in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(runbook.body)
            sections.append((heading.group(1).strip(), runbook.body[heading.end() : end].strip()))
        preamble = runbook.body[: headings[0].start()].strip()
        if preamble:
            sections.insert(0, ("Summary", preamble))
    else:
        sections = [("Summary", runbook.body.strip())]

    document_id = f"runbook:{runbook.id}"
    return [
        Chunk(
            document_id=document_id,
            section=section,
            section_index=index,
            text=text,
            origin=AUTHORED,
            split="",
            scenario_id="",
            fault_class="",
            scenario_fingerprint="",
            recorded_from="",
            title=runbook.title,
            source_path=str(source_path),
        )
        for index, (section, text) in enumerate(sections)
        if text
    ]
