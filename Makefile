# ────────────────────────────────────────────────────────
# Pi Backend — developer shortcuts
# ────────────────────────────────────────────────────────

.PHONY: help install dev run stop logs shell db-shell redis-shell \
        migrate migration test lint format clean build deploy

help:
	@echo "Pi Backend — available targets:"
	@echo "  make install        Install deps into .venv"
	@echo "  make dev            Start full stack (postgres + redis + api + worker)"
	@echo "  make run            Run API server locally (no docker)"
	@echo "  make stop           Stop docker stack"
	@echo "  make logs           Tail API logs"
	@echo "  make shell          Open shell in API container"
	@echo "  make db-shell       psql into postgres"
	@echo "  make redis-shell    redis-cli into redis"
	@echo "  make migrate        Apply pending DB migrations"
	@echo "  make migration m=...  Generate new migration with message"
	@echo "  make test           Run pytest"
	@echo "  make lint           Run ruff + mypy"
	@echo "  make format         Run ruff format"
	@echo "  make seed           Seed DB with demo license + templates"

install:
	python -m venv .venv
	.venv/Scripts/pip install -r requirements.txt -e ".[dev]"

dev:
	docker compose up -d
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

stop:
	docker compose down

logs:
	docker compose logs -f api

shell:
	docker compose exec api bash

db-shell:
	docker compose exec postgres psql -U pi -d pi_backend

redis-shell:
	docker compose exec redis redis-cli

migrate:
	docker compose exec api alembic upgrade head

migration:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test:
	pytest -v --cov=app tests/

lint:
	ruff check app/ tests/
	mypy app/

format:
	ruff format app/ tests/
	ruff check --fix app/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov dist build

seed:
	docker compose exec api python -m scripts.seed_templates
	docker compose exec api python -m scripts.create_license --tier pro --email demo@pi.com
