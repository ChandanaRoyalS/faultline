.PHONY: help install lint format type test check up down eval-up eval-down eval demo \
        ffs-stub world-up world-down world-ps world-logs dashboards

help:
	@grep -E '^[a-z][a-z0-9-]*:' Makefile | sed 's/:.*//' | tr '\n' ' '; echo

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

# ---- T0.3: the three bring-ups ----
# The plan names three profiles: platform-only, full-world, eval. Two are compose
# profiles here and one deliberately is not. The world is a pinned clone of somebody
# else's repository (ADR-0026), never vendored into this one, so it cannot be a profile
# in this compose file - it comes up from its own, under our overlays, via `world-up`.
#
# `eval` is the platform plus the world: a scored run talks to postgres and redis here
# and to the demo's telemetry backends there, and needs both. The harness itself runs on
# the host rather than in a container, which is why the eval profile adds no service of
# its own and sits on the same two as `platform`.
eval-up:
	docker compose --profile eval up -d
	$(MAKE) world-up

eval-down:
	$(MAKE) world-down
	docker compose --profile eval down

# One scored scenario, end to end: baseline gate, inject, correlate, investigate, revert,
# confirm recovery, score. Real model calls - see README's "Scoring a scenario".
#
# T7.47: this was a stub echoing "eval harness arrives in Phase 4" long after it had. A
# documented target that does nothing is worse than an absent one. G4's condition names
# `make eval` and is met when this has scored the catalog and the A/A check declares null.
#
# INTENT is mandatory and has no default, because the baseline gate projects kafka's memory
# over the work still to come and cannot do that unless told what the work is (T7.33).
SCENARIO ?=
INTENT   ?=
eval:
ifeq ($(strip $(SCENARIO)),)
	@echo "usage: make eval SCENARIO=<id> INTENT=--single-run"
	@echo "       make eval SCENARIO=<id> INTENT='--runs-remaining N'   # part of a sweep"
	@echo ""
	@echo "scenario ids: uv run faultline-inject list"
	@exit 2
endif
ifeq ($(strip $(INTENT)),)
	@echo "refusing: INTENT is required - --single-run, or --runs-remaining N."
	@echo "The gate projects kafka's memory over the work still to come and cannot"
	@echo "do that unless told what the work is (T7.33). Nothing was injected."
	@exit 2
endif
	uv run faultline-eval $(SCENARIO) $(INTENT) \
		--max-tool-calls 4 --max-tool-calls-changes 8 --max-tokens 120000

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

# The clone carries exactly two untracked files and both are expected (T7.16, ADR-0026):
#
#   .cloned                                        this marker
#   src/grafana/provisioning/datasources/loki.yml  EMPTY, created by Docker
#
# The second is a mount point, not a file anyone wrote. The demo's grafana bind-mounts
# src/grafana/provisioning/ as a directory, and compose/telemetry.yml mounts a single file
# at datasources/loki.yml inside it; Docker has to materialise that target, and because the
# parent is a host bind mount the empty file lands here. The container reads the real
# content from compose/grafana-loki-datasource.yml, which overlays it. Deleting it
# accomplishes nothing - the next `make world-up` recreates it.
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
	@$(MAKE) --no-print-directory dashboards

# T1.2: the shop-health dashboard, pushed over Grafana's API rather than mounted.
# A compose mount would move compose_digest and re-found the world for a panel that
# changes nothing the harness measures - see ADR-0030 and the script's own docstring.
# Idempotent: overwrite: true, so running it twice is running it once.
dashboards:
	uv run python scripts/provision_dashboards.py

world-down:
	cd world && $(COMPOSE_WORLD) down

world-ps:
	cd world && $(COMPOSE_WORLD) ps

world-logs:
	cd world && $(COMPOSE_WORLD) logs -f --tail=50

test-integration: ## run the integration tests against real Postgres and Redis (needs Docker)
	uv run pytest -m integration -o addopts=-q

migrate: ## apply the database schema (alembic upgrade head)
	uv run faultline-migrate

openapi: ## regenerate the committed REST contract snapshot (docs/contracts/)
	uv run python -c "import json, pathlib; from faultline.ingest.app import app; \
	pathlib.Path('docs/contracts/ingest-openapi.json').write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + '\n')"
	@echo "docs/contracts/ingest-openapi.json regenerated - read the diff before committing"
