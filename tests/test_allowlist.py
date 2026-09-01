"""The allowlist action catalog: that it is coherent, and that it stays read-only.

The read-only guard is the point of this file. ADR-0032 argues the catalog is a control
rather than data, and a control the investigation runtime can edit is not one - the runtime
is precisely the part of this system that reads untrusted telemetry. Prose saying "read-only"
is enforced by nothing; these tests are the enforcement.
"""

from __future__ import annotations

import ast
from pathlib import Path

from evalharness.scenario import RemediationClass
from faultline.context.allowlist import (
    ActionStatus,
    TargetSelector,
    catalog_path,
    load_allowlist,
)
from injector.world import SERVICE_CONTAINERS

MODULE = Path("src/faultline/context/allowlist.py")
SRC = Path("src")


def test_the_catalog_loads_and_carries_its_provenance() -> None:
    catalog = load_allowlist()
    assert catalog.catalog_version >= 1
    assert catalog.origin == "authored", "ADR-0008 axis 2: authored knowledge is never excluded"


def test_action_ids_are_unique() -> None:
    ids = [a.id for a in load_allowlist().actions]
    assert len(ids) == len(set(ids))


def test_every_remediation_class_the_scorer_knows_has_exactly_one_entry() -> None:
    """The catalog covers the vocabulary, or the gap is visible.

    `AllowlistAction.remediation_class` is a `str` and not this enum on purpose: ADR-0004
    forbids the product depending on the harness, and `RemediationClass` lives in
    `evalharness`. A test may import both, so the correspondence is checked here rather than
    enforced by a type the product is not allowed to hold.
    """
    entries = [a.remediation_class for a in load_allowlist().actions]
    assert sorted(entries) == sorted(c.value for c in RemediationClass)


def test_an_unperformable_action_says_why_and_cites_the_measurement() -> None:
    for action in load_allowlist().actions:
        if action.status is ActionStatus.UNPERFORMABLE:
            assert action.unperformable_reason, f"{action.id} is unperformable and unexplained"
            assert "ADR-" in action.unperformable_reason, (
                f"{action.id}: an unperformable action must cite what measured it, "
                "otherwise the claim is an opinion in a control document"
            )


def test_every_available_action_needs_an_approval() -> None:
    """The propose/execute boundary, asserted where it is written down rather than assumed."""
    for action in load_allowlist().performable:
        assert action.approval == "required", f"{action.id} would execute without a human"
        assert action.target_selector is TargetSelector.INCIDENT_SCOPED_SERVICE


def test_excluded_targets_name_services_this_world_has() -> None:
    """Empty today. The guard exists so the first entry cannot be a typo."""
    for action in load_allowlist().actions:
        for target in action.excluded_targets:
            assert target in SERVICE_CONTAINERS, (
                f"{action.id} excludes {target!r}, which injector.world does not describe"
            )


def test_only_the_loader_names_the_catalog_file() -> None:
    """No other module may reach for it - not to read it, and certainly not to write it."""
    offenders = [
        str(path)
        for path in SRC.rglob("*.py")
        if path != MODULE and "allowlist.yaml" in path.read_text()
    ]
    assert not offenders, f"these modules name the catalog file directly: {offenders}"


def test_the_loader_cannot_write() -> None:
    """AST, not `grep`: a docstring may say "write" and this must still pass."""
    tree = ast.parse(MODULE.read_text())
    forbidden = {"open", "write_text", "write_bytes", "write", "dump", "dump_all", "safe_dump"}
    called = {
        node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not called & forbidden, f"the loader can write: {sorted(called & forbidden)}"


def test_the_loader_does_not_import_the_harness() -> None:
    """ADR-0004: the product may not depend on the eval harness."""
    assert "evalharness" not in MODULE.read_text()


def test_the_catalog_lives_outside_the_package() -> None:
    """Repository data, not package data - it is versioned by git, and reviewed as a diff."""
    assert catalog_path().parent.name == "knowledge"
    assert "src" not in catalog_path().parts
