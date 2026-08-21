FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
# Dependency layer first, so code changes don't invalidate the dependency cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
# Project layer: hatchling reads readme/license from pyproject, so both must be present.
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --create-home appuser
WORKDIR /app
COPY --from=base /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
# Placeholder entrypoint until T2.1 (ingest API) exists.
CMD ["python", "-c", "import faultline; print(f'faultline {faultline.__version__} - platform arrives at T2.1')"]
