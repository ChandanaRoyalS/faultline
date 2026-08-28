.PHONY: help install lint format type test check up down eval demo

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

# ---- T5.3: the demo ----
# One narrated run of the whole system, end to end, against the live world. Makes real
# model calls; refuses with instructions if the world is down or no key is present.
# Costs about $0.60 and takes about fifteen minutes. The transcript of a real run is in
# docs/demo/transcript.txt for anyone who would rather read than run.
demo:
	uv run faultline-demo

# ---- T1.1: the world (OpenTelemetry Demo, pinned) ----
OTEL_DEMO_VERSION := v1.2.1
OTEL_DEMO_REPO := https://github.com/open-telemetry/opentelemetry-demo.git

world/.cloned:
	git clone --depth 1 --branch $(OTEL_DEMO_VERSION) $(OTEL_DEMO_REPO) world
	touch world/.cloned

COMPOSE_WORLD := docker compose --progress plain -f docker-compose.yml -f ../compose/world-arm64.override.yml -f ../compose/telemetry.yml

# Rebuild the stub only when its source changes. An unconditional build re-resolves the
# pip layer and produces a new image id from identical code, which silently changes the
# world between two rehearsals - it did, and it split the catalog's provenance in half.
# The digest comes from evalharness.provenance so the stamp and the manifest field are
# computed by one function and cannot drift.
FFS_STUB_STAMP := .faultline/ffs-stub.digest

ffs-stub:
	@mkdir -p $(dir $(FFS_STUB_STAMP))
	@digest=$$(uv run python -c 'from evalharness.provenance import ffs_stub_source_digest; print(ffs_stub_source_digest())'); \
	if [ "$$digest" = "$$(cat $(FFS_STUB_STAMP) 2>/dev/null)" ] \
	   && docker image inspect ffs-stub:1 >/dev/null 2>&1; then \
		echo "ffs-stub:1 already built from this source ($${digest})"; \
	else \
		docker build -t ffs-stub:1 compose/ffs-stub && printf '%s' "$$digest" > $(FFS_STUB_STAMP); \
	fi

world-up: world/.cloned ffs-stub
	cd world && $(COMPOSE_WORLD) up -d --no-build

world-down:
	cd world && $(COMPOSE_WORLD) down

world-ps:
	cd world && $(COMPOSE_WORLD) ps

world-logs:
	cd world && $(COMPOSE_WORLD) logs -f --tail=50
