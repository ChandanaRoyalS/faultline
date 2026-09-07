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


@pytest.mark.parametrize("service", ["postgres", "faultline", "redis", "orchestrator"])
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


def test_every_settings_class_with_a_dsn_is_pointed_at_the_one_database(compose: dict) -> None:
    """**Fixing an instance is not fixing the class** - the guard above fixed `FAULTLINE_ORCH_` and
    the deployment then failed identically on `FAULTLINE_CONTEXT_`: `docker compose exec faultline
    faultline-seed` refused on `127.0.0.1:5432` on the VM, a day after the migration had been fixed
    for the same reason one settings class over (T5.5c). The orchestrator's retrieval reads through
    the same class, so a deployed investigation would have searched its own loopback for a corpus.

    So the list of prefixes is derived from the code, not typed here: every `BaseSettings` under
    `faultline` that declares a `postgres_dsn` field must have its prefixed variable set, in both
    containers that run the image, to the DSN the app itself serves from.
    """
    import importlib
    import inspect
    import pkgutil

    from pydantic_settings import BaseSettings

    import faultline

    prefixes: set[str] = set()
    for module in pkgutil.walk_packages(faultline.__path__, "faultline."):
        if not module.name.endswith(".settings"):
            continue
        for _, cls in inspect.getmembers(importlib.import_module(module.name), inspect.isclass):
            if issubclass(cls, BaseSettings) and "postgres_dsn" in cls.model_fields:
                prefixes.add(str(cls.model_config.get("env_prefix", "")))
    assert prefixes >= {"FAULTLINE_ORCH_", "FAULTLINE_CONTEXT_", "FAULTLINE_TOOLS_"}, prefixes

    app = compose["services"]["faultline"]
    served = app["command"][app["command"].index("--postgres-dsn") + 1]
    for name in ("faultline", "orchestrator"):
        env = compose["services"][name]["environment"]
        for prefix in prefixes:
            if name == "faultline" and prefix == "FAULTLINE_TOOLS_":
                continue  # the read surface runs no tools; nothing in it reads this class
            assert env.get(f"{prefix}POSTGRES_DSN") == served, (
                f"{name}: {prefix}POSTGRES_DSN must name the served database, got "
                f"{env.get(f'{prefix}POSTGRES_DSN')!r}"
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
        # **`FOO=''` carries no value and the quotes are the instruction.** A bcrypt hash is mostly
        # dollar signs and Compose's dotenv parser expands `$VAR` in an unquoted value, so the
        # required form is part of what this file teaches - showing empty quotes is how it teaches
        # it without carrying a credential.
        and line.split("=", 1)[1].strip().strip("'\"")
        # The username is not a secret and a working default saves a step.
        and not line.startswith("FAULTLINE_API_USER=")
    ]

    assert filled == [], f"deploy/env.example carries values: {filled}"


def test_the_secrets_are_ignored() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text()

    assert "deploy/.env" in ignored
    assert "deploy/snapshot.sql.gz" in ignored


# --- the deployment runs what CI built, and the whole MVP -----------------------------------------
#
# Every guard below fails against the version of these files that preceded it. That is the point:
# a guard written to pass against the state it is meant to prevent asserts nothing, and four of
# this file's guards were wrong on first writing for exactly that reason (T5.5, T5.4b).


@pytest.mark.parametrize("service", ["faultline", "orchestrator"])
def test_the_deployment_pulls_rather_than_builds(compose: dict, service: str) -> None:
    """T5.5: *"the same images CI builds"*, *"images pulled from the registry CI publishes to"*.

    `build:` compiles a fresh image on the VM out of whatever the working tree holds - a different
    artifact from the one CI tested, and one the registry cannot identify after the fact.
    """
    assert "build" not in compose["services"][service], (
        f"{service} builds on the VM. T5.5 deploys the image CI published."
    )
    assert "image" in compose["services"][service]


def test_the_image_is_named_by_commit_and_never_by_a_moving_tag(compose: dict) -> None:
    """`:latest` moves under a running VM, so "what is deployed?" stops having an answer and a
    rollback becomes a question about what the tag pointed at on the day."""
    for service in ("faultline", "orchestrator"):
        image = compose["services"][service]["image"]
        assert image.startswith("${FAULTLINE_IMAGE"), f"{service} pins an image inline"
        assert ":?" in image, f"{service} lets FAULTLINE_IMAGE default; it must be named"
    assert "never :latest" in COMPOSE.read_text()


