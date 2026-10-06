.PHONY: setup api web test lint build check
setup:
	uv sync --locked
	npm ci
	npm run setup:web
api:
	uv run uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
web:
	npm run dev
test:
	uv run pytest -q
	npm run test:tracker
lint:
	uv run python scripts/check_release.py
	uv run ruff check apps scripts
	npm run format:check
build:
	npm run build
check: lint test build
