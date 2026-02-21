BASE_URL ?= http://127.0.0.1:8000
EMAIL ?= admin@example.com
POLL_SECONDS ?= 2

db-up:
	docker compose up -d postgres

db-down:
	docker compose down

migrate:
	alembic upgrade head

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

bootstrap-local:
	curl -X POST http://127.0.0.1:8000/api/v1/bootstrap \
		-H "Content-Type: application/json" \
		-d '{"organization_name":"Revenue OS Org","admin_email":"admin@example.com","admin_password":"ChangeMeNow!","admin_name":"Admin User"}'

dev: db-up migrate run

test:
	pytest -m "not postgres"

test-pg:
	pytest -m "postgres"

era-validate:
	python scripts/era_validate.py --file "$(FILE)" --base-url "$(BASE_URL)" $(if $(TOKEN),--token "$(TOKEN)")

local-smoke:
	python scripts/local_smoke.py --file "$(FILE)"

era-login:
	python scripts/era_ops.py login --base-url "$(BASE_URL)" --email "$(EMAIL)"

era-ingest:
	python scripts/era_ops.py ingest --dir "$(DIR)" --base-url "$(BASE_URL)" --email "$(EMAIL)"

era-watch:
	python scripts/era_ops.py ingest --dir "$(DIR)" --watch --poll-seconds "$(POLL_SECONDS)" --base-url "$(BASE_URL)" --email "$(EMAIL)"
