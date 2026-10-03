.PHONY: check test run selftest verify-audit fmt models docs bench

UV := uv run
TARGET ?= http://127.0.0.1:8080

check:
	$(UV) ruff check .
	$(UV) ruff format --check .
	$(UV) mypy
	$(UV) lint-imports
	$(UV) pytest -q

test:
	$(UV) pytest -q

run:
	$(UV) uvicorn control_layer.app:create_app --factory --host 127.0.0.1 --port 8080

selftest:
	mkdir -p var
	$(UV) pytest -q tests/test_cases.py --target $(TARGET) --junitxml=var/selftest.xml

verify-audit:
	$(UV) python -m control_layer.adapters.audit_jsonl verify var/audit.jsonl

fmt:
	$(UV) ruff format .
	$(UV) ruff check --fix .

models:
	$(UV) python scripts/fetch_models.py

docs:
	python3 -m http.server --directory site --bind 127.0.0.1 8000

bench:
	mkdir -p var
	$(UV) python scripts/bench.py --target $(TARGET) --key sk-bench-agent --out var/bench.json
