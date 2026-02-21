db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

dev: db-up migrate run

test:
	pytest -m "not postgres"

test-pg:
	pytest -m "postgres"

era-validate:
	python scripts/era_validate.py --file "$(FILE)" --base-url "$(BASE_URL)" $(if $(TOKEN),--token "$(TOKEN)")

local-smoke:
	python scripts/local_smoke.py --file "$(FILE)"