def test_the_deployment_investigates_rather_than_only_remembering(compose: dict) -> None:
    """Phase 5: *"The MVP is a complete story: world, investigation, grounding, evaluation."*

    A deployed instance with a world and no orchestrator alerts on a fault and investigates
    nothing. An earlier version of this file had neither, and served a snapshot.
    """
    orchestrator = compose["services"]["orchestrator"]

    assert orchestrator["command"] == ["faultline-orchestrate"]
    assert "redis" in compose["services"], "the event bus the orchestrator consumes"
    assert "ANTHROPIC_API_KEY" in orchestrator["environment"]


def test_the_receiver_is_not_reachable_from_the_internet() -> None:
    """**The reason this exists changed when the orchestrator arrived.**

    `POST /api/v1/alerts` takes no credential and cannot - Alertmanager sends none, so a password
    there would stop alerts rather than attackers (THREAT-MODEL thesis 3). Harmless while the
    deployment investigated nothing; an unauthenticated endpoint that bills the owner once it does.
    """
    caddyfile = CADDYFILE.read_text()

    assert "handle /api/v1/alerts*" in caddyfile
    assert re.search(r"handle /api/v1/alerts\*\s*\{[^}]*respond[^}]*404", caddyfile), (
        "the alerts path must be answered by Caddy, not proxied"
    )


def test_the_health_endpoint_stays_open_for_the_uptime_check() -> None:
    """T5.5 names *"an uptime check"*. A monitor holding a credential has "the credential expired"
    among its failure modes, and `/healthz` returns a status and nothing about the incidents."""
    caddyfile = CADDYFILE.read_text()
    health = caddyfile.index("handle /healthz")

    assert "basic_auth" not in caddyfile[health : caddyfile.index("handle", health + 1)]


def test_the_worlds_own_uis_are_behind_the_credential() -> None:
    """Grafana and Jaeger ship with no authentication in the demo, and the deep link T5.1 builds
    now points a reader at Grafana through this hostname."""
    caddyfile = CADDYFILE.read_text()

    assert "@world path /grafana* /jaeger* /loadgen*" in caddyfile
    assert re.search(r"handle @world\s*\{[^}]*basic_auth", caddyfile)


def test_the_credential_is_checked_by_caddy_and_never_shown_to_grafana() -> None:
    """**Grafana treats an incoming `Authorization: Basic` header as a login attempt** against its
    own users before it falls back to anonymous access. So the header that satisfied Caddy's
    `basic_auth` reached Grafana intact and every citation click on the live instance answered
    `{"message":"invalid username or password"}` (T5.5c, defect thirty-one) - the first public
    click, after seven hours of everything else being fixed. Caddy strips the header after checking
    it, inside the world handler and nowhere else: the Faultline API reads the same credential
    itself and must keep receiving it."""
    caddyfile = CADDYFILE.read_text()
    start = caddyfile.index("handle @world")
    world = caddyfile[start : caddyfile.index("\n\t}\n", start)]

    assert re.search(
        r"reverse_proxy frontend-proxy:8080\s*\{[^}]*header_up -Authorization", world
    ), "the world handler forwards the credential to Grafana, which rejects it"
    rest = caddyfile[:start] + caddyfile[start + len(world) :]
    assert "header_up -Authorization" not in rest, (
        "only the world's UIs must lose the header; Faultline authenticates with it"
    )


def test_the_citation_link_sends_a_reader_somewhere_public(compose: dict) -> None:
    """Every other `FAULTLINE_TOOLS_*` endpoint is where a *tool* reaches. This one is where a
    *human* is sent, so an internal hostname would be a dead link with extra steps.

    **And it must be set on the container that renders the page.** `api.view.deep_link` reads
    `ToolSettings.grafana_url` in the read-surface process; the first version of this test asserted
    the orchestrator's value, the orchestrator never renders anything, and the live instance served
    every citation as `http://localhost:3000/...` (T5.5c, defect twenty-seven). The service that
    runs the read surface is found by its command, not named here, so the assertion follows the
    process rather than a label.
    """
    renderers = [
        name
        for name, svc in compose["services"].items()
        if "faultline-ingest" in (svc.get("command") or [])
    ]
    assert renderers == ["faultline"], renderers

    grafana = compose["services"]["faultline"]["environment"]["FAULTLINE_TOOLS_GRAFANA_URL"]
    assert grafana.startswith("https://${SITE_ADDRESS")
    assert grafana.endswith("/grafana"), "the prefix the demo's frontend-proxy already serves"

    assert (
        "FAULTLINE_TOOLS_GRAFANA_URL" not in compose["services"]["orchestrator"]["environment"]
    ), "set where it is read; a value on a container that never renders is false comfort"


