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
import tomllib
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


# --- the deployment is not the developer's platform ----------------------------------------------


def test_the_deployment_has_its_own_compose_project(compose: dict) -> None:
    """**The guard for the defect the first rehearsal found.**

    Compose derives a project name from the directory when none is given, so the repository's own
    `docker-compose.yml` is project `faultline`. This file declared `name: faultline` too, and so
    did not create a deployment - it joined the developer's one, attaching to the running
    `faultline-postgres-1` and pointing the deployment's DSN at the development database.

    It failed safe by luck: `POSTGRES_PASSWORD` initialises only an empty volume, so the existing
    one kept its old password and authentication failed. Against an empty volume, one `--build` in
    the wrong directory hands a public deployment the developer's data, and `down -v` in either
    directory destroys the other's.
    """
    development = yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text()).get("name")

    # **The distribution name, not `REPO_ROOT.name`.** The first version of this guard compared
    # against the checkout directory, which is what compose actually uses - and so passed in a
    # clone named anything else while failing in one named `faultline`. A test whose verdict
    # depends on what the operator called their directory is worse than no test: it is green
    # wherever it was written. `pyproject.toml` names the project the same way in every clone,
    # and it is the name a clone gets by default.
    distribution = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]["name"]

    assert compose.get("name"), "deploy/compose.yml must name its project explicitly"
    assert compose["name"] != development
    assert compose["name"] not in {distribution, REPO_ROOT.name}, (
        f"project {compose['name']!r} collides with the name compose derives for the "
        "repository's own docker-compose.yml in a default clone, so this file would join "
        "the developer's platform rather than create a deployment"
    )


def test_the_deployment_shares_no_volume_name_with_development(compose: dict) -> None:
    """Belt and braces. Volumes are namespaced by project, so distinct project names already
    separate them - this fails loudly if someone later sets `external: true` or a fixed `name:`
    on one, which would reconnect the two through the back door."""
    for volume in (compose.get("volumes") or {}).values():
        assert not (volume or {}).get("external"), "an external volume is shared, by definition"
        assert not (volume or {}).get("name"), "a fixed volume name escapes the project namespace"


# --- the read surface is actually mounted -------------------------------------------------------


def test_the_deployment_starts_the_read_surface(compose: dict) -> None:
    """Without `--postgres-dsn` the process is T2.1's receiver alone: the URL would answer
    `/healthz`, 404 the screen, and look like a successful deployment."""
    command = compose["services"]["faultline"]["command"]

    assert "--postgres-dsn" in command
    dsn = command[command.index("--postgres-dsn") + 1]
    assert dsn.startswith("postgresql://")
    assert "@postgres:5432/" in dsn, "the DSN must name the compose service, not localhost"


def test_no_password_is_interpolated_into_the_dsn(compose: dict) -> None:
    """**A DSN is a URL, and a password is arbitrary bytes.**

    Found by running it. `openssl rand -base64 24` - which `env.example` recommends - emits `/`
    and `+`. A `/` in an interpolated password ends the URL's authority section, so libpq read the
    host as `faultline` and the password's tail as the port, and the container crash-looped on
    `Servname not supported for ai_socktype`. Percent-encoding in YAML would also work and would be
    one more thing to get right; not putting a secret in a URL is free.

    Second reason, independent of the first: `command:` is visible in `docker inspect`,
    `docker compose config` and the process list.
    """
    service = compose["services"]["faultline"]
    dsn = service["command"][service["command"].index("--postgres-dsn") + 1]

    assert "${POSTGRES_PASSWORD" not in dsn, (
        "the database password must not be interpolated into the DSN - any URL-special "
        "character in it silently repoints the connection. Pass PGPASSWORD instead."
    )
    assert ":" not in dsn.split("//", 1)[1].split("@", 1)[0], (
        f"the DSN carries a password in its userinfo: {dsn}"
    )
    assert service["environment"]["PGPASSWORD"].startswith("${POSTGRES_PASSWORD:?"), (
        "libpq needs the password from PGPASSWORD once it is out of the DSN"
    )


def test_the_migration_and_the_app_agree(compose: dict) -> None:
    """**They resolve their database independently, so they can disagree.**

    `faultline-migrate --dsn` defaults to none and falls through to
    `OrchestratorSettings.postgres_dsn`, whose default is `localhost:5432` - right on a
    developer's machine, wrong inside a container where localhost *is* the container. The
    documented `docker compose exec faultline faultline-migrate` failed on `Connection refused`
    while the platform beside it served happily from the same network.

    The failure mode this guards is worse than that one, because it is quiet: a deployment that
    migrates one database and serves another starts cleanly and answers every request against an
    unmigrated schema.
    """
    service = compose["services"]["faultline"]
    served = service["command"][service["command"].index("--postgres-dsn") + 1]
    migrated = service["environment"]["FAULTLINE_ORCH_POSTGRES_DSN"]

    assert migrated == served, (
        f"the app serves {served} and migrations would run against {migrated}"
    )


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


