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
