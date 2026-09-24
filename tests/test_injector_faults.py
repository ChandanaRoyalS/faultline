"""Each fault class breaks one thing and puts it back, with no live world involved."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evalharness.scenario import FaultClass
from injector import faults
from injector.catalog import CATALOG, by_id
from injector.docker import CommandError, ComposeCli, DockerCli
from injector.faults import (
    FAULT_TYPES,
    BadConfigFault,
    BadDeployFault,
    DatastoreCorruptionFault,
    DependencyLatencyFault,
    DiskFillFault,
    FaultUsageError,
    FeatureFlagFault,
    NetworkPartitionFault,
    ProcessFreezeFault,
    ResourceExhaustionFault,
    build_handlers,
)
from injector.models import (
    ComposeServiceRestore,
    CorruptionRestore,
    CpuQuotaRestore,
    DiskFillRestore,
    FaultDefinition,
    FlagRestore,
    MemoryLimitRestore,
    NetworkRestore,
    PauseRestore,
    PumbaRestore,
)
from injector.settings import InjectorSettings
from tests.fakes import FakeRunner, RecordedCall

ALIVE = {"{{.State.Running}}": "true\n"}
"""FakeRunner stdout making the pumba sidecar look like it survived startup."""


@pytest.fixture(autouse=True)
def instant_sidecar_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The recorder waits 4s for the sidecar to settle; the tests must not."""
    monkeypatch.setattr(faults, "SIDECAR_SETTLE_SECONDS", 0)


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


def squeeze(runner: FakeRunner, settings: InjectorSettings) -> ResourceExhaustionFault:
    """The resource_exhaustion handler: memory goes through docker, CPU through compose."""
    return ResourceExhaustionFault(DockerCli(runner), ComposeCli(runner, settings), settings)


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


def test_the_handler_registry_and_the_type_list_agree(settings: InjectorSettings) -> None:
    """target_kind() reads FAULT_TYPES; inject() reads build_handlers(). They must match."""
    runner = FakeRunner()
    handlers = build_handlers(DockerCli(runner), ComposeCli(runner, settings), settings)

    assert {t.fault_class for t in FAULT_TYPES} == set(handlers)
    assert {type(h) for h in handlers.values()} == set(FAULT_TYPES)


# --- resource_exhaustion ----------------------------------------------------


def test_memory_squeeze_records_the_limit_it_overwrote(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"inspect": "838860800 -1\n"})
    outcome = squeeze(runner, settings).inject(definition("recommendation-memory-squeeze"))

    assert runner.argv("update") == (
        "docker",
        "update",
        "--memory",
        "32m",
        "--memory-swap",
        "32m",
        "recommendation-service",
    )
    assert isinstance(outcome.restore, MemoryLimitRestore)
    assert outcome.restore.memory_bytes == 838860800
    assert "800M -> 32m" in outcome.changes[0]


