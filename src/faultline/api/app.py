r"""One process, one port, the whole HTTP surface (T5.1's missing half).

## What was wrong

`faultline.api.view` assembles the incident payload. `faultline.api.incidents` serves it on
`GET /api/v1/incidents{,/{id}}` and serves T5.1's screen on `GET /ui/incidents/{id}`.
`faultline.api.static.incident.html` polls that API every three seconds. `faultline.notify.messages`
builds a Slack link to `/ui/incidents/{id}`. Four modules, twelve tests, and

    $ grep -rn "incidents.build\|page_router" src/
    src/faultline/notify/messages.py:86:  # a docstring

**`build()` and `page_router()` were called from no running process.** `tests/test_incident_routes`
mounts them on a `FastAPI()` it constructs itself, proves the routes work, and proves nothing about
whether anything serves them - which is why it stayed green for the whole time nobody could open the
page. The Slack notification T5.2 sends has been linking to a 404 by construction.

That is the eighth time in this project that something built, green and never run turned out to be
broken, and `incidents.py`'s own module docstring names the pattern in its second sentence: *"A view
nobody can fetch is a view nobody has."* It was written about `view.py` and it was still true of
`incidents.py`.

## The shape of the fix

`assemble()` builds one app from two halves that keep their existing meanings:

| half | routes | needs | credential |
|---|---|---|---|
| receiver (T2.1) | `POST /alerts`, `GET /healthz` | Redis | **none** - see `auth.py` |
| read surface (T5.1) | `GET /incidents{,/{id}}`, `GET /ui/incidents/{id}` | Postgres | **basic** |

**The read half is opt-in on a DSN.** Without `--postgres-dsn` the process is byte-for-byte the
receiver T2.1 shipped: same routes, same dependency on Redis alone, same behaviour when Postgres is
absent. A deployment that only receives alerts does not acquire a database dependency because a
different task needed one.

**With a DSN it is mandatory, not opportunistic.** A factory that tried Postgres and quietly served
the receiver alone when the connection failed would turn a misconfigured DSN into a 404 on the page,
and the operator would go looking for the bug in the frontend. It connects or it refuses to start.

## The connection, and why one is enough

Both stores share a single `psycopg` connection, as `orchestrator.cli` does. The read routes run
short `SELECT`s against a database whose writer is a different process; a pool would be the right
answer under concurrency this surface does not have, and the wrong thing to guess at now. If the
screen ever serves more than a handful of readers, the pool goes here and the routes do not change -
they were handed stores, not a connection, precisely so that this stays true.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from faultline.api import auth, incidents
from faultline.ingest.app import app as receiver_app

TITLE = "Faultline"
"""Not "Faultline ingest" any more when both halves are mounted. The receiver keeps its own title
on its own app object; this one describes what it actually serves."""


def read_surface(app: FastAPI, postgres_dsn: str) -> FastAPI:
    """Mount T5.1's routes, behind the credential, on an app that already has the receiver.

    Imports psycopg and the stores **inside the function** so that importing this module - which
    `tests/test_api_app` does, and which any tooling that only wants the receiver does - needs
    neither a driver nor a database.
    """
    import psycopg

    from faultline.agents.trajectory import PostgresTrajectoryStore
    from faultline.orchestrator.store import PostgresIncidentStore

    # Read before connecting. An operator who forgot the password should be told that, not told it
    # after a connection timeout to a database they were about to expose anyway.
    credential = auth.guard()

    connection = psycopg.connect(postgres_dsn)
    app.include_router(
        incidents.build(
            PostgresIncidentStore(connection),
            # No archive: `latest_for_incident` and `get` read Postgres only, and handing this a
            # writer's object-store credentials would put them in a process that never writes.
            PostgresTrajectoryStore(connection),
        ),
        dependencies=[credential],
    )
    app.include_router(incidents.page_router(), dependencies=[credential])
    return app


def assemble(postgres_dsn: str | None = None, **kwargs: Any) -> FastAPI:
    """The app `faultline-ingest` serves. Read half mounted only when a DSN is given.

    **Composed from `receiver_app.router`, not by re-declaring the routes.** There is exactly one
    definition of `POST /api/v1/alerts` in this codebase and it is the one Alertmanager has been
    posting to since T1.3; a second copy here would be a second thing to keep in step with the
    committed OpenAPI snapshot, and the first divergence would show up as a demo that receives
    alerts and an evidence directory that says it should not.
    """
    app = FastAPI(title=TITLE, version="0.1.0", **kwargs)
    app.include_router(receiver_app.router)
    if postgres_dsn:
        read_surface(app, postgres_dsn)
    return app
