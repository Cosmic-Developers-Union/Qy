.PHONY: bench bench-baseline bench-check clean build check release lint test

BENCH_BASELINE ?= benchmarks/baseline.json
BENCH_MAX_REGRESSION_PERCENT ?= 10

test:
	uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing

bench:
	uv run python -m qy.benchmark

bench-baseline:
	uv run python -m qy.benchmark --write-baseline $(BENCH_BASELINE)

bench-check:
	uv run python -m qy.benchmark --baseline $(BENCH_BASELINE) --max-regression-percent $(BENCH_MAX_REGRESSION_PERCENT)

clean:
	rm -rf dist/ build/ *.egg-info

build: clean
	uv build
	uv run twine check dist/*

check:
	uv run twine check dist/*

lint:
	uv run ruff check .
	uv run ruff format .
	uv run ty check .

lint-fix:
	uv run ruff check . --fix --unsafe-fixes
	uv run ruff format .
	uv run ty check .

release:
	git push
	$(MAKE) build
	uv run twine upload -r testpypi dist/*
	uv run twine upload dist/*

tokens:
	python scripts/tokens.py
