"""The postmortem document class, and the guard that is this benchmark's rather than the world's.

**T6.5's first piece: the artefact, before anything writes one.** The drafter is a separate
change and so is the accept gate; what is here is the shape a postmortem has, the rule about
what it may say, and the chunking that puts it in the corpus without colliding with the
narrative of the same incident.

## What a postmortem is that a narrative is not

`evals/runs/PREREGISTRATION-T6.5.md` §1 decided this and then had to narrow it, and the
narrowing is the load-bearing part. A postmortem is written **after the incident resolves**, and
the obvious reading - that it carries the outcome - is unavailable: **no scored run executes a
remediation.** `recovery` on 266 manifests is the world's state after the injector reverts, not
*did the fix work*. A postmortem saying "the system recovered" would be false and would leak the
harness into the corpus in one sentence.

So it carries what is recorded for every run and what a narrative provably cannot, because the
narrative is written mid-investigation:

- the verdict and root cause **as finally stated**, after the investigation closed;
- what **ruled the alternatives out** - §2's mechanism, and the section that does the transfer;
- what the **proposal rested on**, in mechanism terms;
- the proposal's **fate at the validator boundary**;
- what stayed **unmeasured**, which every verdict already records as `OPEN` lines.

**It never claims a remediation worked.** `SECTIONS` is closed for exactly that reason: an open
section list is one heading away from an outcome nobody registered.

## §1 and §2 are in tension, and §2 wins by construction

§1's third bullet names *"the proposal - action, target, preconditions, blast radius"*. §2 then
forbids naming the remediation action at all. Both were written; the narrower clause governs,
because §2 carries the argument and §1 does not:

`baselines.CLASS_TO_REMEDIATION` maps fault class to remediation **one-to-one across all
eighteen scenarios** - measured, and what Q53's prediction 4 was written against. A same-class
postmortem naming `rollback_image` hands the reader `bad_deploy` through a lookup table, and a
transfer measurement over it would be measuring an agent reading a mapping.

So the proposal section survives and its **vocabulary** does not: preconditions, blast radius
and falsifier stated as mechanism, with every action id and every performable remediation class
banned by `POSTMORTEM_VOCABULARY`. §1 is read as constrained by §2 here rather than quietly
dropped, and `docs/QUEUE.md` is where a disagreement with that reading belongs.

**This is a property of this benchmark and not of production**, and it costs the artefact real
realism - a postmortem that cannot say what fixed it is a strange postmortem. §7 of the
registration keeps it as a limitation instead of burying it as a guard.

## The one that hurts, named rather than discovered

`restart` is banned, and `flag-service-crashloop`'s entire observable **is** restart looping. An
honest mechanism description of every crashloop incident has to route around the word.

It is banned anyway, because `dependency_latency` maps to `restart` and the ban is the mapping's
ban. The registration anticipated this and wrote the paraphrase itself, in §2's own examples:
*"repeated boot banners with no request handling"*. That is the sentence a responder would write
and it names no remediation, so the guard is survivable - but it is survivable by paraphrase, and
that is the cost §7 records.

`scale` is **not** banned, and the asymmetry is principled rather than convenient: `scale_service`
is `unperformable` (ADR-0029 - Compose refuses to scale a service declaring `container_name`, and
25 of this world's services declare one), so no scenario maps to it and the word carries no class.
Banning ordinary English that leaks nothing is how `fault` cost run 3 its whole narrative.

## Where a postmortem sits in the corpus

`document_id = postmortem:<scenario_id>` and `origin = scenario:<scenario_id>`, which is the
only pairing that works:

- **`origin` is the exclusion key** (ADR-0008, axis 2), so T4.1b's self-exclusion covers the
  postmortem for free, and §4's WITHOUT arm - which excludes every dev scenario in the class -
  reaches it through the same column with no second mechanism.
- **`document_id` is what `_reconcile` prunes against.** Reusing `scenario:<id>` would make the
  seeder's narrative pass and postmortem pass each delete the other's rows, quietly, on every
  seed.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from faultline.context.allowlist import ActionStatus, load_allowlist
from faultline.context.corpus import FRONT_MATTER, SECTION, TITLE, Chunk
from faultline.tools.changes import HARNESS_VOCABULARY, matched_words

DOCUMENT_PREFIX = "postmortem:"
ORIGIN_PREFIX = "scenario:"

SECTIONS: tuple[str, ...] = (
    "What the investigation concluded",
    "What ruled the alternatives out",
    "What the proposal rested on",
    "What happened at the approval boundary",
    "What was never measured",
)
"""**Closed, and in this order.** Exactly these, no more and no fewer.

Two reasons it is a tuple and not a floor. A postmortem missing *"What was never measured"* is
a document that states conclusions and hides their limits, which is the shape this repo spends
its registrations avoiding. And an *extra* section is the route by which a drafter adds *"Did
the fix work"* - which §1 forbids because the answer does not exist in any scored run.

