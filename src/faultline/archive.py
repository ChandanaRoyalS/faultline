"""Durable storage for evidence envelopes and rendered reports (T2.3).

T2.3 asks for *"raw evidence payloads and rendered reports archived to S3-compatible object
storage so citations stay re-verifiable forever"*, and the proposal's architecture names
`S3-compatible (report archive)` beside Postgres.

**What this is not for.** Citations are already re-verifiable: `trajectory.ToolCallRecord`
stores each envelope inline under its `result_id` with a sha256, and `narrative.py` refuses a
citation it cannot resolve. That mechanism is not being replaced. What it does not give is the
word *forever* - Postgres holds the only copy, so a database that is reset, migrated badly, or
pruned takes every recorded citation's evidence with it, and the reports that cite them become
unfalsifiable rather than wrong.

So this is a second copy with a different failure mode, and the ordering matters: the database
write happens first and the archive write second. An archive that is down must never cost a
trajectory - the trajectory is the record, and the archive is the copy that outlives it.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from pydantic_settings import BaseSettings, SettingsConfigDict


class ArchiveSettings(BaseSettings):
    """Overridable via FAULTLINE_ARCHIVE_*. Dev credentials are in docker-compose.yml."""

    model_config = SettingsConfigDict(
        env_prefix="FAULTLINE_ARCHIVE_", env_file=".env", extra="ignore"
    )

    endpoint_url: str = "http://localhost:9000"
    bucket: str = "faultline-evidence"
    access_key: str = "faultline"
    secret_key: str = "faultline-dev"
    region: str = "us-east-1"

    enabled: bool = False
    """**Off by default, deliberately.**

    On means every agent run reaches for object storage at startup, so a developer who has not
    brought up the platform profile pays a connection timeout per run for a copy they do not
    need. Off means the inline envelopes in Postgres are the only copy, which is exactly what
    the system did before this existed - no behaviour is lost by the default, only the second
    copy. `make up` now runs MinIO, so turning it on is `FAULTLINE_ARCHIVE_ENABLED=true`.

    A deployment should set it. T5.5 is where that stops being a sentence in a docstring."""


ENVELOPE_PREFIX = "envelopes"
REPORT_PREFIX = "reports"


def envelope_key(result_id: str) -> str:
    """Keyed by `result_id`, the same handle the citation validator resolves."""
    return f"{ENVELOPE_PREFIX}/{result_id}"


def report_key(investigation_id: str) -> str:
    return f"{REPORT_PREFIX}/{investigation_id}.md"


class Archive(Protocol):
    """The seam. `InMemoryArchive` in tests, `S3Archive` in a deployment."""

    def put(self, key: str, body: bytes, *, content_type: str = ...) -> None: ...

    def get(self, key: str) -> bytes | None: ...


class InMemoryArchive:
    """A dict. For tests, and for a deployment that has not configured an archive.

    Deliberately not a no-op: a silent discard would let a test assert that archiving
    happened when nothing was stored, which is the failure this whole audit keeps finding.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, body: bytes, *, content_type: str = "application/octet-stream") -> None:
        self.objects[key] = body

    def get(self, key: str) -> bytes | None:
        return self.objects.get(key)


class S3Archive:
    """Any S3-compatible endpoint. MinIO in the compose profile; S3 itself in a deployment."""

    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def connect(cls, settings: ArchiveSettings | None = None) -> S3Archive:
        """Build a client and ensure the bucket exists.

        `boto3` is an optional dependency and imported here rather than at module scope, so
        `make check` and every process that does not archive stay free of it - the same
        treatment ADR-0018 gives the embedding model and ADR-0020 gives the model client.
        """
        import boto3

        resolved = settings or ArchiveSettings()
        client = boto3.client(
            "s3",
            endpoint_url=resolved.endpoint_url,
            aws_access_key_id=resolved.access_key,
            aws_secret_access_key=resolved.secret_key,
            region_name=resolved.region,
        )
        existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
        if resolved.bucket not in existing:
            client.create_bucket(Bucket=resolved.bucket)
        return cls(client, resolved.bucket)

    def put(self, key: str, body: bytes, *, content_type: str = "application/octet-stream") -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)

    def get(self, key: str) -> bytes | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception:
            # Absent and unreachable are the same answer to a reader: this archive cannot
            # produce the object. The caller's job is to say so, not to guess which it was.
            return None
        body: bytes = response["Body"].read()
        return body


def archive_trajectory(trajectory: Any, archive: Archive) -> list[str]:
    """Put every tool-call envelope this trajectory produced. Returns the keys written.

    Takes `trajectory` as `Any` rather than importing `faultline.agents`: the archive is
    infrastructure and must not depend on the layer it stores for, the same way
    `machine.record_agent_outcome` duck-types an `InvestigationResult`.
    """
    written: list[str] = []
    for step in getattr(trajectory, "steps", ()):
        call = getattr(step, "tool_call", None)
        if call is None:
            continue
        key = envelope_key(call.result_id)
        archive.put(key, call.envelope.encode(), content_type="text/plain; charset=utf-8")
        written.append(key)
    return written


def connect_or_none(settings: ArchiveSettings | None = None) -> Archive | None:
    """The archive if it is configured and reachable, `None` otherwise, loudly either way.

    Two failures are being kept apart. Not configured is a choice and is silent. Configured
    and unreachable is a problem, and returning `None` without saying so would produce a
    system that believes it is archiving and is not - the precise shape of every defect this
    project has spent its audits finding.
    """
    resolved = settings or ArchiveSettings()
    if not resolved.enabled:
        return None
    try:
        return S3Archive.connect(resolved)
    except Exception:
        logging.getLogger(__name__).warning(
            "the evidence archive is enabled but %s is unreachable; envelopes will be stored "
            "inline in Postgres only, and this run leaves no second copy",
            resolved.endpoint_url,
            exc_info=True,
        )
        return None