# --- the world is on the same network, and posts to the container ---------------------------------

WORLD_OVERLAY = DEPLOY / "compose.world.yml"
DEPLOY_ALERTMANAGER = DEPLOY / "alertmanager.yml"


@pytest.fixture(scope="module")
def world() -> dict:
    return yaml.safe_load(WORLD_OVERLAY.read_text())


@pytest.mark.parametrize("service", ["alertmanager", "prometheus", "loki", "frontendproxy"])
def test_every_service_the_platform_talks_to_shares_its_network(world: dict, service: str) -> None:
    """Two compose projects, one network. The orchestrator queries three of these and Caddy
    forwards the demo's UIs through the fourth; a service left off the network is a tool that
    times out at the moment it is asked a question.

    **This list said `frontend-proxy` and passed for two merges** - it was checking the overlay's
    keys against a copy of the overlay's keys, and both were the container name rather than the
    service name the demo actually defines. `injector.world.SERVICE_CONTAINERS` is the authority
    now; see the guard beside the rehearsal tests (T5.5c).

    **And `default` must be there too.** The demo puts every service on its implicit default
    network by naming none; an overlay that lists only `faultline` *replaces* that membership
    rather than adding to it, and the first live deployment cut all four services off the world:
    Prometheus with 0 of 2 targets up, Envoy answering a citation click with "no healthy upstream"
    (defect twenty-eight). This assertion checked half the truth and passed."""
    networks = world["services"][service]["networks"]
    assert "faultline" in networks, f"{service} is not reachable from the platform"
    assert "default" in networks, (
        f"{service} has been taken off the world's own network - an explicit list replaces the "
        "implicit default, it does not add to it"
    )


def test_the_shared_network_is_external_so_neither_project_owns_it(world: dict) -> None:
    """`docker compose down` on the platform would otherwise tear out a network the world is still
    attached to."""
    for spec in (
        world["networks"]["faultline"],
        yaml.safe_load(COMPOSE.read_text())["networks"]["faultline"],
    ):
        assert spec["external"] is True
        assert spec["name"] == "faultline-deploy-net"


def test_alertmanager_posts_to_the_container_not_a_developers_host(world: dict) -> None:
    """`host.docker.internal` is right on a development machine, where the receiver runs on the
    host, and resolves to nothing that listens on a Linux VM."""
    config = yaml.safe_load(DEPLOY_ALERTMANAGER.read_text())
    url = config["receivers"][0]["webhook_configs"][0]["url"]

    assert url == "http://faultline:8000/api/v1/alerts"
    # **Against the parsed config, not the file text.** The first version of this line grepped the
    # raw file and failed on the comment that explains why `host.docker.internal` is wrong here -
    # a guard that forbids a document from naming the thing it is documenting. Fifth time a guard
    # in this repository has been wrong on first writing, and the fifth caught only by running it.
    assert all(
        "host.docker.internal" not in hook["url"]
        for receiver in config["receivers"]
        for hook in receiver["webhook_configs"]
    )
    assert world["services"]["alertmanager"]["command"] == [
        "--config.file=/etc/alertmanager/alertmanager.deploy.yml",
        "--web.listen-address=:9093",
    ], "an overlay replaces command, which is how the second config is selected"


def test_the_deployment_alertmanager_batches_exactly_as_development_does() -> None:
    """A deployment that grouped alerts differently would produce incidents of a different shape,
    and every figure in docs/RESULTS.md was measured under these numbers."""
    dev = yaml.safe_load((REPO_ROOT / "compose/prometheus/alertmanager.yml").read_text())
    deployed = yaml.safe_load(DEPLOY_ALERTMANAGER.read_text())

    assert {k: v for k, v in dev["route"].items() if k != "receiver"} == {
        k: v for k, v in deployed["route"].items() if k != "receiver"
    }


# --- --wait has something to wait on --------------------------------------------------------------


