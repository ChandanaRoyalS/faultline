"""The past-incident store: hybrid retrieval over seeded narratives (T2.4b, ADR-0002/0018).

ADR-0002 chose pgvector inside the existing Postgres so that "provenance filters (origin,
service, recency - the contamination model's enforcement point) are plain SQL WHERE clauses
in the same query", and so leave-one-out exclusion at T4.1b is enforced in the query itself.

**`exclude_origins` is in the signature from day one.** T4.1b then passes an argument rather
than patching a query, and the two arms of the hybrid cannot drift into filtering
differently, because both take the same parameter at the same call.

**It was `exclude_origin: str | None` until T6.5**, which widened it to a set so the
learning-effect measurement's two arms could sit on one corpus - the WITHOUT arm excluding a
whole fault class, the WITH arm excluding one scenario, neither re-seeding anything. That was
the only production change the measurement required, and ADR-0018's T6.5 addendum records it.

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


def normalise_exclusions(origins: frozenset[str] | str | None) -> frozenset[str]:
    """`None` and the empty set both mean *exclude nothing*. **A bare string is an error.**

    The guard is not pedantry. `str` is a `Collection[str]`, so `exclude_origins="scenario:x"`
    would type-check at most call sites and exclude sixteen single characters - matching no
    origin, excluding nothing, and reporting a perfectly healthy `excluded_count` of zero, which
    T4.1b would read as *the corpus does not hold this scenario*. A leave-one-out that silently
    does not happen is the exact defect ADR-0008 axis 2 exists to prevent, so the parameter that
    used to take a string refuses one now rather than doing something plausible with it.
    """
    if origins is None:
        return frozenset()
    if isinstance(origins, str):
        raise TypeError(
            f"exclude_origins takes a set of origins, not the string {origins!r}. A string is "
            "iterable, so this would have excluded its characters and nothing else - see "
            "ADR-0008 axis 2 and T6.5's widening of this parameter."
        )
    return frozenset(origins)


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

    def prune_document(self, document_id: str, keep: set[str]) -> int:
        """Remove this document's chunks that its current source no longer produces.

        **Seeding was idempotent and not reconciling** (T6.4 §2.5, Q40). A chunk's key is
        `document_id#section_index`, so deleting or renaming a section leaves the old row behind:
        `add` upserts the sections that still exist and has nothing to say about the ones that
        do not. The orphan stays in the retrieval pool, stays inside `body_sha256`, and looks
        like a legitimate chunk of a legitimate document.

        It is not theoretical. T6.4's first retrieval measurement ran against a corpus holding
        263 chunks over 50 documents whose seed had just reported 261.
        """

    def excluded_count(self, origins: frozenset[str]) -> int:
        """How many chunks carry one of `origins`, and are unreachable while they are excluded.

        **T4.1b's "count of filtered artifacts", and the number that answers whether the filter
        fired.** The plan asks for the count to be logged per run and for a scored run where the
        filter did not fire to be *marked invalid, not merely annotated* - because
        *"silent non-enforcement is how this defect returns"*.

        **Counted by origin rather than by candidates dropped, and the difference is the whole
        design.** A dropped-candidate count is implementation-specific: retrieval has two arms,
        each takes its own top-k, and neither ever sees most of the corpus, so "how many rows the
        exclusion removed from the ranking" is a number about the ranking rather than about the
        contamination boundary. What ADR-0008 axis 2 actually asserts is that a scenario's own
        artifacts were *unreachable*, and this is the count of exactly those.

        **Zero is the signal.** On a scored dev run the scenario's own narrative is in the corpus
        by construction - that is what leave-one-out means - so a zero here says either the
        corpus does not hold it or the exclusion did not apply to it. Both invalidate the run's
        leave-one-out claim, and neither is visible from `exclude_origins` alone, which records
        only that an argument was passed.

        **A set makes this number weaker than it was, and T6.5 says so rather than discovering
        it.** With one origin, a positive count meant *S's own artifacts were unreachable*. With
        four, a positive count means *something in the set was unreachable* - which a run
        excluding three same-class scenarios satisfies while S's own narrative stays reachable.
        The count alone can no longer carry T4.1b's assertion, so `run.classify_retrievals`
        takes the scenario's own origin and checks it is in the recorded set.
        """

    def search(
        self, query: str, k: int = 5, exclude_origins: frozenset[str] | None = None
    ) -> list[Hit]:
        """Hybrid retrieval, with the exclusion applied to **both** arms.

        `exclude_origins=None` is legal and is the product case: a live incident has no origin
        to exclude. **Every benchmark retrieval passes it** - ADR-0008's axis 2, where the
        nearest neighbour to scenario S is S's own rehearsal, written in the label author's
        own words. See ADR-0018 and its T6.5 addendum.
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

    def prune_document(self, document_id: str, keep: set[str]) -> int:
        stale = [
            key
            for key, chunk in self.chunks.items()
            if chunk.document_id == document_id and key not in keep
        ]
        for key in stale:
            del self.chunks[key]
        return len(stale)

    def excluded_count(self, origins: frozenset[str]) -> int:
        return sum(1 for chunk in self.chunks.values() if chunk.origin in origins)

    def search(
        self, query: str, k: int = 5, exclude_origins: frozenset[str] | None = None
    ) -> list[Hit]:
        excluded = normalise_exclusions(exclude_origins)
        candidates = [key for key, chunk in self.chunks.items() if chunk.origin not in excluded]
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


