"""The HTTP surface: one route, and it returns fast (T2.1).

`POST /api/v1/alerts` is the path already configured in
`compose/prometheus/alertmanager.yml`, so this is the receiver Alertmanager has been
posting to since T1.3 - the eight deliveries in `docs/evidence/t2.1-webhook/` were captured
against that exact URL by a bare listener.

**No authentication, and that is a recorded gap rather than an oversight.** Measured over
those deliveries: Alertmanager sends no signature, no shared secret and no credential of
any kind, only `User-Agent: Alertmanager/0.27.0`. Anything that can reach the port can
fabricate an incident. See docs/THREAT-MODEL.md; the defence is T2.6/T6.8's, not this
task's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

import redis
from fastapi import FastAPI

from faultline.ingest.dedupe import RedisEpisodeLog
from faultline.ingest.models import WebhookPayload
from faultline.ingest.receiver import Receiver
from faultline.ingest.settings import IngestSettings
from faultline.ingest.stream import RedisEventStream

app = FastAPI(title="Faultline ingest", version="0.0.1")


@lru_cache(maxsize=1)
def receiver() -> Receiver:
    """The process-wide receiver, built on first use so importing this module needs no Redis.

    Overridden in tests through `app.dependency_overrides` is the FastAPI idiom, but this
    route has no other dependencies and the receiver's own seams (`EpisodeLog`,
    `EventStream`) are where the tests substitute - so the tests drive `Receiver` directly
    and this stays a one-liner rather than a dependency graph.
    """
    settings = IngestSettings()
    client: redis.Redis = redis.from_url(settings.redis_url)
    return Receiver(
        episodes=RedisEpisodeLog(client, settings.episode_key_prefix, settings.episode_ttl_seconds),
        stream=RedisEventStream(client, settings.stream),
    )


@app.post("/api/v1/alerts")
def receive_alerts(payload: WebhookPayload) -> dict[str, int]:
    """Accept one Alertmanager delivery. Publishes what is new, counts what repeated."""
    result = receiver().receive(payload, received_at=datetime.now(UTC))
    return {
        "received": result.received,
        "published": result.published,
        "duplicates": result.duplicates,
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness only. It deliberately does not touch Redis: a health check that fails when
    the bus is down turns a recoverable backlog into a restart loop."""
    return {"status": "ok"}


def run() -> None:
    """`faultline-ingest`. Uvicorn with one worker - dedupe is in Redis, not in memory,
    so more would be safe, but nothing yet needs them.

    **Known bug: this ignores `--help` and every other flag, and starts the server.**
    Found during the live smoke (`docs/evidence/t2.1-live-smoke/`). It takes no arguments
    and hands straight to uvicorn, so the process binds a port instead of describing
    itself. Left as it is deliberately - the fix is argument parsing, not a `--help`
    special case, and that lands when this needs real flags. See ADR-0015, consequences.
    """
    import uvicorn

    settings = IngestSettings()
    uvicorn.run(app, host=settings.host, port=settings.port)