**There is deliberately no "What was observed".** That is the narrative's first section and it
is already in the corpus for every dev scenario with a bundle. Repeating it would make the
postmortem partly a copy, double one incident's symptom prose in every query that returns both,
and reduce T6.5 to the scheduling change the design note's §4.1 says would not be worth doing.
A postmortem starts where the narrative stops.
"""


class PostmortemError(ValueError):
    """A postmortem that cannot be parsed, or that disagrees with where it was found."""


class PostmortemLeakError(PostmortemError):
    """Banned vocabulary in a postmortem. **Fails the parse, so it can never be seeded.**"""


@cache
def remediation_vocabulary() -> frozenset[str]:
    """Every allowlist action id, and every **performable** remediation class.

    **Read from the catalog rather than listed here**, so an allowlist entry added at T6.2 is
    guarded the day it lands instead of the day someone remembers this module. The catalog is
    read-only by construction (ADR-0032), which is what makes deriving a guard from it safe -
    and it is reached through `load_allowlist` rather than by path, because
    `tests/test_allowlist.py` lets exactly one module name the file and caught this docstring
    doing it.

    Ids for every entry, including `unperformable` ones: naming an action the world cannot
    perform is still naming a remediation, and `scale_service` is not a word anyone writes by
    accident. Classes for performable entries only - see the module docstring on `scale`.

    Three spellings each, the way `tests/test_runbooks.py` matches scenario ids under ADR-0036:
    `rollback_image`, `rollback-image`, `rollback image`. An underscored id is the one a model
    copies out of a proposal record; the other two are what it writes when it is paraphrasing.
    """
    catalog = load_allowlist()
    terms: set[str] = set()
    for action in catalog.actions:
        terms.add(action.id)
        if action.status is ActionStatus.AVAILABLE:
            terms.add(action.remediation_class)
    spellings = {
        spelling
        for term in terms
        for spelling in (term, term.replace("_", "-"), term.replace("_", " "))
    }
    return frozenset(spellings)


def postmortem_vocabulary() -> frozenset[str]:
    """`HARNESS_VOCABULARY`, and this task's addition.

    The existing rules apply unchanged - injector words, the four `fault_class` values - because
    a postmortem joins the same corpus a narrative does and is retrieved by the same agents.
    """
    return HARNESS_VOCABULARY | remediation_vocabulary()


def leaked_words(text: str) -> list[str]:
    """Banned vocabulary in a postmortem, on word boundaries.

    Same matcher as the narrative guard's (`changes.matched_words`), wider vocabulary. The
    boundary semantics are the shared part precisely because a leak guard that disagrees with
    itself about where a word ends is worse than one guard.
    """
    return matched_words(text, postmortem_vocabulary())


def named_scenarios(text: str, scenario_ids: set[str]) -> list[str]:
    """Catalog scenario ids named in `text`, **in any spelling** (ADR-0036).

    A postmortem's own scenario is in `origin` and in `document_id`, where it belongs - it is
    how the exclusion finds it. In the *prose* it is the answer key, exactly as it is in a
    runbook, and `test_runbooks.py` already records that an id-matching test is the weak half
    of this rule. The strong half is a person reading, which is what the accept gate is for.
    """
    lowered = text.lower()
    named: set[str] = set()
    for scenario in scenario_ids:
        for spelling in (scenario, scenario.replace("-", "_"), scenario.replace("-", " ")):
            if spelling.lower() in lowered:
                named.add(scenario)
    return sorted(named)


class Postmortem(BaseModel):
    """One parsed postmortem. **Parsing says nothing about whether it may be seeded.**

    It carried `accepted_by` and `accepted_at` for one commit, and T6.5's second piece removed
    them. The docstring then said what was wrong with them: *a name in front matter is a string
    anyone can type*. Acceptance now lives in `context/acceptance.py` - an append-only row
    naming the authenticated caller and pinning the prose by digest - and a field beside it
    would be a second answer to one question, editable by whoever edits the file.

    So there is nothing here to consult about acceptance, deliberately. The seeder asks the
    ledger, which is the only thing that can answer.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    """The incident's scenario. Present as data, banned from the prose - see `named_scenarios`."""

    origin: str
    """`scenario:<scenario_id>`. **The exclusion key**, shared with the narrative on purpose."""

    split: str
    incident_id: str
    """The incident record this was drafted from. Not a `Chunk` field: `recorded_from` already
    means *which recording*, and overloading it would make one column answer two questions."""

    recorded_from: str = ""
    """Copied from the bundle manifest, as a narrative's is - so a re-record moves it and a
    stale postmortem is detectable by the same rule."""

    title: str
    sections: list[tuple[str, str]]

    @property
    def document_id(self) -> str:
        return f"{DOCUMENT_PREFIX}{self.scenario_id}"


def parse_postmortem(path: Path, *, scenario_ids: set[str] | None = None) -> Postmortem:
    """One postmortem file. `parse_postmortem_text` with the path as the name in every error."""
    return parse_postmortem_text(path.read_text(), source=str(path), scenario_ids=scenario_ids)


