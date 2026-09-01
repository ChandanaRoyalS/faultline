"""The past-incident store: hybrid retrieval over seeded narratives (T2.4b, ADR-0002/0018).

ADR-0002 chose pgvector inside the existing Postgres so that "provenance filters (origin,
service, recency - the contamination model's enforcement point) are plain SQL WHERE clauses
in the same query", and so leave-one-out exclusion at T4.1b is enforced in the query itself.

**`exclude_origin` is in the signature from day one.** T4.1b then passes an argument rather
than patching a query, and the two arms of the hybrid cannot drift into filtering
differently, because both take the same parameter at the same call.

The fusion rule lives here in Python rather than in SQL, deliberately: both implementations
use it, so the in-memory double exercises the same ranking the real store does.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

from faultline.context.corpus import Chunk
from faultline.context.embedding import Embedder

RRF_K = 60
"""Reciprocal-rank-fusion constant, at its conventional value.

Chosen rather than tuned, and there is nothing to tune it against: ranking quality is a T4.2
measurement over scored runs, and this corpus holds seven documents. Recorded as a default
with a reason and no measurement, in the same class as ADR-0016's four."""

TOKEN = re.compile(r"[a-z0-9_-]+")


@dataclass(frozen=True, slots=True)
class Hit:
    chunk: Chunk
    score: float
    dense_rank: int | None = None
    text_rank: int | None = None


class PastIncidentStore(Protocol):
    """What T3.x retrieves from. The seam the tests substitute at."""

    def add(self, chunks: list[Chunk]) -> int:
        """Upsert chunks. Returns how many were written."""

    def count(self) -> int: ...

    def search(self, query: str, k: int = 5, exclude_origin: str | None = None) -> list[Hit]:
        """Hybrid retrieval, with the exclusion applied to **both** arms.

        `exclude_origin=None` is legal and is the product case: a live incident has no origin
        to exclude. **Every benchmark retrieval passes it** - ADR-0008's axis 2, where the
        nearest neighbour to scenario S is S's own rehearsal, written in the label author's
        own words. See ADR-0018.
        """