def test_every_service_caddy_forwards_to_declares_when_it_is_ready(compose: dict) -> None:
    """**Found by the rollback rehearsal, not by reading.** `up -d --wait` returned, `ps` read
    `Up Less than a second`, and `curl /healthz` got *connection reset by peer* twice. Compose
    treats a service with no healthcheck as ready when its process starts, so `--wait` had nothing
    to wait on and the README's rollback procedure - `up --wait`, then curl - was racing itself.

    T5.4b's defect, one service over: there `--wait` was missing; here it was present and idle.
    """
    faultline = compose["services"]["faultline"]

    assert "healthcheck" in faultline, "--wait does not wait for a service with no healthcheck"
    assert "/healthz" in " ".join(faultline["healthcheck"]["test"])
    assert faultline["healthcheck"].get("start_period"), (
        "an arm64 laptop runs this image under emulation; a check that flaps on its own startup "
        "teaches operators to distrust it"
    )


def test_caddy_waits_for_a_serving_upstream_not_a_started_one(compose: dict) -> None:
    """The short-form `depends_on: [faultline]` means "after its process starts". During a deploy
    or a rollback that is a window in which Caddy's upstream is a port nobody listens on, and every
    visitor in it sees a 502 - the same race the rehearsal saw as a reset, from the other side."""
    depends = compose["services"]["caddy"]["depends_on"]

    assert isinstance(depends, dict), "short-form depends_on cannot express a health condition"
    assert depends["faultline"] == {"condition": "service_healthy"}


# --- the uptime check exists and watches more than liveness ---------------------------------------

UPTIME = REPO_ROOT / ".github/workflows/uptime.yml"


def test_the_uptime_check_is_a_committed_artifact_rather_than_an_account() -> None:
    """T5.5 names *"an uptime check"* as a deliverable. A setting in a vendor's dashboard cannot be
    reviewed, cannot be diffed, and cannot be shown to a reader of this repository."""
    assert UPTIME.is_file()
    workflow = yaml.safe_load(UPTIME.read_text())

    # `on:` parses as the boolean True in YAML 1.1, which pyyaml implements.
    assert "schedule" in workflow[True]


def test_the_uptime_check_would_notice_more_than_the_process_being_alive() -> None:
    """`/healthz` is deliberately shallow: a deployment started without `--postgres-dsn` answers it
    perfectly and 404s the incident screen. That failure is exactly the one T5.5's guards were
    written for, and a check that reported it as health would be worse than none.

    The alerts assertion is the other half - not an outage check at all, but the one that notices
    if a Caddyfile edit ever puts the receiver back on the internet, where anything reaching it can
    open incidents that bill the deployment's key.
    """
    steps = yaml.safe_load(UPTIME.read_text())["jobs"]["healthz"]["steps"]
    script = "\n".join(step.get("run", "") for step in steps)

    assert "/healthz" in script
    assert "/api/v1/incidents" in script, "liveness alone would miss an unmounted read surface"
    assert "/api/v1/alerts" in script, "nothing else would notice the receiver going public"


def test_an_unconfigured_uptime_check_skips_rather_than_failing_forever() -> None:
    """This file is committed before the VM exists. A permanently red check is worse than no check:
    people learn to ignore it, and then they ignore the next one too."""
    steps = yaml.safe_load(UPTIME.read_text())["jobs"]["healthz"]["steps"]

    assert all("configured == 'true'" in str(step.get("if", "")) for step in steps[1:])


def test_the_documented_world_command_layers_every_file_the_generation_is_hashed_from() -> None:
    """**This guard asserted the opposite for one merge, and the file's name is why.**

    `world-arm64.override.yml` reads as an Apple Silicon accommodation. It is the world's
    operational configuration - kafka's glibc arena fix (T7.27), redis-cart's eviction policy
    (T7.19), a dozen limits raised because containers idled above the baseline gate's 90% guard,
    and the feature-flag stub every recorded scenario ran against (ADR-0005) - and it is one of the
    three files `evalharness.provenance.compose_digest` hashes. A world brought up without it is a
    different generation from `f5bd108f4f70`, wearing the same image tag.

    So the documented command must layer all three digest inputs, in the order the Makefile does,
    with the deploy overlay fourth and outside the hash. Asserted against the README's fenced
    command because the command an operator copies is the one that runs (T5.4b).
    """
    from injector.settings import InjectorSettings

    readme = (DEPLOY / "README.md").read_text()
    blocks = re.findall(r"```bash\n(.*?)```", readme, re.S)
    world = [b for b in blocks if "compose.world.yml" in b]

    assert world, "deploy/README.md documents no command that brings the world up"
    hashed = [Path(name).name for name in InjectorSettings().compose_files]
    for block in world:
        positions = [block.find(name) for name in hashed]
        assert all(p >= 0 for p in positions), (
            f"the world command omits a file the generation is hashed from: "
            f"{[n for n, p in zip(hashed, positions, strict=True) if p < 0]}"
        )
        assert positions == sorted(positions), "the digest inputs must be layered in Makefile order"
        assert block.find("compose.world.yml") > max(positions), "the deploy overlay layers last"


