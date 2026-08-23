UV = uv run

install:
	uv sync

ruff:
	$(UV) ruff check src --fix && $(UV) ruff format src

ruff-ci:
	$(UV) ruff check src && $(UV) ruff format --check src

format: ruff

check: ruff-ci

evaluate:
	$(UV) python -m wmt26_terminology.evaluate --submissions $(SUBMISSIONS) --out $(OUT)

evaluate-oracle:
	$(UV) python -m wmt26_terminology.evaluate --oracle

.PHONY: install evaluate evaluate-oracle ruff ruff-ci format check
