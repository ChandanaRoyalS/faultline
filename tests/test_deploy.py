"""Guards on the deployment's configuration (T5.5).

**None of this proves the deployment works.** A compose file that parses is not a site that
serves, and only §3.4 of `deploy/README.md`, run against a real VM, settles that.

What these do prove is that the four failures which are *invisible until the VM is public* are not
present in the committed files. Each one has already happened somewhere in this project or is one
character away from happening:

| guard | what it would look like in production |
|---|---|
| no `ports:` on postgres or the app | a database, or a plaintext credential, open to the internet |
| the app is started with `--postgres-dsn` | the URL serves `/healthz` and 404s the screen |
| `Dockerfile` starts a server | a container that exits 0 on boot and restarts forever |
| every `${VAR}` is in `env.example` | the deploy stops, naming a variable nobody documented |

The last is the one this codebase keeps re-learning: the Dockerfile's `CMD` printed a version
string and exited from T0 until T5.5, because nothing ever started the image.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY = REPO_ROOT / "deploy"
COMPOSE = DEPLOY / "compose.yml"
CADDYFILE = DEPLOY / "Caddyfile"
ENV_EXAMPLE = DEPLOY / "env.example"
DOCKERFILE = REPO_ROOT / "Dockerfile"

yaml = pytest.importorskip("yaml", reason="pyyaml is a dev dependency; the guards need a parser")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text())


# --- nothing is published that should not be ----------------------------------------------------


@pytest.mark.parametrize("service", ["postgres", "faultline"])
def test_only_caddy_publishes_a_port(compose: dict, service: str) -> None:
    """The difference between this file and `docker-compose.yml`, and the reason it is a separate
    file rather than another profile.

    Development publishes 5432, 6379 and 9000 on the host for convenience. The same lines on a
    public VM are a database and an object store on the internet, and an exposure that depends on
    remembering which profile is selected is one flag away from an incident of its own.
    """
    assert "ports" not in compose["services"][service], (
        f"{service} publishes a host port. Only caddy may: it terminates TLS, and basic auth "
        "over plain HTTP is a published password."
    )


def test_caddy_is_the_only_way_in(compose: dict) -> None:
    published = {
        name: service.get("ports")
        for name, service in compose["services"].items()
        if service.get("ports")
    }

    assert set(published) == {"caddy"}
    assert set(published["caddy"]) == {"80:80", "443:443"}


def test_the_platform_is_reachable_from_caddy_without_being_public(compose: dict) -> None:
    """`expose` is the compose network only. Dropping it would still work - compose networks reach
    every port - so this asserts the intent is written down, not that it is load-bearing."""
    assert compose["services"]["faultline"]["expose"] == ["8000"]
    assert "faultline:8000" in CADDYFILE.read_text()


# --- the read surface is actually mounted -------------------------------------------------------


def test_the_deployment_starts_the_read_surface(compose: dict) -> None:
    """Without `--postgres-dsn` the process is T2.1's receiver alone: the URL would answer
    `/healthz`, 404 the screen, and look like a successful deployment."""
    command = compose["services"]["faultline"]["command"]

    assert "--postgres-dsn" in command
    dsn = command[command.index("--postgres-dsn") + 1]
    assert dsn.startswith("postgresql://")
    assert "@postgres:5432/" in dsn, "the DSN must name the compose service, not localhost"


def test_the_credential_is_passed_and_has_no_default(compose: dict) -> None:
    """`assemble` raises before it connects if the password is unset, so a deployment that forgot
    it fails at boot rather than serving. This asserts compose does not paper over that with a
    default value."""
    environment = compose["services"]["faultline"]["environment"]

    assert environment["FAULTLINE_API_PASSWORD"].startswith("${FAULTLINE_API_PASSWORD:?"), (
        "the password must be `${VAR:?message}` - a `:-default` here would put a known "
        "credential on every deployment that copied this file"
    )


def test_the_database_password_has_no_default_either(compose: dict) -> None:
    assert compose["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"].startswith(
        "${POSTGRES_PASSWORD:?"
    )


def test_no_committed_file_carries_the_development_password() -> None:
    """`faultline-dev` is in `docker-compose.yml`, in this repository, on a public GitHub.

    **Comments excluded, and that is not a loophole.** The first version of this checked whole
    files and failed on `env.example`'s own line telling the operator not to reuse that password -
    a guard firing on the warning against the thing it guards against. Prose naming the danger is
    the documentation working; a value is the danger.
    """
    for path in (COMPOSE, ENV_EXAMPLE, CADDYFILE, DEPLOY / "README.md"):
        live = [
            line
            for line in path.read_text().splitlines()
            if "faultline-dev" in line and not line.lstrip().startswith(("#", ">", "*", "-"))
        ]
        assert live == [], f"{path.name} carries the dev password: {live}"


# --- the image starts something -----------------------------------------------------------------


def test_the_image_starts_a_server_rather_than_printing_a_version() -> None:
    """From T0 until T5.5 the `CMD` printed a version string and exited, because nothing ever ran
    the image. `deploy/` is the first thing that would have, and a container that exits 0 on boot
    under `restart: unless-stopped` is an infinite restart loop that logs a success message."""
    body = DOCKERFILE.read_text()
    cmd = re.search(r"^CMD (.+)$", body, re.MULTILINE)

    assert cmd is not None, "the Dockerfile has no CMD"
    assert "faultline-ingest" in cmd.group(1)
    assert "platform arrives at" not in body, "the T2.1 placeholder CMD is still here"


# --- every variable the deployment needs is documented -------------------------------------------


def documented() -> set[str]:
    return {
        line.split("=", 1)[0].strip()
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }


def test_every_interpolated_variable_is_in_the_example() -> None:
    """`compose.yml` uses `${VAR:?message}`, so an undocumented variable stops the deployment with
    an error naming something the operator has never seen."""
    referenced = set(re.findall(r"\$\{([A-Z_][A-Z0-9_]*)[:?}-]", COMPOSE.read_text()))

    assert referenced <= documented(), (
        f"undocumented in deploy/env.example: {sorted(referenced - documented())}"
    )


def test_the_example_holds_no_values() -> None:
    """A filled-in example is a credential, and the one thing worse than no example is one whose
    placeholder password reaches production because it looked like a default."""
    filled = [
        line
        for line in ENV_EXAMPLE.read_text().splitlines()
        if "=" in line
        and not line.lstrip().startswith("#")
        and line.split("=", 1)[1].strip()
        # The username is not a secret and a working default saves a step.
        and not line.startswith("FAULTLINE_API_USER=")
    ]

    assert filled == [], f"deploy/env.example carries values: {filled}"


def test_the_secrets_are_ignored() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text()

    assert "deploy/.env" in ignored
    assert "deploy/snapshot.sql.gz" in ignored


# --- the rehearsal changes only what it claims to ------------------------------------------------


def test_the_rehearsal_only_moves_the_port_and_stops_caddy() -> None:
    """The rehearsal exists so the deployment gets run before a VM exists. It is worth nothing if
    it rehearses a different deployment - so it may change the two things its own header names and
    no others."""
    override = yaml.safe_load((DEPLOY / "compose.rehearsal.yml").read_text())

    assert set(override["services"]) == {"caddy", "faultline"}
    assert override["services"]["caddy"] == {"deploy": {"replicas": 0}}
    assert override["services"]["faultline"] == {"ports": ["8001:8000"]}


def test_the_rehearsal_does_not_collide_with_make_ui() -> None:
    """`make ui` and the development receiver both use 8000. A rehearsal that collided would look
    like a deployment failure and be debugged as one."""
    override = yaml.safe_load((DEPLOY / "compose.rehearsal.yml").read_text())
    published = override["services"]["faultline"]["ports"][0].split(":")[0]

    assert published != "8000"


def test_no_snapshot_was_committed() -> None:
    """It carries the monitored world's telemetry - every log line an agent quoted."""
    assert not list(DEPLOY.glob("snapshot.sql*"))