# `ts_rank_cd`'s normalisation moved to `ContextSettings.text_normalisation` at Q53. It was a
# module constant here and a constant cannot be varied across a subprocess, which the Q53 pilot
# has to do - one `faultline-investigate` at (0, k=3) and one at (2, k=5) on the same incident.
# The setting carries the argument for why it is 0; this comment exists so a reader who greps for
# the old name lands somewhere.

TEXT_QUERY = "replace(plainto_tsquery('english', %(q)s)::text, ' & ', ' | ')::tsquery"
"""The text arm's query, **disjunctive** (Q39, `PREREGISTRATION-Q39.md`).

**What was wrong.** `plainto_tsquery` ANDs every lexeme, so a query had to have all of its terms
in one chunk to match at all. Measured against the corpus: one term matched 37 chunks, three
matched 1, and a real six-term planner query matched **none**. All 43 golden queries returned
zero rows on this arm, so `fuse()` had been fusing one list since T2.4b and `RRF_K` had been a
constant over a single arm. Every figure in `RETRIEVAL-2026-09-12-t6.4.md` is labelled one-armed
for that reason.

**Why the operator is swapped rather than the function.** `websearch_to_tsquery` was the other
candidate Q39 named and it is not one: it ANDs too, matching 0 of 43, and differs from
`plainto_tsquery` on only 22 queries and only by rendering hyphenated compounds as phrase
constraints - *more* restrictive. Taking `plainto_tsquery`'s own output and replacing ` & ` with
` | ` keeps its stemming, its stopword removal and its quoting exactly, and changes the one thing
that was wrong. Postgres quotes each lexeme, so a `&` in the input is inside quotes and is not a
separator; an empty or stopword-only query yields an empty `tsquery`, which matches nothing -
the correct answer rather than an error.

**What it costs, stated because the registration predicts from it.** The arm stops being a filter
and becomes a ranking problem: a disjunction over six terms matches a **median of 174 of the 211
authored chunks**, and `ts_rank_cd` with `LIMIT k` then does the discriminating. Whether that is
an improvement is the question `PREREGISTRATION-Q39.md` §4 registers ten predictions about.
"""


