"""Where the injector finds the world, and where it remembers what it broke (T1.4)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def repo_root() -> Path:
    """The checkout root, located by pyproject.toml rather than assumed from cwd."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


class InjectorSettings(BaseSettings):
    """Injector configuration. Every field is overridable via FAULTLINE_INJECTOR_*."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_INJECTOR_", env_file=".env", extra="ignore"
    )

    world_dir: Path = repo_root() / "world"
    """The pinned OTel demo clone. Compose runs here, so the project name matches make."""

    state_dir: Path = repo_root() / ".faultline"
    """Active injections and generated overrides. Not version-controlled: it is runtime state."""

    compose_files: tuple[str, ...] = (
        "docker-compose.yml",
        "../compose/world-arm64.override.yml",
        "../compose/telemetry.yml",
    )
    """Mirrors COMPOSE_WORLD in the Makefile; paths are relative to world_dir, as there."""

    ffs_stub_context: Path = repo_root() / "compose" / "ffs-stub"

    pumba_image: str = "gaiaadm/pumba:0.10.1"
    """Pinned, and multi-arch: 0.10.1 publishes arm64, so the injector itself is not emulated."""

    tc_image: str = "gaiadocker/iproute2:latest"
    """Pumba runs tc from here, so the target container needs no tooling of its own."""

    @property
    def state_file(self) -> Path:
        return self.state_dir / "injections.json"

    @property
    def override_dir(self) -> Path:
        return self.state_dir / "overrides"
