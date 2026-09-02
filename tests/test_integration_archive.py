"""The evidence archive against a real S3-compatible server (T2.3).

`tests/test_archive.py` pins what is written and where, against a dict. This is the half a
dict cannot answer: that the client talks to a real endpoint, that the bucket is created when
absent, and that the bytes come back unchanged - which is the whole claim, since the archive
exists so a citation stays resolvable after the database holding the inline copy is gone.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator

import pytest
from testcontainers.core.container import DockerContainer

from faultline.archive import ArchiveSettings, S3Archive, envelope_key

pytestmark = pytest.mark.integration

ACCESS, SECRET = "faultline", "faultline-dev"


def _ready(endpoint: str, attempts: int = 60) -> None:
    """Poll rather than match a log line: a readiness test that greps stdout breaks on the
    release that reworded its banner, and this must not be the flaky test in the suite."""
    import boto3

    for _ in range(attempts):
        try:
            boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=ACCESS,
                aws_secret_access_key=SECRET,
                region_name="us-east-1",
            ).list_buckets()
            return
        except Exception:
            # Any failure here means "not up yet" - connection refused, no credentials
            # loaded, bucket listing not served. Distinguishing them would be a readiness
            # check with opinions about startup order.
            time.sleep(1)
    raise RuntimeError(f"minio at {endpoint} never became ready")


@pytest.fixture(scope="module")
def endpoint() -> Iterator[str]:
    container = (
        DockerContainer("minio/minio:RELEASE.2025-04-22T22-12-26Z")
        .with_env("MINIO_ROOT_USER", ACCESS)
        .with_env("MINIO_ROOT_PASSWORD", SECRET)
        .with_command("server /data")
        .with_exposed_ports(9000)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(9000)}"
        _ready(url)
        yield url


def settings_for(endpoint: str, bucket: str) -> ArchiveSettings:
    return ArchiveSettings(
        endpoint_url=endpoint, bucket=bucket, access_key=ACCESS, secret_key=SECRET
    )


def test_connect_creates_the_bucket_when_it_is_absent(endpoint: str) -> None:
    """A first deployment has no bucket, and an archive that needs one made by hand is an
    archive that is empty on the day it is first needed."""
    archive = S3Archive.connect(settings_for(endpoint, "created-on-connect"))

    archive.put("probe", b"x")

    assert archive.get("probe") == b"x"


def test_an_envelope_round_trips_unchanged(endpoint: str) -> None:
    envelope = "PromQL: sum(rate(errors[5m]))\n  value 0.42\n\ttrailing tab\t\n"
    archive = S3Archive.connect(settings_for(endpoint, "round-trip"))

    archive.put(envelope_key("r-1"), envelope.encode(), content_type="text/plain")
    restored = archive.get(envelope_key("r-1"))

    assert restored == envelope.encode()
    assert hashlib.sha256(restored).hexdigest() == hashlib.sha256(envelope.encode()).hexdigest()


def test_the_archived_bytes_verify_against_the_recorded_hash(endpoint: str) -> None:
    """`ToolCallRecord.envelope_sha256` is stored in Postgres beside the inline copy.

    The archived object must satisfy the same hash, or the second copy cannot be used to
    check the first and the archive is decoration.
    """
    envelope = "evidence body"
    recorded = hashlib.sha256(envelope.encode()).hexdigest()
    archive = S3Archive.connect(settings_for(endpoint, "hash-check"))

    archive.put(envelope_key("r-2"), envelope.encode())
    body = archive.get(envelope_key("r-2"))

    assert body is not None
    assert hashlib.sha256(body).hexdigest() == recorded


def test_a_key_that_was_never_written_reads_as_none(endpoint: str) -> None:
    archive = S3Archive.connect(settings_for(endpoint, "absent-keys"))

    assert archive.get(envelope_key("never-written")) is None
