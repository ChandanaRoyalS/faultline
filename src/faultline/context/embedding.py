"""Where vectors come from (T2.4b, ADR-0018).

ADR-0002 chose pgvector and assumed vectors without naming a source. ADR-0018 names one: a
**local model**, because a benchmark whose numbers have to be defensible cannot have its
retrieval depend on a remote service nobody pins. The full trade-off is recorded there.

Three things make the choice replaceable rather than load-bearing:

- `Embedder` is a Protocol, and nothing else in the corpus layer imports a model.
- Every chunk is stored with the **embedder name and dimension that produced its vector**, so
  a model change is visible in the data rather than silently mixing incomparable vectors -
  the same argument ADR-0014 makes about a bundle knowing which world it was recorded against.
- The real model is an optional dependency, imported lazily, so `make check` never loads it.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

TOKEN = re.compile(r"[a-z0-9_-]+")


class Embedder(Protocol):
    """Text to vector. The seam the tests substitute at, and the model choice's escape hatch."""

    @property
    def name(self) -> str:
        """Recorded on every chunk, so vectors from two models cannot be compared by accident."""

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbedder:
    """Deterministic, dependency-free, and **not a model**.

    Hashed bag-of-words projected onto the unit sphere. Two texts sharing vocabulary land
    close together, which is enough for a test to assert that exclusion changed a result and
    not enough for anything to be judged on. It exists so the corpus logic can be tested
    without downloading weights, and so `make check` stays hermetic and fast.

    It is deterministic across processes and machines - `hashlib`, not `hash()`, whose seed
    is randomised per process.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return f"hashing-{self._dimensions}"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        for token in TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        return vector if norm == 0 else [value / norm for value in vector]


class SentenceTransformerEmbedder:
    """`all-MiniLM-L6-v2`, 384 dimensions, run locally (ADR-0018).

    Imported lazily and installed as an optional dependency (`faultline[embeddings]`),
    because it pulls torch and this repo's `make check` runs in under three seconds without
    it. Nothing in the seeding or retrieval path imports this module's model until something
    asks for a vector.
    """

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self._model_name = model
        self._model: object | None = None

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return 384

    def _load(self) -> object:  # pragma: no cover - needs the optional dependency
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - as above
        model = self._load()
        encoded = model.encode(texts, normalize_embeddings=True)  # type: ignore[attr-defined]
        return [[float(value) for value in row] for row in encoded]