class PgVectorPastIncidentStore:
    """The real one. Not exercised by `make check` - the tests use the in-memory double.

    Two queries per search, fused in Python by `fuse`, so the ranking rule is the one the
    tests cover. The exclusion is a `WHERE origin <> %s` on both, which is exactly the shape
    ADR-0002 chose pgvector for.
    """

    def __init__(
        self, connection: Any, embedder: Embedder, normalisation: int | None = None
    ) -> None:
        self._conn = connection
        self._embedder = embedder
        if normalisation is None:
            from faultline.context.settings import ContextSettings

            normalisation = ContextSettings().text_normalisation
        self._normalisation = int(normalisation)
        """Read once at construction, not per query: a store whose ranking could change
        mid-investigation would make a trajectory describe two pipelines."""

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
                    # **Every column the source produces, not a chosen subset.** The subset was
                    # body, embedding, embedder, recorded_from, scenario_fingerprint - and it
                    # omitted `section`, so renaming a heading at an unchanged index wrote the
                    # new body under the old heading and left the old heading there forever.
                    # `prune_document` cannot catch it either: the key is
                    # `document_id#section_index`, which a rename does not move, so the row is
                    # never stale by that test.
                    #
                    # **That is Q45's nine runbooks.** The row diagnosed them as a deployment the
                    # seeder had not reached. They survived a seeder that reached them - measured
                    # 2026-09-15, thirteen headings still stale in the store immediately after a
                    # full `faultline-seed` that printed all forty runbooks as seeded. A corpus
                    # that cannot take an edit to a document it already holds is one the drift
                    # check can never report agreement about, and its exit code had been
                    # permanently 1 for that reason.
                    #
                    # Listed exhaustively rather than extended by one column, because the next
                    # omission would be found the same way. `id` is the conflict target and the
                    # only thing that does not move; `tests/test_corpus_hygiene.py` parses this
                    # statement and asserts every other inserted column appears here.
                    "ON CONFLICT (id) DO UPDATE SET document_id = EXCLUDED.document_id, "
                    "section = EXCLUDED.section, section_index = EXCLUDED.section_index, "
                    "body = EXCLUDED.body, origin = EXCLUDED.origin, split = EXCLUDED.split, "
                    "scenario_id = EXCLUDED.scenario_id, fault_class = EXCLUDED.fault_class, "
                    "scenario_fingerprint = EXCLUDED.scenario_fingerprint, "
                    "recorded_from = EXCLUDED.recorded_from, title = EXCLUDED.title, "
                    "source_path = EXCLUDED.source_path, embedder = EXCLUDED.embedder, "
                    "dimensions = EXCLUDED.dimensions, embedding = EXCLUDED.embedding",
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

    def prune_document(self, document_id: str, keep: set[str]) -> int:
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM incident_chunks WHERE document_id = %s AND NOT (id = ANY(%s))",
                (document_id, list(keep)),
            )
            return int(cur.rowcount)

    def excluded_count(self, origins: frozenset[str]) -> int:
        if not origins:
            return 0
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM incident_chunks WHERE origin = ANY(%s)",
                (sorted(origins),),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def search(
        self, query: str, k: int = 5, exclude_origins: frozenset[str] | None = None
    ) -> list[Hit]:
        vector = str(self._embedder.embed([query])[0])
        excluded = normalise_exclusions(exclude_origins)
        # `<> ALL(...)` rather than `NOT IN (...)`, because `NOT IN` against an array containing
        # a NULL is NULL for every row and would return nothing at all. No origin is null today;
        # the form that cannot break that way costs nothing.
        exclusion = "" if not excluded else " AND origin <> ALL(%(origins)s)"
        params: dict[str, Any] = {
            "q": query,
            "v": vector,
            "k": k,
            "origins": sorted(excluded),
        }

        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM incident_chunks WHERE TRUE"
                + exclusion
                # **`, id` is a tiebreaker and not a ranking change** (Q68). Without it both
                # arms end `ORDER BY ... LIMIT k` on one key, so at a tie the rows returned are
                # whichever the scan reaches first - heap order, which moves whenever rows are
                # rewritten. Measured 2026-09-15: 22 of the 43 golden queries tie across the k
                # boundary in the text arm, and re-seeding an unchanged corpus moved `recall@3`
                # over 0.302 / 0.326 / 0.349, a two-query spread with byte-identical bodies and
                # embeddings.
                #
                # `id` is `document_id#section_index`, so the order it imposes is alphabetical
                # and arbitrary. **That is deliberate.** A tiebreaker that preferred shorter
                # chunks or authored ones would be a ranking change wearing a determinism
                # repair, and it would move figures for a reason nobody registered. This makes
                # the instrument reproducible; it does not make a tie correct, because a tie has
                # no correct answer.
                + " ORDER BY embedding <=> %(v)s::vector, id LIMIT %(k)s",
                params,
            )
            dense = [str(row[0]) for row in cur.fetchall()]
            cur.execute(
                "WITH tq AS (SELECT " + TEXT_QUERY + " AS q) "
                "SELECT id FROM incident_chunks, tq WHERE body_tsv @@ tq.q"
                + exclusion
                + f" ORDER BY ts_rank_cd(body_tsv, tq.q, {self._normalisation}) DESC, id"
                + " LIMIT %(k)s",
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
