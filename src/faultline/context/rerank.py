"""T7.3's E7 arm: a local cross-encoder that re-scores retrieved candidates.

**Built for the ablation and off by default** (`PREREGISTRATION-T7.3.md`, Addendum 1, the owner's
decision of 2026-10-04). T6.4 deferred reranking by name (Q42), so *rerank on/off* - one of the
plan's T7.3 experiments - had nothing to switch. This is the smallest thing that makes it
switchable: when `ContextSettings.rerank_model` names a cross-encoder, the store fuses
`rerank_candidates` candidates and keeps the `k` this scores highest. Unset, nothing here is
imported and retrieval is exactly what it was.

**Local, from the embedder's own dependency** (`sentence-transformers`, ADR-0018), so it adds no
API cost. **Pinned**: the store refuses to build it without `ContextSettings.rerank_revision`,
and the loaded revision is printed, so an investigation's transcript says which weights ranked
its retrieval.
"""

from __future__ import annotations

from typing import Protocol


class Reranker(Protocol):
    """Scores each text's relevance to the query. Higher is more relevant."""

    name: str

    def score(self, query: str, texts: list[str]) -> list[float]: ...


class CrossEncoderReranker:
    """`sentence_transformers.CrossEncoder`, loaded on first use."""

    def __init__(self, name: str, revision: str | None = None) -> None:
        self.name = name
        self.revision = revision
        self._model: object | None = None

    def _load(self) -> object:  # pragma: no cover - needs the optional dependency
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.name, revision=self.revision)
            config = getattr(getattr(self._model, "model", None), "config", None)
            loaded = getattr(config, "_commit_hash", None)
            print(f"reranker: {self.name} at revision {loaded or self.revision}")
        return self._model

    def score(self, query: str, texts: list[str]) -> list[float]:  # pragma: no cover - as above
        if not texts:
            return []
        model = self._load()
        scores = model.predict([(query, text) for text in texts])  # type: ignore[attr-defined]
        return [float(s) for s in scores]


def rerank(
    reranker: Reranker, query: str, keyed: list[tuple[str, str]], k: int
) -> list[tuple[str, float]]:
    """`(key, text)` candidates, re-ordered by the reranker's score and cut to `k`.

    Ties keep the order the candidates arrived in (Python's sort is stable), so a reranker that
    scores two chunks equally leaves fusion's order between them.
    """
    scores = reranker.score(query, [text for _, text in keyed])
    order = sorted(range(len(keyed)), key=lambda i: -scores[i])
    return [(keyed[i][0], scores[i]) for i in order[:k]]
