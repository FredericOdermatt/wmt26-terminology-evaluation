SHELL := /bin/bash
UV = uv run

install:
	uv sync

convert-datasets:
	$(UV) python -m wmt26_terminology.convert

evaluate:
	@echo "not implemented yet"

ruff:
	$(UV) ruff check src --fix && $(UV) ruff format src

ruff-ci:
	$(UV) ruff check src && $(UV) ruff format --check src

format: ruff

check: ruff-ci