def test_memory_restore_puts_the_original_bytes_back(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    squeeze(runner, settings).restore(
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


def test_memory_restore_omits_an_unset_swap_ceiling(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    squeeze(runner, settings).restore(
        MemoryLimitRestore(container="cart-service", memory_bytes=419430400, memory_swap_bytes=0)
    )

    assert "--memory-swap" not in runner.argv("update")


def test_memory_restore_is_a_no_op_when_the_container_is_gone(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    changes = squeeze(runner, settings).restore(
        MemoryLimitRestore(container="ghost", memory_bytes=1, memory_swap_bytes=0)
    )

    assert not runner.called("update")
    assert "nothing to restore" in changes[0]


def test_ad_memory_squeeze_targets_the_container_below_its_jvm_working_set(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(stdout={"inspect": "734003200 -1\n"})
    outcome = squeeze(runner, settings).inject(definition("ad-memory-squeeze"))

    assert runner.argv("update") == (
        "docker",
        "update",
        "--memory",
        "256m",
        "--memory-swap",
        "256m",
        "ad-service",
    ), "the container name, not the compose service - they differ in this world"
    assert isinstance(outcome.restore, MemoryLimitRestore)
    assert outcome.restore.memory_bytes == 734003200, "the 700M ceiling the arm64 override sets"


def test_cpu_throttle_inspects_the_quota_before_it_overwrites_it(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(stdout={"ps --quiet": "c0ffee\n", "NanoCpus": "2000000000\n"})
    outcome = squeeze(runner, settings).inject(definition("currency-cpu-throttle"))

    assert runner.argv("ps")[-2:] == ("--quiet", "currencyservice"), (
        "the container behind a compose service has a different name; ask compose for it"
    )
    assert runner.argv("{{.HostConfig.NanoCpus}}")[-1] == "c0ffee"
    inspect_index = next(i for i, c in enumerate(runner.calls) if "NanoCpus" in " ".join(c.args))
    up_index = next(i for i, c in enumerate(runner.calls) if "up" in c.args)
    assert inspect_index < up_index, "the pre-fault quota is gone once the override is on"

    assert isinstance(outcome.restore, CpuQuotaRestore)
    assert outcome.restore.nano_cpus == 2000000000
    assert "2 -> 0.05" in outcome.changes[0]


def test_cpu_throttle_writes_the_quota_as_a_deploy_limit(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"ps --quiet": "c0ffee\n", "NanoCpus": "0\n"})
    outcome = squeeze(runner, settings).inject(definition("currency-cpu-throttle"))

    assert isinstance(outcome.restore, CpuQuotaRestore)
    override = Path(outcome.restore.override_file)
    body = yaml.safe_load(override.read_text())
    assert body["services"]["currencyservice"] == {
        "deploy": {"resources": {"limits": {"cpus": "0.05"}}}
    }
    assert str(override) in runner.argv("up"), "compose only reads the quota when it creates"
    assert "unlimited -> 0.05" in outcome.changes[0]


def test_cpu_throttle_restore_drops_the_override_and_names_the_old_quota(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(stdout={"ps --quiet": "c0ffee\n", "NanoCpus": "2000000000\n"})
    fault = squeeze(runner, settings)
    outcome = fault.inject(definition("currency-cpu-throttle"))
    assert isinstance(outcome.restore, CpuQuotaRestore)
    override = Path(outcome.restore.override_file)

    runner.calls.clear()
    changes = fault.restore(outcome.restore)

    assert not override.exists()
    recreate = runner.argv("up")
    files = [recreate[i + 1] for i, a in enumerate(recreate) if a == "-f"]
    assert files == list(settings.compose_files), "restore must use the world's files alone"
    assert "2 at inject time" in changes[-1]


def test_cpu_throttle_refuses_a_service_that_is_not_running(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"ps --quiet": "\n"})

    with pytest.raises(FaultUsageError, match="not running"):
        squeeze(runner, settings).inject(definition("currency-cpu-throttle"))

    assert not runner.called("up"), "no capture, no injection - restore would have nothing to say"


def test_resource_exhaustion_refuses_to_squeeze_two_resources_at_once(
    settings: InjectorSettings,
) -> None:
    both = FaultDefinition(
        id="both-at-once",
        fault_class=FaultClass.RESOURCE_EXHAUSTION,
        target="currencyservice",
        description="two incidents wearing one label",
        params={"memory": "48m", "cpus": "0.05"},
    )
    with pytest.raises(FaultUsageError, match="one resource at a time"):
        squeeze(FakeRunner(), settings).inject(both)


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
        "ffs-stub:2",
        "--build-arg",
        "SERVER=server_v2.py",
        str(settings.ffs_stub_context),
    )
    assert runner.calls[0].args[1] == "build", "build before deploy, or compose pulls a stale tag"

    assert isinstance(outcome.restore, ComposeServiceRestore)
    override = Path(outcome.restore.override_file)
    body = yaml.safe_load(override.read_text())
    assert body["services"]["featureflagservice"] == {"image": "ffs-stub:2"}
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


def test_crashloop_builds_the_crashing_server_and_swaps_to_it(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner()
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    outcome = fault.inject(definition("flag-service-crashloop"))

    assert runner.argv("build") == (
        "docker",
        "build",
        "--tag",
        "ffs-stub:3",
        "--build-arg",
        "SERVER=server_v3.py",
        str(settings.ffs_stub_context),
    )
    assert isinstance(outcome.restore, ComposeServiceRestore)
    body = yaml.safe_load(Path(outcome.restore.override_file).read_text())
    assert body["services"]["featureflagservice"] == {"image": "ffs-stub:3"}


def test_crashloop_restores_the_same_way_as_the_other_image_swaps(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner()
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    outcome = fault.inject(definition("flag-service-crashloop"))

    runner.calls.clear()
    fault.restore(outcome.restore)

    assert not Path(outcome.restore.override_file).exists()
    recreate = runner.argv("up")
    files = [recreate[i + 1] for i, a in enumerate(recreate) if a == "-f"]
    assert files == list(settings.compose_files), (
        "the flag service comes back on ffs-stub:1, as the world declares it"
    )


def test_every_bad_deploy_is_a_different_shape_of_failure(settings: InjectorSettings) -> None:
    """Same class, five signatures: serves-then-fails, flaps, never starts, and two that
    start and then die - one on memory (exit 137) and one on configuration (exit 1)."""
    bad_deploys = [f for f in CATALOG if f.fault_class is FaultClass.BAD_DEPLOY]

    assert {f.id for f in bad_deploys} == {
        "flag-service-bad-deploy",
        "flag-service-crashloop",
        "cart-bad-image-tag",
        "email-wrong-image",
        "shipping-wrong-image",
    }
    images = {str(f.params["image"]) for f in bad_deploys}
    assert len(images) == len(bad_deploys), "each has to deploy a distinct image, or two coincide"

    built = [f for f in bad_deploys if "server" in f.params]
    assert {str(f.params["server"]) for f in built} == {"server_v2.py", "server_v3.py"}, (
        "the two built variants must come from different sources in the stub context"
    )
    # A bare image swap must say which way it is expected to go; inferring it mislabelled
    # a deploy whose image resolves as one whose image does not.
    swaps = [f for f in bad_deploys if "server" not in f.params]
    assert {str(f.params.get("expect_start")) for f in swaps} == {"yes", "no"}, (
        "the image-swap deploys must declare expect_start, and cover both outcomes"
    )


def test_bad_image_tag_stops_the_service_before_pointing_it_at_the_missing_tag(
    settings: InjectorSettings,
) -> None:
    # The `up` that fails is the one carrying our override; compose cannot resolve
    # the tag. That failure is the fault, not an error to roll back.
    runner = FakeRunner(returncodes={"cart-bad-image-tag.yml": 1})
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    outcome = fault.inject(definition("cart-bad-image-tag"))

    assert not runner.called("build"), "nothing to build; the tag is meant to resolve nowhere"
    stop_index = next(i for i, c in enumerate(runner.calls) if "stop" in c.args)
    up_index = next(i for i, c in enumerate(runner.calls) if "up" in c.args)
    assert stop_index < up_index, (
        "compose resolves images before it touches containers, so a failed up would "
        "otherwise leave the healthy container running and inject no fault at all"
    )
    assert runner.argv("stop")[-1] == "cartservice"

    assert isinstance(outcome.restore, ComposeServiceRestore)
    override = Path(outcome.restore.override_file)
    assert override.exists(), "the override is the evidence, and the thing stop must remove"
    body = yaml.safe_load(override.read_text())
    assert body["services"]["cartservice"] == {
        "image": "ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2"
    }


def test_bad_image_tag_restore_brings_the_service_back_on_the_world_image(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(returncodes={"cart-bad-image-tag.yml": 1})
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    outcome = fault.inject(definition("cart-bad-image-tag"))

    runner.calls.clear()
    fault.restore(outcome.restore)

    assert not Path(outcome.restore.override_file).exists()
    recreate = runner.argv("up")
    files = [recreate[i + 1] for i, a in enumerate(recreate) if a == "-f"]
    assert files == list(settings.compose_files)


def test_a_built_deploy_still_rolls_back_when_its_recreate_fails(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(returncodes={"flag-service-bad-deploy.yml": 1})
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)

    with pytest.raises(CommandError):
        fault.inject(definition("flag-service-bad-deploy"))

    override = settings.override_dir / "flag-service-bad-deploy.yml"
    assert not override.exists(), (
        "a failed build-and-deploy leaves no restore record, so nothing would clean it up later"
    )


def test_bad_image_tag_refuses_to_pass_if_the_tag_turns_out_to_resolve(
    settings: InjectorSettings,
) -> None:
    # Nothing fails: upstream published the tag and the service comes up healthy.
    runner = FakeRunner()
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)

    with pytest.raises(FaultUsageError, match="no fault was injected"):
        fault.inject(definition("cart-bad-image-tag"))

    assert not (settings.override_dir / "cart-bad-image-tag.yml").exists(), (
        "a fault that did not fire must leave nothing behind, or a later scenario is "
        "scored against a world with a stray override on it"
    )


def test_bad_deploy_refuses_a_definition_with_no_image(settings: InjectorSettings) -> None:
    broken = FaultDefinition(
        id="no-image",
        fault_class=FaultClass.BAD_DEPLOY,
        target="cartservice",
        description="missing its params",
    )
    runner = FakeRunner()
    fault = BadDeployFault(DockerCli(runner), ComposeCli(runner, settings), settings)
    with pytest.raises(FaultUsageError, match="image"):
        fault.inject(broken)


# --- dependency_latency -----------------------------------------------------


def test_latency_runs_pumba_with_a_pinned_tc_image(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout=ALIVE)
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
    runner = FakeRunner(stdout=ALIVE)
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


def test_productcatalog_latency_delays_its_own_container(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout=ALIVE)
    DependencyLatencyFault(DockerCli(runner), settings).inject(
        definition("productcatalog-dependency-latency")
    )

    argv = runner.argv("run")
    assert argv[argv.index("--time") + 1] == "300"
    assert argv[-1] == "product-catalog-service", "the container name, not the compose service"
    assert "faultline-pumba-productcatalog-dependency-latency" in argv, (
        "one sidecar per fault id, or two latency faults would fight over one helper"
    )


# --- bad_config -------------------------------------------------------------


def test_bad_config_writes_a_single_wrong_variable(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    outcome = BadConfigFault(ComposeCli(runner, settings), settings).inject(
        definition("cart-redis-misconfig")
    )

    assert isinstance(outcome.restore, ComposeServiceRestore)
    body = yaml.safe_load(Path(outcome.restore.override_file).read_text())
    assert body["services"]["cartservice"] == {"environment": {"REDIS_ADDR": "redis-cart:6380"}}
    # Compose validates its own schema: anything but `services` at the top level
    # is rejected outright, so provenance has to live in a comment.
    assert list(body) == ["services"]
    assert Path(outcome.restore.override_file).read_text().startswith("# generated by")


def test_checkout_misconfig_points_only_the_caller_at_a_dead_host(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner()
    outcome = BadConfigFault(ComposeCli(runner, settings), settings).inject(
        definition("checkout-currency-misconfig")
    )

    assert isinstance(outcome.restore, ComposeServiceRestore)
    body = yaml.safe_load(Path(outcome.restore.override_file).read_text())
    assert body["services"]["checkoutservice"] == {
        "environment": {"CURRENCY_SERVICE_ADDR": "currencyservice-canary:7001"}
    }
    assert runner.argv("up")[-1] == "checkoutservice", (
        "currency itself stays healthy; only its caller is misconfigured"
    )


def test_flag_failure_turns_on_one_flag_at_the_stub(settings: InjectorSettings) -> None:
    runner = FakeRunner()
    outcome = BadConfigFault(ComposeCli(runner, settings), settings).inject(
        definition("product-catalog-flag-failure")
    )

    assert isinstance(outcome.restore, ComposeServiceRestore)
    body = yaml.safe_load(Path(outcome.restore.override_file).read_text())
    assert body["services"]["featureflagservice"] == {
        "environment": {"FAULTLINE_ENABLED_FLAGS": "productCatalogFailure"}
    }
    assert "--no-deps" in runner.argv("up"), (
        "the flag service's own dependencies are not part of this incident"
    )


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
        squeeze(FakeRunner(), settings).restore(
            PumbaRestore(helper_container="faultline-pumba-cart-dependency-latency")
        )


def test_a_sidecar_that_dies_on_startup_fails_the_injection(settings: InjectorSettings) -> None:
    """Measured: pumba died at startup and the fault reported success for thirteen minutes.

    `docker run --detach` returns when the container is created, not when it works. Pumba
    enumerates every container on the host and exits if one references a missing image
    (ADR-0007), which happens before it touches its target.
    """
    runner = FakeRunner(
        stdout={"{{.State.Running}}": "false\n", "logs": 'level=fatal msg="no such image"\n'}
    )

    with pytest.raises(FaultUsageError) as caught:
        DependencyLatencyFault(DockerCli(runner), settings).inject(
            definition("cart-dependency-latency")
        )

    message = str(caught.value)
    assert "has NOT been injected" in message, "the operator must not think a delay exists"
    assert "no such image" in message, "the sidecar's own logs are the diagnosis"
    assert runner.called("rm", "--force", "faultline-pumba-cart-dependency-latency"), (
        "the dead sidecar must be cleaned up, or the next run's cleanup looks like it "
        "removed a working one"
    )


def test_a_sidecar_that_survives_is_left_alone(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout=ALIVE)

    outcome = DependencyLatencyFault(DockerCli(runner), settings).inject(
        definition("cart-dependency-latency")
    )

    assert isinstance(outcome.restore, PumbaRestore)
    assert not runner.called("logs"), "no need to read logs from a healthy sidecar"


# --- T7.0's five: feature_flag ---------------------------------------------------------------


def _flagd_file(settings: InjectorSettings, flags: dict) -> Path:
    path = settings.world_dir / "src" / "flagd" / "demo.flagd.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"flags": flags}, indent=2) + "\n")
    return path


def _flag_def(fault_id: str = "product-catalog-flag", **params: object) -> FaultDefinition:
    body = {"flag": "productCatalogFailure", "variant": "on", **params}
    return FaultDefinition(
        id=fault_id,
        fault_class=FaultClass.FEATURE_FLAG,
        target="product-catalog",
        description="flip a flag",
        params=body,  # type: ignore[arg-type]
    )


def test_feature_flag_flips_the_default_variant_and_captures_the_old_one(
    settings: InjectorSettings,
) -> None:
    _flagd_file(
        settings,
        {
            "productCatalogFailure": {
                "defaultVariant": "off",
                "variants": {"on": True, "off": False},
            }
        },
    )
    outcome = FeatureFlagFault(settings).inject(_flag_def())

    assert isinstance(outcome.restore, FlagRestore)
    assert outcome.restore.previous_variant == "off"
    written = json.loads(Path(outcome.restore.flag_file).read_text())
    assert written["flags"]["productCatalogFailure"]["defaultVariant"] == "on"


def test_feature_flag_restore_puts_the_previous_variant_back(settings: InjectorSettings) -> None:
    flags = {
        "productCatalogFailure": {"defaultVariant": "off", "variants": {"on": True, "off": False}}
    }
    path = _flagd_file(settings, flags)
    flag = FeatureFlagFault(settings)
    outcome = flag.inject(_flag_def())
    flag.restore(outcome.restore)
    written = json.loads(path.read_text())
    assert written["flags"]["productCatalogFailure"]["defaultVariant"] == "off"


def test_feature_flag_records_no_change(settings: InjectorSettings) -> None:
    assert FeatureFlagFault.records_change is False


def test_feature_flag_refuses_a_flag_that_is_not_in_the_file(settings: InjectorSettings) -> None:
    _flagd_file(settings, {"someOtherFlag": {"defaultVariant": "off", "variants": {"off": False}}})
    with pytest.raises(FaultUsageError):
        FeatureFlagFault(settings).inject(_flag_def())


def test_feature_flag_refuses_to_flip_to_the_value_already_set(settings: InjectorSettings) -> None:
    _flagd_file(
        settings,
        {"productCatalogFailure": {"defaultVariant": "on", "variants": {"on": True, "off": False}}},
    )
    with pytest.raises(FaultUsageError):
        FeatureFlagFault(settings).inject(_flag_def())


def test_feature_flag_restore_is_a_no_op_when_the_file_is_gone(settings: InjectorSettings) -> None:
    changes = FeatureFlagFault(settings).restore(
        FlagRestore(
            flag_file=str(settings.world_dir / "gone.json"), flag="x", previous_variant="off"
        )
    )
    assert "nothing to restore" in changes[0]


# --- process_freeze ---------------------------------------------------------------------------


def _def(fault_id: str, fault_class: FaultClass, target: str, **params: object) -> FaultDefinition:
    return FaultDefinition(
        id=fault_id,
        fault_class=fault_class,
        target=target,
        description="t",
        params=params,  # type: ignore[arg-type]
    )


def test_process_freeze_pauses_the_container_and_verifies_it(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.State.Running}}": "true\n", "{{.State.Paused}}": "true\n"})
    outcome = ProcessFreezeFault(DockerCli(runner)).inject(
        _def("cart-freeze", FaultClass.PROCESS_FREEZE, "cart")
    )
    assert runner.argv("pause", "cart") == ("docker", "pause", "cart")
    assert isinstance(outcome.restore, PauseRestore)
    assert outcome.restore.container == "cart"


def test_process_freeze_fails_if_pause_did_not_take(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.State.Running}}": "true\n", "{{.State.Paused}}": "false\n"})
    with pytest.raises(FaultUsageError, match="NOT been injected"):
        ProcessFreezeFault(DockerCli(runner)).inject(
            _def("cart-freeze", FaultClass.PROCESS_FREEZE, "cart")
        )


def test_process_freeze_refuses_a_container_that_is_not_running(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.State.Running}}": "false\n"})
    with pytest.raises(FaultUsageError):
        ProcessFreezeFault(DockerCli(runner)).inject(
            _def("cart-freeze", FaultClass.PROCESS_FREEZE, "cart")
        )


def test_process_freeze_restore_unpauses(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.Id}}": "abc\n", "{{.State.Paused}}": "true\n"})
    changes = ProcessFreezeFault(DockerCli(runner)).restore(PauseRestore(container="cart"))
    assert runner.called("unpause", "cart")
    assert "resumed" in changes[0]


def test_process_freeze_restore_is_a_no_op_when_gone(settings: InjectorSettings) -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    changes = ProcessFreezeFault(DockerCli(runner)).restore(PauseRestore(container="cart"))
    assert "gone" in changes[0]
    assert not runner.called("unpause")


# --- network_partition ------------------------------------------------------------------------

_ON_NET = {"Networks": '{"opentelemetry-demo": {"Aliases": ["product-catalog", "abc123"]}}\n'}
_OFF_NET = {"Networks": "{}\n"}


class _SequencedNetworks(FakeRunner):
    """A FakeRunner whose network-inspect answers come from a queue: on the net, then off it.

    The partition handler inspects once to capture aliases and once to verify the disconnect
    took, and those two reads must differ. Every other command falls through to FakeRunner.
    """

    def __init__(self, network_bodies: list[str]) -> None:
        super().__init__(stdout={"{{.Id}}": "abc\n"})
        self._network_bodies = list(network_bodies)

    def run(self, args, *, cwd=None, check=True):  # type: ignore[no-untyped-def]
        if "Networks" in " ".join(args) and self._network_bodies:
            from injector.docker import CommandResult

            self.calls.append(RecordedCall(args=tuple(args), cwd=cwd, check=check))
            return CommandResult(
                args=tuple(args), returncode=0, stdout=self._network_bodies.pop(0), stderr=""
            )
        return super().run(args, cwd=cwd, check=check)


def test_network_partition_disconnects_and_captures_aliases(settings: InjectorSettings) -> None:
    runner = _SequencedNetworks([_ON_NET["Networks"], _OFF_NET["Networks"]])
    outcome = NetworkPartitionFault(DockerCli(runner)).inject(
        _def(
            "pc-partition",
            FaultClass.NETWORK_PARTITION,
            "product-catalog",
            network="opentelemetry-demo",
        )
    )
    assert runner.called("network", "disconnect", "opentelemetry-demo", "product-catalog")
    assert isinstance(outcome.restore, NetworkRestore)
    assert outcome.restore.aliases == ["product-catalog", "abc123"]


def test_network_partition_refuses_a_network_the_container_is_not_on(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(stdout={"Networks": _OFF_NET["Networks"]})
    with pytest.raises(FaultUsageError):
        NetworkPartitionFault(DockerCli(runner)).inject(
            _def(
                "pc-partition",
                FaultClass.NETWORK_PARTITION,
                "product-catalog",
                network="opentelemetry-demo",
            )
        )


def test_network_partition_restore_reconnects_with_the_aliases(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.Id}}": "abc\n", "Networks": _OFF_NET["Networks"]})
    NetworkPartitionFault(DockerCli(runner)).restore(
        NetworkRestore(
            container="product-catalog", network="opentelemetry-demo", aliases=["product-catalog"]
        )
    )
    assert runner.called("network", "connect", "--alias", "product-catalog")


def test_network_partition_restore_is_a_no_op_when_gone(settings: InjectorSettings) -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    changes = NetworkPartitionFault(DockerCli(runner)).restore(
        NetworkRestore(container="product-catalog", network="opentelemetry-demo", aliases=[])
    )
    assert "gone" in changes[0]


# --- datastore_corruption ---------------------------------------------------------------------


def test_corruption_verifies_one_sweep_then_starts_the_loop(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.State.Running}}": "true\n", "EVAL": "225\n"})
    outcome = DatastoreCorruptionFault(DockerCli(runner)).inject(
        _def("cart-corrupt", FaultClass.DATASTORE_CORRUPTION, "valkey-cart")
    )
    # the probe (a single EVAL, not detached) and the loop (sh -c, detached) both ran
    assert runner.called("exec", "valkey-cart", "valkey-cli", "EVAL")
    assert runner.called("exec", "--detach", "valkey-cart", "sh", "-c")
    assert isinstance(outcome.restore, CorruptionRestore)
    assert outcome.restore.flush is True


def test_corruption_fails_if_the_probe_sweep_errors(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.State.Running}}": "true\n"}, returncodes={"EVAL": 1})
    with pytest.raises(FaultUsageError, match="NOT been injected"):
        DatastoreCorruptionFault(DockerCli(runner)).inject(
            _def("cart-corrupt", FaultClass.DATASTORE_CORRUPTION, "valkey-cart")
        )


def test_corruption_restore_stops_the_loop_then_flushes(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.Id}}": "abc\n"})
    changes = DatastoreCorruptionFault(DockerCli(runner)).restore(
        CorruptionRestore(
            container="valkey-cart",
            stop_file="/tmp/faultline-cart-corrupt.stop",
            cli="valkey-cli",
            flush=True,
        )
    )
    assert runner.called("exec", "valkey-cart", "touch", "/tmp/faultline-cart-corrupt.stop")
    assert runner.called("exec", "valkey-cart", "valkey-cli", "FLUSHALL")
    assert any("FLUSHALL" in c for c in changes)


def test_corruption_restore_is_a_no_op_when_gone(settings: InjectorSettings) -> None:
    runner = FakeRunner(returncodes={"inspect": 1})
    changes = DatastoreCorruptionFault(DockerCli(runner)).restore(
        CorruptionRestore(
            container="valkey-cart", stop_file="/tmp/x.stop", cli="valkey-cli", flush=True
        )
    )
    assert "gone" in changes[0]


# --- disk_fill --------------------------------------------------------------------------------

_DF_ROW = "tmpfs 262144 0 262144 0% /tmp/kafka-logs"
_DF = {"df": f"Filesystem 1024-blocks Used Available Capacity Mounted\n{_DF_ROW}\n"}


def test_disk_fill_reads_the_mount_and_fills_it(settings: InjectorSettings) -> None:
    runner = FakeRunner(
        stdout={"{{.State.Running}}": "true\n", **_DF, "dd": "no space left on device\n"}
    )
    outcome = DiskFillFault(DockerCli(runner), ComposeCli(runner, settings)).inject(
        _def(
            "kafka-disk-fill",
            FaultClass.DISK_FILL,
            "kafka",
            service="kafka",
            directory="/tmp/kafka-logs",
            restart_after="accounting,checkout",
        )
    )
    assert runner.called("exec", "kafka", "df", "-P", "-k", "/tmp/kafka-logs")
    assert runner.called("exec", "kafka", "dd", "if=/dev/zero")
    assert isinstance(outcome.restore, DiskFillRestore)
    assert outcome.restore.restart_after == ["accounting", "checkout"]


def test_disk_fill_fails_when_dd_did_not_run_out_of_space(settings: InjectorSettings) -> None:
    runner = FakeRunner(stdout={"{{.State.Running}}": "true\n", **_DF, "dd": "256+0 records out\n"})
    with pytest.raises(FaultUsageError, match="NOT been injected"):
        DiskFillFault(DockerCli(runner), ComposeCli(runner, settings)).inject(
            _def(
                "kafka-disk-fill",
                FaultClass.DISK_FILL,
                "kafka",
                service="kafka",
                directory="/tmp/kafka-logs",
            )
        )


def test_disk_fill_refuses_a_directory_that_is_not_a_mount_point(
    settings: InjectorSettings,
) -> None:
    df = {"df": "Filesystem 1024-blocks Used Available Capacity Mounted\noverlay 999 1 998 1% /\n"}
    runner = FakeRunner(stdout={"{{.State.Running}}": "true\n", **df})
    with pytest.raises(FaultUsageError, match="not a mount point"):
        DiskFillFault(DockerCli(runner), ComposeCli(runner, settings)).inject(
            _def(
                "kafka-disk-fill",
                FaultClass.DISK_FILL,
                "kafka",
                service="kafka",
                directory="/tmp/kafka-logs",
            )
        )


def test_disk_fill_restore_removes_the_file_and_restarts_consumers(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(stdout={"{{.Id}}": "abc\n"})
    changes = DiskFillFault(DockerCli(runner), ComposeCli(runner, settings)).restore(
        DiskFillRestore(
            container="kafka",
            service="kafka",
            fill_file="/tmp/kafka-logs/f.fill",
            restart_after=["accounting"],
        )
    )
    assert runner.called("exec", "kafka", "rm", "-f", "/tmp/kafka-logs/f.fill")
    assert runner.called("restart", "accounting")
    assert any("accounting" in c for c in changes)


def test_disk_fill_restore_recreates_when_the_file_cannot_be_removed(
    settings: InjectorSettings,
) -> None:
    runner = FakeRunner(stdout={"{{.Id}}": "abc\n"}, returncodes={"rm -f": 1})
    changes = DiskFillFault(DockerCli(runner), ComposeCli(runner, settings)).restore(
        DiskFillRestore(
            container="kafka", service="kafka", fill_file="/tmp/kafka-logs/f.fill", restart_after=[]
        )
    )
    assert runner.called("up", "-d", "--no-build", "--no-deps", "--force-recreate", "kafka")
    assert any("recreated" in c for c in changes)


def test_all_five_new_classes_record_no_change() -> None:
    for handler_type in (
        FeatureFlagFault,
        ProcessFreezeFault,
        NetworkPartitionFault,
        DatastoreCorruptionFault,
        DiskFillFault,
    ):
        assert handler_type.records_change is False, handler_type.__name__
    for handler_type in (
        ResourceExhaustionFault,
        BadDeployFault,
        DependencyLatencyFault,
        BadConfigFault,
    ):
        assert handler_type.records_change is True, handler_type.__name__
