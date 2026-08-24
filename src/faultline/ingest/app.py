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

import argparse
import os
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


def parser() -> argparse.ArgumentParser:
    """Flags override `FAULTLINE_INGEST_*`, which overrides the defaults."""
    settings = IngestSettings()
    p = argparse.ArgumentParser(
        prog="faultline-ingest",
        description=(
            "Receive Alertmanager webhook deliveries, deduplicate them by alert episode, "
            "and publish alert-episode transitions to the Redis stream (T2.1, ADR-0015)."
        ),
        epilog="The receiver has no authentication - see docs/THREAT-MODEL.md, thesis 3.",
    )
    p.add_argument("--host", default=settings.host, help="default: %(default)s")
    p.add_argument("--port", type=int, default=settings.port, help="default: %(default)s")
    p.add_argument("--redis-url", default=settings.redis_url, help="default: %(default)s")
    p.add_argument("--stream", default=settings.stream, help="default: %(default)s")
    return p


def run(argv: list[str] | None = None) -> int:
    """`faultline-ingest`. Uvicorn with one worker - dedupe is in Redis, not in memory,
    so more would be safe, but nothing yet needs them.

    Argument parsing landed with T2.2, which needed a CLI of its own: ADR-0015 recorded that
    this ignored `--help` and started the server, and that the fix was real flags rather than
    a `--help` special case. Two CLIs with the same need is when that stopped being true.
    """
    args = parser().parse_args(argv)
    import uvicorn

    # The route builds its receiver from settings on first use, so the flags have to reach
    # it that way rather than by being passed down through FastAPI.
    os.environ["FAULTLINE_INGEST_REDIS_URL"] = args.redis_url
    os.environ["FAULTLINE_INGEST_STREAM"] = args.stream
    receiver.cache_clear()

    uvicorn.run(app, host=args.host, port=args.port)
    return 0
