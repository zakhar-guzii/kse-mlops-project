.PHONY: setup lint

setup:
	uv sync --locked

lint:
	uv run --locked ruff check .
