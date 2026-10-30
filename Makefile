.PHONY: help up down up-prod api test migrate e2e backup loadtest helm-template

help:
	@echo "VRAV Studio targets:"
	@echo "  make up          - dev postgres+redis"
	@echo "  make up-prod     - prod compose (needs .env.production)"
	@echo "  make api         - run API locally"
	@echo "  make migrate     - alembic upgrade head"
	@echo "  make test        - unit tests"
	@echo "  make e2e         - in-process smoke"
	@echo "  make backup      - postgres dump"
	@echo "  make loadtest    - credit/chat load (API must be up)"
	@echo "  make helm-template - render helm chart"

up:
	docker compose -f infra/docker/docker-compose.dev.yml up -d

down:
	docker compose -f infra/docker/docker-compose.dev.yml down

up-prod:
	docker compose -f infra/docker/docker-compose.prod.yml up -d --build

api:
	cd apps/api && PYTHONPATH=.:../../packages/ai-gateway uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	cd apps/api && PYTHONPATH=.:../../packages/ai-gateway alembic -c alembic.ini upgrade head

test:
	cd apps/api && PYTHONPATH=.:../../packages/ai-gateway pytest -q tests/

e2e:
	PYTHONPATH=apps/api:packages/ai-gateway python scripts/e2e_smoke.py

backup:
	./scripts/backup/backup_postgres.sh

loadtest:
	python scripts/loadtest/load_credits.py --users $${USERS:-10} --requests $${REQS:-20}

helm-template:
	helm template vrav infra/helm/vrav-studio
