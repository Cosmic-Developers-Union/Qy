.PHONY: clean build check release lint

clean:
	rm -rf dist/ build/ *.egg-info

build: clean
	uv build
	uv run twine check dist/*

check:
	uv run twine check dist/*

lint:
	uv run ruff check .
	uv run ty check .
	uv run ruff format --check .

release:
	git push
	$(MAKE) build
	uv run twine upload -r testpypi dist/*
	uv run twine upload dist/*
