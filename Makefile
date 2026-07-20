# Convenience targets. Prefer `uv run <cmd>` directly if you like.
.PHONY: install browsers sync temporal-up temporal-down migrate initdb recon lint typecheck test fmt

install sync:
	uv sync --extra dev

browsers:
	uv run playwright install chromium

temporal-up:
	docker compose up -d

temporal-down:
	docker compose down

migrate:
	uv run alembic upgrade head

initdb:
	uv run job-intel initdb

recon:
	uv run job-intel recon --company wells_fargo

lint:
	uv run ruff check src tests

fmt:
	uv run ruff format src tests

typecheck:
	uv run pyright

test:
	uv run pytest