def fuse(ranked: list[list[str]], limit: int) -> dict[str, tuple[float, list[int | None]]]:
    """Reciprocal rank fusion over one ranked id list per arm.

    Rank-based rather than score-based because a cosine distance and a `ts_rank_cd` have no
    common scale, and normalising two incomparable scores invents a relationship between them.
    """
    scores: dict[str, float] = {}
    positions: dict[str, list[int | None]] = {}
    for arm_index, arm in enumerate(ranked):
        for rank, key in enumerate(arm, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            positions.setdefault(key, [None] * len(ranked))[arm_index] = rank
    best = sorted(scores, key=lambda key: -scores[key])[:limit]
    return {key: (scores[key], positions[key]) for key in best}


def chunk_key(chunk: Chunk) -> str:
    return f"{chunk.document_id}#{chunk.section_index}"


class InMemoryPastIncidentStore:
    """A dict with the same retrieval rule. For tests, and for reading in a REPL.

    The dense arm is cosine over the injected embedder; the text arm is token overlap, which
    stands in for Postgres full-text. Neither is the real ranking - what it exercises is the
    fusion, the exclusion, and the provenance, which is where the logic that can be wrong is.
    """

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self.chunks: dict[str, Chunk] = {}
        self.vectors: dict[str, list[float]] = {}

    def add(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            key = chunk_key(chunk)
            self.chunks[key] = chunk
            self.vectors[key] = vector
        return len(chunks)

    def count(self) -> int:
        return len(self.chunks)

    def search(self, query: str, k: int = 5, exclude_origin: str | None = None) -> list[Hit]:
        candidates = [
            key
            for key, chunk in self.chunks.items()
            if exclude_origin is None or chunk.origin != exclude_origin
        ]
        if not candidates:
            return []

        embedded = self._embedder.embed([query])[0]
        dense = sorted(candidates, key=lambda key: -_cosine(embedded, self.vectors[key]))
        wanted = set(TOKEN.findall(query.lower()))
        text = sorted(
            candidates,
            key=lambda key: -len(wanted & set(TOKEN.findall(self.chunks[key].text.lower()))),
        )
        fused = fuse([dense, text], limit=k)
        return [
            Hit(chunk=self.chunks[key], score=score, dense_rank=ranks[0], text_rank=ranks[1])
            for key, (score, ranks) in fused.items()
        ]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return 0.0 if norm == 0 else dot / norm


class PgVectorPastIncidentStore:
    """The real one. Not exercised by `make check` - the tests use the in-memory double.

    Two queries per search, fused in Python by `fuse`, so the ranking rule is the one the
    tests cover. The exclusion is a `WHERE origin <> %s` on both, which is exactly the shape
    ADR-0002 chose pgvector for.
    """

    def __init__(self, connection: Any, embedder: Embedder) -> None:
        self._conn = connection
        self._embedder = embedder

    def add(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        vectors = self._embedder.embed([chunk.text for chunk in chunks])
        with self._conn.cursor() as cur:
            for chunk, vector in zip(chunks, vectors, strict=True):
                cur.execute(
                    "INSERT INTO incident_chunks (id, document_id, section, section_index, "
                    "body, origin, split, scenario_id, fault_class, scenario_fingerprint, "
                    "recorded_from, title, source_path, embedder, dimensions, embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (id) DO UPDATE SET body = EXCLUDED.body, "
                    "embedding = EXCLUDED.embedding, embedder = EXCLUDED.embedder, "
                    "recorded_from = EXCLUDED.recorded_from, "
                    "scenario_fingerprint = EXCLUDED.scenario_fingerprint",
                    (
                        chunk_key(chunk),
                        chunk.document_id,
                        chunk.section,
                        chunk.section_index,
                        chunk.text,
                        chunk.origin,
                        chunk.split,
                        chunk.scenario_id,
                        chunk.fault_class,
                        chunk.scenario_fingerprint,
                        chunk.recorded_from,
                        chunk.title,
                        chunk.source_path,
                        self._embedder.name,
                        self._embedder.dimensions,
                        str(vector),
                    ),
                )
        self._conn.commit()
        return len(chunks)

    def count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM incident_chunks")
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def search(self, query: str, k: int = 5, exclude_origin: str | None = None) -> list[Hit]:
        vector = str(self._embedder.embed([query])[0])
        exclusion = "" if exclude_origin is None else " AND origin <> %(origin)s"
        params: dict[str, Any] = {"q": query, "v": vector, "k": k, "origin": exclude_origin}

        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM incident_chunks WHERE TRUE"
                + exclusion
                + " ORDER BY embedding <=> %(v)s::vector LIMIT %(k)s",
                params,
            )
            dense = [str(row[0]) for row in cur.fetchall()]
            cur.execute(
                "SELECT id FROM incident_chunks WHERE body_tsv @@ plainto_tsquery("
                "'english', %(q)s)" + exclusion + " ORDER BY ts_rank_cd(body_tsv, "
                "plainto_tsquery('english', %(q)s)) DESC LIMIT %(k)s",
                params,
            )
            text = [str(row[0]) for row in cur.fetchall()]

            fused = fuse([dense, text], limit=k)
            if not fused:
                return []
            cur.execute(
                "SELECT id, document_id, section, section_index, body, origin, split, "
                "scenario_id, fault_class, scenario_fingerprint, recorded_from, title, "
                "source_path FROM incident_chunks WHERE id = ANY(%s)",
                (list(fused),),
            )
            rows = {row[0]: row for row in cur.fetchall()}

        hits = []
        for key, (score, ranks) in fused.items():
            row = rows[key]
            hits.append(
                Hit(
                    chunk=Chunk(
                        document_id=row[1],
                        section=row[2],
                        section_index=row[3],
                        text=row[4],
                        origin=row[5],
                        split=row[6],
                        scenario_id=row[7],
                        fault_class=row[8],
                        scenario_fingerprint=row[9],
                        recorded_from=row[10],
                        title=row[11],
                        source_path=row[12],
                    ),
                    score=score,
                    dense_rank=ranks[0],
                    text_rank=ranks[1],
                )
            )
        return hits
