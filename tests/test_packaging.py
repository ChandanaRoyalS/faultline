"""Repository data the runtime resolves at run time must exist in the image.

`faultline.context.allowlist.catalog_path()` and `faultline.migrate.ini_path()` both walk up
from the installed package looking for a repository directory. That resolves in a clone and in
an editable install, and resolved in *nothing* inside the container image, which copied only
`src`. Neither loader had a caller yet, so the failure was waiting for a deployment.

The rule this file enforces: if the runtime finds a file by walking up, the image ships it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_DATA = {
    "alembic.ini": "faultline.migrate.ini_path()",
    "migrations": "the revision history alembic.ini points at",
    "knowledge": "faultline.context.allowlist.catalog_path()",
    # The third one found by a deployment rather than a test: `faultline-seed` inside the
    # container walked its default root and found no directory at all (T5.5c, defect twenty-five).
    "evals/scenarios/artifacts/dev": "faultline.context.cli.DEFAULT_DEV_ROOT",
}


def test_the_image_ships_every_file_the_runtime_walks_up_to_find() -> None:
    dockerfile = Path("Dockerfile").read_text()
    for name, resolver in REPO_DATA.items():
        assert re.search(rf"^COPY .*\b{re.escape(name)}\b", dockerfile, re.MULTILINE), (
            f"{name} is resolved at run time by {resolver} and is not copied into the image, "
            "so it exists in a clone and not in a container"
        )


def test_the_image_ships_the_dev_split_and_never_the_holdout() -> None:
    """ADR-0008 axis 1 in the Dockerfile: the corpus source that ships is `artifacts/dev`, named
    to the leaf, and no `COPY` line is broad enough to carry `holdout` in beside it. The seeder's
    own guard refuses a holdout root, but a guard that runs inside the container is worth less than
    a directory that was never put there."""
    dockerfile = Path("Dockerfile").read_text()
    copies = [line for line in dockerfile.splitlines() if line.startswith("COPY ")]

    assert any("evals/scenarios/artifacts/dev " in line for line in copies), copies
    for line in copies:
        assert "holdout" not in line, line
        assert not re.search(r"COPY (\./)?evals/?( |$)", line), f"copies the whole tree: {line}"
        assert not re.search(r"COPY (\./)?evals/scenarios/artifacts/?( |$)", line), (
            f"copies both splits: {line}"
        )
        assert not re.match(r"COPY \. ", line), f"copies the whole repository: {line}"
