# ADR-0002: pgvector over a dedicated vector database

- **Status:** accepted
- **Date:** 2026-08-21

## Context
Retrieval serves runbooks, postmortems, and past incidents — a corpus of order 10^2–10^3
documents (T6.4 commits to ≥50). Retrieval is hybrid: dense vectors fused with Postgres
full-text search, then reranked. Postgres is already the system of record for incidents,
evidence, and eval runs.

## Decision
pgvector inside the existing Postgres. Dense and sparse retrieval live beside the
relational data they describe; provenance filters (origin, service, recency — the
contamination model's enforcement point) are plain SQL WHERE clauses in the same query.

## Consequences
Easier: one database, transactional consistency between documents and their metadata,
leave-one-out exclusion (T4.1b) enforced in the query itself. Harder: no ANN performance at
scale — irrelevant below ~10^5 vectors. Revisit if: corpus grows past ~10^5 chunks or
per-query latency budgets shrink below what exact search delivers.