def parse_postmortem_text(
    text: str, *, source: str = "<submitted>", scenario_ids: set[str] | None = None
) -> Postmortem:
    """Front matter, title, sections - then every guard, before the object exists.

    **Guarded at parse time rather than at seed time**, which is one layer earlier than the
    narrative's guard runs and deliberately so. The narrative's leak check lives in `render`
    because the scribe composes it; a postmortem also arrives as a hand-edited file and as an
    HTTP body, and a guard that only the writing path runs is a guard an editor walks around.

    **Text rather than a path, so the accept route runs exactly these guards** (T6.5 piece 2).
    A route that re-implemented them would be a second opinion about what may enter the corpus,
    and the two would drift on the first rule that changed.

    `scenario_ids` is injected rather than globbed so this stays a pure function over its input;
    `faultline.context.seed` and `api/postmortems.py` both pass the catalog.
    """
    path = source
    match = FRONT_MATTER.match(text)
    if match is None:
        raise PostmortemError(f"{path}: no YAML front matter, so it carries no provenance")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise PostmortemError(f"{path}: front matter is not a mapping")

    body = text[match.end() :]
    title_match = TITLE.search(body)
    if title_match is None:
        raise PostmortemError(f"{path}: no `# Title` heading")

    headings = list(SECTION.finditer(body))
    sections: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        sections.append((heading.group(1).strip(), body[heading.end() : end].strip()))

    found = tuple(name for name, _ in sections)
    if found != SECTIONS:
        raise PostmortemError(
            f"{path}: sections are {list(found)}, and a postmortem's are exactly {list(SECTIONS)} "
            "in that order. An extra section is how an outcome claim gets in (registration §1); "
            "a missing one is usually `What was never measured`."
        )
    empty = [name for name, text_ in sections if not text_.strip()]
    if empty:
        raise PostmortemError(f"{path}: {empty} are empty. An empty section is not a short one.")

    scenario_id = str(loaded.get("scenario_id", ""))
    origin = str(loaded.get("origin", ""))
    if origin != f"{ORIGIN_PREFIX}{scenario_id}":
        raise PostmortemError(
            f"{path}: origin {origin!r} does not match scenario_id {scenario_id!r}. `origin` is "
            "the exclusion key (ADR-0008, axis 2), so a postmortem carrying the wrong one is "
            "excluded from the wrong scenario - and read by the one it is about."
        )

    prose = "\n".join([title_match.group(1), *(f"{n}\n{t}" for n, t in sections)])
    leaked = leaked_words(prose)
    if leaked:
        raise PostmortemLeakError(
            f"{path} mentions {leaked}. A postmortem may state the mechanism and may not name "
            "its remediation: fault class maps to remediation one-to-one across this catalog, "
            "so the action is the class in another spelling (registration §2)."
        )
    if scenario_ids:
        named = named_scenarios(prose, scenario_ids)
        if named:
            raise PostmortemLeakError(
                f"{path} names {named} in its prose. The scenario belongs in `origin`, where the "
                "exclusion reads it; in the text it is the answer key (ADR-0036)."
            )

    return Postmortem(
        scenario_id=scenario_id,
        origin=origin,
        split=str(loaded.get("split", "")),
        incident_id=str(loaded.get("incident_id", "")),
        recorded_from=str(loaded.get("recorded_from", "")),
        title=title_match.group(1).strip(),
        sections=sections,
    )


def chunk_postmortem(
    postmortem: Postmortem,
    *,
    scenario_fingerprint: str,
    fault_class: str,
    source_path: Path,
) -> list[Chunk]:
    """One chunk per section, sectioned the way everything else in this corpus is (ADR-0018).

    `document_id` is `postmortem:<id>` and `origin` is `scenario:<id>` - the module docstring
    has the argument. `fault_class` rides as metadata exactly as it does on a narrative chunk:
    it is not in the text, and the guard above is what keeps it out.
    """
    return [
        Chunk(
            document_id=postmortem.document_id,
            section=section,
            section_index=index,
            text=text,
            origin=postmortem.origin,
            split=postmortem.split,
            scenario_id=postmortem.scenario_id,
            fault_class=fault_class,
            scenario_fingerprint=scenario_fingerprint,
            recorded_from=postmortem.recorded_from,
            title=postmortem.title,
            source_path=str(source_path),
        )
        for index, (section, text) in enumerate(postmortem.sections)
    ]


def render(postmortem: Postmortem) -> str:
    """The document, back to text. Round-trips through `parse_postmortem`."""
    front: dict[str, Any] = {
        "scenario_id": postmortem.scenario_id,
        "origin": postmortem.origin,
        "split": postmortem.split,
        "incident_id": postmortem.incident_id,
        "recorded_from": postmortem.recorded_from,
    }
    lines = ["---", yaml.safe_dump(front, sort_keys=False).rstrip(), "---", ""]
    lines += [f"# {postmortem.title}", ""]
    for section, text in postmortem.sections:
        lines += [f"## {section}", "", text, ""]
    return "\n".join(lines).rstrip() + "\n"
