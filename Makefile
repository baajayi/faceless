.PHONY: up down build logs shell-api shell-worker migrate run-daily test lint clean

# ── Docker Compose ────────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f

logs-worker:
	docker compose logs -f worker

logs-api:
	docker compose logs -f api

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	docker compose exec api alembic upgrade head

migrate-down:
	docker compose exec api alembic downgrade -1

# ── Shells ────────────────────────────────────────────────────────────────────
shell-api:
	docker compose exec api bash

shell-worker:
	docker compose exec worker bash

shell-db:
	docker compose exec postgres psql -U faceless -d faceless

# ── Pipeline ──────────────────────────────────────────────────────────────────
run-daily:
	docker compose exec api python -m app.run_daily

run-daily-date:
	docker compose exec api python -m app.run_daily --date $(DATE)

run-daily-force:
	docker compose exec api python -m app.run_daily --force

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	docker compose exec api pytest tests/ -v

test-unit:
	docker compose exec api pytest tests/unit/ -v

test-integration:
	docker compose exec api pytest tests/integration/ -v

test-local:
	pytest tests/ -v

# ── Linting ───────────────────────────────────────────────────────────────────
lint:
	ruff check app/ tests/
	ruff format --check app/ tests/

fmt:
	ruff format app/ tests/

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage

clean-output:
	find output/ -mindepth 1 -not -name .gitkeep -delete
