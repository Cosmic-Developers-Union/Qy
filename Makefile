.PHONY: clean build check release lint test

test:
	uv run python -m pytest tests/ -v --cov=qy --cov-report=term-missing

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