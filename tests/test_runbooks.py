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

import re
from pathlib import Path
from typing import Any

import yaml

from faultline.context.allowlist import load_allowlist
from faultline.context.runbooks import load_runbooks, runbooks_dir
from injector.world import SERVICE_CONTAINERS

ALERT_RULES = Path("compose/prometheus/alert-rules.yml")
SCENARIOS = Path("evals/scenarios")


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


def test_every_runbook_says_something() -> None:
    for runbook in load_runbooks():
        assert len(runbook.body) > 400, f"{runbook.id} is too thin to be worth retrieving"
        assert re.search(r"^## ", runbook.body, re.MULTILINE), f"{runbook.id} has no sections"
