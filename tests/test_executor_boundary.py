"""The investigation runtime cannot reach the executor (T6.2, ADR-0028 §3).

*"Read-only is a property of the tool surface, not of the credential"* (ADR-0019 §4), and the
surface stays read-only only while nothing in it constructs a write path. These tests hold the
property by AST: no module under `faultline.agents` or `faultline.tools` may import the executor
package, the injector's Docker or compose clients, or `subprocess`. Docstrings and comments are
excluded - prose may name what code must not do - and the check reads `import` statements, not
text, so a module that spells the forbidden name inside a string is not caught and does not need
to be: a string is not an import.

`PREREGISTRATION-T6.2.md` prediction 2: written to fail first, on a planted `import subprocess`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
RUNTIME = ("faultline/agents", "faultline/tools")
FORBIDDEN_MODULES = (
    "faultline.executor",
    "injector.docker",
    "injector.engine",
    "subprocess",
    # T6.3: the approve button is a write path too, and it holds the minting key. An agent that
    # could import the router could mint against any incident it could name.
    "faultline.api.approvals",
)
"""Anything from which a write path to the world could be constructed. `injector.world` and
`injector.settings` are data - names and paths - and stay importable; `tools.py` reads
`SERVICE_CONTAINERS` for the world's two naming schemes."""


def _imports(module: Path) -> list[tuple[str, int]]:
    tree = ast.parse(module.read_text())
    names: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append((node.module, node.lineno))
    return names


def _runtime_modules() -> list[Path]:
    return sorted(p for root in RUNTIME for p in (SRC / root).rglob("*.py"))


@pytest.mark.parametrize("module", _runtime_modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_the_runtime_imports_nothing_that_can_write_to_the_world(module: Path) -> None:
    offending = [
        (name, line)
        for name, line in _imports(module)
        if any(name == f or name.startswith(f + ".") for f in FORBIDDEN_MODULES)
    ]
    assert not offending, (
        f"{module.relative_to(SRC)} imports {offending}: the investigation runtime has no write "
        "path to the world, and this import would be one (ADR-0028 §3, T6.2)"
    )


def test_the_guard_sees_a_planted_import(tmp_path: Path) -> None:
    """A guard that has never been red has not been shown to see. Plant the import in a copy."""
    planted = tmp_path / "tools.py"
    planted.write_text('"""prose may say subprocess."""\nimport subprocess\n')
    names = [n for n, _ in _imports(planted)]
    assert "subprocess" in names


def test_the_executor_is_the_only_product_code_that_builds_a_world_client() -> None:
    """The other direction: `World` (which constructs the compose and docker clients) lives in
    `faultline.executor.core` and nowhere else under `faultline/`."""
    builders = [
        p.relative_to(SRC)
        for p in (SRC / "faultline").rglob("*.py")
        if any(n.startswith("injector.docker") for n, _ in _imports(p))
    ]
    assert builders == [Path("faultline/executor/core.py")], builders


READ_SURFACE = SRC / "faultline" / "api" / "incidents.py"
WRITERS = (
    "faultline.executor",
    "faultline.api.approvals",
    "faultline.orchestrator.machine",
    "faultline.orchestrator.rejections",
    "faultline.orchestrator.acknowledgements",
)


def test_the_read_surface_still_imports_no_writer() -> None:
    """T6.3's invariant, and it is `incidents.py`'s own sentence about itself: *"the router never
    imports a writer, never opens a transaction, and cannot advance a state machine."* The product
    now has a write surface; it is a different module (`api/approvals.py`) behind the same
    credential, so the claim the read routes make about themselves stays true rather than becoming
    a comment about how things used to be."""
    offending = [
        (name, line)
        for name, line in _imports(READ_SURFACE)
        if any(name == w or name.startswith(w + ".") for w in WRITERS)
    ]
    assert not offending, (
        f"faultline/api/incidents.py imports {offending}: the read surface is read-only "
        "structurally, and T6.3's write routes live in faultline/api/approvals.py"
    )