def test_every_service_the_world_overlay_touches_exists_under_that_key() -> None:
    """**The demo names its service `frontendproxy` and its container `frontend-proxy`.** The first
    version of `compose.world.yml` used the container name as the service key, so compose saw a new
    service with no image and refused the entire world project - on the VM, at deploy time (T5.5c).
    Two rehearsals on the Mac never caught it because neither brought the world up under this file.

    `injector.world.SERVICE_CONTAINERS` is the naming map the injector already keeps for exactly
    this confusion, and it is drift-tested against the clone. An overlay key that is not in it is a
    service the world does not have.
    """
    from injector.world import SERVICE_CONTAINERS

    overlay = yaml.safe_load((DEPLOY / "compose.world.yml").read_text())
    unknown = set(overlay["services"]) - set(SERVICE_CONTAINERS)
    assert not unknown, f"compose.world.yml names services the world does not define: {unknown}"


# --- the rehearsal changes only what it claims to ------------------------------------------------


def test_the_rehearsal_only_moves_the_port_and_stops_what_it_cannot_run() -> None:
    """The rehearsal exists so the deployment gets run before a VM exists. It is worth nothing if
    it rehearses a *different* deployment - so it may change the three things its own header names
    and no others.

    It was two things until the deployment gained an orchestrator.
    """
    override = yaml.safe_load((DEPLOY / "compose.rehearsal.yml").read_text())

    assert set(override["services"]) == {"caddy", "orchestrator", "faultline"}
    assert override["services"]["caddy"] == {"deploy": {"replicas": 0}}
    assert override["services"]["orchestrator"] == {"deploy": {"replicas": 0}}
    assert override["services"]["faultline"] == {"ports": ["8001:8000"]}


def test_a_rehearsal_cannot_spend_money() -> None:
    """**The rehearsal's whole promise is that running it costs nothing**, and the deployment just
    gained a container that makes model calls. A rehearsal that quietly started an agent loop would
    break that promise silently, which is the worst way to break it.

    Asserted separately from the guard above rather than folded into it: that one is about the
    rehearsal staying faithful to the deployment, and this one is about what an operator is
    promised. They would be edited for different reasons.
    """
    override = yaml.safe_load((DEPLOY / "compose.rehearsal.yml").read_text())
    deployment = yaml.safe_load(COMPOSE.read_text())

    spenders = [
        name
        for name, service in deployment["services"].items()
        if "ANTHROPIC_API_KEY" in (service.get("environment") or {})
    ]

    assert spenders, "no service holds the key; this guard is watching the wrong thing"
    for name in spenders:
        assert override["services"].get(name, {}).get("deploy", {}).get("replicas") == 0, (
            f"{name} holds the model key and the rehearsal starts it"
        )


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
    section = (REPO_ROOT / "README.md").read_text().split("## Demo", 1)[1].split("\n## ", 1)[0]

    # **The fenced command blocks, not the prose around them.** The first version searched the
    # whole section and passed with the `faultline-seed` line deleted, because the paragraph
    # explaining *why* it matters still contained the word. Prose about a command is not an
    # instruction to run it, and this guard exists for the reader who copies the block.
    demo = "\n".join(block for index, block in enumerate(section.split("```")) if index % 2 == 1)

    # **`faultline-seed` was missing from the first version of this list**, and the rehearsal that
    # added the other four then lost a *correct* demo verdict to an empty corpus: the leave-one-out
    # filter excluded nothing, asserted nothing, and the run was marked INVALID. A repair that
    # leaves out a step is the same defect one iteration later.
    needed = (
        "faultline-ingest",
        "faultline-orchestrate",
        "faultline-migrate",
        "faultline-seed",
        "make up",
    )
    for command in needed:
        assert command in demo, f"README's Demo section never mentions `{command}`"
