.PHONY: help install install-dev lint format typecheck test test-cov verify clean render-diagrams run-orchestrator run-litellm

help:
	@echo "Eidolon development targets"
	@echo ""
	@echo "  install           Install runtime deps"
	@echo "  install-dev       Install runtime + dev deps"
	@echo "  lint              Run ruff"
	@echo "  format            Run ruff format"
	@echo "  typecheck         Run mypy"
	@echo "  test              Run pytest"
	@echo "  test-cov          Run pytest with coverage"
	@echo "  verify            Run lint + typecheck + tests + cli smoke (CI gate)"
	@echo "  clean             Remove build artifacts"
	@echo "  render-diagrams   Render D2 diagrams to SVG"
	@echo "  run-orchestrator  Run orchestrator locally"
	@echo "  run-litellm       Run LiteLLM router locally"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy eidolon

test:
	pytest

test-cov:
	pytest --cov=eidolon --cov-report=term-missing --cov-report=html

verify: lint typecheck test
	@eidolon --help > /dev/null
	@echo "verify ok"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist *.egg-info htmlcov .coverage

render-diagrams:
	cd docs/diagrams && for d2 in *.d2; do \
		d2 "$$d2" "$${d2%.d2}.svg"; \
	done

run-orchestrator:
	uvicorn eidolon.orchestrator.app:app --host 127.0.0.1 --port 8000 --reload

run-litellm:
	litellm --config eidolon/orchestrator/litellm-config/router.yaml --port 4000
