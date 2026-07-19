SHELL := /bin/bash
UV = uv run

install:
	uv sync

convert-datasets:
	$(UV) python -m wmt26_terminology.convert

evaluate:
	$(UV) python -m wmt26_terminology.evaluate --submissions $(SUBMISSIONS)

evaluate-oracle:
	$(UV) python -m wmt26_terminology.evaluate --oracle

ruff:
	$(UV) ruff check src --fix && $(UV) ruff format src

ruff-ci:
	$(UV) ruff check src && $(UV) ruff format --check src

format: ruff

check: ruff-ci
