FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Dependency layer first, so code changes don't invalidate the dependency cache.
COPY pyproject.toml uv.lock ./
# **Both extras, and that is the point** - the same sentence `make install` carries. A bare
# `uv sync` gives a tree that passes every check and cannot run the demo or a scored run (T5.4b),
# and it gave an image whose orchestrator could not open a model client and whose seeder could not
# import its embedder: the deployment could remember investigations and not produce one, which is
# T5.5b's deviation three, reintroduced by the build (T5.5c, defect twenty-six). `archive` is
# deliberately left out: nothing in the deployment writes to an object store.
RUN uv sync --frozen --no-dev --no-install-project --extra agents --extra embeddings
# Project layer: hatchling reads readme/license from pyproject, so both must be present.
COPY README.md LICENSE ./
COPY src ./src
# Repository data the runtime resolves by walking up from the installed package: the schema
# history and its configuration (T2.3), and the allowlist action catalog (ADR-0032). The image
# copied only `src` until 2026-09-01, which left both unreachable inside a container while
# resolving perfectly in a clone - the kind of difference that first appears on deployment.
COPY alembic.ini ./
COPY migrations ./migrations
COPY knowledge ./knowledge
# The retrieval corpus's source, and **the dev split alone** (ADR-0008 axis 1: a holdout narrative
# in the corpus is the answer key to a scenario nothing downstream would notice had leaked). The
# documented `docker compose exec faultline faultline-seed` walked `/app/evals/scenarios/artifacts/dev`
# and found the directory absent - the third run-time path the image had left out (T5.5c).
COPY evals/scenarios/artifacts/dev ./evals/scenarios/artifacts/dev
# The dependency graph ADR-0017 committed rather than querying Jaeger for - `ServiceGraph.from_snapshot`
# reads it at the start of every investigation. The fifth run-time path found missing, by the first
# live investigation on the first live deployment (T5.5c, defect thirty). `tests/test_packaging.py`
# now derives this list from the resolvers in the code rather than from anyone's memory.
COPY docs/evidence/t2.4-dependency-graph/dependencies.json ./docs/evidence/t2.4-dependency-graph/dependencies.json
RUN uv sync --frozen --no-dev --extra agents --extra embeddings

FROM python:3.12-slim
RUN useradd --create-home appuser
WORKDIR /app
COPY --from=base /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
# T5.5. The placeholder that stood here until now printed a version string and exited - written
# before T2.1 had a server to start, and never revisited once it did. An image whose CMD exits
# immediately is an image nobody ran, and `deploy/` is the first thing that would have.
#
# `faultline-ingest` serves the alert receiver alone. `deploy/compose.yml` passes --postgres-dsn,
# which adds T5.1's incident read surface and screen on the same port, behind basic auth.
EXPOSE 8000
CMD ["faultline-ingest", "--host", "0.0.0.0", "--port", "8000"]
