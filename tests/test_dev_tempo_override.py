"""The last compose file on every development host, and what it may and may not be (Q77).

`compose/dev-tempo-otlp.override.yml` exists because the platform's daemons run outside Docker on
a development host and need Tempo's OTLP receiver published to reach it - since Q77 they export to
Tempo directly rather than through the world's collector, whose `spanmetrics` made the platform a
service in the world's metrics. It is layered *outside* `compose_digest` on the argument its header
makes: a published port changes nothing a bundle records. That argument holds only while the file
stays exactly as small as it is. These tests are the hold, the same one the Linux gateway shim and
the runner's kafka flag are under.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from evalharness import provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
OVERRIDE = REPO_ROOT / "compose" / provenance.DEV_TEMPO_OTLP_OVERRIDE
HOST_PORT = "4327"
"""Not 4317: that is the collector's published port on a development host, and the whole point
is that the daemons stop talking to it."""


def test_the_override_publishes_one_port_on_one_service_and_does_nothing_else() -> None:
    """**One service, one key, one entry.** Anything more is a change to the world that the digest
    would not see, and at that point the file is a way around ADR-0014 rather than a host shim."""
    override = yaml.safe_load(OVERRIDE.read_text())

    assert set(override) == {"services"}
    assert set(override["services"]) == {"tempo"}
    assert override["services"]["tempo"] == {"ports": [f"{HOST_PORT}:4317"]}


def test_the_override_is_outside_the_digest() -> None:
    from injector.settings import InjectorSettings

    assert OVERRIDE.name not in {Path(n).name for n in InjectorSettings().compose_files}


def test_the_container_port_is_the_receiver_tempo_actually_opens() -> None:
    """`compose/tempo.yaml` is digest-locked and this file is not; if the receiver ever moves,
    this is the line that says the port file is pointing at nothing."""
    tempo = yaml.safe_load((REPO_ROOT / "compose" / "tempo.yaml").read_text())
    grpc = tempo["distributor"]["receivers"]["otlp"]["protocols"]["grpc"]["endpoint"]

    assert grpc.endswith(":4317"), grpc


def test_the_deployment_does_not_use_it_and_does_not_need_to() -> None:
    """On the VM the daemons are containers on the shared network and name `tempo:4317` directly;
    the overlay that puts Tempo there is `deploy/compose.world.yml`. Neither deploy file should
    mention the development port."""
    for name in ("compose.yml", "compose.world.yml", "README.md"):
        assert HOST_PORT not in (REPO_ROOT / "deploy" / name).read_text(), name


def test_the_header_makes_the_argument() -> None:
    """The reason for staying outside the digest has to be on the file, because the file is what
    the next reader opens."""
    text = OVERRIDE.read_text()
    for phrase in ("compose_digest", "host_overrides", "spanmetrics", "ADR-0030", "4327"):
        assert phrase in text, phrase