# --- the clean-clone race (T5.4) ------------------------------------------------------------------


def makefile_recipe(target: str) -> str:
    """The tab-indented lines of ONE Makefile recipe, stopping where that recipe stops.

    **The first version did not stop.** It filtered every later tab-indented line in the whole
    file, so asking for `up` returned `eval-up`'s recipe too - and the guard below passed with
    `--wait` deleted from the target it was written to check, because the flag was still present
    further down. Third time in one evening that a guard passed for a reason that had nothing to
    do with what it asserted, and the reason each was caught is that it was run against the broken
    state before being kept.
    """
    lines = (REPO_ROOT / "Makefile").read_text().splitlines()
    start = lines.index(f"{target}:") + 1
    recipe = []
    for line in lines[start:]:
        if not line.startswith("\t"):
            break
        recipe.append(line)
    return "\n".join(recipe)


@pytest.mark.parametrize("target", ["up", "eval-up"])
def test_bringing_the_platform_up_waits_for_it_to_be_healthy(target: str) -> None:
    """**The defect T5.4's first clean-clone rehearsal found.**

    `docker compose up -d` returns when the container has *started*, not when Postgres accepts
    connections. On a machine with an existing `pgdata` volume that gap is invisible - the server
    is ready in milliseconds. On a **new** volume Postgres runs initdb first, so the port is bound
    while the server is not listening, and the next command in every documented sequence dies with
    `server closed the connection unexpectedly`.

    README and `docs/RELEASE.md` both document `make up` followed immediately by
    `faultline-migrate`. That sequence worked for the person who wrote it and failed for every
    first-time user, which is the exact shape of defect Gate 5 exists to catch and the reason it
    took a clean clone to find.

    The healthcheck has been in `docker-compose.yml` since T0.3. Only the flag consulting it was
    missing.
    """
    assert "--wait" in makefile_recipe(target), (
        f"`make {target}` does not wait for the healthcheck, so a first run on empty volumes "
        "returns before Postgres is accepting connections"
    )


def test_the_migration_reports_the_revision_it_reached() -> None:
    """A successful `faultline-migrate` printed nothing: alembic's INFO lines go through
    `logging`, which `alembic.ini` does not route to stdout. Silent success and silent failure had
    to be told apart by making a request afterwards and reasoning back from the status code -
    twice in one evening. A command that changes a schema should name what it changed it to."""
    source = (REPO_ROOT / "src" / "faultline" / "migrate.py").read_text()

    assert "print(" in source, "faultline-migrate reports nothing on success"
    assert "get_current_head()" in source


def test_the_install_target_takes_the_extras_the_demo_needs() -> None:
    """**A tree that passes every check and cannot run the demo.**

    `agents` (the model client) and `embeddings` (the local encoder) are optional and lazily
    imported, deliberately: `make check` never calls a model and `embeddings` pulls torch. The
    consequence is that a bare `uv sync` produces a working test suite and a broken demo, and
    README said `uv sync` "installs everything" until the first clean-clone rehearsal ran it.

    The two fail differently, which is why both are named here: `agents` refuses with a message
    that gives the fix, and `embeddings` raises a bare `ImportError` from inside the retrieval
    path.
    """
    recipe = makefile_recipe("install")

    assert "--extra agents" in recipe
    assert "--extra embeddings" in recipe


def test_no_document_claims_a_bare_sync_installs_everything() -> None:
    """The claim was in two places in README and in the release checklist, and it was false in
    all three. This fails if it comes back."""
    for name in ("README.md", "docs/RELEASE.md"):
        body = (REPO_ROOT / name).read_text()
        for line in body.splitlines():
            if "uv sync" not in line or line.lstrip().startswith(("|", ">")):
                continue
            claim = line.lower()
            assert not ("install" in claim and "everything" in claim), (
                f"{name} claims a bare `uv sync` installs everything: {line.strip()!r}"
            )


def test_the_readme_names_the_two_servers_the_demo_needs() -> None:
    """**The headline command could not work from a clean clone as documented.**

    README's demo block showed `make world-up` and `make demo` — two of the seven steps a first
    run takes. Missing: `make install`, `make up`, the migration, and the two long-running
    processes without which no incident can ever open. T5.4's rehearsal ran it twice and was
    refused twice with `pipeline-down`.

    The refusal is good and names its own fix, which is why nothing was spent. But a refusal
    doing the documentation's job is still documentation that is missing.
    """
    demo = (REPO_ROOT / "README.md").read_text().split("## Demo", 1)[1].split("\n## ", 1)[0]

    for command in ("faultline-ingest", "faultline-orchestrate", "faultline-migrate", "make up"):
        assert command in demo, f"README's Demo section never mentions `{command}`"
