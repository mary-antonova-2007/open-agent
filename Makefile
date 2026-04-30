.PHONY: install test lint typecheck quality migrate revision seed-admin run

install:
	python3 -m pip install -e ".[dev]"

test:
	pytest

lint:
	ruff check .

typecheck:
	mypy app/domain app/application app/tools app/api

quality: lint typecheck test

migrate:
	alembic upgrade head

revision:
	alembic revision --autogenerate -m "$(m)"

seed-admin:
	python -m scripts.seed_admin

run:
	uvicorn app.api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
