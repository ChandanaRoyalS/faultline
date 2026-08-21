FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project
COPY src ./src
RUN uv sync --no-dev

FROM python:3.12-slim
RUN useradd --create-home appuser
WORKDIR /app
COPY --from=base /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
# Placeholder entrypoint until T2.1 (ingest API) exists.
CMD ["python", "-c", "import faultline; print(f'faultline {faultline.__version__} - platform arrives at T2.1')"]
