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


def test_the_image_installs_the_extras_the_runtime_needs() -> None:
    """**`uv sync` alone is not enough**, and README has said so since T5.4b - for a developer's
    tree. The Dockerfile ran exactly that, so the orchestrator container had no model client and
    the seeder no embedder: a deployment that could remember investigations and not produce one,
    T5.5b's deviation three reintroduced by the build (T5.5c, defect twenty-six). Every `uv sync`
    in the image names both extras; `archive` is deliberately not one of them."""
    dockerfile = Path("Dockerfile").read_text()
    # RUN lines, not comments: the comment above the first sync quotes the bare command in order
    # to explain why it is wrong, and the first version of this test failed on it.
    syncs = [
        line for line in dockerfile.splitlines() if line.startswith("RUN") and "uv sync" in line
    ]

    assert syncs, "the image does not install the project"
    for line in syncs:
        assert "--extra agents" in line and "--extra embeddings" in line, line
        assert "--all-extras" not in line and "archive" not in line, line


def test_torch_comes_from_the_cpu_index_on_linux_and_the_lock_shows_it() -> None:
    """The `embeddings` extra pulls torch, and PyPI's Linux wheel pulls ~3 GB of CUDA libraries a
    GPU-less VM never loads. `[tool.uv.sources]` sends Linux to the CPU index and leaves macOS -
    the platform every published figure was produced on - exactly as it was. The lock is the proof
    the stanza was applied: regenerated with it, no `nvidia-*` package remains."""
    import tomllib

    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    # A source binds only to a direct dependency. With torch reached transitively through
    # sentence-transformers, `uv lock` resolved in 1ms, changed nothing, and the stanza was inert.
    assert any(
        d.split(">")[0].split("=")[0].strip() == "torch"
        for d in pyproject["project"]["optional-dependencies"]["embeddings"]
    ), "torch must be a direct dependency of the embeddings extra or its source is ignored"
    sources = pyproject["tool"]["uv"]["sources"]["torch"]
    assert any(
        s.get("index") == "pytorch-cpu" and "linux" in s.get("marker", "") for s in sources
    ), sources
    indexes = {i["name"]: i for i in pyproject["tool"]["uv"]["index"]}
    assert indexes["pytorch-cpu"]["url"].rstrip("/") == "https://download.pytorch.org/whl/cpu"
    assert indexes["pytorch-cpu"].get("explicit") is True, "must not shadow PyPI for other packages"

    lock = Path("uv.lock").read_text()
    assert 'name = "nvidia-' not in lock, (
        "uv.lock still resolves torch's CUDA dependencies: run `uv lock` after this change"
    )
    assert "download.pytorch.org/whl/cpu" in lock, "the lock never consulted the CPU index"
