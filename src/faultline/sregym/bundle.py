"""What Faultline ships into SREGym's container: a source bundle, not a wheel (T7.2).

**Found registering the pilot, before anything ran**: a wheel carries `src/` and nothing else, and
Faultline walks up from its own `__file__` to find repository data at run time - the dependency
snapshots (`faultline.context.graph.repo_root`), `knowledge/`, `alembic.ini` and `migrations/`.
Installed from a wheel into site-packages, none of it is above the package, and the first
investigation would fail to load its graph. Stage 0 imported Faultline and never loaded a graph,
so it could not see this. `tests/test_packaging.py::REPO_DATA` lists the same paths for the
Docker image, and `tests/test_sregym.py` holds this list to it.

The box gets `git archive` of exactly these paths at the run's commit, extracted to
`/opt/faultline` and installed editable, so `__file__` sits under the bundle's own root, as it does
under `/app` in the image.

    git archive --format=tar.gz -o faultline-src.tar.gz HEAD $(python -m faultline.sregym.bundle)
"""

from __future__ import annotations

import sys

BUNDLE_PATHS: tuple[str, ...] = (
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "src",
    "alembic.ini",
    "migrations",
    "knowledge",
    "docs/evidence/t2.4-dependency-graph/dependencies.json",
    "docs/evidence/t7.2-topology/q121-v2-dependencies-1h.json",
    "docs/evidence/t7.2-topology/g3-deps-60m.json",
    "docs/evidence/t7.2-topology/g4-hotel-deps-5m.json",
    "docs/evidence/t7.2-topology/g4-social-deps-30m.json",
)
"""The box's bundle. **No corpus source**: the benchmark database is seeded outside the box, and
the box never holds a narrative (ADR-0008 axis 1 holds by absence)."""

SEED_PATHS: tuple[str, ...] = (*BUNDLE_PATHS, "evals/scenarios/artifacts/dev")
"""The seeding container's bundle: the box's, plus the dev split alone, as the image ships it."""


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    print(" ".join(SEED_PATHS if "--seed" in args else BUNDLE_PATHS))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
