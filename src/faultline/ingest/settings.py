"""Where ingest listens and what it writes to (T2.1)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestSettings(BaseSettings):
    """Ingest configuration. Every field is overridable via FAULTLINE_INGEST_*."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_INGEST_", env_file=".env", extra="ignore"
    )

    redis_url: str = "redis://localhost:6379/0"
    """The platform profile's `redis`, published on 6379 by docker-compose.yml."""

    stream: str = "faultline:alerts"
    """The T2.2 consumer group reads this (ADR-0001)."""

    episode_key_prefix: str = "faultline:seen:"

    episode_ttl_seconds: int = 7 * 24 * 60 * 60
    """Must exceed the longest episode we expect. See dedupe.RedisEpisodeLog."""

    host: str = "0.0.0.0"
    """All interfaces: Alertmanager reaches this from another container, not from localhost.
    That is also what makes the missing authentication exploitable - see docs/THREAT-MODEL.md."""

    port: int = 8000
    """Alertmanager posts to host.docker.internal:8000 - see compose/prometheus/alertmanager.yml."""
