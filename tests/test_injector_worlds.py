"""The injector addresses one world at a time, and it is the tools' world (T7.0 #6).

Before this, `InjectorSettings` knew v1 only while `ToolSettings.world` could say v2: a harness
pointed at v2 read v2's metrics and injected into v1's compose project, and `compose_digest`
hashed v1's files into a v2 bundle. Everything here pins the one-value-moves-everything property
and the refusals that keep the two halves of a run on the same world.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from evalharness import provenance
from evalharness.scenario import FaultClass
from injector.catalog import CatalogError, check_target
from injector.docker import ComposeCli
from injector.engine import Engine, InjectorError
from injector.models import FaultDefinition
from injector.settings import WORLDS, InjectorSettings, layout_for
from injector.world import (
    SERVICE_CONTAINERS,
    SERVICE_CONTAINERS_V2,
    canonical_service,
    container_services,
    service_containers,
)
from tests.fakes import FakeRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (REPO_ROOT / "Makefile").read_text()


@pytest.fixture
def on_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAULTLINE_TOOLS_WORLD", "v2")
    monkeypatch.delenv("FAULTLINE_INJECTOR_WORLD", raising=False)


@pytest.fixture
def on_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAULTLINE_TOOLS_WORLD", raising=False)
    monkeypatch.delenv("FAULTLINE_INJECTOR_WORLD", raising=False)


# --- settings ---------------------------------------------------------------------------------


def test_the_default_world_is_v1_and_unchanged(on_v1: None) -> None:
    """Every published figure was measured on v1; a world is opted into (ADR-0026)."""
    settings = InjectorSettings()
    assert settings.world == "v1"
    assert settings.world_dir == REPO_ROOT / "world"
    assert settings.compose_files == WORLDS["v1"].compose_files
    assert settings.compose_env == {}


def test_the_tools_world_moves_the_injectors_world(on_v2: None) -> None:
    settings = InjectorSettings()
    assert settings.world == "v2"
    assert settings.world_dir == REPO_ROOT / "world-v2"
    assert settings.compose_files == (
        "docker-compose.yml",
        "../compose/world-v2.override.yml",
        "../compose/telemetry-v2.yml",
    )
    assert settings.compose_env == {"DEMO_VERSION": "2.2.0"}


def test_an_injector_world_that_disagrees_with_the_tools_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two halves of one run on two worlds is the failure this setting exists to prevent."""
    monkeypatch.setenv("FAULTLINE_TOOLS_WORLD", "v2")
    monkeypatch.setenv("FAULTLINE_INJECTOR_WORLD", "v1")
    with pytest.raises(ValueError, match="must address one world"):
        InjectorSettings()


def test_an_explicit_world_dir_is_kept_and_the_rest_still_derives(
    on_v2: None, tmp_path: Path
) -> None:
    settings = InjectorSettings(world_dir=tmp_path)
    assert settings.world_dir == tmp_path
    assert settings.compose_env == {"DEMO_VERSION": "2.2.0"}


def test_an_unknown_world_is_named_in_the_refusal() -> None:
    with pytest.raises(ValueError, match="unknown world 'v3'"):
        layout_for("v3")


# --- the Makefile is the reference -----------------------------------------------------------


def _makefile_var(name: str) -> str:
    match = re.search(rf"^{name}\s*:?=\s*(.+)$", MAKEFILE, re.MULTILINE)
    assert match, f"{name} is not in the Makefile"
    return match.group(1).strip()


def test_v2s_compose_files_mirror_the_makefile() -> None:
    """`compose_digest` covers exactly what the Makefile layers, or a bundle names a world the
    Makefile never brought up."""
    files = re.findall(r"-f\s+(\S+)", _makefile_var("COMPOSE_WORLD_V2_FILES"))
    assert tuple(files) == WORLDS["v2"].compose_files


def test_v1s_compose_files_mirror_the_makefile() -> None:
    files = re.findall(r"-f\s+(\S+)", _makefile_var("COMPOSE_WORLD_FILES"))
    assert tuple(files) == WORLDS["v1"].compose_files


def test_v2s_demo_version_is_the_makefiles_pin() -> None:
    """v2's `.env` says `DEMO_VERSION=latest`; the Makefile pins the tag in the environment. A
    compose call without it recreates a service on whatever `latest` is that day."""
    assert WORLDS["v2"].compose_env == {"DEMO_VERSION": _makefile_var("OTEL_DEMO_V2_VERSION")}


