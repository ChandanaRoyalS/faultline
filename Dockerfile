FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Dependency layer first, so code changes don't invalidate the dependency cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
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
RUN uv sync --frozen --no-dev

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
