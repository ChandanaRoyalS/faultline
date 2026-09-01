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
# Placeholder entrypoint until T2.1 (ingest API) exists.
CMD ["python", "-c", "import faultline; print(f'faultline {faultline.__version__} - platform arrives at T2.1')"]