def test_compose_calls_carry_the_worlds_environment(on_v2: None, tmp_path: Path) -> None:
    runner = FakeRunner()
    ComposeCli(runner, InjectorSettings(world_dir=tmp_path)).recreate("kafka")
    call = runner.calls[-1]
    assert call.env == {"DEMO_VERSION": "2.2.0"}
    assert call.cwd == tmp_path
    assert "../compose/telemetry-v2.yml" in call.args


def test_compose_digest_hashes_the_worlds_own_files(on_v2: None, tmp_path: Path) -> None:
    """The fault T7.0 #6 was opened for: v1's files hashed into a v2 bundle's manifest."""
    for name in WORLDS["v2"].compose_files:
        path = (tmp_path / name).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n")
    digest = provenance.compose_digest(InjectorSettings(world_dir=tmp_path))
    assert digest is not None
    # The same three files under v1's names would be a different world; the digest must see
    # the v2 files and nothing else.
    hashed = provenance._digest_of([(tmp_path / n).resolve() for n in WORLDS["v2"].compose_files])
    assert digest == hashed


# --- the naming map ---------------------------------------------------------------------------


def test_v2s_map_is_the_identity_and_v1s_is_not() -> None:
    assert all(k == v for k, v in SERVICE_CONTAINERS_V2.items())
    assert any(k != v for k, v in SERVICE_CONTAINERS.items())


def test_canonical_service_follows_the_world(on_v2: None) -> None:
    """On v1, `load-generator` is the container behind service `loadgenerator`. On v2 it is the
    service, and reading v1's map would name a service v2 does not have."""
    assert canonical_service("load-generator") == "load-generator"
    assert service_containers() is SERVICE_CONTAINERS_V2
    assert container_services()["kafka"] == "kafka"


def test_canonical_service_still_collapses_v1_names_on_v1(on_v1: None) -> None:
    assert canonical_service("load-generator") == "loadgenerator"
    assert canonical_service("cart-service") == "cartservice"


def test_v2s_map_matches_the_clone_when_it_is_present() -> None:
    """Drift guard, the v2 twin of `test_injector_world`'s. Skips where the clone is absent."""
    layout = WORLDS["v2"]
    paths = [(REPO_ROOT / layout.clone_dir / name).resolve() for name in layout.compose_files]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        pytest.skip(f"v2 world not cloned: {missing[0]}")
    declared: dict[str, str] = {}
    for path in paths:
        services = yaml.safe_load(path.read_text()).get("services") or {}
        for name, body in services.items():
            body = body or {}
            if body.get("profiles"):
                continue
            declared[name] = body.get("container_name", name)
    assert declared == SERVICE_CONTAINERS_V2, "v2's naming has moved under injector.world"


# --- definitions carry their world --------------------------------------------------------------


def _v2_definition(
    target: str, fault_class: FaultClass = FaultClass.PROCESS_FREEZE
) -> FaultDefinition:
    return FaultDefinition(
        id="v2-freeze", fault_class=fault_class, target=target, description="t", world="v2"
    )


def test_a_definition_is_validated_against_its_own_worlds_names() -> None:
    check_target(_v2_definition("product-catalog"))  # a v2 container name
    with pytest.raises(CatalogError, match="not a name in the world"):
        check_target(_v2_definition("product-catalog-service"))  # v1's, not v2's


def test_every_definition_names_a_world_the_injector_knows() -> None:
    from injector.catalog import CATALOG

    assert {d.world for d in CATALOG} <= set(WORLDS)
    v2 = [d for d in CATALOG if d.world == "v2"]
    assert all(d.id.startswith("v2-") for d in v2), "v2 ids say so, as the attempts' targets do"
    assert all(d.target in SERVICE_CONTAINERS_V2 for d in v2)


def test_the_engine_refuses_to_start_a_definition_on_another_world(
    on_v1: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A v2 fault on a v1 injector addresses nothing, or the wrong thing where names collide."""
    from injector import catalog

    v2_def = _v2_definition("product-catalog")
    monkeypatch.setattr(
        catalog, "by_id", lambda fault_id: v2_def if fault_id == v2_def.id else None
    )
    monkeypatch.setattr("injector.engine.by_id", catalog.by_id)
    engine = Engine(
        InjectorSettings(world_dir=tmp_path, state_dir=tmp_path / ".faultline"),
        runner=FakeRunner(),
        clock=lambda: datetime(2026, 9, 24, tzinfo=UTC),
    )
    with pytest.raises(InjectorError, match="cannot be injected here"):
        engine.start("v2-freeze")
