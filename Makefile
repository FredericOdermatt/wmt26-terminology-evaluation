UV = uv run

install:
	uv sync

ruff:
	$(UV) ruff check src --fix && $(UV) ruff format src

ruff-ci:
	$(UV) ruff check src && $(UV) ruff format --check src

format: ruff

check: ruff-ci

.PHONY: install ruff ruff-ci format check
