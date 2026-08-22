"""Each fault class breaks one thing and puts it back, with no live world involved."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from evalharness.scenario import FaultClass
from injector.catalog import CATALOG, by_id
from injector.docker import ComposeCli, DockerCli
from injector.faults import (
    BadConfigFault,
    BadDeployFault,
    DependencyLatencyFault,
    FaultUsageError,
    ResourceExhaustionFault,
    build_handlers,
)
from injector.models import (
    ComposeServiceRestore,
    FaultDefinition,
    MemoryLimitRestore,
    PumbaRestore,
)
from injector.settings import InjectorSettings
from tests.fakes import FakeRunner


@pytest.fixture
def settings(tmp_path: Path) -> InjectorSettings:
    return InjectorSettings(
        world_dir=tmp_path / "world",
        state_dir=tmp_path / ".faultline",
        ffs_stub_context=tmp_path / "compose" / "ffs-stub",
    )


def definition(fault_id: str) -> FaultDefinition:
    found = by_id(fault_id)
    assert found is not None
    return found


def test_catalog_covers_the_four_classes_exactly() -> None:
    assert {f.fault_class for f in CATALOG} == {
        FaultClass.RESOURCE_EXHAUSTION,
        FaultClass.BAD_DEPLOY,
        FaultClass.DEPENDENCY_LATENCY,
        FaultClass.BAD_CONFIG,
    }
    assert len({f.id for f in CATALOG}) == len(CATALOG), "fault ids must be unique"


def test_every_catalog_entry_has_a_handler(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    handlers = build_handlers(DockerCli(runner), ComposeCli(runner, settings), settings)
    assert all(f.fault_class in handlers for f in CATALOG)


# --- resource_exhaustion ----------------------------------------------------


def test_memory_squeeze_records_the_limit_it_overwrote() -> None:
    runner = FakeRunner(stdout={"inspect": "838860800 -1\n"})
    outcome = ResourceExhaustionFault(DockerCli(runner)).inject(
        definition("recommendation-memory-squeeze")
    )

    assert runner.argv("update") == (
        "docker",
        "update",
        "--memory",
        "64m",
        "--memory-swap",
        "64m",
        "recommendation-service",
    )
    assert isinstance(outcome.restore, MemoryLimitRestore)
    assert outcome.restore.memory_bytes == 838860800
    assert "800M -> 64m" in outcome.changes[0]


def test_memory_restore_puts_the_original_bytes_back() -> None:
    runner = FakeRunner()
    ResourceExhaustionFault(DockerCli(runner)).restore(
        MemoryLimitRestore(
            container="recommendation-service", memory_bytes=838860800, memory_swap_bytes=-1
        )
    )

    assert runner.argv("update") == (
        "docker",
        "update",
        "--memory",
        "838860800",
        "--memory-swap",
        "-1",
        "recommendation-service",
    )


def test_memory_restore_omits_an_unset_swap_ceiling() -> None:
    runner = FakeRunner()
    ResourceExhaustionFault(DockerCli(runner)).restore(
        MemoryLimitRestore(container="cart-service", memory_bytes=419430400, memory_swap_bytes=0)
    )

    assert "--memory-swap" not in runner.argv("update")


def test_memory_restore_is_a_no_op_when_the_container_is_gone() -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    changes = ResourceExhaustionFault(DockerCli(runner)).restore(
        MemoryLimitRestore(container="ghost", memory_bytes=1, memory_swap_bytes=0)
    )

    assert not runner.called("update")
    assert "nothing to restore" in changes[0]


# --- bad_deploy -------------------------------------------------------------


def test_bad_deploy_builds_the_image_then_recreates_the_service(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner()
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    outcome = fault.inject(definition("flag-service-bad-deploy"))

    assert runner.argv("build") == (
        "docker",
        "build",
        "--tag",
        "faultline/ffs-stub:broken",
        "--build-arg",
        "SERVER=server_broken.py",
        str(settings.ffs_stub_context),
    )
    assert runner.calls[0].args[1] == "build", "build before deploy, or compose pulls a stale tag"

    assert isinstance(outcome.restore, ComposeServiceRestore)
    override = Path(outcome.restore.override_file)
    body = yaml.safe_load(override.read_text())
    assert body["services"]["featureflagservice"] == {"image": "faultline/ffs-stub:broken"}
    assert str(override) in runner.argv("up")


def test_bad_deploy_restore_drops_the_override_and_recreates(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    outcome = fault.inject(definition("flag-service-bad-deploy"))
    assert isinstance(outcome.restore, ComposeServiceRestore)
    override = Path(outcome.restore.override_file)

    runner.calls.clear()
    fault.restore(outcome.restore)

    assert not override.exists()
    recreate = runner.argv("up")
    files = [recreate[i + 1] for i, a in enumerate(recreate) if a == "-f"]
    assert files == list(settings.compose_files), "restore must use the world's files alone"


def test_compose_restore_survives_an_override_someone_deleted(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    fault = BadConfigFault(ComposeCli(runner, settings), settings)
    fault.restore(
        ComposeServiceRestore(service="cartservice", override_file=str(settings.override_dir / "x"))
    )

    assert runner.called("up"), "the service is still recreated even if the file is gone"


# --- dependency_latency -----------------------------------------------------


def test_latency_runs_pumba_with_a_pinned_tc_image(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    outcome = DependencyLatencyFault(DockerCli(runner), settings).inject(
        definition("cart-dependency-latency")
    )

    argv = runner.argv("run")
    assert argv[:6] == (
        "docker",
        "run",
        "--detach",
        "--name",
        "faultline-pumba-cart-dependency-latency",
        "--volume",
    )
    assert settings.pumba_image in argv
    assert argv[argv.index("--tc-image") + 1] == settings.tc_image
    assert argv[argv.index("--time") + 1] == "300"
    assert argv[-1] == "cart-service", "pumba matches the container by name, last argument"
    assert isinstance(outcome.restore, PumbaRestore)


def test_latency_clears_a_leftover_sidecar_before_starting(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    DependencyLatencyFault(DockerCli(runner), settings).inject(
        definition("cart-dependency-latency")
    )

    assert runner.calls[0].args[:3] == ("docker", "rm", "--force")


def test_latency_restore_stops_before_removing(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    DependencyLatencyFault(DockerCli(runner), settings).restore(
        PumbaRestore(helper_container="faultline-pumba-cart-dependency-latency")
    )

    verbs = [c.args[1] for c in runner.calls]
    assert verbs == ["inspect", "stop", "rm"], "SIGTERM is what makes pumba revert its netem rule"


def test_latency_restore_is_a_no_op_when_the_sidecar_expired(settings: InjectorSettings) -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    changes = DependencyLatencyFault(DockerCli(runner), settings).restore(
        PumbaRestore(helper_container="faultline-pumba-gone")
    )

    assert not runner.called("stop")
    assert "already gone" in changes[0]


# --- bad_config -------------------------------------------------------------


def test_bad_config_writes_a_single_wrong_variable(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    outcome = BadConfigFault(ComposeCli(runner, settings), settings).inject(
        definition("cart-redis-misconfig")
    )

    assert isinstance(outcome.restore, ComposeServiceRestore)
    body = yaml.safe_load(Path(outcome.restore.override_file).read_text())
    assert body["services"]["cartservice"] == {"environment": {"REDIS_ADDR": "redis-cart:6380"}}


def test_bad_config_refuses_a_definition_with_no_variable(settings: InjectorSettings) -> None:
    broken = FaultDefinition(
        id="no-variable",
        fault_class=FaultClass.BAD_CONFIG,
        target="cartservice",
        description="missing its params",
    )
    with pytest.raises(FaultUsageError, match="env_var"):
        BadConfigFault(ComposeCli(FakeRunner(), settings), settings).inject(broken)


def test_a_handler_refuses_restore_data_from_another_fault_class(
    settings: InjectorSettings,
) -> None:
    with pytest.raises(FaultUsageError):
        ResourceExhaustionFault(DockerCli(FakeRunner())).restore(
            PumbaRestore(helper_container="faultline-pumba-cart-dependency-latency")
        )
