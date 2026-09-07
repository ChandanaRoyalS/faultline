"""The read routes T5.1's UI calls (T5.1).

`faultline.api.view` assembles the payload; **nothing served it.** A view nobody can fetch is a
view nobody has, which is the same shape as the A/A check that was library-only until its CLI
landed — twice in one day is enough to treat "and the caller" as part of the deliverable rather
than as follow-up.

Two routes, because T5.1 asks for *"one great screen"*:

- `GET /api/v1/incidents` — the list the screen is reached from, newest first
- `GET /api/v1/incidents/{id}` — everything that screen shows, in one payload

and, since T5.6's audit, the pages over them: `GET /ui/incidents` lists, `GET /ui/incidents/{id}`
is the screen, and `GET /` redirects to the list so the deployment's hostname is a place to start.

## Read-only, and structurally so

These routes take an `IncidentStore` and a `TrajectoryStore` and call `get` on them. **Neither
protocol offers a write from here** — the router never imports a writer, never opens a
transaction, and cannot advance a state machine. T5.1 is a *view*; a read surface that could
mutate would be an action plane nobody designed, and ADR-0020's two-credential-plane thesis
(THREAT-MODEL thesis 2) is about exactly that boundary.

## The unauthenticated-port gap was inherited, named, and then closed on this half

`app.py` records that `POST /api/v1/alerts` is unauthenticated and that **anything reaching the
port can fabricate an incident** (THREAT-MODEL thesis 3). These routes sit on the same port and
inherited the same gap in the other direction: **anything reaching it could read every incident,
every log line the agent quoted, and every query it ran** - a wider exposure than the write path's,
because incident data contains the monitored world's telemetry.

T5.5 closed the read half: `app.read_surface` mounts these routes behind `auth.guard()`, and the
deployment's edge answers 404 on the alert path from the internet (`deploy/Caddyfile`). This module
still checks no credential itself - the guard is a dependency on the mount, so a test can drive the
routes without one and a process cannot serve them without one. What remains open is recorded in
`docs/THREAT-MODEL.md` under the deployed-surface addendum, not here.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from faultline.api import view

PAGE = Path(__file__).parent / "static" / "incident.html"
"""T5.1's one screen, served from the same origin as the API it polls.

Same-origin so the page needs no CORS and the API needs no allowlist - a read surface that had to
name the origins allowed to call it would be one more thing to get wrong before a demo, and T5.4
rehearses this from a clean clone."""

LIST_PAGE = Path(__file__).parent / "static" / "incidents.html"
"""The list that screen is reached from, and the root's destination (T5.6's audit).

`GET /api/v1/incidents` existed from T5.1 and had no page. T5.5 asked for *"a URL to point at"*
and the deployment's root answered 404: a reader had to be handed an incident id out of band, which
is not a URL to point at, it is a URL to be led to. `/` redirects here; this lists; each row links
to `PAGE`."""

router = APIRouter(prefix="/api/v1")

LIST_PATH = "/ui/incidents"
"""Where `/` sends a browser. `notify.messages.UI_PATH` is this plus a trailing slash and an id."""

LIST_LIMIT = 50
"""How many incidents the list returns. A cap rather than a page count, because the screen this
serves is reached by scanning a short list - and an uncapped read of every incident ever is a
query whose cost grows with the record it is meant to make legible."""


def build(incidents: Any, trajectories: Any) -> APIRouter:
    """Bind the routes to two stores. **Both read-only from here.**

    Passed in rather than constructed, so a test drives them without Postgres and so the routes
    hold no opinion about where an incident lives - the same seam `Receiver` uses.
    """
    bound = APIRouter(prefix="/api/v1")

    @bound.get("/incidents")
    def list_incidents() -> dict[str, Any]:
        # `recent`, **not `correlation_candidates`**. The first version of this route borrowed
        # the orchestrator's query, which by design excludes every finished incident - so the
        # list a responder uses to find last night's report could show only what was still open,
        # and against a database of completed investigations it returned `[]`. Found on the
        # route's first real use, three days after its tests went green: the test incidents were
        # all fresh and therefore all candidates.
        #
        # One more than the cap, so `truncated` is measured rather than inferred from a full page.
        found = incidents.recent(LIST_LIMIT + 1)
        ordered = sorted(
            found, key=lambda i: getattr(i, "opened_at", None) or datetime.min, reverse=True
        )
        return {
            "incidents": [
                {
                    "incident_id": incident.id,
                    "state": getattr(incident.state, "value", str(incident.state)),
                    "severity": getattr(incident.severity, "value", str(incident.severity)),
                    "opened_at": (incident.opened_at.isoformat() if incident.opened_at else None),
                    "services": sorted(
                        {e.service for e in incident.episodes.values() if e.service}
                    ),
                }
                for incident in ordered[:LIST_LIMIT]
            ],
            "truncated": len(ordered) > LIST_LIMIT,
        }

    @bound.get("/incidents/{incident_id}")
    def get_incident(incident_id: str) -> dict[str, Any]:
        incident = incidents.get(incident_id)
        if incident is None:
            # 404 rather than an empty view. An incident that does not exist and one that has not
            # been investigated are different states, and the second is a legal 200 - see
            # `view.incident_view`, which renders an incident with no trajectory.
            raise HTTPException(status_code=404, detail=f"no incident {incident_id}")
        # **Not `incident.trajectory_id`** - there is no such field, and adding one would
        # duplicate an edge `trajectories.incident_id` already carries and let the two copies
        # disagree. The store traverses it instead, newest first.
        return view.incident_view(incident, trajectories.latest_for_incident(incident_id))

    return bound


def page_router() -> APIRouter:
    """The page itself. Separate from `build` because it needs no stores - a router that took
    them to serve a static file would suggest the file depends on them."""
    pages = APIRouter()

    @pages.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        # Behind the same credential as the pages, though it reveals nothing: a read surface on
        # which *one* path answers anonymously is a surface with two rules, and the uptime check
        # already has `/healthz` for the anonymous probe.
        return RedirectResponse(url=LIST_PATH, status_code=307)

    @pages.get(LIST_PATH)
    def incidents_page() -> FileResponse:
        return FileResponse(LIST_PAGE, media_type="text/html")

    @pages.get("/ui/incidents/{incident_id}")
    def incident_page(incident_id: str) -> FileResponse:
        # The id is not interpolated into the HTML: the page reads it from its own URL. A server
        # that templated it in would be building markup out of a request parameter, which is the
        # injection this whole surface is careful about.
        return FileResponse(PAGE, media_type="text/html")

    return pages
