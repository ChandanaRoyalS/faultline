"""Hand-authored runbooks (T2.4b): complete, grounded, and not an answer key.

T4.1b's exclusion filter never excludes an `authored` document - that is what makes runbooks
legitimate institutional knowledge rather than a rehearsal of the scenario being scored. It is
also what makes their content dangerous: anything true of *one scenario* written here reaches
every scored run afterwards, permanently, through the one channel the quarantine does not
filter.

So the boundary is enforced rather than trusted. A runbook may say what is true of the world -
its alert rules, its fault classes, its measured limits. It may not name a scenario.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from faultline.context.allowlist import load_allowlist
from faultline.context.graph import ARTIFACT_EDGES, EDGE_KINDS, EdgeKind, ServiceGraph
from faultline.context.runbooks import load_runbooks, runbooks_dir
from injector.world import SERVICE_CONTAINERS, canonical_service

ALERT_RULES = Path("compose/prometheus/alert-rules.yml")
SCENARIOS = Path("evals/scenarios")
DEPENDENCY_GRAPH = Path("docs/evidence/t2.4-dependency-graph/dependencies.json")
ARTIFACT_EDGE_RUNBOOK = "world-tracing-artifact-edges"


def scenario_ids() -> set[str]:
    return {path.stem for path in SCENARIOS.glob("*.yaml")}


def alert_names() -> set[str]:
    rules: Any = yaml.safe_load(ALERT_RULES.read_text())
    return {rule["alert"] for group in rules["groups"] for rule in group.get("rules", [])}


def test_the_corpus_is_the_size_the_plan_asks_for() -> None:
    """T2.4b names "~15 runbooks". Floor, not ceiling - growing it is fine."""
    assert len(load_runbooks()) >= 15


def test_every_runbook_is_stamped_authored() -> None:
    """ADR-0008: the provenance stamp is what exempts these from exclusion."""
    for runbook in load_runbooks():
        assert runbook.origin == "authored", f"{runbook.id} is stamped {runbook.origin!r}"


def test_ids_are_unique_and_match_their_filename() -> None:
    ids = [r.id for r in load_runbooks()]
    assert len(ids) == len(set(ids))
    assert sorted(ids) == sorted(p.stem for p in runbooks_dir().glob("*.md"))


def test_no_runbook_names_a_catalog_scenario() -> None:
    """**The contamination guard.**

    Not holdout scenarios only - *any* scenario. A runbook that reaches for a specific
    scenario has stopped being knowledge about the world and started being knowledge about the
    answer, and the dev/holdout line is the wrong place to draw this one: a runbook written
    around a dev scenario is a template for writing one around a holdout scenario.
    """
    ids = scenario_ids()
    for runbook in load_runbooks():
        text = f"{runbook.title}\n{runbook.body}"
        named = sorted(scenario for scenario in ids if scenario in text)
        assert not named, (
            f"{runbook.id} names {named}. Runbooks are never excluded from retrieval, so a "
            "scenario named here reaches every scored run afterwards. Say what is true of the "
            "world instead."
        )


def test_no_runbook_names_a_scenario_in_any_spelling() -> None:
    """**ADR-0036's rule, matched harder** (T6.4).

    The check beside this one compares scenario ids against the text with a case-sensitive
    substring test. That catches `cart-redis-misconfig` and nothing else: not `Cart-Redis-
    Misconfig`, not `cart_redis_misconfig`, not `cart redis misconfig`. ADR-0036 already records
    that an id-matching test is weak - two of the first fifteen runbooks cited a holdout
    scenario's fault *without naming it* and would have passed - and T6.4 adds 25 documents, so
    the cheap half of that gap is worth closing before they land rather than after.

    What this still cannot catch is a paraphrase, and no test can. The per-document review the
    pre-registration commits to is the other half, and it is a person reading, not a regex.
    """
    scenarios = scenario_ids()
    assert scenarios, "no scenario catalog found; this test would pass vacuously"

    for runbook in load_runbooks():
        text = f"{runbook.title}\n{runbook.body}".lower()
        for scenario in scenarios:
            for spelling in (scenario, scenario.replace("-", "_"), scenario.replace("-", " ")):
                assert spelling.lower() not in text, (
                    f"{runbook.id} contains {spelling!r}. A runbook may say what is true of the "
                    "world; it may not name a scenario, in any spelling (ADR-0036)."
                )


def test_every_action_names_a_real_allowlist_entry() -> None:
    """A runbook pointing at an action the executor does not have is a dead end."""
    known = {action.id for action in load_allowlist().actions}
    for runbook in load_runbooks():
        for action in runbook.actions:
            assert action in known, f"{runbook.id} points at unknown action {action!r}"


def test_every_signal_names_a_rule_that_can_fire() -> None:
    """Signals are how a runbook is found. One naming a rule that does not exist is unfindable."""
    known = alert_names()
    for runbook in load_runbooks():
        for signal in runbook.signals:
            assert signal in known, f"{runbook.id} names alert {signal!r}, which has no rule"


def test_every_service_named_exists_in_the_world() -> None:
    for runbook in load_runbooks():
        for service in runbook.applies_to:
            assert service == "any" or service in SERVICE_CONTAINERS, (
                f"{runbook.id} applies to {service!r}, which injector.world does not describe"
            )


def test_every_fault_class_has_a_runbook() -> None:
    """The four classes the injector can produce, each with somewhere to start."""
    from evalharness.scenario import FaultClass

    ids = {r.id for r in load_runbooks()}
    for fault_class in FaultClass:
        assert f"class-{fault_class.value.replace('_', '-')}" in ids, (
            f"no runbook for fault class {fault_class.value}"
        )


def test_every_allowlist_action_has_a_runbook() -> None:
    """Including the unperformable one - especially the unperformable one."""
    bodies = "\n".join(r.body for r in load_runbooks())
    for action in load_allowlist().actions:
        assert action.id in bodies, f"no runbook mentions the action {action.id}"


def edge_table(service: str) -> str:
    """The measured edges of one service, rendered from the graph rather than from memory.

    Of the eight errors in the five service runbooks removed on 2026-09-12, two were numbers or
    kinds that `dependencies.json` and `EDGE_KINDS` already hold: an outbound count of seven
    against a list of eight, and "all five **sync**" against four sync and one `unmeasured`.
    Facts copied by hand out of a machine-readable source are the cheapest kind of wrong to be,
    so this block is generated and a service runbook has to contain it verbatim.
    """
    graph = ServiceGraph.from_snapshot()
    name = canonical_service(service)
    inbound = sorted(
        (e for e in graph.edges if e.child == name), key=lambda e: (-e.call_count, e.parent)
    )
    outbound = sorted(
        (e for e in graph.edges if e.parent == name), key=lambda e: (-e.call_count, e.child)
    )
    if not inbound and not outbound:
        return "No measured edges: this service appears in no trace and has no node in the graph."

    rows = [
        f"| {direction} | `{edge.parent} -> {edge.child}` | {edge.call_count} | {edge.kind.value} |"
        for direction, edges in (("inbound", inbound), ("outbound", outbound))
        for edge in edges
    ]
    return "\n".join(["| | edge | calls | kind |", "|---|---|---|---|", *rows])


def service_runbooks() -> list[tuple[str, Any]]:
    return [
        (r.id.removeprefix("service-"), r) for r in load_runbooks() if r.id.startswith("service-")
    ]


def test_every_service_runbook_carries_the_generated_edge_table() -> None:
    """**The accuracy guard** (T6.4, added after the first five service runbooks were removed).

    A service runbook's dependency facts are not written; they are pasted from `edge_table`,
    which reads the same snapshot production reads. The truth is then *in the document*, next to
    whatever the author says about it.

    **It does not check the prose, and that is not a detail.** The assertion is containment of
    the generated block. A summary sentence above the table saying "seven outbound, all sync"
    passes this test - a reviewer confirmed it by planting exactly that and watching the suite go
    green. So this guard removes one way to be wrong (a fact that never had to be retyped) and
    leaves the rest to the review ADR-0036 Addendum 1 requires. Claiming more of it here would be
    the same pretence the addendum was written about.
    """
    for service, runbook in service_runbooks():
        expected = edge_table(service)
        assert expected in runbook.body, (
            f"{runbook.id} does not carry the generated edge table. Paste this:\n\n{expected}\n"
        )


def test_no_runbook_but_one_cites_an_artifact_edge() -> None:
    """The two excluded edges are not facts about the world's dependencies.

    `loadgenerator -> frontend` is the synthetic client and `frontendproxy -> jaeger-all-in-one`
    is the tracing UI routing itself; ADR-0017 excludes both, and excluding an edge is what
    removes a node. A service runbook citing one as though it were measured would reintroduce
    the reading ADR-0017 exists to prevent - that the world's most-depended-on service is the one
    our own load generator calls.

    **One document is exempt, by name**: `world-tracing-artifact-edges`, whose subject is that
    these edges must not be used. Every other runbook is checked, not only the `service-*` ones -
    a class or alert runbook citing the synthetic client's edge would do the same damage.
    """
    claim = re.compile(r"`([a-z][a-z-]+) -> ([a-z][a-z-]+)`")
    for runbook in load_runbooks():
        if runbook.id == ARTIFACT_EDGE_RUNBOOK:
            continue
        for parent, child in claim.findall(runbook.body):
            pair = (canonical_service(parent), canonical_service(child))
            assert pair not in ARTIFACT_EDGES, (
                f"{runbook.id} cites `{parent} -> {child}`, which ADR-0017 excludes as an "
                "artifact of how this world is run. It is not one of the 15 measured edges."
            )


def test_every_edge_claim_in_a_runbook_matches_the_measured_graph() -> None:
    """The same check for edges cited inline, outside the generated block.

    ``` `parent -> child` ``` followed within 120 characters by a call count or an edge kind is
    checked against the sources. The form is part of the rule and an edge written some other way
    is not caught - which is why the block above exists and why the review still happens.

    **It would not have caught most of what it was written for.** Of the eight errors in the
    removed batch, this catches none: their wrong numbers were attached to bare service names
    in a list, and "seven outbound" was a summary attached to no pair at all. It is kept as a
    second net for the inline case, and recorded here as a net rather than as the answer.
    """
    measured = json.loads(DEPENDENCY_GRAPH.read_text())["data"]
    counts = {
        (canonical_service(edge["parent"]), canonical_service(edge["child"])): edge["callCount"]
        for edge in measured
    }
    assert counts, "no measured graph found; this test would pass vacuously"

    claim = re.compile(r"`([a-z][a-z-]+) -> ([a-z][a-z-]+)`([^\n]{0,120})")
    kinds = re.compile(r"\b(sync|async|unmeasured)\b")

    for runbook in load_runbooks():
        for parent, child, trailing in claim.findall(runbook.body):
            pair = (canonical_service(parent), canonical_service(child))
            assert pair in counts, (
                f"{runbook.id} cites `{parent} -> {child}`, which is not in the capture at all. "
                "Say what the graph measured or do not cite an edge."
            )

            for number in re.findall(r"\b(\d{2,5})\b", trailing):
                assert int(number) == counts[pair], (
                    f"{runbook.id} puts {number} beside `{parent} -> {child}`, which the graph "
                    f"measured at {counts[pair]} calls. An inbound total is not an edge count."
                )

            for named in kinds.findall(trailing):
                actual = EDGE_KINDS.get(pair, EdgeKind.UNMEASURED)
                assert named == actual.value, (
                    f"{runbook.id} calls `{parent} -> {child}` {named!r}; it is "
                    f"{actual.value!r}. `unmeasured` is not a synonym for `sync` and the "
                    "difference decides whether a callee's failure reaches the caller."
                )


def test_every_runbook_says_something() -> None:
    for runbook in load_runbooks():
        assert len(runbook.body) > 400, f"{runbook.id} is too thin to be worth retrieving"
        assert re.search(r"^## ", runbook.body, re.MULTILINE), f"{runbook.id} has no sections"
