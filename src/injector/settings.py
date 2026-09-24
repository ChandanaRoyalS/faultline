"""Where the injector finds the world, and where it remembers what it broke (T1.4, T7.0).

**One world at a time, and the tools' world is the injector's** (T7.0 #6, 2026-09-24). Until this
change `InjectorSettings` knew one world - the v1 clone under `world/` and v1's three compose files
- while `faultline.tools.settings.ToolSettings.world` could already say `v2`. So a harness pointed
at v2 read v2's metrics and injected into v1's compose project, and `compose_digest` hashed v1's
files into a v2 bundle's manifest, which is the exact species of silent lie ADR-0014 exists to
prevent: a bundle that names a world it was not recorded on.

The injector therefore takes `world` from `ToolSettings` by default, and everything that depends
on it - the clone directory, the compose triple, the environment compose needs - follows from
that one value through `WORLDS`. `FAULTLINE_INJECTOR_WORLD` may still be set, and when it
disagrees with `FAULTLINE_TOOLS_WORLD` the settings refuse to construct rather than let the two
halves of one run describe different worlds.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    """The checkout root, located by pyproject.toml rather than assumed from cwd."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


@dataclass(frozen=True, slots=True)
class WorldLayout:
    """What one demo generation is called on disk and how the Makefile composes it."""

    clone_dir: str
    """The pinned clone, relative to the repository root."""
    compose_files: tuple[str, ...]
    """Mirrors the Makefile's `COMPOSE_WORLD*_FILES`; paths are relative to the clone, as there."""
    compose_env: dict[str, str]
    """Environment the Makefile sets in front of `docker compose` for this world. v2's compose
    file reads image tags from `${DEMO_VERSION}` and its `.env` says `latest`; the Makefile pins
    2.2.0 in the environment, and so must every compose call the injector makes, or a recreate
    silently pulls a different world (`tests/test_world_v2.py` pins the value to the Makefile)."""


WORLDS: dict[str, WorldLayout] = {
    "v1": WorldLayout(
        clone_dir="world",
        compose_files=(
            "docker-compose.yml",
            "../compose/world-arm64.override.yml",
            "../compose/telemetry.yml",
        ),
        compose_env={},
    ),
    "v2": WorldLayout(
        clone_dir="world-v2",
        compose_files=(
            "docker-compose.yml",
            "../compose/world-v2.override.yml",
            "../compose/telemetry-v2.yml",
        ),
        compose_env={"DEMO_VERSION": "2.2.0"},
    ),
}
"""Every world the injector can address, keyed as `ToolSettings.world` keys them."""


def _tools_world() -> str:
    # Lazy: `faultline.tools` imports `injector.world`, and a module-level import here would
    # close the cycle. The tools' setting is the one source of truth for which world a run is on.
    from faultline.tools.settings import ToolSettings

    return ToolSettings().world


def layout_for(world: str) -> WorldLayout:
    try:
        return WORLDS[world]
    except KeyError:
        raise ValueError(f"unknown world {world!r}; the injector knows {sorted(WORLDS)}") from None


class InjectorSettings(BaseSettings):
    """Injector configuration. Every field is overridable via FAULTLINE_INJECTOR_*."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_INJECTOR_", env_file=".env", extra="ignore"
    )

    world: str = ""
    """Which demo generation the injector addresses. **Defaults to the tools' world**, so one
    `FAULTLINE_TOOLS_WORLD` moves the whole run; see the module docstring."""

    world_dir: Path = Path()
    """The pinned demo clone. Compose runs here, so the project name matches make. Derived from
    `world` unless set explicitly - tests point it at a temporary directory."""

    compose_files: tuple[str, ...] = ()
    """Mirrors the Makefile's file list for `world`; derived unless set explicitly."""

    compose_env: dict[str, str] = {}
    """What compose must see in its environment for `world`; derived unless set explicitly.
    (The empty defaults on these four fields mean *derive*; the validator fills them.)"""

    state_dir: Path = repo_root() / ".faultline"
    """Active injections and generated overrides. Not version-controlled: it is runtime state."""

    ffs_stub_context: Path = repo_root() / "compose" / "ffs-stub"

    pumba_image: str = "gaiaadm/pumba:0.10.1"
    """Pinned, and multi-arch: 0.10.1 publishes arm64, so the injector itself is not emulated."""

    tc_image: str = "gaiadocker/iproute2:latest"
    """Pumba runs tc from here, so the target container needs no tooling of its own."""

    @model_validator(mode="before")
    @classmethod
    def _derive_from_world(cls, values: Any) -> Any:
        """Fill the world-dependent fields from `world` before validation, so their types stay
        plain (`Path`, not `Path | None`) for every consumer."""
        if not isinstance(values, dict):
            return values
        tools_world = _tools_world()
        world = values.get("world") or tools_world
        if world != tools_world:
            raise ValueError(
                f"FAULTLINE_INJECTOR_WORLD={world!r} but FAULTLINE_TOOLS_WORLD={tools_world!r}: "
                "the injector and the tools must address one world; set the tools' and leave this"
            )
        layout = layout_for(world)
        values = dict(values)
        values["world"] = world
        if not values.get("world_dir"):
            values["world_dir"] = repo_root() / layout.clone_dir
        if not values.get("compose_files"):
            values["compose_files"] = layout.compose_files
        if "compose_env" not in values:
            values["compose_env"] = dict(layout.compose_env)
        return values

    @property
    def state_file(self) -> Path:
        return self.state_dir / "injections.json"

    @property
    def override_dir(self) -> Path:
        return self.state_dir / "overrides"
