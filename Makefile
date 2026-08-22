.PHONY: help install lint format type test check up down eval

help:
	@grep -E '^[a-z]+:' Makefile | sed 's/:.*//' | tr '\n' ' '; echo

install:
	uv sync

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

type:
	uv run mypy

test:
	uv run pytest

check: lint type test
	@echo "all checks passed"

up:
	docker compose --profile platform up -d

down:
	docker compose --profile platform down

eval:
	@echo "eval harness arrives in Phase 4 (T4.1) - see docs/adr and the execution plan"

# ---- T1.1: the world (OpenTelemetry Demo, pinned) ----
OTEL_DEMO_VERSION := v1.2.1
OTEL_DEMO_REPO := https://github.com/open-telemetry/opentelemetry-demo.git

world/.cloned:
	git clone --depth 1 --branch $(OTEL_DEMO_VERSION) $(OTEL_DEMO_REPO) world
	touch world/.cloned

COMPOSE_WORLD := docker compose --progress plain -f docker-compose.yml -f ../compose/world-arm64.override.yml -f ../compose/telemetry.yml

ffs-stub:
	docker build -t faultline/ffs-stub:1 compose/ffs-stub

world-up: world/.cloned ffs-stub
	cd world && $(COMPOSE_WORLD) up -d --no-build

world-down:
	cd world && $(COMPOSE_WORLD) down

world-ps:
	cd world && $(COMPOSE_WORLD) ps

world-logs:
	cd world && $(COMPOSE_WORLD) logs -f --tail=50
